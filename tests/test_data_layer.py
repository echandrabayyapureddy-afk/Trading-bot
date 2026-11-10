"""Synthetic independent expected values; no real market observations."""
import unittest
from dataclasses import replace, FrozenInstanceError
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D, localcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import socket

from config import BotConfig, ConfigError, load_config, load_manifest, content_hash, readiness_issues, from_dict
from data_records import (IST, Segment, TradingDay, ExchangeCalendar, Identity, DailyBar,
                          CorporateAction, Universe, Snapshot, digest, canonical, calendar_as_of)
from data_validator import validate_daily, daily_as_of, batch_issues, universe_as_of
from data_fetcher import (FixtureProvider, UnverifiedProvider, fetch_daily, completed_candle,
                          split_adjusted_view, period_bounds, snapshot_metadata,
                          authorize_actual_research, ingest_ordered_fixture)
from data_cache import LocalCache


def instant(day, hour=16, minute=0):
    return datetime.combine(day, datetime.min.time(), IST).replace(hour=hour, minute=minute)


def fixture():
    """Feb 2024: synthetic holiday Feb 2; special split session Saturday Feb 3."""
    start, end = date(2024, 1, 29), date(2024, 3, 4)
    days, bars = [], []
    for n in range((end-start).days):
        day = start + timedelta(days=n)
        opened = day.weekday() < 5 and day != date(2024, 2, 2)
        segments = (Segment(instant(day, 9), instant(day, 15, 30)),) if opened else ()
        if day == date(2024, 2, 3):
            segments = (Segment(instant(day, 9), instant(day, 10)), Segment(instant(day, 11), instant(day, 12)))
        days.append(TradingDay(day, segments, 'SYNTHETIC session' if segments else 'SYNTHETIC closure'))
        if segments:
            bars.append(DailyBar('ID1', 'SYN', day, segments[-1].closes, instant(day),
                                 'FIXTURE', 'v1', 0, 'synthetic:' + day.isoformat(),
                                 D(100+n), D(105+n), D(95+n), D(102+n), D(10+n)))
    cal = ExchangeCalendar('SYNTHETIC-v1', instant(date(2024, 1, 1)), start, end, tuple(days), 'SYNTHETIC: not NSE evidence')
    identity = Identity('ID1', 'SYN', start, end, cal.available_at, 'LISTED', 'SYNTHETIC')
    return Snapshot(cal, tuple(bars), (identity,))


class DailyTests(unittest.TestCase):
    def setUp(self):
        self.s = fixture()
        self.b = min(self.s.bars, key=lambda b:b.trading_date)
        self.now = instant(date(2024, 3, 3))

    def test_valid(self):
        self.assertEqual(validate_daily(self.b, self.s.calendar).status, 'VALID')

    def test_bad_prices(self):
        for change, reason in [({'open':D(0)}, 'nonpositive_price'), ({'volume':D(-1)}, 'negative_volume'), ({'high':D(1)}, 'inconsistent_ohlc')]:
            with self.subTest(change=change):
                self.assertIn(reason, validate_daily(replace(self.b, **change), self.s.calendar).reasons)

    def test_invalid_types_nonfinite_missing(self):
        for value in (True, 100.0, '100', D('NaN'), D('Infinity')):
            with self.subTest(value=value), self.assertRaises(ConfigError):
                replace(self.b, open=value)
        document = canonical(self.b); del document['provider']
        with self.assertRaises(ConfigError): from_dict(DailyBar, document)

    def test_naive_timestamp(self):
        with self.assertRaises(ConfigError): replace(self.b, available_at=datetime(2024,1,29))

    def test_impossible_availability(self):
        b = replace(self.b, available_at=self.b.session_close-timedelta(seconds=1))
        self.assertIn('available_before_completion', validate_daily(b, self.s.calendar).reasons)

    def test_unexpected_session(self):
        b = replace(self.b, trading_date=date(2024,2,2))
        self.assertIn('unexpected_session', validate_daily(b, self.s.calendar).reasons)

    def test_duplicate_and_conflict(self):
        self.assertIn('duplicate_record', batch_issues((self.b,self.b)))
        self.assertIn('conflicting_revision', batch_issues((self.b,replace(self.b, close=D(101)))))
        for extra in (self.b, replace(self.b, close=D(101))):
            s=replace(self.s,bars=self.s.bars+(extra,))
            _,q=daily_as_of(s,'ID1',self.b.trading_date,self.b.trading_date+timedelta(days=1),self.now)
            self.assertEqual(q.status,'REJECTED')

    def test_ordering(self):
        bars=tuple(sorted(self.s.bars,key=lambda b:b.trading_date))
        self.assertEqual(batch_issues(bars),())
        self.assertIn('unordered_input',batch_issues(tuple(reversed(bars))))
        with self.assertRaises(ConfigError): ingest_ordered_fixture(self.s.calendar,tuple(reversed(bars)),self.s.identities)

    def test_revision_visibility(self):
        cutoff=instant(date(2024,1,30))
        rev=replace(self.b,revision=1,close=D(104),available_at=cutoff+timedelta(days=1))
        s=replace(self.s,bars=self.s.bars+(rev,))
        args=('ID1',self.b.trading_date,self.b.trading_date+timedelta(days=1))
        self.assertEqual(daily_as_of(self.s,*args,cutoff), daily_as_of(s,*args,cutoff))
        self.assertEqual(daily_as_of(s,*args,self.now)[0],(rev,))

    def test_invalid_latest_no_fallback(self):
        rev=replace(self.b,revision=1,close=D(-1),available_at=self.now)
        bars,q=daily_as_of(replace(self.s,bars=self.s.bars+(rev,)),'ID1',self.b.trading_date,self.b.trading_date+timedelta(days=1),self.now)
        self.assertEqual(bars,()); self.assertEqual(q.status,'REJECTED')

    def test_revision_order(self):
        rev=replace(self.b,revision=1)
        _,q=daily_as_of(replace(self.s,bars=self.s.bars+(rev,)),'ID1',self.b.trading_date,self.b.trading_date+timedelta(days=1),self.now)
        self.assertTrue(any('revision_availability_order' in r for r in q.reasons))

    def test_delayed_daily(self):
        b=replace(self.b,available_at=self.now)
        bars,q=daily_as_of(replace(self.s,bars=(b,)),'ID1',b.trading_date,b.trading_date+timedelta(days=1),instant(b.trading_date))
        self.assertFalse(bars);self.assertEqual(q.status,'REJECTED')

    def test_staleness(self):
        _,q=daily_as_of(self.s,'ID1',date(2024,1,29),date(2024,2,1),self.now,require_current=True)
        self.assertIn('stale_query_window',q.reasons)

    def test_symbol_change(self):
        cut=date(2024,2,1); old=self.s.identities[0]
        ids=(replace(old,end=cut),replace(old,start=cut,symbol='NEW'))
        bars=tuple(replace(b,symbol='NEW') if b.trading_date>=cut else b for b in self.s.bars)
        selected,q=daily_as_of(replace(self.s,identities=ids,bars=bars),'ID1',date(2024,1,29),date(2024,2,5),self.now)
        self.assertEqual(q.status,'VALID');self.assertEqual(len(selected),5)

    def test_suspension_and_missing_identity(self):
        for ids in ((),(replace(self.s.identities[0],status='SUSPENDED'),),(replace(self.s.identities[0],status='UNAVAILABLE'),)):
            _,q=daily_as_of(replace(self.s,identities=ids),'ID1',date(2024,1,29),date(2024,1,30),self.now)
            self.assertEqual(q.status,'REJECTED')

    def test_future_append_invariance(self):
        cutoff=instant(date(2024,2,3));args=('ID1',date(2024,1,29),date(2024,2,5),cutoff)
        before=replace(self.s,bars=tuple(b for b in self.s.bars if b.available_at<=cutoff))
        self.assertEqual(daily_as_of(before,*args),daily_as_of(self.s,*args))


class CalendarCandleTests(unittest.TestCase):
    def setUp(self): self.s=fixture();self.now=instant(date(2024,3,3))

    def test_week_expected(self):
        c=completed_candle(self.s,'ID1',date(2024,2,1),'WEEKLY',self.now)
        self.assertEqual((c.open,c.high,c.low,c.close,c.volume),(D(100),D(110),D(95),D(107),D(61)))
        self.assertEqual((c.start,c.end),(date(2024,1,29),date(2024,2,5)))
        self.assertEqual(c.final_session_close,instant(date(2024,2,3),12))
        self.assertEqual(len(c.lineage),5)

    def test_month_expected(self):
        c=completed_candle(self.s,'ID1',date(2024,2,10),'MONTHLY',self.now)
        # Feb 1,3,5-9,12-16,19-23,26-29: 21 sessions; n offsets sum 366.
        self.assertEqual((c.open,c.high,c.low,c.close,c.volume),(D(103),D(136),D(98),D(133),D(576)))
        self.assertEqual(len(c.lineage),21)
        self.assertEqual(c.end,date(2024,3,1))

    def test_leap_and_december_boundaries(self):
        self.assertEqual(period_bounds(date(2024,2,29),'MONTHLY'),(date(2024,2,1),date(2024,3,1)))
        self.assertEqual(period_bounds(date(2023,12,31),'MONTHLY'),(date(2023,12,1),date(2024,1,1)))

    def test_incomplete_period(self):
        for tf,day in [('WEEKLY',date(2024,2,7)),('MONTHLY',date(2024,2,14))]:
            with self.subTest(tf=tf),self.assertRaises(ConfigError): completed_candle(self.s,'ID1',day,tf,instant(day))

    def test_truncated_calendar(self):
        cal=replace(self.s.calendar,end=date(2024,2,15),days=tuple(d for d in self.s.calendar.days if d.trading_date<date(2024,2,15)))
        with self.assertRaises(ConfigError):completed_candle(replace(self.s,calendar=cal),'ID1',date(2024,2,1),'MONTHLY',self.now)

    def test_missing_calendar_date(self):
        with self.assertRaises(ConfigError):replace(self.s.calendar,days=self.s.calendar.days[1:])

    def test_missing_bar(self):
        s=replace(self.s,bars=tuple(b for b in self.s.bars if b.trading_date!=date(2024,2,1)))
        with self.assertRaises(ConfigError):completed_candle(s,'ID1',date(2024,2,1),'WEEKLY',self.now)

    def test_delayed_period(self):
        cutoff=instant(date(2024,2,3));s=replace(self.s,bars=tuple(replace(b,available_at=cutoff+timedelta(days=1)) if b.trading_date==date(2024,2,3) else b for b in self.s.bars))
        with self.assertRaises(ConfigError):completed_candle(s,'ID1',date(2024,2,1),'WEEKLY',cutoff)
        c=completed_candle(s,'ID1',date(2024,2,1),'WEEKLY',cutoff+timedelta(days=1))
        self.assertEqual(c.available_at,cutoff+timedelta(days=1))

    def test_segment_completion(self):
        b=next(b for b in self.s.bars if b.trading_date==date(2024,2,3))
        self.assertIn('session_completion_mismatch',validate_daily(replace(b,session_close=instant(b.trading_date,10)),self.s.calendar).reasons)

    def test_calendar_revision_invariance(self):
        old=self.s.calendar;new=replace(old,version='v2',available_at=self.now)
        early=instant(date(2024,2,3))
        self.assertEqual(calendar_as_of((old,),early),calendar_as_of((old,new),early))
        self.assertEqual(calendar_as_of((old,new),self.now),new)

    def test_calendar_not_yet_known(self):
        with self.assertRaises(ConfigError):completed_candle(replace(self.s,calendar=replace(self.s.calendar,available_at=self.now+timedelta(days=1))),'ID1',date(2024,2,1),'WEEKLY',self.now)

    def test_deterministic_and_future_candles(self):
        early=instant(date(2024,2,3));s=replace(self.s,bars=tuple(b for b in self.s.bars if b.available_at<=early))
        args=('ID1',date(2024,2,1),'WEEKLY',early)
        self.assertEqual(completed_candle(s,*args),completed_candle(self.s,*args))
        self.assertEqual(digest(completed_candle(s,*args)),digest(completed_candle(s,*args)))


class ActionUniverseTests(unittest.TestCase):
    def setUp(self):
        self.s=fixture(); self.b=min(self.s.bars,key=lambda b:b.trading_date)
        self.now=instant(date(2024,2,10))
        self.a=CorporateAction('split1','ID1',date(2024,2,1),instant(date(2024,1,31)),instant(date(2024,1,30)),'SPLIT',D(2),'SYNTHETIC split evidence')

    def test_split_expected_raw_preserved(self):
        s=replace(self.s,actions=(self.a,));v=split_adjusted_view(s,self.b,self.now)
        self.assertEqual((v.open,v.high,v.low,v.close,v.volume),(D(50),D('52.5'),D('47.5'),D(51),D(20)))
        self.assertEqual(self.b.open,D(100));self.assertEqual(v.raw_sha256,digest(self.b))
        self.assertEqual(v.basis,'SPLIT_ADJUSTED_NONTRADABLE')

    def test_future_action_invariance(self):
        early=instant(date(2024,1,29));s=replace(self.s,actions=(self.a,))
        self.assertEqual(split_adjusted_view(self.s,self.b,early),split_adjusted_view(s,self.b,early))

    def test_later_notification_does_not_rewrite_earlier(self):
        a=replace(self.a,known_at=self.now,available_at=self.now)
        early=instant(date(2024,2,2))
        self.assertEqual(split_adjusted_view(self.s,self.b,early),split_adjusted_view(replace(self.s,actions=(a,)),self.b,early))

    def test_unavailable_evidence(self):
        a=replace(self.a,available_at=self.now+timedelta(days=1))
        with self.assertRaises(ConfigError):split_adjusted_view(replace(self.s,actions=(a,)),self.b,self.now)

    def test_unsupported_action(self):
        with self.assertRaises(ConfigError):split_adjusted_view(replace(self.s,actions=(replace(self.a,kind='UNSUPPORTED'),)),self.b,self.now)

    def test_duplicate_action(self):
        with self.assertRaises(ConfigError):split_adjusted_view(replace(self.s,actions=(self.a,self.a)),self.b,self.now)

    def test_universe_missing(self):
        with self.assertRaisesRegex(ConfigError,'survivorship'):universe_as_of(self.s,date(2024,2,1),self.now)

    def test_dated_universe(self):
        u=Universe('SYNTHETIC-U1',date(2024,2,1),date(2024,3,1),instant(date(2024,2,1)),('ID1',),'SYNTHETIC')
        s=replace(self.s,universes=(u,))
        self.assertEqual(universe_as_of(s,date(2024,2,3),self.now).members,('ID1',))
        with self.assertRaises(ConfigError):universe_as_of(s,date(2024,1,31),self.now)
        with self.assertRaises(ConfigError):universe_as_of(s,date(2024,2,3),instant(date(2024,1,31)))


class CacheIntegrationTests(unittest.TestCase):
    def setUp(self):self.s=fixture();self.now=instant(date(2024,3,3))

    def test_roundtrip(self):
        with TemporaryDirectory() as d:
            cache=LocalCache(d);key=cache.put(self.s)
            self.assertEqual(cache.get(key,retrieved_at=self.now).snapshot,self.s)
            self.assertEqual(cache.put(self.s),key)
            self.assertNotEqual(cache.get(key,retrieved_at=self.now).retrieved_at,cache.get(key,retrieved_at=self.now+timedelta(days=1)).retrieved_at)

    def test_corrupt_and_no_overwrite(self):
        with TemporaryDirectory() as d:
            cache=LocalCache(d);key=cache.put(self.s);Path(d,key+'.json').write_text('{}')
            with self.assertRaises(ConfigError):cache.get(key,retrieved_at=self.now)
            with self.assertRaises(ConfigError):cache.put(self.s)

    def test_hash_mismatch(self):
        with TemporaryDirectory() as d:
            cache=LocalCache(d);key=cache.put(self.s);Path(d,key+'.json').rename(Path(d,'0'*64+'.json'))
            with self.assertRaises(ConfigError):cache.get('0'*64,retrieved_at=self.now)

    def test_cache_miss(self):
        with TemporaryDirectory() as d:
            with self.assertRaises(ConfigError):LocalCache(d).get('0'*64,retrieved_at=self.now)

    def test_path_traversal(self):
        with TemporaryDirectory() as d:
            with self.assertRaises(ConfigError):LocalCache(d).get('../x',retrieved_at=self.now)

    def test_hash_order_decimal_timezone(self):
        b=self.s.bars[0]
        same=replace(b,open=D(str(b.open)+'.00'),available_at=b.available_at.astimezone(timezone.utc))
        s=replace(self.s,bars=(same,)+self.s.bars[1:])
        self.assertEqual(digest(self.s),digest(s))
        self.assertEqual(digest(self.s),digest(replace(self.s,bars=tuple(reversed(self.s.bars)))))
        with localcontext() as ctx:
            ctx.prec=3
            self.assertEqual(digest(self.s),digest(s))

    def test_offline_unsealed_config_unchanged(self):
        c=load_config('config.example.json'); before=content_hash(c)
        with patch.object(socket,'socket',side_effect=AssertionError('network forbidden')):
            self.assertEqual(fetch_daily(FixtureProvider(self.s),c),self.s)
            with self.assertRaises(ConfigError):fetch_daily(UnverifiedProvider(),c)
        self.assertEqual(content_hash(c),before)
        self.assertIn('operational_trust_not_provisioned',readiness_issues(c))
        self.assertEqual(load_manifest('research_manifest.json').status.value,'UNSEALED')

    def test_config_pin_mismatch(self):
        c=BotConfig()
        for kw in ({'provider':'OTHER'},{'provider_version':'OTHER'},{'snapshot_sha256':'0'*64},{'calendar_version':'OTHER'},{'universe_version':'OTHER'}):
            with self.subTest(kw=kw),self.assertRaises(ConfigError):fetch_daily(FixtureProvider(self.s),replace(c,data=replace(c.data,**kw)))

    def test_explicit_research_cutoff_and_unsealed_block(self):
        c=BotConfig();m=load_manifest('research_manifest.json')
        kw={'verification_profiles':(),'expected_manifest_sha256':content_hash(m)}
        with self.assertRaises(TypeError):authorize_actual_research(c,m,date(2024,1,1),date(2024,2,1),**kw)
        with self.assertRaisesRegex(ConfigError,'UNSEALED'):authorize_actual_research(c,m,date(2024,1,1),date(2024,2,1),authorization_at=self.now,**kw)

    def test_synthetic_metadata(self):
        m=snapshot_metadata(self.s,BotConfig())
        self.assertEqual(m['origin'],'SYNTHETIC');self.assertFalse(m['unbiased_historical_validation'])
        self.assertEqual(m['snapshot_sha256'],digest(self.s))

    def test_real_origin_rejected(self):
        with self.assertRaises(ConfigError):replace(self.s,origin='OPERATIONAL')

    def test_frozen(self):
        with self.assertRaises(FrozenInstanceError):self.s.schema_version='2.0'



class AdditionalBoundaryTests(unittest.TestCase):
    def test_overlapping_and_reversed_segments(self):
        day=date(2024,2,3)
        with self.assertRaises(ConfigError):Segment(instant(day,12),instant(day,9))
        seg=Segment(instant(day,9),instant(day,12))
        with self.assertRaises(ConfigError):TradingDay(day,(seg,seg),'SYNTHETIC')

    def test_provider_mixture(self):
        s=fixture();s=replace(s,bars=tuple(replace(b,provider='OTHER') if b.trading_date==date(2024,2,1) else b for b in s.bars))
        with self.assertRaises(ConfigError):completed_candle(s,'ID1',date(2024,2,1),'WEEKLY',instant(date(2024,2,5)))

    def test_exact_volume_independent_decimal_context(self):
        s=fixture();s=replace(s,bars=tuple(replace(b,volume=D('100000000000000000000000000000000000000000000000000000000000.1')) for b in s.bars))
        with localcontext() as ctx:
            ctx.prec=2
            c=completed_candle(s,'ID1',date(2024,2,1),'WEEKLY',instant(date(2024,2,5)))
        self.assertEqual(c.volume,D('500000000000000000000000000000000000000000000000000000000000.5'))

    def test_calendar_ambiguous_versions(self):
        c=fixture().calendar
        with self.assertRaises(ConfigError):calendar_as_of((c,replace(c,version='different')),instant(date(2024,3,3)))
        with self.assertRaises(ConfigError):calendar_as_of((c,c),instant(date(2024,3,3)))

    def test_partial_final_data_month(self):
        s=fixture();s=replace(s,bars=tuple(b for b in s.bars if b.trading_date<=date(2024,2,14)))
        with self.assertRaises(ConfigError):completed_candle(s,'ID1',date(2024,2,1),'MONTHLY',instant(date(2024,3,3)))

    def test_unavailable_history(self):
        _,q=daily_as_of(fixture(),'UNKNOWN',date(2024,2,1),date(2024,2,5),instant(date(2024,3,3)))
        self.assertEqual(q.status,'REJECTED')

    def test_no_import_side_effects(self):
        import subprocess, sys
        code="""import socket, pathlib
socket.socket=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('network'))
pathlib.Path.write_text=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('write'))
import data_records, data_fetcher, data_validator, data_cache
"""
        result=subprocess.run([sys.executable,'-B','-c',code],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)


class ReportAndLineageTests(unittest.TestCase):
    def test_quality_report(self):
        from data_validator import synthetic_quality_report
        report=synthetic_quality_report(fixture(),'ID1',date(2024,1,29),date(2024,3,4),instant(date(2024,3,3)))
        self.assertEqual(report['status'],'VALID')
        self.assertEqual(report['valid_visible_daily_records'],25)
        self.assertEqual(report['origin'],'SYNTHETIC')
        self.assertFalse(report['suitable_for_unbiased_historical_validation'])

    def test_late_identity_controls_output_availability(self):
        s=fixture();late=instant(date(2024,2,4))
        s=replace(s,identities=(replace(s.identities[0],available_at=late),))
        c=completed_candle(s,'ID1',date(2024,2,1),'WEEKLY',instant(date(2024,2,5)))
        self.assertEqual(c.available_at,late)
        self.assertEqual(c.identity_lineage,(digest(s.identities[0]),))
        b=min(s.bars,key=lambda b:b.trading_date)
        v=split_adjusted_view(s,b,instant(date(2024,2,5)))
        self.assertEqual(v.available_at,late)
        self.assertEqual(v.calendar_sha256,digest(s.calendar))

    def test_multiple_splits_deterministic(self):
        from decimal import ROUND_UP, ROUND_DOWN
        s=fixture();b=min(s.bars,key=lambda b:b.trading_date)
        a=CorporateAction('a','ID1',date(2024,2,1),instant(date(2024,1,31)),instant(date(2024,1,30)),'SPLIT',D(3),'SYNTHETIC')
        s=replace(s,actions=(a,));now=instant(date(2024,2,5))
        with localcontext() as ctx:
            ctx.prec=3;ctx.rounding=ROUND_UP
            one=split_adjusted_view(s,b,now)
        with localcontext() as ctx:
            ctx.prec=7;ctx.rounding=ROUND_DOWN
            two=split_adjusted_view(s,b,now)
        self.assertEqual(one,two)


if __name__ == '__main__':unittest.main()
