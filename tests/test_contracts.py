"""Synthetic contract regression fixtures: never operational credentials/data."""
import json
import unittest
from dataclasses import replace, FrozenInstanceError
from datetime import datetime, timezone, timedelta
from pathlib import Path
from decimal import Decimal as D
import config as c
import config_contracts as k
import config_schema as schemas
import test_config as fixtures
from test_config import ready_config

T = datetime(2022,1,1,tzinfo=timezone.utc)
E = k.Evidence('SYNTHETIC evidence', 'a'*64, T)
H = 'b'*64

def profile(kind='ADVERSE_EXECUTION', purpose='SYNTHETIC'):
    b=k.ProfileBody(kind, 'fixture-1', purpose, 'VERIFIED', (E,), T,
                    T, T+timedelta(days=10), E, 'SYNTHETIC specification; not real rates',knowledge_basis='POINT_IN_TIME')
    h=c.content_hash(b)
    a=k.ProfileApproval(b.version,h,purpose,T,('fixture-1','fixture-2'),E,validity_mode='NO_SCHEDULED_EXPIRY',validity_evidence=E)
    return k.VerificationProfile(b,h,a)

def events():
    def ev(i,kind,parent,sec,qty=None,price=None,state=None):
        t=T+timedelta(seconds=sec)
        return k.ExecutionEvent(i,kind,'position-1', 'protect-1' if kind=='PROTECTION_ACTIVATION' else 'order-1', parent,
            '0.2.0',H,'ACTUAL',t,t,None,(E,),qty,price,state)
    return (ev('d','DECISION',None,0),ev('a','TRADE_APPROVAL','d',1),
            ev('s','MANUAL_SUBMISSION','a',2),ev('ack','ACKNOWLEDGEMENT','s',3),
            ev('f','FILL','s',4,10,D('100')),ev('p','PROTECTION_ACTIVATION','f',5,10,D('90'),'EXCHANGE_ACTIVE'))

def position():
    return k.PositionRiskContract('position-1',10,D('100'),D('110'),T,T+timedelta(days=1),E,
        D('90'),10,'EXCHANGE_ACTIVE','p',D('2'),E,True,D('3'),profile().content_sha256,'CONFIRMED',D('105'),D('205'),D('205'))

class RiskContracts(unittest.TestCase):
    def test_dual_policy_only(self):
        self.assertEqual(c.RiskConfig().open_risk_basis,'MAX_ENTRY_AND_MARK')
        for v in ('MARK_TO_STOP','ENTRY_TO_STOP',None):
            with self.subTest(v=v), self.assertRaises(c.ConfigError): c.RiskConfig(open_risk_basis=v)
    def test_valid_contract(self):
        self.assertEqual(position().issues(T),())
    def test_unprotected_and_exposure_separate(self):
        p=replace(position(),protective_quantity=4)
        self.assertEqual(p.unprotected_quantity,6)
        self.assertEqual(p.marked_capital_exposure,D('1100'))
        self.assertIn('insufficient protection quantity',p.issues(T))
    def test_all_nonactive_protection_blocks(self):
        for state in ('UNKNOWN','PLANNED','SUBMITTED','BROKER_HELD_CONDITIONAL','TRIGGERED_UNFILLED','CANCELLED','EXPIRED'):
            with self.subTest(state=state):
                p=replace(position(),protection_state=state)
                self.assertTrue(p.issues(T)); self.assertEqual(p.unprotected_quantity,10)
    def test_unknown_never_zero(self):
        for field in ('current_mark','mark_at','mark_valid_until','mark_validity_evidence','protective_trigger','protective_quantity','protection_event_id','remaining_expenses','expense_basis','adverse_allowance','adverse_profile_sha256','r_entry','r_mark','r_position'):
            with self.subTest(field=field): self.assertTrue(replace(position(),**{field:None}).issues(T))
        self.assertIsNone(replace(position(),current_mark=None).marked_capital_exposure)
    def test_stale_future_marks(self):
        self.assertTrue(position().issues(T+timedelta(days=1)))
        self.assertTrue(position().issues(T-timedelta(seconds=1)))
    def test_expenses_and_reconciliation(self):
        self.assertTrue(replace(position(),expenses_exclude_booked=False).issues(T))
        self.assertTrue(replace(position(),reconciliation='UNRESOLVED').issues(T))
    def test_bad_numbers_and_types(self):
        for f,v in [('remaining_quantity',True),('remaining_quantity',0),('entry_price',D('NaN')),('remaining_expenses',D('-1')),('adverse_allowance',D('-1'))]:
            with self.subTest(field=f),self.assertRaises(c.ConfigError): replace(position(),**{f:v})

class EventContracts(unittest.TestCase):
    def test_normal_chain(self): self.assertEqual(k.event_issues(events(),T+timedelta(days=1)),())
    def test_late_ack_notification_preserves_fill(self):
        es=list(events()); es[3]=replace(es[3],notified_at=T+timedelta(hours=2),recorded_at=T+timedelta(hours=3))
        self.assertEqual(k.event_issues(tuple(es),T+timedelta(days=1)),())
        self.assertEqual(es[4].occurred_at,T+timedelta(seconds=4))
    def test_out_of_order_arrival(self):
        self.assertEqual(k.event_issues(tuple(reversed(events())),T+timedelta(days=1)),())
    def test_actual_anomaly_retained_blocked(self):
        es=list(events()); es[4]=replace(es[4],occurred_at=T-timedelta(seconds=1))
        self.assertEqual(es[4].quantity,10)
        self.assertTrue(k.event_issues(tuple(es),T+timedelta(days=1)))
    def test_naive_timestamp_rejected(self):
        for f in ('occurred_at','recorded_at','notified_at'):
            with self.subTest(f=f),self.assertRaises(c.ConfigError): replace(events()[4],**{f:datetime(2022,1,1)})
    def test_missing_and_duplicate_links(self):
        self.assertTrue(k.event_issues(events()[1:],T+timedelta(days=1)))
        self.assertTrue(k.event_issues(events()+events()[-1:],T+timedelta(days=1)))
    def test_configuration_origin_order_mismatch(self):
        for kwargs in ({'config_sha256':'c'*64},{'origin':'SIMULATED'},{'order_id':'wrong'}):
            es=list(events());es[4]=replace(es[4],**kwargs)
            self.assertTrue(k.event_issues(tuple(es),T+timedelta(days=1)))
    def test_partial_fills_are_individual_facts(self):
        es=list(events());es[4]=replace(es[4],quantity=4);es[5]=replace(es[5],quantity=4)
        es.append(replace(es[4],event_id='f2',quantity=6,occurred_at=T+timedelta(seconds=6),recorded_at=T+timedelta(seconds=6)))
        self.assertEqual(k.event_issues(tuple(es),T+timedelta(days=1)),())
    def test_no_inferred_activation(self):
        es=list(events());es[-1]=replace(es[-1],protection_state='BROKER_HELD_CONDITIONAL')
        self.assertTrue(k.event_issues(tuple(es),T+timedelta(days=1)))
    def test_immutable_event(self):
        with self.assertRaises(FrozenInstanceError): events()[4].occurred_at=T

class ProfileContracts(unittest.TestCase):
    def test_valid_synthetic_only(self):
        self.assertEqual(profile().issues(T,'SYNTHETIC'),())
        self.assertTrue(profile().issues(T,'OPERATIONAL'))
    def test_altered_body_or_approval(self):
        p=profile()
        with self.assertRaises(c.ConfigError): replace(p,body=replace(p.body,specification='changed'))
        with self.assertRaises(c.ConfigError): replace(p,approval=replace(p.approval,content_sha256='f'*64))
    def test_no_approval(self): self.assertTrue(replace(profile(),approval=None).issues(T,'SYNTHETIC'))
    def test_validity_boundaries(self):
        self.assertFalse(profile().issues(T,'SYNTHETIC'))
        for t in (T-timedelta(seconds=1),T+timedelta(days=10)):
            self.assertTrue(profile().issues(t,'SYNTHETIC'))
    def test_unverified_unsupported_missing_validity(self):
        p=profile()
        for kwargs in ({'status':'UNVERIFIED'},{'status':'UNSUPPORTED'},{'validity_basis':None}, {'effective_start':None,'effective_end':None},{'evidence':()},{'specification':None}):
            b=replace(p.body,**kwargs);h=c.content_hash(b)
            x=k.VerificationProfile(b,h,replace(p.approval,content_sha256=h))
            self.assertTrue(x.issues(T,'SYNTHETIC'))
    def test_future_approval(self):
        p=profile();p=replace(p,approval=replace(p.approval,approved_at=T+timedelta(days=1)))
        self.assertTrue(p.issues(T,'SYNTHETIC'))
    def test_required_profiles_and_linkage(self):
        ps=tuple(profile(kind) for kind in ('BROKER','FEES','SLIPPAGE','ADVERSE_EXECUTION'))
        args=((position(),),events(),ps,T+timedelta(hours=1),'0.2.0',H,'SYNTHETIC',tuple(p.content_sha256 for p in ps))
        self.assertEqual(k.entry_contract_issues(*args),())
        self.assertTrue(k.entry_contract_issues((replace(position(),protection_event_id='missing'),),*args[1:]))
        self.assertTrue(k.entry_contract_issues(args[0],args[1],(),*args[3:]))
    def test_synthetic_key_cannot_load_operational(self):
        fixture=fixtures.ApprovalTests();fixture.setUp()
        try:
            # The same signed fixture is valid cryptographically, not operationally.
            self.assertEqual(fixture.load(),fixture.cfg)
            with self.assertRaisesRegex(c.ConfigError,'operational'):
                c.load_approved_live(fixture.config_path,fixture.receipt_path,
                    approval_key=fixture.key,expected_version=fixture.cfg.config_version,
                    expected_config_sha256=fixture.digest,as_of=T)
        finally: fixture.doCleanups()
    def test_readiness_never_accepts_caller_trust(self):
        with self.assertRaisesRegex(c.ConfigError,'trust_not_provisioned'):c.require_ready(ready_config())
    def test_v1_rejected(self):
        doc=c.to_dict(c.BotConfig());doc['schema_version']='1.0'
        with self.assertRaises(c.ConfigError):c.from_dict(c.BotConfig,doc)
    def test_contract_roundtrip_and_missing(self):
        for obj in (position(),events()[4],profile()):
            doc=c.to_dict(obj);self.assertEqual(c.from_dict(type(obj),doc),obj)
            for name in doc:
                missing=dict(doc);del missing[name]
                with self.subTest(name=name),self.assertRaises(c.ConfigError):c.from_dict(type(obj),missing)
    def test_generated_schemas_exact(self):
        for filename,generated in [('config_schema.json',schemas.config_schema()),('research_manifest_schema.json',schemas.manifest_schema()),('contracts_schema.json',schemas.contracts_schema())]:
            self.assertEqual(json.loads(Path(filename).read_text()),generated)

class AdditionalRegressionTests(unittest.TestCase):
    def test_research_profiles_required_even_when_sealed(self):
        cfg=ready_config(); m=fixtures.sealed_manifest(cfg)
        with self.assertRaisesRegex(c.ConfigError,'four research'):
            c.authorize_development_window(cfg,m,m.development_start,m.development_end,expected_manifest_sha256=c.content_hash(m))
    def test_synthetic_research_profile_denied(self):
        cfg=ready_config();m=fixtures.sealed_manifest(cfg)
        ps=tuple(profile(kind) for kind in ('BROKER','FEES','SLIPPAGE','ADVERSE_EXECUTION'))
        cfg=replace(cfg,execution=replace(cfg.execution,profile_sha256=tuple(p.content_sha256 for p in ps)))
        m=replace(m,config_sha256=c.content_hash(cfg))
        with self.assertRaisesRegex(c.ConfigError,'research profile'):
            c.authorize_development_window(cfg,m,m.development_start,m.development_end,expected_manifest_sha256=c.content_hash(m),verification_profiles=ps)
    def test_activation_cannot_precede_filled_quantity(self):
        es=list(events());es[-1]=replace(es[-1],quantity=11)
        self.assertTrue(k.event_issues(tuple(es),T+timedelta(days=1)))
    def test_old_receipt_cannot_approve_new_configuration(self):
        fixture=fixtures.ApprovalTests();fixture.setUp()
        try:
            old=replace(fixture.receipt,config_version='0.1.0')
            import hmac, hashlib
            old=replace(old,signature=hmac.new(fixture.key,c.approval_payload(old),hashlib.sha256).hexdigest())
            fixture.write(fixture.cfg,old)
            with self.assertRaisesRegex(c.ConfigError,'version/hash'): fixture.load()
        finally:fixture.doCleanups()
    def test_all_contract_types_strict(self):
        with self.assertRaises(c.ConfigError):k.event_issues(list(events()),T)
        with self.assertRaises(c.ConfigError):profile().issues(T,'LIVE')
    def test_operational_delay_not_silently_approved(self):
        with self.assertRaises(c.ConfigError):c.ExecutionConfig(operator_delay_operational_approved=True)

class RiskArithmeticTests(unittest.TestCase):
    def test_both_risks_and_max_required(self):
        with self.assertRaises(c.ConfigError): replace(position(),r_position=D('105'))
        with self.assertRaises(c.ConfigError): replace(position(),r_entry=D('0'))
    def test_stop_above_prices_does_not_remove_costs(self):
        p=replace(position(),protective_trigger=D('120'),r_entry=D('5'),r_mark=D('5'),r_position=D('5'))
        self.assertEqual(p.r_position,D('5'))
    def test_arithmetic_independent_of_callers_precision(self):
        from decimal import localcontext
        with localcontext() as ctx:
            ctx.prec=2
            self.assertEqual(position().r_position,D('205'))
