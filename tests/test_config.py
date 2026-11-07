"""Offline configuration tests. All sealed datasets/approvals here are fictitious."""
import copy
import hashlib
import hmac
import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError, fields, replace
from datetime import date, datetime, timezone
from decimal import Decimal, localcontext
from pathlib import Path

import config as c

ROOT = Path(__file__).resolve().parents[1]


def ready_config():
    """Synthetic prerequisites only; not an assertion about an actual broker."""
    return c.BotConfig(
        account=c.AccountConfig(account_id="SYNTHETIC_ACCOUNT", capital_inr=Decimal("5000")),
        data=c.DataConfig(provider="SYNTHETIC", provider_version="fixture-1",
                          snapshot_sha256="a" * 64, calendar_version="fixture-calendar-1",
                          universe_version="fixture-universe-1", point_in_time_verified=True,
                          availability_verified=True),
        risk=c.RiskConfig(open_risk_basis="MARK_TO_STOP"),
        execution=c.ExecutionConfig(broker_profile_version="SYNTHETIC-1",
                                     broker_rules_verified=True, order_cutoff_rule="SYNTHETIC_RULE",
                                     protective_order_type="STOP_LIMIT", fee_model_version="SYNTHETIC_FEES-1",
                                     fee_source_reference="synthetic fixture, not official rates",
                                     fee_effective_start=date(2019, 1, 1), fee_effective_end=date(2024, 1, 1),
                                     fee_schedule_verified=True, slippage_bps=Decimal("5"),
                                     fixed_execution_allowance_inr=Decimal("1")))


def sealed_manifest(cfg=None):
    cfg = cfg or ready_config()
    return c.ResearchManifest(status=c.SealStatus.SEALED, snapshot_id="SYNTHETIC_ONLY",
        snapshot_sha256=cfg.data.snapshot_sha256,
        snapshot_created_at=datetime(2024, 2, 1, tzinfo=timezone.utc),
        sealed_at=datetime(2024, 2, 2, tzinfo=timezone.utc), instruments=("SYNTHETIC_SECURITY",),
        provider_version=cfg.data.provider_version, calendar_version=cfg.data.calendar_version,
        universe_version=cfg.data.universe_version, fee_model_version=cfg.execution.fee_model_version,
        config_sha256=c.content_hash(cfg), snapshot_start=date(2019, 1, 1), snapshot_end=date(2024, 1, 1),
        development_start=date(2019, 1, 1), development_end=date(2023, 1, 1),
        holdout_start=date(2023, 1, 1), holdout_end=date(2024, 1, 1))


class ConfigurationTests(unittest.TestCase):
    def test_default_policy_exact(self):
        r = c.BotConfig().risk
        self.assertEqual((r.trade_risk, r.stock_allocation, r.gross_exposure, r.max_positions,
                          r.total_stop_risk, r.drawdown_review, r.drawdown_hard, r.leverage),
                         (Decimal('.005'), Decimal('.4'), Decimal('.8'), 2,
                          Decimal('.01'), Decimal('.05'), Decimal('.08'), Decimal('0')))

    def test_account_capital_not_assumed(self):
        self.assertIsNone(c.BotConfig().account.capital_inr)
        for capital in ("5000", "10000", "11000"):
            self.assertEqual(c.AccountConfig(capital_inr=Decimal(capital)).capital_inr, Decimal(capital))

    def test_invalid_capital(self):
        for capital in (Decimal('0'), Decimal('-1'), Decimal('NaN'), Decimal('Infinity'), 5000, True):
            with self.subTest(capital=capital), self.assertRaises(c.ConfigError):
                c.AccountConfig(capital_inr=capital)

    def test_nested_objects_are_immutable(self):
        cfg = c.BotConfig()
        with self.assertRaises(FrozenInstanceError):
            cfg.risk.trade_risk = Decimal('.2')
        with self.assertRaises(FrozenInstanceError):
            cfg.strategy.candidate = c.Candidate.B
        with self.assertRaises(TypeError):
            cfg.backtesting.candidates[0] = c.Candidate.B
        self.assertFalse(hasattr(cfg, '__dict__'))

    def test_serialized_copy_does_not_mutate_config(self):
        cfg = c.BotConfig()
        data = c.to_dict(cfg)
        data['risk']['trade_risk'] = '.9'
        data['backtesting']['candidates'].append('C')
        self.assertEqual(cfg.risk.trade_risk, Decimal('.005'))
        self.assertEqual(len(cfg.backtesting.candidates), 2)

    def test_roundtrip(self):
        cfg = ready_config()
        self.assertEqual(c.from_dict(c.BotConfig, c.parse_json(c.canonical_json(cfg))), cfg)

    def test_hash_stable_for_json_order_and_decimal_representation(self):
        a = c.BotConfig()
        b = replace(a, risk=replace(a.risk, stock_allocation=Decimal('0.4000')))
        self.assertEqual(c.content_hash(a), c.content_hash(b))
        reversed_dict = dict(reversed(list(c.to_dict(a).items())))
        self.assertEqual(c.content_hash(a), c.content_hash(c.from_dict(c.BotConfig, reversed_dict)))

    def test_config_version_changes_hash(self):
        a = c.BotConfig()
        self.assertNotEqual(c.content_hash(a), c.content_hash(replace(a, config_version="0.1.1")))

    def test_hash_preserves_decimal_precision_independent_of_context(self):
        a = c.AccountConfig(capital_inr=Decimal('123456789012345678901234567890.1'))
        b = replace(a, capital_inr=Decimal('123456789012345678901234567890.2'))
        digest = c.content_hash(a)
        with localcontext() as context:
            context.prec = 4
            self.assertEqual(c.content_hash(a), digest)
            self.assertNotEqual(c.content_hash(a), c.content_hash(b))

    def test_every_leaf_has_provenance(self):
        catalog = c.parameter_catalog()
        allowed = {p.value for p in c.Provenance}
        self.assertGreater(len(catalog), 90)
        self.assertEqual(len({r['path'] for r in catalog}), len(catalog))
        for row in catalog:
            self.assertIn(row['provenance'], allowed)
            self.assertTrue(row['reason'])

    def test_missing_fields_rejected_at_every_section(self):
        for section in (None, 'account', 'data', 'timeframes', 'regime', 'strategy', 'risk',
                        'execution', 'backtesting', 'reporting'):
            data = c.to_dict(c.BotConfig())
            target = data if section is None else data[section]
            for name in list(target):
                changed = copy.deepcopy(data)
                del (changed if section is None else changed[section])[name]
                with self.subTest(section=section, name=name), self.assertRaises(c.ConfigError):
                    c.from_dict(c.BotConfig, changed)

    def test_unknown_fields_rejected(self):
        data = c.to_dict(c.BotConfig())
        data['execution']['auto_submit'] = True
        with self.assertRaises(c.ConfigError):
            c.from_dict(c.BotConfig, data)

    def test_duplicate_json_keys_and_nonfinite_tokens(self):
        for text in ('{"a":1,"a":2}', '{"a":{"b":1,"b":2}}', '{"a":NaN}', '{"a":Infinity}', '[]', '{'):
            with self.subTest(text=text), self.assertRaises(c.ConfigError):
                c.parse_json(text)

    def test_numeric_coercion_not_allowed(self):
        for section, name, value in [('risk', 'max_positions', True), ('risk', 'trade_risk', .005),
                                     ('strategy', 'fast_ema', '9'), ('regime', 'confirmation_sessions', True),
                                     ('account', 'long_only', 1)]:
            data = c.to_dict(c.BotConfig()); data[section][name] = value
            with self.subTest(name=name), self.assertRaises(c.ConfigError):
                c.from_dict(c.BotConfig, data)

    def test_invalid_risk_and_fixed_policy_changes(self):
        for changes in ({'trade_risk': Decimal('.02')}, {'trade_risk': Decimal('.004')},
                        {'stock_allocation': Decimal('.9')}, {'gross_exposure': Decimal('1.1')},
                        {'max_positions': 3}, {'leverage': Decimal('1')},
                        {'drawdown_review': Decimal('.09')}, {'drawdown_hard': Decimal('0')}):
            with self.subTest(changes=changes), self.assertRaises(c.ConfigError):
                replace(c.RiskConfig(), **changes)

    def test_scope_invariants(self):
        for obj, changes in [(c.AccountConfig(), {'long_only': False}),
                             (c.ExecutionConfig(), {'broker_submission_api': True}),
                             (c.ExecutionConfig(), {'manual_approval': False}),
                             (c.TimeframeConfig(), {'completed_only': False}),
                             (c.RiskConfig(), {'automatic_resume': True}),
                             (c.RiskConfig(), {'liquidate_on_drawdown': True}),
                             (c.BacktestConfig(), {'auto_promote': True}),
                             (c.BacktestConfig(), {'holdout_months': 6}),
                             (c.RegimeConfig(), {'confirmation_sessions': 1})]:
            with self.subTest(changes=changes), self.assertRaises(c.ConfigError):
                replace(obj, **changes)

    def test_invalid_indicator_and_strategy_parameters(self):
        for obj, changes in [(c.RegimeConfig(), {'adx_sideways': Decimal('25')}),
                             (c.RegimeConfig(), {'vol_recent_returns': 1}),
                             (c.RegimeConfig(), {'atr_spike_ratio': Decimal('0')}),
                             (c.StrategyConfig(), {'fast_ema': 21}),
                             (c.StrategyConfig(), {'stop_atr_multiple': Decimal('-2')}),
                             (c.StrategyConfig(), {'ranking_sessions': 0})]:
            with self.subTest(changes=changes), self.assertRaises(c.ConfigError):
                replace(obj, **changes)

    def test_negative_expense_assumptions_rejected(self):
        for n in ('slippage_bps', 'fixed_execution_allowance_inr'):
            with self.subTest(field=n), self.assertRaises(c.ConfigError):
                replace(c.ExecutionConfig(), **{n: Decimal('-1')})

    def test_invalid_fee_coverage(self):
        with self.assertRaises(c.ConfigError):
            c.ExecutionConfig(fee_effective_start=date(2024, 1, 1))
        with self.assertRaises(c.ConfigError):
            c.ExecutionConfig(fee_effective_start=date(2024, 1, 1), fee_effective_end=date(2023, 1, 1))

    def test_invalid_versions_and_dates(self):
        for version in ('', '1', 'v1.0.0', ' 1.0.0'):
            with self.subTest(version=version), self.assertRaises(c.ConfigError):
                c.BotConfig(config_version=version)
        data = c.to_dict(c.BotConfig()); data['schema_version'] = '9.0'
        with self.assertRaises(c.ConfigError):
            c.from_dict(c.BotConfig, data)
        data = c.to_dict(ready_config()); data['execution']['fee_effective_start'] = '2024-02-30'
        with self.assertRaises(c.ConfigError):
            c.from_dict(c.BotConfig, data)

    def test_draft_cannot_authorize_executable_recommendations(self):
        issues = c.readiness_issues(c.BotConfig())
        for n in ('account.capital_inr', 'risk.open_risk_basis', 'execution.slippage_bps', 'execution.fee_model_version'):
            self.assertIn(n, issues)
        with self.assertRaises(c.ConfigError):
            c.require_ready(c.BotConfig())

    def test_each_missing_readiness_input_blocks(self):
        cfg = ready_config()
        self.assertEqual(c.readiness_issues(cfg), ())
        for section, name, value in [('account', 'capital_inr', None), ('risk', 'open_risk_basis', None),
                                     ('execution', 'slippage_bps', None), ('execution', 'broker_rules_verified', False),
                                     ('data', 'point_in_time_verified', False), ('data', 'availability_verified', False)]:
            changed = replace(cfg, **{section: replace(getattr(cfg, section), **{name: value})})
            with self.subTest(name=name), self.assertRaises(c.ConfigError):
                c.require_ready(changed)

    def test_candidate_fork_is_isolated(self):
        a = c.BotConfig(); digest = c.content_hash(a)
        b = replace(a, strategy=replace(a.strategy, candidate=c.Candidate.B), config_version='0.1.1')
        self.assertEqual(a.strategy.candidate, c.Candidate.A)
        self.assertEqual(c.content_hash(a), digest)
        self.assertNotEqual(c.content_hash(b), digest)

    def test_two_candidates_only(self):
        for candidates in ((c.Candidate.A,), (c.Candidate.A, c.Candidate.A), [c.Candidate.A, c.Candidate.B]):
            with self.subTest(candidates=candidates), self.assertRaises(c.ConfigError):
                c.BacktestConfig(candidates=candidates)

    def test_no_import_time_files_or_stdout(self):
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE='1')
            p = subprocess.run([sys.executable, '-c', 'import config'], cwd=directory,
                               env=env, capture_output=True, text=True, check=True)
            self.assertEqual(p.stdout, '')
            self.assertEqual(list(Path(directory).iterdir()), [])


class ManifestTests(unittest.TestCase):
    def test_template_contains_no_invented_snapshot_or_dates(self):
        m = c.load_manifest(ROOT / 'research_manifest.json')
        self.assertEqual(m.status, c.SealStatus.UNSEALED)
        for name in ('snapshot_id', 'snapshot_sha256', 'holdout_start', 'holdout_end', 'sealed_at'):
            self.assertIsNone(getattr(m, name))

    def test_unsealed_research_denied(self):
        m = c.ResearchManifest()
        with self.assertRaisesRegex(c.ConfigError, 'UNSEALED'):
            c.authorize_development_window(c.BotConfig(), m, date(2020, 1, 1), date(2021, 1, 1),
                                            expected_manifest_sha256=c.content_hash(m))

    def test_incomplete_seal_rejected(self):
        with self.assertRaises(c.ConfigError):
            c.ResearchManifest(status=c.SealStatus.SEALED)

    def test_exact_final_calendar_year_and_leap_day(self):
        m = sealed_manifest()
        leap = replace(m, snapshot_end=date(2024, 2, 29), holdout_end=date(2024, 2, 29),
                       holdout_start=date(2023, 2, 28), development_end=date(2023, 2, 28))
        self.assertEqual(leap.holdout_start, date(2023, 2, 28))
        with self.assertRaises(c.ConfigError):
            replace(m, holdout_start=date(2023, 1, 2), development_end=date(2023, 1, 2))

    def test_overlap_gap_and_partial_boundaries_rejected(self):
        m = sealed_manifest()
        for changes in ({'development_end': date(2023, 1, 2)}, {'development_end': date(2022, 12, 31)},
                        {'holdout_end': date(2023, 12, 31)}, {'holdout_start': None},
                        {'development_start': date(2018, 1, 1)}):
            with self.subTest(changes=changes), self.assertRaises(c.ConfigError):
                replace(m, **changes)

    def test_seal_timestamp_order_and_timezone(self):
        m = sealed_manifest()
        with self.assertRaises(c.ConfigError):
            replace(m, sealed_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
        with self.assertRaises(c.ConfigError):
            replace(m, sealed_at=datetime(2024, 2, 2))

    def test_duplicate_symbols_and_invalid_hash(self):
        with self.assertRaises(c.ConfigError):
            replace(sealed_manifest(), instruments=('X', 'X'))
        with self.assertRaises(c.ConfigError):
            replace(sealed_manifest(), snapshot_sha256='wrong')

    def test_valid_development_window_authorized_metadata_only(self):
        cfg = ready_config(); m = sealed_manifest(cfg)
        c.authorize_development_window(cfg, m, date(2020, 1, 1), date(2023, 1, 1),
                                       expected_manifest_sha256=c.content_hash(m))

    def test_holdout_and_crossing_windows_denied(self):
        cfg = ready_config(); m = sealed_manifest(cfg)
        for start, end in ((date(2023, 1, 1), date(2024, 1, 1)),
                           (date(2022, 12, 31), date(2023, 1, 2)),
                           (date(2018, 1, 1), date(2020, 1, 1)),
                           (date(2020, 1, 1), date(2020, 1, 1))):
            with self.subTest(start=start, end=end), self.assertRaises(c.ConfigError):
                c.authorize_development_window(cfg, m, start, end, expected_manifest_sha256=c.content_hash(m))

    def test_manifest_and_config_tampering_denied(self):
        cfg = ready_config(); m = sealed_manifest(cfg)
        changed = replace(m, snapshot_id='DIFFERENT')
        with self.assertRaisesRegex(c.ConfigError, 'manifest hash'):
            c.authorize_development_window(cfg, changed, date(2020, 1, 1), date(2021, 1, 1),
                                            expected_manifest_sha256=c.content_hash(m))
        with self.assertRaisesRegex(c.ConfigError, 'configuration differs'):
            c.authorize_development_window(replace(cfg, config_version='0.2.0'), m,
                date(2020, 1, 1), date(2021, 1, 1), expected_manifest_sha256=c.content_hash(m))

    def test_snapshot_and_fee_version_mismatch(self):
        cfg = ready_config(); m = sealed_manifest(cfg)
        for name in ('snapshot_sha256', 'provider_version', 'calendar_version', 'universe_version', 'fee_model_version'):
            changed = replace(m, **{name: 'b' * 64 if name.endswith('sha256') else 'DIFFERENT'})
            with self.subTest(name=name), self.assertRaises(c.ConfigError):
                c.authorize_development_window(cfg, changed, date(2020, 1, 1), date(2021, 1, 1),
                                               expected_manifest_sha256=c.content_hash(changed))

    def test_fee_coverage_required(self):
        cfg = ready_config(); cfg = replace(cfg, execution=replace(cfg.execution, fee_effective_start=date(2021, 1, 1)))
        m = sealed_manifest(cfg)
        with self.assertRaisesRegex(c.ConfigError, 'fee profile'):
            c.authorize_development_window(cfg, m, date(2020, 1, 1), date(2021, 1, 1),
                                           expected_manifest_sha256=c.content_hash(m))


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.config_path = Path(self.directory.name) / 'config.json'
        self.receipt_path = Path(self.directory.name) / 'approval.json'
        self.cfg = ready_config()
        self.key = b'SYNTHETIC_TEST_KEY_ONLY_NOT_FOR_USE' * 2
        self.digest = c.content_hash(self.cfg)
        self.receipt = c.ApprovalReceipt(self.cfg.config_version, self.digest,
            datetime(2020, 1, 1, tzinfo=timezone.utc), ('fixture-reviewer-1', 'fixture-reviewer-2'),
            'MANUAL_LIVE_SETTINGS', '0' * 64)
        self.receipt = replace(self.receipt, signature=hmac.new(self.key, c.approval_payload(self.receipt), hashlib.sha256).hexdigest())
        self.write(self.cfg, self.receipt)

    def write(self, cfg, receipt):
        self.config_path.write_text(c.canonical_json(cfg)); self.receipt_path.write_text(c.canonical_json(receipt))

    def load(self, **overrides):
        args = dict(approval_key=self.key, expected_version=self.cfg.config_version,
                    expected_config_sha256=self.digest, as_of=datetime(2022, 1, 1, tzinfo=timezone.utc)); args.update(overrides)
        return c.load_approved_live(self.config_path, self.receipt_path, **args)

    def test_signed_pinned_config_loads_read_only(self):
        before = self.config_path.read_bytes(), self.receipt_path.read_bytes()
        self.assertEqual(self.load(), self.cfg)
        self.assertEqual(before, (self.config_path.read_bytes(), self.receipt_path.read_bytes()))

    def test_config_change_without_approval_rejected(self):
        changed = replace(self.cfg, strategy=replace(self.cfg.strategy, fast_ema=10))
        self.write(changed, self.receipt)
        with self.assertRaisesRegex(c.ConfigError, 'hash mismatch'):
            self.load()

    def test_recomputed_hash_does_not_forge_signature(self):
        changed = replace(self.cfg, strategy=replace(self.cfg.strategy, fast_ema=10))
        self.write(changed, replace(self.receipt, config_sha256=c.content_hash(changed)))
        with self.assertRaisesRegex(c.ConfigError, 'signature'):
            self.load(expected_config_sha256=c.content_hash(changed))

    def test_wrong_key_and_weak_key_rejected(self):
        for key in (b'wrong' * 10, b'short'):
            with self.subTest(key_length=len(key)), self.assertRaises(c.ConfigError):
                self.load(approval_key=key)

    def test_trusted_version_and_hash_pin_required(self):
        for overrides in ({'expected_version': '0.2.0'}, {'expected_config_sha256': 'f' * 64}):
            with self.subTest(overrides=overrides), self.assertRaises(c.ConfigError):
                self.load(**overrides)

    def test_review_metadata_tamper_rejected(self):
        self.write(self.cfg, replace(self.receipt, reviewers=('intruder-1', 'intruder-2')))
        with self.assertRaisesRegex(c.ConfigError, 'signature'):
            self.load()

    def test_two_distinct_reviewers_required(self):
        with self.assertRaises(c.ConfigError):
            replace(self.receipt, reviewers=('same', 'same'))

    def test_future_approval_rejected(self):
        with self.assertRaisesRegex(c.ConfigError, 'not yet available'):
            self.load(as_of=datetime(2019, 1, 1, tzinfo=timezone.utc))

    def test_expired_fee_profile_and_naive_decision_rejected(self):
        with self.assertRaisesRegex(c.ConfigError, 'not effective'):
            self.load(as_of=datetime(2025, 1, 1, tzinfo=timezone.utc))
        with self.assertRaises(c.ConfigError):
            self.load(as_of=datetime(2022, 1, 1))

    def test_fee_effectivity_uses_exchange_date(self):
        # 2023-12-31 20:00 UTC is already 2024-01-01 in India (exclusive end).
        with self.assertRaisesRegex(c.ConfigError, 'not effective'):
            self.load(as_of=datetime(2023, 12, 31, 20, tzinfo=timezone.utc))

    def test_live_load_refuses_signed_unready_config(self):
        cfg = c.BotConfig(); digest = c.content_hash(cfg)
        receipt = replace(self.receipt, config_sha256=digest)
        receipt = replace(receipt, signature=hmac.new(self.key, c.approval_payload(receipt), hashlib.sha256).hexdigest())
        self.write(cfg, receipt)
        with self.assertRaisesRegex(c.ConfigError, 'not executable'):
            self.load(expected_config_sha256=digest)


class ArtifactTests(unittest.TestCase):
    def test_checked_in_draft_and_catalog_match_code(self):
        self.assertEqual(c.load_config(ROOT / 'config.example.json'), c.BotConfig())
        self.assertEqual(json.loads((ROOT / 'parameter_catalog.json').read_text()), c.parameter_catalog())

    def test_checked_in_schema_is_versioned(self):
        schema = json.loads((ROOT / 'config_schema.json').read_text())
        self.assertEqual(schema['title'], 'NSE Bot Configuration 1.0')
        self.assertFalse(schema['additionalProperties'])
        self.assertEqual(set(schema['required']), {f.name for f in fields(c.BotConfig)})


if __name__ == '__main__':
    unittest.main()
