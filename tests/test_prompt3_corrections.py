"""Independent expected-value regressions for the two Prompt 3 findings."""
import unittest
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal as D
from config import ConfigError
from data_records import CorporateAction, digest
from data_fetcher import split_adjusted_view, completed_candle
from data_validator import daily_as_of
from test_data_layer import fixture, instant


class SplitEffectivityTests(unittest.TestCase):
    def setUp(self):
        self.s = fixture()
        self.b = min(self.s.bars, key=lambda b: b.trading_date)
        self.boundary = instant(date(2024, 2, 1), 0)
        announced = instant(date(2024, 1, 30))
        self.a = CorporateAction('split1', 'ID1', date(2024, 2, 1), announced,
                                 announced, 'SPLIT', D(2), 'SYNTHETIC')
        self.s = replace(self.s, actions=(self.a,))

    def test_announced_before_effectivity(self):
        original = digest(self.b)
        v = split_adjusted_view(self.s, self.b, self.boundary)
        self.assertEqual(v.close, D(51))
        self.assertEqual(v.available_at, self.boundary)
        self.assertEqual(v.applied_effective_at, (self.boundary,))
        self.assertEqual(v.as_of, self.boundary)
        self.assertEqual(v.effective_time_convention, 'EFFECTIVE_DATE_MIDNIGHT_ASIA_KOLKATA')
        self.assertEqual(digest(self.b), original)

    def test_before_at_after_boundary(self):
        for delta, expected in ((-1, D(102)), (0, D(51)), (1, D(51))):
            with self.subTest(delta=delta):
                decision = self.boundary + timedelta(microseconds=delta)
                v = split_adjusted_view(self.s, self.b, decision)
                self.assertEqual(v.close, expected)
                self.assertLessEqual(v.available_at, decision)
                if delta >= 0:
                    self.assertEqual(v.available_at, self.boundary)
                else:
                    self.assertEqual(v.action_lineage, ())

    def test_evidence_after_effectivity(self):
        late = self.boundary + timedelta(hours=16)
        s = replace(self.s, actions=(replace(self.a, available_at=late),))
        with self.assertRaises(ConfigError):
            split_adjusted_view(s, self.b, late - timedelta(microseconds=1))
        for decision in (late, late + timedelta(hours=1)):
            v = split_adjusted_view(s, self.b, decision)
            self.assertEqual(v.close, D(51))
            self.assertEqual(v.available_at, late)

    def test_multiple_splits(self):
        second_boundary = instant(date(2024, 2, 5), 0)
        a2 = replace(self.a, action_id='split2', effective_date=date(2024, 2, 5), new_per_old=D(3))
        s = replace(self.s, actions=(self.a, a2))
        v = split_adjusted_view(s, self.b, second_boundary)
        self.assertEqual(v.close, D(17))
        self.assertEqual(v.volume, D(60))
        self.assertEqual(v.available_at, second_boundary)
        self.assertEqual(set(v.applied_effective_at), {self.boundary, second_boundary})

    def test_future_append_preserves_earlier_output(self):
        future = replace(self.a, action_id='future', effective_date=date(2024, 2, 5))
        earlier = split_adjusted_view(self.s, self.b, self.boundary)
        appended = split_adjusted_view(replace(self.s, actions=(self.a, future)), self.b, self.boundary)
        self.assertEqual(earlier, appended)
        self.assertEqual(digest(earlier), digest(appended))

    def test_view_reuse_guard(self):
        v = split_adjusted_view(self.s, self.b, self.boundary)
        self.assertIs(v.require_as_of(self.boundary), v)
        for delta in (-1, 1):
            with self.assertRaisesRegex(ConfigError, 'as-of mismatch'):
                v.require_as_of(self.boundary + timedelta(seconds=delta))


class SeriesCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.s = fixture()
        self.start, self.end = date(2024, 1, 29), date(2024, 2, 5)
        self.decision = instant(date(2024, 2, 5))

    def query(self, s):
        return daily_as_of(s, 'ID1', self.start, self.end, self.decision)

    def test_consistent(self):
        bars, q = self.query(self.s)
        self.assertEqual(len(bars), 5)
        self.assertEqual(q.status, 'VALID')
        self.assertEqual(q.reasons, ())

    def test_mixed_providers(self):
        self.check_mixed('provider')

    def test_mixed_versions(self):
        self.check_mixed('provider_version')

    def check_mixed(self, field):
        s = replace(self.s, bars=tuple(replace(b, **{field: 'OTHER'}) if b.trading_date == date(2024, 2, 1) else b for b in self.s.bars))
        bars, q = self.query(s)
        self.assertEqual(len(bars), 5)  # Diagnostic facts preserved.
        self.assertEqual(q.status, 'REJECTED')
        self.assertIn('incompatible_series_' + field, q.reasons)
        self.assertEqual(q.lineage, tuple(digest(b) for b in bars))
        for timeframe in ('WEEKLY', 'MONTHLY'):
            with self.assertRaisesRegex(ConfigError, 'incompatible_series_' + field):
                completed_candle(s, 'ID1', date(2024, 2, 1), timeframe, instant(date(2024, 3, 3)))

    def test_future_unavailable_other_provider_revision(self):
        b = next(b for b in self.s.bars if b.trading_date == date(2024, 2, 1))
        future = replace(b, revision=1, provider='OTHER', provider_version='v2',
                         available_at=self.decision + timedelta(days=1))
        self.assertEqual(self.query(self.s), self.query(replace(self.s, bars=self.s.bars + (future,))))

    def test_unsupported_bases_rejected_at_construction(self):
        # Current schema admits only RAW / RAW_SHARES / UNADJUSTED.
        for field in ('price_basis', 'volume_basis', 'corporate_action_treatment'):
            with self.subTest(field=field), self.assertRaises(ConfigError):
                replace(self.s.bars[0], **{field: 'OTHER'})


if __name__ == '__main__':
    unittest.main()
