"""Focused independent-review regressions: synthetic facts and schedules only."""
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from zoneinfo import ZoneInfo
import config as c
import config_contracts as k
import test_config as fixtures
import test_contracts as contracts

class ReviewRegressions(unittest.TestCase):
    def setUp(self):
        self.cfg=fixtures.ready_config()
        self.ps=fixtures.research_profiles()
        self.manifest=fixtures.sealed_manifest(self.cfg)

    def authorize(self, cfg=None, ps=None, cutoff=None):
        cfg=self.cfg if cfg is None else cfg
        ps=self.ps if ps is None else ps
        cfg=replace(cfg,execution=replace(cfg.execution,profile_sha256=tuple(p.content_sha256 for p in ps)))
        m=replace(self.manifest,config_sha256=c.content_hash(cfg))
        c.authorize_development_window(cfg,m,m.development_start,m.development_end,
            expected_manifest_sha256=c.content_hash(m),verification_profiles=ps,authorization_at=cutoff)

    def changed_profile(self, index, **changes):
        ps=list(self.ps);p=ps[index];body=replace(p.body,**changes);h=c.content_hash(body)
        # Explicitly reapprove altered synthetic test assumptions, never mutate a live approval.
        approved_at=max(p.approval.approved_at,body.verified_at or p.approval.approved_at)
        ps[index]=k.VerificationProfile(body,h,replace(p.approval,content_sha256=h,approved_at=approved_at))
        return tuple(ps)

    def mark_check(self, mark, blocked):
        t=contracts.T+timedelta(hours=1)
        r_mark=10*max(mark-D('90'),D(0))+D(5)
        p=replace(contracts.position(),current_mark=mark,r_mark=r_mark,r_position=max(D(105),r_mark))
        before=c.canonical_json(p)
        ps=tuple(contracts.profile(kind) for kind in ('BROKER','FEES','SLIPPAGE','ADVERSE_EXECUTION'))
        direct=p.issues(t)
        combined=k.entry_contract_issues((p,),contracts.events(),ps,t,'0.2.0',contracts.H,'SYNTHETIC',tuple(x.content_sha256 for x in ps))
        issue='mark at/below protective trigger; reconcile before new entries'
        self.assertEqual(issue in direct,blocked)
        self.assertEqual(issue in combined,blocked)
        if not blocked:self.assertEqual(combined,())
        self.assertEqual(c.canonical_json(p),before)
        self.assertEqual(p.protection_state,'EXCHANGE_ACTIVE')
        self.assertEqual(p.remaining_quantity,10)
        self.assertEqual(p.r_mark,r_mark)

    def test_mark_above_trigger(self):self.mark_check(D('91'),False)
    def test_mark_equal_trigger(self):self.mark_check(D('90'),True)
    def test_mark_below_trigger(self):self.mark_check(D('80'),True)

    def test_unrelated_broker_version_rejected(self):
        cfg=replace(self.cfg,execution=replace(self.cfg.execution,broker_profile_version='UNRELATED-BROKER-VERSION'))
        with self.assertRaisesRegex(c.ConfigError,'broker profile version mismatch'):self.authorize(cfg=cfg)

    def test_duplicated_execution_fields_bound(self):
        for field,value,reason in (
            ('order_cutoff_rule','different','broker execution'),
            ('protective_order_type','STOP_MARKET','broker execution'),
            ('fee_source_reference','different','fee source'),
            ('slippage_bps',D('99'),'slippage'),
            ('fixed_execution_allowance_inr',D('99'),'adverse execution'),
            ('fee_effective_start',fixtures.date(2018,1,1),'fee applicability')):
            with self.subTest(field=field),self.assertRaisesRegex(c.ConfigError,reason):
                self.authorize(cfg=replace(self.cfg,execution=replace(self.cfg.execution,**{field:value})))

    def test_free_text_does_not_replace_structured_binding(self):
        with self.assertRaisesRegex(c.ConfigError,'typed execution assumptions'):
            self.authorize(ps=self.changed_profile(0,assumptions=None))

    def test_approved_profile_numeric_change_still_must_match_config(self):
        a=replace(self.ps[2].body.assumptions,slippage_bps=D('99'))
        with self.assertRaisesRegex(c.ConfigError,'slippage assumption'):
            self.authorize(ps=self.changed_profile(2,assumptions=a))

    def test_historical_schedule_ending_before_sealing_accepted(self):
        self.assertLess(self.ps[1].body.effective_end,self.manifest.sealed_at)
        self.authorize()
        self.assertTrue(self.ps[1].issues(self.manifest.sealed_at,'RESEARCH'))  # not currently applicable

    def test_missing_historical_coverage_rejected(self):
        for changes in ({'effective_start':datetime(2020,1,1,tzinfo=timezone.utc)},
                        {'effective_end':datetime(2022,1,1,tzinfo=timezone.utc)},
                        {'effective_start':None,'effective_end':None}):
            with self.subTest(changes=changes),self.assertRaisesRegex(c.ConfigError,'applicability'):
                self.authorize(ps=self.changed_profile(0,**changes))

    def test_partial_first_day_not_full_coverage(self):
        late=datetime(2019,1,1,12,tzinfo=ZoneInfo('Asia/Kolkata'))
        with self.assertRaisesRegex(c.ConfigError,'applicability'):
            self.authorize(ps=self.changed_profile(0,effective_start=late))

    def test_future_evidence_unavailable(self):
        t=self.manifest.sealed_at+timedelta(days=1)
        evidence=replace(self.ps[0].body.evidence[0],available_at=t)
        with self.assertRaisesRegex(c.ConfigError,'unavailable|future evidence'):
            self.authorize(ps=self.changed_profile(0,evidence=(evidence,),verified_at=t,knowledge_basis='RETROSPECTIVE_RESEARCH'))

    def test_missing_approval(self):
        ps=list(self.ps);ps[0]=replace(ps[0],approval=None)
        with self.assertRaisesRegex(c.ConfigError,'approval unavailable'):self.authorize(ps=tuple(ps))

    def test_expired_revoked_and_unknown_approval(self):
        for changes,reason in (
            ({'validity_mode':'EXPIRES','valid_until':self.manifest.sealed_at},'expired'),
            ({'revoked_at':self.manifest.sealed_at},'revoked'),
            ({'validity_mode':'UNVERIFIED'},'validity unverified'),
            ({'validity_evidence':None},'validity unverified')):
            ps=list(self.ps);ps[0]=replace(ps[0],approval=replace(ps[0].approval,**changes))
            with self.subTest(reason=reason),self.assertRaisesRegex(c.ConfigError,reason):self.authorize(ps=tuple(ps))

    def test_approval_validity_independent_of_historical_applicability(self):
        ps=list(self.ps)
        expiry=self.manifest.sealed_at+timedelta(days=1)
        ps[0]=replace(ps[0],approval=replace(ps[0].approval,validity_mode='EXPIRES',valid_until=expiry))
        self.authorize(ps=tuple(ps))
        with self.assertRaisesRegex(c.ConfigError,'expired'):self.authorize(ps=tuple(ps),cutoff=expiry)

    def test_future_approval_and_validity_evidence_block(self):
        ps=list(self.ps);p=ps[0]
        ps[0]=replace(p,approval=replace(p.approval,approved_at=self.manifest.sealed_at+timedelta(days=1)))
        with self.assertRaisesRegex(c.ConfigError,'approval unavailable'):self.authorize(ps=tuple(ps))
        ps[0]=replace(p,approval=replace(p.approval,validity_evidence=replace(p.approval.evidence,available_at=self.manifest.sealed_at+timedelta(days=1))))
        with self.assertRaisesRegex(c.ConfigError,'validity evidence unavailable'):self.authorize(ps=tuple(ps))

    def test_retrospective_evidence_requires_explicit_label(self):
        t=datetime(2024,1,1,tzinfo=timezone.utc)
        evidence=replace(self.ps[0].body.evidence[0],available_at=t)
        ps=self.changed_profile(0,evidence=(evidence,),verified_at=t)
        with self.assertRaisesRegex(c.ConfigError,'point-in-time'):self.authorize(ps=ps)
        ps=self.changed_profile(0,evidence=(evidence,),verified_at=t,knowledge_basis='RETROSPECTIVE_RESEARCH')
        self.authorize(ps=ps)
        self.assertIn('retrospective assumptions are research-only',ps[0].issues(self.manifest.sealed_at,'OPERATIONAL'))

    def test_cutoff_before_sealing_or_naive_rejected(self):
        for t in (self.manifest.sealed_at-timedelta(seconds=1),datetime(2024,2,2)):
            with self.subTest(t=t),self.assertRaises(c.ConfigError):self.authorize(cutoff=t)

    def test_old_schema_and_profile_documents_rejected(self):
        doc=c.to_dict(self.cfg);doc['schema_version']='2.0'
        with self.assertRaises(c.ConfigError):c.from_dict(c.BotConfig,doc)
        doc=c.to_dict(self.ps[0]);del doc['body']['knowledge_basis']
        with self.assertRaises(c.ConfigError):c.from_dict(k.VerificationProfile,doc)

    def test_operational_stays_blocked(self):
        with self.assertRaisesRegex(c.ConfigError,'operational'):c.require_ready(self.cfg)
