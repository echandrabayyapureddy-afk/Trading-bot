"""Independent arithmetic, calendar, visibility and durable-audit method checks."""
from dataclasses import FrozenInstanceError, replace
from datetime import date
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from config import Candidate, ConfigError, ResearchManifest, load_manifest, readiness_issues
import walk_forward as wf


class WalkForwardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.path = Path(cls.temp.name) / 'research-test'
        cls.audit = wf.TrialAudit.create(cls.path)
        cls.spec = wf.prepare()
        cls.report = wf.run(cls.spec, cls.audit, 'first')
        cls.first, cls.second, cls.cash, cls.cash_b = cls.report.trials

    def scenario(self, case):
        with TemporaryDirectory() as d:
            audit = wf.TrialAudit.create(Path(d) / 'research-scenario')
            return wf.run(wf.prepare(wf.Scope(case), self.spec.folds[:1]), audit, 'one')

    def test_two_arms_and_expanding_folds(self):
        self.assertEqual([t.candidate for t in self.report.trials], [Candidate.A, Candidate.B]*2)
        self.assertEqual(self.first.fold, self.second.fold)
        self.assertEqual(self.first.fold.train, self.cash.fold.train)
        self.assertEqual(self.first.fold.end, self.cash.fold.selection)
        self.assertEqual(len(set(t.trial_id for t in self.report.trials)), 4)
        for t in self.report.trials:
            self.assertEqual(t.status, 'COMPLETE', t.reasons)
            self.assertEqual([c.at.date() for c in t.closes],
                             [o.at.date() for o in t.decisions if t.fold.test <= o.at.date() < t.fold.end])
        self.assertEqual(self.report.paired_net_differences, ('0', '0'))

    def test_holiday_weekend_session_and_exclusive_boundary(self):
        fold = replace(self.first.fold, train=date(2020, 1, 11))
        self.assertEqual(wf.prepare(folds=(fold,)).folds[0].train, date(2020, 1, 11))
        for invalid in (date(2020, 1, 6), date(2020, 1, 12)):
            with self.assertRaisesRegex(ConfigError, 'session'):
                wf.prepare(folds=(replace(fold, train=invalid),))
        with self.assertRaises(ConfigError):
            replace(fold, selection=fold.test)
        with self.assertRaises(ConfigError):
            wf.prepare(folds=(fold, fold))

    def test_monthly_daily_seed_and_completed_week(self):
        selection = next(o for o in self.second.decisions if o.at.date() == self.first.fold.test)
        self.assertTrue(selection.eligible)
        self.assertEqual(selection.monthly.final_session, date(2020, 10, 30))
        self.assertLess(abs(selection.monthly.close - selection.monthly.daily_ema200 - Decimal('99.5')), Decimal('1e-44'))
        self.assertLessEqual(selection.monthly.available_at, selection.at)
        self.assertTrue(all(o.monthly is None for o in self.first.decisions))
        thursday = next(o for o in self.first.decisions if o.at.date() == date(2020, 11, 12))
        self.assertFalse(thursday.eligible)
        self.assertEqual(thursday.rebalance_observation, 'THURSDAY_SHADOW')
        self.assertEqual(selection.rebalance_observation, 'FRIDAY_REFERENCE')

    def test_account_conservation_and_cost(self):
        for t in (self.first, self.second):
            self.assertEqual(t.metrics.buy_fills, 1)
            self.assertEqual((t.metrics.cash_closes, t.metrics.sessions), (2, 3))
            c = t.closes[-1]
            self.assertEqual((c.held, c.protected, c.charges, c.settled_cash), (2, 0, 1, 9779))
            self.assertEqual(c.settled_cash + 110*c.held, c.marked_equity)
            self.assertEqual(c.marked_equity, 9999)
            self.assertEqual(Fraction(t.metrics.net_return), Fraction(-1, 10000))
            self.assertEqual(Fraction(t.metrics.max_drawdown), Fraction(1, 10000))

    def test_cash_benchmark_and_no_forced_trade(self):
        self.assertEqual(self.cash.metrics.cash_closes, 3)
        self.assertEqual((self.cash.metrics.buy_fills, self.cash.metrics.net_return), (0, '0'))
        self.assertEqual(self.cash.metrics.cash_benchmark_return, '0')
        self.assertIn('UNAVAILABLE', self.cash.metrics.low_turnover_benchmark)

    def test_no_warmup_or_training_account_effects(self):
        self.assertEqual(self.first.decisions[0].at.date(), date(2020, 11, 10))
        self.assertEqual(self.first.closes[0].at.date(), date(2020, 11, 13))
        self.assertEqual(self.cash.closes[0].settled_cash, 10000)
        self.assertTrue(all(not c.held and not c.charges for c in self.cash.closes))
        self.assertEqual(self.first.decisions, self.cash.decisions[:len(self.first.decisions)])

    def test_shadow_confirmation_does_not_select(self):
        obs = self.first.decisions
        self.assertTrue(obs[0].shadow_one)
        self.assertFalse(obs[1].shadow_three)
        self.assertTrue(obs[2].shadow_three)
        self.assertFalse(obs[2].eligible)
        self.assertEqual(self.spec.selection_rule, 'RETAIN_BOTH_NO_FIT')

    def test_all_planned_attempted_losers_retained(self):
        facts = self.audit.receipts()
        self.assertEqual(sum(r['key'][-1] == 'PLANNED' for r in facts), 4)
        results = [r['value'] for r in facts if r['key'][-1] == 'RESULT']
        self.assertEqual(len(results), 4)
        self.assertEqual(sum(Fraction(v['metrics']['net_return']) < 0 for v in results), 2)
        self.assertEqual(len({r['value']['input'] for r in facts if r['key'][-1] == 'STARTED'}), 1)

    def test_duplicate_restart_replay_and_distinct_attempt(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'research-restart'
            a = wf.TrialAudit.create(path)
            spec = wf.prepare(folds=(self.cash.fold,))
            first = wf.run(spec, a, 'same')
            facts = a.receipts()
            reopened = wf.TrialAudit(path)
            self.assertEqual(wf.run(spec, reopened, 'same'), first)
            self.assertEqual(reopened.receipts(), facts)
            self.assertEqual(wf.run(spec, reopened, 'rerun'), first)
            self.assertEqual(len(reopened.receipts()) - len(facts), 4)

    def test_conflict_cannot_replace_receipt_or_declaration(self):
        with TemporaryDirectory() as tmp:
            audit = wf.TrialAudit.create(Path(tmp) / 'research-conflict')
            audit._append(('study',), self.spec)
            before = audit.receipts()
            with self.assertRaisesRegex(ConfigError, 'conflicting'):
                wf.run(wf.prepare(wf.Scope('gap')), audit, 'retry')
            self.assertEqual(before, audit.receipts())

    def test_preflight_before_data_outcomes_or_journal(self):
        with patch.object(wf, 'build', side_effect=AssertionError), patch.object(wf, '_trial', side_effect=AssertionError):
            before = self.audit.receipts()
            for scope in (wf.Scope(origin='REAL'), wf.Scope(purpose='HOLDOUT'),
                          wf.Scope(purpose='UNSEALED'), wf.Scope('research_manifest.json')):
                with self.assertRaises(ConfigError):
                    wf.prepare(scope)
                with self.assertRaises(ConfigError):
                    wf.run(replace(self.spec, scope=scope), self.audit, 'denied')
            self.assertEqual(self.audit.receipts(), before)

    def test_tampered_binding_and_immutable_spec(self):
        with self.assertRaises(FrozenInstanceError):
            self.spec.version = 'other'
        with self.assertRaisesRegex(ConfigError, 'changed'):
            wf.run(replace(self.spec, fixture_sha256='0'*64), self.audit, 'wrong')
        with self.assertRaises(ConfigError):
            replace(self.spec, selection_rule='highest return')

    def test_gap_never_clipped_to_limit(self):
        r = self.scenario('gap')
        self.assertEqual(r.paired_net_differences, (None,))
        for t in r.trials:
            self.assertEqual(t.status, 'INCONCLUSIVE', t.reasons)
            self.assertIsNone(t.metrics)
            self.assertEqual((t.closes[-1].held, t.closes[-1].settled_cash, t.closes[-1].pending_orders), (0, 10000, 1))
            self.assertLess(t.closes[-1].buying_power, 10000)
        self.assertEqual(self.first.closes[:2], r.trials[0].closes[:2])

    def test_touch_without_receipt_and_missing_mark(self):
        pending = self.scenario('unresolved').trials[0]
        self.assertIn('opening execution receipt unavailable', pending.reasons)
        self.assertEqual(pending.closes[-1].held, 0)
        missing = self.scenario('missing-mark').trials[0]
        self.assertEqual(missing.status, 'INCONCLUSIVE')
        self.assertIsNone(missing.metrics)
        self.assertEqual(missing.closes[-1].held, 2)
        self.assertIsNone(missing.closes[-1].marked_equity)

    def test_missing_constituents_and_unverified_fees(self):
        for case, message in [('missing-universe', 'survivorship'), ('missing-fees', 'unverified')]:
            with self.subTest(case=case):
                for t in self.scenario(case).trials:
                    self.assertEqual(t.status, 'BLOCKED')
                    self.assertIn(message, str(t.reasons))
                    self.assertIsNone(t.metrics)

    def test_later_revision_preserves_decisions_and_execution(self):
        r = self.scenario('future-revision')
        self.assertNotEqual(r.study_sha256, self.report.study_sha256)
        for earlier, revised in zip(self.report.trials, r.trials):
            self.assertEqual(earlier.decisions, revised.decisions)
            self.assertEqual(earlier.closes, revised.closes)
            self.assertEqual(earlier.metrics, revised.metrics)

    def test_intervening_revision_cannot_erase_preexisting_decision(self):
        later = self.scenario('intervening-revision').trials[0]
        self.assertEqual(self.first.closes[0], later.closes[0])
        self.assertEqual(self.first.decisions[:4], later.decisions[:4])
        self.assertEqual(later.status, 'COMPLETE', later.reasons)
        self.assertEqual(later.metrics.buy_fills, 0)

    def test_declining_completed_month_is_never_eligible_for_b(self):
        a, b = self.scenario('declining-index').trials
        self.assertTrue(all(o.monthly is None for o in a.decisions))
        self.assertTrue(all(o.monthly.close < o.monthly.daily_ema200 for o in b.decisions))
        self.assertTrue(all(not o.monthly.passes and not o.eligible for o in b.decisions))
        self.assertEqual(b.metrics.buy_fills, 0)

    def test_failed_attempt_and_all_plans_durable_before_evaluation(self):
        with TemporaryDirectory() as d:
            a = wf.TrialAudit.create(Path(d) / 'research-failed')
            def fail(*args):
                self.assertEqual(sum(r['key'][-1] == 'PLANNED' for r in a.receipts()), 4)
                raise RuntimeError('fixture fault')
            with patch.object(wf, '_trial', side_effect=fail):
                r = wf.run(self.spec, a, 'injected')
            self.assertTrue(all(t.status == 'FAILED' and 'fixture fault' in t.reasons for t in r.trials))
            self.assertEqual(sum(x['key'][-1] == 'RESULT' for x in a.receipts()), 4)

    def test_research_only_store_and_operational_isolation(self):
        self.assertEqual(load_manifest(wf.ROOT / 'research_manifest.json'), ResearchManifest())
        self.assertTrue(readiness_issues(wf.BotConfig()))
        self.assertTrue(all(not p.name.endswith('.sqlite') for p in self.path.iterdir()))
        with self.assertRaises(ConfigError):
            wf.TrialAudit.create(wf.ROOT / 'research-forbidden')
