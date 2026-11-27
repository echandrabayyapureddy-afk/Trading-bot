"""Physical development-only reader probes. No network or real market rows."""
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from zoneinfo import ZoneInfo

from config import ConfigError, ResearchManifest, content_hash
from data_records import (DailyBar, ExchangeCalendar, Identity, Segment, Snapshot, TradingDay,
                          Universe, digest, encoded)
from restricted_development import DayObject, Partition, read_development
from test_config import ready_config, research_profiles, sealed_manifest
from test_data_layer import instant


class RestrictedTests(TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dev = Path(tmp.name)/'development'
        self.dev.mkdir()
        hold = Path(tmp.name)/'holdout'
        hold.mkdir()
        self.sentinel = hold/'2023-01-01.json'
        self.sentinel.write_bytes(b'holdout sentinel')
        self.fd = os.open(self.dev, os.O_DIRECTORY)
        self.addCleanup(os.close, self.fd)
        stat = os.fstat(self.fd)
        c = ready_config()
        self.ids = ('EQUITY', 'NIFTY_50')
        self.m = replace(sealed_manifest(c), instruments=self.ids)
        self.end = self.m.development_end
        self.start = date(2022, 12, 30)
        self.warm = self.start-timedelta(days=1)
        known = instant(self.warm-timedelta(days=1))
        days = [TradingDay(d, (Segment(instant(d, 9), instant(d, 15)),), 'generated')
                for d in (self.warm, self.start)]
        days.append(TradingDay(self.start+timedelta(days=1), (), 'generated closure'))
        cal = ExchangeCalendar(c.data.calendar_version, known, self.warm, self.end, tuple(days), 'synthetic')
        ids = tuple(Identity(i, i, self.warm, self.end, known, 'LISTED', 'fixture') for i in self.ids)
        u = Universe(c.data.universe_version, self.warm, self.end, known, ('EQUITY',), 'fixture')
        meta = Snapshot(cal, (), ids, universes=(u,))
        self.objects = []
        self.documents = []
        for index, d in enumerate((self.warm, self.start)):
            bars = []
            for i in self.ids:
                price = Decimal(100+index)
                b = DailyBar(i, i, d, instant(d, 15), instant(d), 'SYNTHETIC', 'fixture-1', 0,
                             'test', price, price+1, price-1, price, Decimal(10))
                bars.append(b)
                if i == 'EQUITY' and d == self.start:
                    bars.append(replace(b, available_at=instant(d, 17), revision=1, close=price+1))
            doc = dict(snapshot_id=self.m.snapshot_id, day=d.isoformat(), rows=bars)
            self.documents.append(doc)
            self.objects.append(self.write(d, doc))
        self.p = Partition(self.m.snapshot_id, self.m.snapshot_sha256, stat.st_dev, stat.st_ino, meta, tuple(self.objects))
        self.trace = []
        self.args = dict(config=c, manifest=self.m, directory_fd=self.fd, partition=self.p,
                         expected_partition_sha256=digest(self.p), expected_manifest_sha256=content_hash(self.m),
                         warmup_start=self.warm, start=self.start, end=self.end, decision_at=instant(self.start),
                         authorization_at=self.m.sealed_at+timedelta(days=3), verification_profiles=research_profiles(),
                         trace=self.trace)

    def write(self, day, doc):
        (self.dev/(day.isoformat()+'.json')).write_bytes(encoded(doc))
        return DayObject(day, digest(doc))

    def test_boundary_receipt_and_sentinel_invariance(self):
        expected = [('EQUITY', self.warm, 100), ('EQUITY', self.start, 101),
                    ('NIFTY_50', self.warm, 100), ('NIFTY_50', self.start, 101)]
        original_open = os.open
        with patch('restricted_development.os.open', wraps=original_open) as opened:
            a = read_development(**self.args)
            self.sentinel.write_bytes(b'different holdout sentinel')
            b = read_development(**self.args)
            self.assertEqual([(x.args[0], x.kwargs['dir_fd']) for x in opened.call_args_list],
                             [(k+'.json', self.fd) for k in ('2022-12-29','2022-12-30')]*2)
        self.assertEqual([(x.instrument_id, x.trading_date, x.close) for x in a], expected)
        self.assertEqual(b, a)
        self.assertEqual(self.trace[0][1:4], (self.warm, self.start, self.end))
        self.assertEqual(self.trace[-1][1], tuple((i,d,0) for i,d,_ in expected))

    def test_vintage(self):
        later = read_development(**(self.args | dict(decision_at=instant(self.start, 17))))
        self.assertEqual((later[1].revision, later[1].close), (1, 102))

    def test_preopen_refusals(self):
        unsealed = ResearchManifest()
        profiles = self.args['verification_profiles']
        first = profiles[0]
        now = self.args['authorization_at']
        for changes in (dict(end=self.end+timedelta(days=1)),
                        dict(start=self.end, warmup_start=self.end, end=self.end+timedelta(days=1)),
                        dict(warmup_start=self.m.development_start-timedelta(days=1)),
                        dict(manifest=unsealed, expected_manifest_sha256=content_hash(unsealed)),
                        dict(expected_manifest_sha256='0'*64), dict(expected_partition_sha256='0'*64),
                        dict(verification_profiles=profiles[1:]),
                        dict(config=replace(self.args['config'], config_version='0.4.0')),
                        dict(authorization_at=None), dict(decision_at=instant(self.end)),
                        *(dict(verification_profiles=(replace(first, approval=approval),)+profiles[1:])
                          for approval in (replace(first.approval, revoked_at=now),
                                           replace(first.approval, validity_mode='EXPIRES', valid_until=now)))):
            with self.subTest(changes=tuple(changes)), patch('restricted_development.os.open') as opened:
                with self.assertRaises(ConfigError):
                    read_development(**(self.args | changes))
                opened.assert_not_called()

    def test_wrong_directory_or_snapshot(self):
        fd = os.open(self.sentinel.parent, os.O_DIRECTORY)
        self.addCleanup(os.close, fd)
        wrong = replace(self.p, snapshot_id='different')
        with patch('restricted_development.os.open') as opened:
            for changes in (dict(directory_fd=fd), dict(partition=wrong, expected_partition_sha256=digest(wrong))):
                with self.assertRaises(ConfigError):
                    read_development(**(self.args | changes))
            opened.assert_not_called()

    def test_invalid_contents_atomic(self):
        doc = self.documents[-1]
        b = doc['rows'][0]
        for changes in (dict(snapshot_id='different'), dict(rows=[replace(b, trading_date=self.end)]),
                        dict(rows=[replace(b, provider_version='other')]), dict(rows=[replace(b, low=Decimal(999))]),
                        dict(rows=[])):
            obj = self.write(self.start, doc | changes)
            p = replace(self.p, objects=(self.objects[0], obj))
            with self.assertRaises(ConfigError):
                read_development(**(self.args | dict(partition=p, expected_partition_sha256=digest(p))))
            self.assertFalse(any(item[0]=='returned' for item in self.trace))
        with self.assertRaisesRegex(ConfigError, 'content mismatch'):
            read_development(**self.args)

    def test_no_link_to_sentinel(self):
        path = self.dev/(self.start.isoformat()+'.json')
        path.unlink()
        path.symlink_to(self.sentinel)
        with self.assertRaises(OSError):
            read_development(**self.args)
        self.assertNotIn(('opened', path.name), self.trace)

    def test_hard_link_rejected_before_first_open(self):
        first_name = self.warm.isoformat()+'.json'
        alias = self.dev/'alias'
        os.link(self.dev/first_name, alias)
        with patch('restricted_development.os.open', wraps=os.open) as opened:
            with self.assertRaisesRegex(ConfigError, 'single-link regular file'):
                read_development(**self.args)
            opened.assert_not_called()
            self.assertEqual([entry[0] for entry in self.trace], ['request'])

            alias.unlink()
            rows = read_development(**self.args)
            self.assertEqual(len(rows), 4)
            self.assertEqual([(c.args[0], c.kwargs['dir_fd']) for c in opened.call_args_list],
                             [(first_name, self.fd), (self.start.isoformat()+'.json', self.fd)])
            self.assertEqual(self.trace[-1][0], 'returned')

    def test_different_inode_with_identical_bytes_rejected_after_open(self):
        first = self.dev/(self.warm.isoformat()+'.json')
        replacement = self.dev/'replacement'
        replacement.write_bytes(first.read_bytes())
        real_open = os.open

        def swap_then_open(name, flags, *, dir_fd):
            replacement.replace(first)
            return real_open(name, flags, dir_fd=dir_fd)

        with patch('restricted_development.os.open', side_effect=swap_then_open):
            with self.assertRaisesRegex(ConfigError, 'changed during open'):
                read_development(**self.args)
        self.assertEqual([entry[0] for entry in self.trace], ['request', 'opened'])

    def test_repeated_hour_revocation_and_expiry_at_storage_boundary(self):
        ny = ZoneInfo('America/New_York')
        edge = datetime(2024, 11, 3, 5, 45, tzinfo=UTC)
        tick = timedelta(microseconds=1)
        cases = ((edge-tick, True), (edge, False), (edge+tick, False),
                 (datetime(2024, 11, 3, 6, 15, tzinfo=UTC), False))
        profiles = self.args['verification_profiles']
        first = profiles[0]
        for zone in (ny, UTC):
            boundary = edge.astimezone(zone)
            for reason, change in (
                    ('approval expired', dict(validity_mode='EXPIRES', valid_until=boundary)),
                    ('approval revoked', dict(revoked_at=boundary))):
                amended = replace(first, approval=replace(first.approval, **change))
                for when, allowed in cases:
                    cutoff = when.astimezone(zone)
                    trace = []
                    args = self.args | dict(authorization_at=cutoff, trace=trace,
                                            verification_profiles=(amended,) + profiles[1:])
                    with self.subTest(zone=zone, reason=reason, when=when), patch('os.open', wraps=os.open) as opened:
                        if allowed:
                            rows = read_development(**args)
                            self.assertEqual([(b.instrument_id, b.trading_date) for b in rows],
                                             [(i, d) for i in self.ids for d in (self.warm, self.start)])
                            self.assertEqual([(c.args[0], c.kwargs['dir_fd']) for c in opened.call_args_list],
                                             [(d.isoformat()+'.json', self.fd) for d in (self.warm, self.start)])
                            self.assertEqual(trace[-1][0], 'returned')
                        else:
                            with self.assertRaisesRegex(ConfigError, reason):
                                read_development(**args)
                            opened.assert_not_called()
                            self.assertEqual([entry[0] for entry in trace], ['request'])
                        self.assertIs(trace[0][-1], cutoff)

    def test_repeated_hour_seal_and_evidence_chronology(self):
        ny = ZoneInfo('America/New_York')
        early = datetime(2024, 11, 3, 1, 45, tzinfo=ny)
        late = datetime(2024, 11, 3, 1, 15, tzinfo=ny, fold=1)
        manifest = replace(self.m, snapshot_created_at=early, sealed_at=late)
        with self.assertRaisesRegex(ConfigError, 'snapshot cannot be created after sealing'):
            replace(manifest, snapshot_created_at=late, sealed_at=early)
        with patch('os.open', wraps=os.open) as opened:
            with self.assertRaisesRegex(ConfigError, 'authorization precedes sealing'):
                read_development(**(self.args | dict(manifest=manifest, authorization_at=early,
                                                     expected_manifest_sha256=content_hash(manifest))))
            opened.assert_not_called()
        profile = self.args['verification_profiles'][0]
        future = replace(profile.approval.evidence, available_at=late)
        with self.assertRaisesRegex(ConfigError, 'approval evidence unavailable'):
            replace(profile.approval, evidence=future, approved_at=early)
        with self.assertRaisesRegex(ConfigError, 'verification predates evidence'):
            replace(profile.body, evidence=(future,), verified_at=early)
        approved = replace(profile.approval, approved_at=early, valid_until=late, validity_mode='EXPIRES')
        self.assertEqual(replace(profile, approval=approved).issues(
            early, 'RESEARCH', historical_start=profile.body.effective_start,
            historical_end=profile.body.effective_end), ())

    def repeated_hour_request(self, segments, row_close, decision):
        day = date(2022, 11, 6)
        end = day + timedelta(days=1)
        known = instant(day - timedelta(days=1))
        session = TradingDay(day, segments, 'synthetic special session')
        cal = replace(self.p.metadata.calendar, available_at=known, start=day, end=end, days=(session,))
        ids = tuple(replace(i, start=day, end=end, available_at=known) for i in self.p.metadata.identities)
        universe = replace(self.p.metadata.universes[0], start=day, end=end, available_at=known)
        bars = [replace(b, trading_date=day, session_close=row_close, available_at=row_close)
                for b in self.documents[0]['rows']]
        obj = self.write(day, dict(snapshot_id=self.m.snapshot_id, day=day.isoformat(), rows=bars))
        p = replace(self.p, metadata=Snapshot(cal, (), ids, universes=(universe,)), objects=(obj,))
        return self.args | dict(partition=p, expected_partition_sha256=digest(p), warmup_start=day,
                                start=day, end=end, decision_at=decision, trace=[])

    def test_overlapping_repeated_hour_segments_denied_before_open(self):
        ny = ZoneInfo('America/New_York')
        start = datetime(2022, 11, 6, 4, 30, tzinfo=UTC)
        close = start.replace(hour=6, minute=10)
        first = Segment(start, close.replace(minute=50).astimezone(ny))
        second = Segment(start.replace(hour=5, minute=55).astimezone(ny), close)
        with patch('os.open', wraps=os.open) as opened:
            with self.assertRaisesRegex(ConfigError, 'segments unordered or overlapping'):
                args = self.repeated_hour_request((first, second), close, close.replace(minute=15))
                read_development(**args)
            opened.assert_not_called()

    def test_segment_duration_and_touching_across_fold(self):
        ny = ZoneInfo('America/New_York')
        early = datetime(2022, 11, 6, 1, 55, tzinfo=ny)
        late = early.replace(minute=10, fold=1)
        with self.assertRaisesRegex(ConfigError, 'invalid session segment'):
            Segment(late, early)
        forward = Segment(early, late)
        touching = Segment(late.astimezone(UTC), late.replace(minute=20))
        with self.assertRaisesRegex(ConfigError, 'segments unordered or overlapping'):
            TradingDay(early.date(), (forward, touching), 'synthetic')

    def test_same_close_in_utc_and_new_york(self):
        ny = ZoneInfo('America/New_York')
        start = datetime(2022, 11, 6, 4, 30, tzinfo=UTC)
        close = start.replace(hour=5, minute=45)
        decision = start.replace(hour=7)
        args = self.repeated_hour_request((Segment(start, close),), close, decision)
        expected = read_development(**args)
        self.assertEqual(len(expected), 2)
        p = args['partition']
        day, = p.metadata.calendar.days
        local = close.astimezone(ny)
        for fold in (0, 1):
            session = replace(day, segments=(Segment(start, local.replace(fold=fold)),))
            cal = replace(p.metadata.calendar, days=(session,))
            variant = replace(p, metadata=replace(p.metadata, calendar=cal))
            if fold == 0:
                self.assertEqual(digest(variant), args['expected_partition_sha256'])
                self.assertEqual(read_development(**(args | dict(partition=variant))), expected)
            else:
                trace = []
                with self.assertRaisesRegex(ConfigError, 'session_completion_mismatch'):
                    read_development(**(args | dict(partition=variant, expected_partition_sha256=digest(variant),
                                                    trace=trace)))
                self.assertEqual([entry[0] for entry in trace], ['request', 'opened'])
