"""Independent synthetic arithmetic and integration; no market datasets."""
import unittest
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from decimal import Decimal as D, localcontext
from fractions import Fraction as F
from tempfile import TemporaryDirectory
from pathlib import Path
from config import ConfigError, BotConfig
from data_records import digest
from fee_model import FeeRule,FeeSchedule,ScopeTotals,quote,COMPONENTS
from ledger import Record,Journal,reconstruct,SettlementRule,confirmed_settlement
from portfolio import Mark,value,update_nav,Clearance,nav_hash
from risk_manager import size,assess_quantity,Commitment
from accounting_adapter import AccountingDependencies,CostEvidence,project
import test_execution as execution_fixtures

T=datetime(2020,1,1,tzinfo=timezone.utc)
def schedule(at=T):
    rules=tuple(FeeRule(n,'BOTH','ORDER',D(0),D(0),D(0),None,D('.01'),'UP',(),'SYNTHETIC explicit zero') for n in COMPONENTS)
    return FeeSchedule('SYN-1',at-timedelta(days=1),at+timedelta(days=1000),at-timedelta(days=2),at-timedelta(days=1),at+timedelta(days=1000),'SYNTHETIC schedule approval',rules,'VERIFIED')
def rec(name,kind,amount,day=0,**kw):
    at=T+timedelta(days=day)
    return Record(name,'acct',kind,at,at,at,'SYNTHETIC source','SYNTHETIC evidence',D(amount),**kw)
def funded(n='10000'): return (rec('fund','DEPOSIT',n),)
def mark(price='110',day=0):
    at=T+timedelta(days=day)
    return Mark('S',D(price),at,at,at+timedelta(days=1),'SYN@1','SYNTHETIC mark validity')

class FeeTests(unittest.TestCase):
    def test_itemized_independent(self):
        s=schedule(); rr=list(s.rules)
        rr[0]=replace(rr[0],rate=D('.001'),minimum=D(2))
        rr[1]=replace(rr[1],side='SELL',rate=D('.001'))
        rr[5]=replace(rr[5],rate=D('.18'),base_components=('brokerage',))
        q=quote(replace(s,rules=tuple(rr)),'BUY',D(1001),T,T,scopes={'ORDER':D(1001)})
        self.assertEqual(dict(q.items)['brokerage'],2);self.assertEqual(dict(q.items)['gst'],D('.36'));self.assertEqual(q.total,D('2.36'))
    def test_minimum_cap_rounding(self):
        s=schedule();r=replace(s.rules[0],rate=D('.001'),minimum=D(1),maximum=D(2))
        s=replace(s,rules=(r,)+s.rules[1:])
        for n,want in [(1,'1'),(1001,'1.01'),(3000,'2')]:
            self.assertEqual(quote(s,'BUY',D(n),T,T,scopes={'ORDER':D(n)}).total,D(want))
    def test_unverified_future_expiry(self):
        s=schedule()
        for bad in (replace(s,status='UNVERIFIED'),replace(s,effective_end=T),replace(s,approval_until=T),replace(s,available_at=T+timedelta(hours=1),approved_at=T+timedelta(hours=2))):
            with self.assertRaises(ConfigError): quote(bad,'BUY',D(100),T,T,scopes={'ORDER':D(100)})
    def test_scope_deltas(self):
        s=schedule();s=replace(s,rules=(replace(s.rules[0],fixed=D(5),scope='INSTRUMENT_DAY'),)+s.rules[1:])
        q=quote(s,'SELL',D(100),T,T,scopes={k:ScopeTotals(k,D(0),D(100)) for k in ('ORDER','INSTRUMENT_DAY')})
        later=quote(s,'SELL',D(100),T,T,scopes={k:ScopeTotals(k,D(0),D(200)) for k in ('ORDER','INSTRUMENT_DAY')},previous=q)
        self.assertEqual(q.total,5);self.assertEqual(later.total,0)
    def test_missing_component_or_scope(self):
        with self.assertRaises(ConfigError): replace(schedule(),rules=schedule().rules[:-1])
        with self.assertRaises(ConfigError): quote(schedule(),'BUY',D(100),T,T)
    def test_ambient_context(self):
        s=schedule();s=replace(s,rules=(replace(s.rules[0],rate=D('.012345')),)+s.rules[1:])
        with localcontext() as c:
            c.prec=2
            self.assertEqual(quote(s,'BUY',D(12345),T,T,scopes={'ORDER':D(12345)}).total,D('152.40'))

class LedgerTests(unittest.TestCase):
    def cycle(self):
        return funded()+ (rec('r','RESERVE','221'),rec('b','BUY','220',instrument='S',quantity=2,parent='r',series='SYN@1'),
                          rec('fee','CHARGE','1'),rec('pay','PAY','1'),rec('s','SELL','240',1,instrument='S',quantity=2,series='SYN@1'))
    def test_conservation_valuation(self):
        b=reconstruct(self.cycle(),'acct',T+timedelta(days=1))
        self.assertFalse(b.anomalies);self.assertEqual(b.cash,9779);self.assertEqual(b.receivables,(('s',D(240)),))
        self.assertEqual(b.realized,19);self.assertEqual(value(b,(),T+timedelta(days=1)).equity,10019)
    def test_reservation_not_equity(self):
        b=reconstruct(funded()+ (rec('r','RESERVE','4000'),),'acct',T)
        self.assertEqual(b.buying_power,6000);self.assertEqual(value(b,(),T).equity,10000)
    def test_conflict_duplicate(self):
        rs=funded();b=reconstruct(rs+rs,'acct',T)
        self.assertEqual(b.cash,10000)
        b=reconstruct(rs+(replace(rs[0],amount=D(5000)),),'acct',T)
        self.assertEqual(b.cash,10000);self.assertTrue(b.anomalies)
    def test_no_short_or_double_sale(self):
        rs=self.cycle();b=reconstruct(rs+(replace(rs[-1],event_id='second'),),'acct',T+timedelta(days=1))
        self.assertEqual(b.receivables,(('s',D(240)),));self.assertTrue(b.anomalies)
    def test_reserve_competition(self):
        b=reconstruct(funded('5000')+(rec('r1','RESERVE','3000'),rec('r2','RESERVE','3000')),'acct',T)
        self.assertEqual(b.buying_power,2000);self.assertTrue(b.anomalies)
    def test_release_explicit(self):
        b=reconstruct(funded()+(rec('r','RESERVE','100'),rec('rel','RELEASE','100',parent='r')),'acct',T)
        self.assertEqual(b.buying_power,10000)
    def test_charge_actual_once(self):
        rs=funded()+(rec('estimate','CHARGE','5'),rec('actual','ACTUAL_CHARGE','7',parent='estimate'))
        b=reconstruct(rs+(replace(rs[-1],event_id='again'),),'acct',T)
        self.assertEqual(b.charges,7);self.assertEqual(b.payables,7);self.assertEqual(b.buying_power,9993);self.assertTrue(b.anomalies)
    def test_adjustment_link(self):
        b=reconstruct(funded()+(rec('fix','ADJUST','-10',parent='fund'),),'acct',T)
        self.assertEqual(b.cash,9990)
        self.assertEqual(b.realized,-10)
    def test_withdrawal_reject(self):
        b=reconstruct(funded('5000')+(rec('w','WITHDRAW','5001'),),'acct',T)
        self.assertEqual(b.cash,5000);self.assertTrue(b.anomalies)
    def test_restart_and_atomic_failure(self):
        with TemporaryDirectory() as d:
            p=Path(d)/'journal.sqlite';j=Journal(p,'acct');j.append(funded())
            with self.assertRaises(ConfigError): j.append((rec('x','DEPOSIT','1'),replace(rec('y','DEPOSIT','2'),account_id='other')))
            self.assertEqual(len(j.records()),1);j.close()
            j=Journal(p,'acct');j.append(funded());self.assertEqual(j.balance(T).cash,10000);j.close()
    def test_corruption_detected(self):
        with TemporaryDirectory() as d:
            j=Journal(Path(d)/'j','acct');j.append(funded());j.db.execute("UPDATE journal SET chain='broken'")
            with self.assertRaises(ConfigError): j.records()
            j.close()
    def test_prefix_invariance(self):
        rs=funded()+(rec('future','DEPOSIT','5000',1),)
        self.assertEqual(reconstruct(rs,'acct',T),reconstruct(rs[:1],'acct',T))
    def test_missing_stale_incompatible_marks(self):
        b=reconstruct(self.cycle()[:3],'acct',T)
        for marks in ((),(replace(mark(),series='OTHER'),),(mark(day=1),)):
            self.assertIsNone(value(b,marks,T).equity)
        self.assertIsNone(value(b,(mark(),),T+timedelta(days=1)).equity)
    def test_unrealized(self):
        b=reconstruct(self.cycle()[:3],'acct',T)
        v=value(b,(mark('120'),),T)
        self.assertEqual(v.unrealized,20);self.assertEqual(v.equity,10020)

class NavTests(unittest.TestCase):
    def valuation(self,equity,flow='10000',day=0):
        return replace(value(reconstruct(funded(),'acct',T),(),T),equity=D(equity),flows=D(flow),at=T+timedelta(days=day))
    def test_thresholds_and_recovery(self):
        n=update_nav(None,self.valuation('10000'))
        n=update_nav(n,self.valuation('9500',day=1));self.assertEqual(n.latch,1)
        n=update_nav(n,self.valuation('9200',day=2));self.assertEqual(n.latch,2)
        n=update_nav(n,self.valuation('10000',day=3));self.assertEqual(n.latch,2);self.assertEqual(n.peak,1)
        c=Clearance('acct',n.at,nav_hash(n),'review completed','SYNTHETIC approval')
        # Clearance is bound to the same newly computed recovered state.
        before=update_nav(None,self.valuation('10000'))
        before=update_nav(before,self.valuation('9200',day=2))
        recovered=update_nav(before,self.valuation('10000',day=3))
        c=replace(c,state_sha256=nav_hash(recovered))
        self.assertEqual(update_nav(before,self.valuation('10000',day=3),clearance=c).latch,0)
    def test_deposit_no_reset(self):
        n=update_nav(None,self.valuation('10000'))
        pre=self.valuation('9000',day=1)
        post=self.valuation('18000','19000',1)
        n=update_nav(n,post,pre_flow=pre)
        self.assertEqual(n.units,20000);self.assertEqual(n.drawdown,F(1,10));self.assertEqual(n.latch,2)
    def test_withdraw_units(self):
        n=update_nav(None,self.valuation('10000'))
        n=update_nav(n,self.valuation('5000','5000',1),pre_flow=self.valuation('10000',day=1))
        self.assertEqual(n.units,5000);self.assertEqual(n.nav,1)
    def test_missing_preflow_and_depleted(self):
        n=update_nav(None,self.valuation('10000'))
        for v in (self.valuation('11000','11000',1),self.valuation('0',day=1)):
            with self.assertRaises(ConfigError): update_nav(n,v)
    def test_premature_or_stale_clearance(self):
        n=update_nav(None,self.valuation('10000'));v=self.valuation('9200',day=1);x=update_nav(n,v)
        c=Clearance('acct',v.at,nav_hash(x),'review','evidence')
        with self.assertRaises(ConfigError): update_nav(n,v,clearance=c)
        with self.assertRaises(ConfigError): update_nav(n,self.valuation('10000',day=2),clearance=c)

class RiskTests(unittest.TestCase):
    def args(self,equity=D(10000)):
        return dict(instrument='S',low=D(100),high=D(100),stop=D(99),equity=equity,buying_power=equity,gross=D(0),held_instruments=(),positions=(),commitments=(),costs=lambda q:D(0),allowance=D(0),at=T)
    def test_whole_shares_caps(self):
        self.assertEqual(size(**self.args()).quantity,40)
        self.assertEqual(size(**self.args(D(5000))).quantity,20)
    def test_fixed_nonlinear_cost(self):
        a=self.args();a['costs']=lambda q:D(20 if q>=20 else 1)
        self.assertEqual(size(**a).quantity,30)
    def test_zero_affordable(self):
        a=self.args();a['buying_power']=D(99)
        self.assertEqual(size(**a).quantity,0)
    def test_exact_trade_risk(self):
        a=self.args();a['stop']=D(98)
        self.assertEqual(assess_quantity(25,**a).quantity,25)
        self.assertIn('trade risk',assess_quantity(26,**a).reasons)
    def test_pending_aggregate(self):
        a=self.args();a['commitments']=(Commitment('o','OTHER',D(100),D(90),D(100)),)
        self.assertEqual(size(**a).quantity,10)
    def test_slots_pyramiding(self):
        a=self.args();a['held_instruments']=('S',)
        self.assertIn('pyramiding',assess_quantity(1,**a).reasons)
        a['held_instruments']=('A','B');self.assertIn('position slots',assess_quantity(1,**a).reasons)

class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        execution_fixtures.ExecutionTests.setUpClass();cls.helper=execution_fixtures.ExecutionTests()
    def adapter(self):
        h=self.helper;at=h.funding.available_at
        s=schedule(at);c=CostEvidence(at,h.cap.valid_until,D(0),D(0),D(0),'SYNTHETIC explicit zero costs/allowance')
        m=Mark('STOCK',D(110),h.open,h.open,h.cap.valid_until,'SYN-INDEX@v1','SYNTHETIC mark')
        return AccountingDependencies(h.cfg,h.funding,'acct',s,(m,),c)
    def test_computed_dependency_entry_and_projection(self):
        h=self.helper;a=self.adapter();s=h.run_sim(adapter=a)
        self.assertEqual(s.positions[0].quantity,2);self.assertFalse(s.operational_authorized)
        records=project(s,h.funding,'acct');b=reconstruct(records,'acct',h.open)
        self.assertEqual(b.cash,s.settled_cash);self.assertFalse(b.anomalies)
        with TemporaryDirectory() as d:
            j=Journal(Path(d)/'j','acct');j.append(records);j.append(records)
            self.assertEqual(j.balance(h.open),b);j.close()
    def test_quarantined_fill_not_projected(self):
        h=self.helper;cs=h.chain()+h.protect()+(h.trigger(),)
        f=h.exit_fill(h.open+timedelta(minutes=15));receipt=h.open+timedelta(minutes=30)
        f=replace(f,recorded_at=receipt,event=replace(f.event,recorded_at=receipt,notified_at=receipt))
        s=h.run_sim(cs+(f,));b=reconstruct(project(s,h.funding,'acct'),'acct',receipt)
        self.assertEqual(b.holdings[0].quantity,2);self.assertEqual(b.receivables,())
    def test_exit_computed_adapter(self):
        h=self.helper;s=h.run_sim(h.chain()+h.protect()+(h.trigger(),h.exit_fill()),adapter=self.adapter())
        self.assertEqual(s.positions[0].quantity,0)
    def test_settlement_calendar(self):
        h=self.helper;a=self.adapter();s=h.run_sim(h.chain()+h.protect()+(h.trigger(),h.exit_fill()),adapter=a)
        rs=project(s,h.funding,'acct');sale=next(r for r in rs if r.kind=='SELL')
        rule=SettlementRule('SYN',h.funding.available_at,h.funding.available_at,h.cap.valid_until,digest(h.snapshot.calendar),'SYNTHETIC confirmation rule')
        at=h.exit_fill().event.occurred_at
        settlement=confirmed_settlement(sale,rule,h.snapshot.calendar,at,at,'SYNTHETIC confirmed cash receipt')
        b=reconstruct(rs+(settlement,),'acct',at)
        self.assertFalse(b.receivables);self.assertEqual(b.cash,9960)
        with self.assertRaises(ConfigError): confirmed_settlement(sale,replace(rule,calendar_sha256='bad'),h.snapshot.calendar,at,at,'evidence')
    def test_future_marks_do_not_change_prefix(self):
        h=self.helper;a=self.adapter();expected=h.run_sim(adapter=a)
        a.marks+=(replace(a.marks[0],at=h.open+timedelta(days=3),available_at=h.open+timedelta(days=3),price=D(1)),)
        self.assertEqual(expected,h.run_sim(adapter=a))

if __name__=='__main__': unittest.main()

class AdditionalBoundaries(unittest.TestCase):
    def test_journal_nav_restart_flow(self):
        from portfolio import journal_nav
        records=funded()+(rec('w','WITHDRAW','1000',1),rec('d','DEPOSIT','1000',2))
        expected=journal_nav(records,'acct',T+timedelta(days=2))
        self.assertEqual(expected.nav,1);self.assertEqual(expected.units,10000)
        with TemporaryDirectory() as d:
            path=Path(d)/'j';j=Journal(path,'acct');j.append(records);j.close()
            j=Journal(path,'acct');self.assertEqual(journal_nav(j.records(),'acct',T+timedelta(days=2)),expected);j.close()
    def test_dual_risk_and_unknown_protection(self):
        from config_contracts import PositionRiskContract,Evidence
        e=Evidence('synthetic','a'*64,T)
        p=PositionRiskContract('position',2,D(100),D(110),T,T+timedelta(days=1),e,D(90),2,'EXCHANGE_ACTIVE','activation',D(1),e,True,D(1),'b'*64,'CONFIRMED',D(22),D(42),D(42))
        a=RiskTests().args();a['positions']=(p,);a['held_instruments']=('OTHER',);a['gross']=D(220)
        self.assertEqual(assess_quantity(1,**a).quantity,1)
        for bad in (replace(p,protection_state='UNKNOWN'),replace(p,protective_quantity=1),replace(p,mark_valid_until=T+timedelta(seconds=1))):
            a['positions']=(bad,);a['at']=T+timedelta(seconds=2)
            self.assertEqual(assess_quantity(1,**a).quantity,0)
        below=replace(p,current_mark=D(90),r_mark=D(2),r_position=D(22))
        a['positions']=(below,);a['at']=T
        self.assertEqual(assess_quantity(1,**a).quantity,0)
    def test_gross_boundary(self):
        a=RiskTests().args();a['commitments']=(Commitment('pending','OTHER',D(7900),D(0),D(7900)),)
        self.assertEqual(assess_quantity(1,**a).quantity,1)
        self.assertIn('gross exposure',assess_quantity(2,**a).reasons)
    def test_negative_unknown_cost(self):
        a=RiskTests().args();a['costs']=lambda q:None
        with self.assertRaises(ConfigError): assess_quantity(1,**a)
    def test_actual_origin_rejected(self):
        with self.assertRaises(ConfigError): replace(funded()[0],origin='ACTUAL')
    def test_late_journal_fact_quarantined(self):
        late=replace(rec('late','WITHDRAW','100'),recorded_at=T+timedelta(days=2),notified_at=T+timedelta(days=2))
        b=reconstruct(funded()+(rec('d','DEPOSIT','1',1),late),'acct',T+timedelta(days=2))
        self.assertEqual(b.cash,10001);self.assertTrue(b.anomalies)
    def test_conflicting_mark_blocks(self):
        rs=funded()+(rec('r','RESERVE','100'),rec('buy','BUY','100',instrument='S',quantity=1,parent='r',series='SYN@1'))
        self.assertIsNone(value(reconstruct(rs,'acct',T),(mark(),mark('120')),T).equity)
    def test_holiday_settlement_rejected(self):
        from test_regime_detector import fixture,stamp
        from datetime import date
        snapshot,_,_=fixture(20);at=stamp(date(2020,1,6))
        sale=replace(rec('sale','SELL','100'),occurred_at=snapshot.calendar.available_at,notified_at=snapshot.calendar.available_at,recorded_at=snapshot.calendar.available_at)
        rule=SettlementRule('SYN',snapshot.calendar.available_at,snapshot.calendar.available_at,stamp(snapshot.calendar.end),digest(snapshot.calendar),'synthetic')
        with self.assertRaises(ConfigError): confirmed_settlement(sale,rule,snapshot.calendar,at,at,'confirmation')

class DurableClearanceTests(unittest.TestCase):
    def test_bound_journal_clearance(self):
        from portfolio import journal_nav
        rs=funded()+(rec('loss','ADJUST','-800',1,parent='fund'),rec('recover','ADJUST','800',2,parent='loss'))
        at=T+timedelta(days=3)
        old=journal_nav(rs,'acct',at)
        self.assertEqual(old.latch,2)
        candidate=update_nav(old,value(reconstruct(rs,'acct',at),(),at))
        clearance=rec('clear','CLEARANCE','0',3,parent=nav_hash(candidate))
        cleared=journal_nav(rs+(clearance,),'acct',at)
        self.assertEqual(cleared.latch,0);self.assertEqual(cleared.peak,1)
        with self.assertRaises(ConfigError): journal_nav(rs+(replace(clearance,parent='wrong'),),'acct',at)

class FeeCorrectionTests(unittest.TestCase):
    def ledger_case(self,paid,actual):
        rs=(rec('fund','DEPOSIT','100'),rec('estimate','CHARGE','10'))
        if paid: rs+=(rec('payment','PAY',str(paid),parent='estimate'),)
        return rs+(rec('unrelated','CHARGE','20'),rec('actual','ACTUAL_CHARGE',str(actual),parent='estimate'))
    def test_charge_attribution_matrix(self):
        for paid in (0,4,10):
            for actual in (2,5,10,15):
                with self.subTest(paid=paid,actual=actual):
                    b=reconstruct(self.ledger_case(paid,actual),'acct',T)
                    refund=max(paid-actual,0);due=20+max(actual-paid,0)
                    self.assertFalse(b.anomalies)
                    self.assertEqual(b.cash,100-paid);self.assertEqual(b.payables,due)
                    self.assertEqual(sum(v for _,v in b.receivables),refund)
                    self.assertEqual(b.buying_power,100-paid-due)
                    self.assertEqual(b.realized,-20-actual)
                    self.assertEqual(value(b,(),T).equity,80-actual)
    def test_original_reproduction_and_explicit_refund(self):
        rs=self.ledger_case(10,5);b=reconstruct(rs,'acct',T)
        self.assertEqual((b.cash,b.payables,b.buying_power),(90,20,70))
        self.assertEqual(b.receivables,(('actual',D(5)),));self.assertEqual(value(b,(),T).equity,75)
        receipt=rec('refund','REFUND','5',parent='actual')
        b=reconstruct(rs+(receipt,receipt),'acct',T)
        self.assertEqual((b.cash,b.payables,b.buying_power,b.realized),(95,20,75,-25))
        self.assertEqual(b.receivables,());self.assertEqual(value(b,(),T).equity,75)
    def test_refund_cannot_double_or_use_adjust(self):
        rs=self.ledger_case(10,5)
        for extra in (rec('bad','ADJUST','5',parent='estimate'),rec('bad','REFUND','6',parent='actual'),
                      replace(rec('bad','SETTLE','5',parent='actual'),source='settlement:fake')):
            b=reconstruct(rs+(extra,),'acct',T)
            self.assertTrue(b.anomalies);self.assertEqual(b.cash,90);self.assertEqual(b.payables,20)
        r=rec('refund','REFUND','5',parent='actual')
        b=reconstruct(rs+(r,replace(r,event_id='second')),'acct',T)
        self.assertTrue(b.anomalies);self.assertEqual(b.cash,95)
    def test_ambiguous_pay_retained_without_effect(self):
        rs=(rec('f','DEPOSIT','100'),rec('a','CHARGE','10'),rec('b','CHARGE','20'),rec('p','PAY','10'))
        b=reconstruct(rs,'acct',T);self.assertTrue(b.anomalies)
        self.assertEqual((b.cash,b.payables),(100,30))
    def test_actual_above_paid_then_attributed_pay(self):
        rs=self.ledger_case(10,15)+(rec('pay2','PAY','5',parent='estimate'),)
        b=reconstruct(rs,'acct',T);self.assertFalse(b.anomalies)
        self.assertEqual((b.cash,b.payables,b.realized),(85,20,-35))
    def test_conflicting_correction_and_restart(self):
        rs=self.ledger_case(10,5)
        conflict=replace(rs[-1],amount=D(3))
        duplicate_correction=replace(rs[-1],event_id='another')
        with TemporaryDirectory() as d:
            path=Path(d)/'j';j=Journal(path,'acct');j.append(rs);j.close()
            j=Journal(path,'acct');j.append((rs[-1],conflict,duplicate_correction))
            b=j.balance(T);self.assertEqual(b.payables,20);self.assertEqual(b.cash,90)
            self.assertEqual(len(b.anomalies),2);self.assertEqual(b.receivables,(('actual',D(5)),))
            j.append((rec('refund','REFUND','5',parent='actual'),));expected=j.balance(T);j.close()
            j=Journal(path,'acct');self.assertEqual(j.balance(T),expected);self.assertEqual(expected.cash,95);j.close()
    def scoped(self,side='BUY',rate='0',fixed='5',gst=False):
        s=schedule();rr=[replace(r,scope='INSTRUMENT_DAY') for r in s.rules]
        rr[0]=replace(rr[0],side=side,rate=D(rate),fixed=D(fixed))
        if gst: rr[5]=replace(rr[5],rate=D('.18'),base_components=('brokerage',))
        return replace(s,rules=tuple(rr))
    def q(self,s,buy,sell,side='BUY',previous=None,scope_id='S:2020-01-01',correction=None):
        return quote(s,side,D(100),T,T,scopes={'INSTRUMENT_DAY':ScopeTotals(scope_id,D(buy),D(sell))},
                     previous=previous,correction_evidence=correction)
    def test_opposite_side_does_not_refund(self):
        for side in ('BUY','SELL'):
            s=self.scoped(side)
            first=self.q(s,100 if side=='BUY' else 0,100 if side=='SELL' else 0,side)
            second=self.q(s,100,100,'SELL' if side=='BUY' else 'BUY',first)
            self.assertEqual(first.total,5);self.assertEqual(second.total,0)
            self.assertEqual(dict(second.accrued)['brokerage'],5)
    def test_rates_gst_and_same_side_rounding(self):
        s=self.scoped(rate='.001',fixed='0',gst=True)
        first=self.q(s,1001,0)
        self.assertEqual(dict(first.items)['brokerage'],D('1.01'))
        self.assertEqual(dict(first.items)['gst'],D('.19'))
        opposite=self.q(s,1001,1000,'SELL',first);self.assertEqual(opposite.total,0)
        repeated=self.q(s,2001,1000,'BUY',opposite)
        self.assertEqual(dict(repeated.items)['brokerage'],D('1.00'))
        self.assertEqual(dict(repeated.items)['gst'],D('.18'))
        self.assertEqual(self.q(s,2001,1000,'BUY',repeated).total,0)
    def test_explicit_negative_correction_not_clamped(self):
        s=self.scoped(rate='.01',fixed='0',gst=True);first=self.q(s,1000,0)
        with self.assertRaises(ConfigError):self.q(s,500,0,previous=first)
        corrected=self.q(s,500,0,previous=first,correction='SYNTHETIC corrected turnover evidence')
        self.assertEqual(corrected.total,D('-5.90'))
        self.assertEqual(self.q(s,500,100,'SELL',corrected).total,0)
    def test_scope_profile_and_legacy_isolation(self):
        s=self.scoped();first=self.q(s,100,0)
        with self.assertRaises(ConfigError):self.q(s,200,0,previous=first,scope_id='OTHER')
        with self.assertRaises(ConfigError):self.q(replace(s,version='new'),200,0,previous=first)
        with self.assertRaises(ConfigError):quote(s,'SELL',D(100),T,T,scopes={'INSTRUMENT_DAY':D(200)},charged=first.items)
        with self.assertRaises(ConfigError):self.q(s,100,100,'BUY',first)
    def test_ambiguous_dependent_base_rejected(self):
        s=self.scoped();rr=list(s.rules);rr[5]=replace(rr[5],side='SELL',base_components=('brokerage',))
        with self.assertRaises(ConfigError):replace(s,rules=tuple(rr))
    def test_cross_order_adapter_guard_preserved(self):
        h=IntegrationTests.helper if hasattr(IntegrationTests,'helper') else None
        if h is None:
            IntegrationTests.setUpClass();h=IntegrationTests.helper
        a=IntegrationTests().adapter();a.schedule=self.scoped()
        # Use a profile applicable to the execution fixture rather than the Jan fixture.
        a.schedule=replace(a.schedule,effective_start=a.costs.available_at,available_at=a.costs.available_at,
                           approved_at=a.costs.available_at,effective_end=a.costs.valid_until,approval_until=a.costs.valid_until)
        s=h.run_sim(adapter=a)
        self.assertFalse(s.positions)
        self.assertTrue(any('cross-order fee scope' in reason for item in s.audit for reason in item.reasons))

class FurtherCorrectionBoundaries(unittest.TestCase):
    def test_partial_refund_receipt_and_unpaid_reduction(self):
        h=FeeCorrectionTests()
        rs=h.ledger_case(4,2)+(rec('refund','REFUND','2',parent='actual'),)
        b=reconstruct(rs,'acct',T)
        self.assertEqual((b.cash,b.payables,b.buying_power,b.realized),(98,20,78,-22))
        self.assertEqual(value(b,(),T).equity,78)
        rs=h.ledger_case(4,5)+(rec('balance','PAY','1',parent='estimate'),)
        b=reconstruct(rs,'acct',T)
        self.assertEqual((b.cash,b.payables,b.realized),(95,20,-25));self.assertFalse(b.anomalies)
    def test_both_sides_with_dependent_tax(self):
        h=FeeCorrectionTests();s=h.scoped(rate='.01',fixed='0',gst=True)
        rr=list(s.rules);rr[1]=replace(rr[1],side='SELL',rate=D('.02'))
        rr[5]=replace(rr[5],base_components=('brokerage','stt'))
        s=replace(s,rules=tuple(rr))
        first=h.q(s,0,100,'SELL');self.assertEqual(first.total,D('2.36'))
        second=h.q(s,100,100,'BUY',first);self.assertEqual(second.total,D('1.18'))
        self.assertEqual(dict(second.accrued)['stt'],2)
        self.assertEqual(dict(second.accrued)['gst'],D('.54'))
        other=h.q(s,100,0,'BUY',scope_id='OTHER:DAY')
        self.assertEqual(other.total,D('1.18'))
    def test_forged_previous_accrual_rejected(self):
        h=FeeCorrectionTests();s=h.scoped();first=h.q(s,100,0)
        forged=replace(first,accrued=tuple((n,D(99) if n=='brokerage' else v) for n,v in first.accrued))
        with self.assertRaises(ConfigError):h.q(s,200,0,previous=forged)

class PurchaseConservationTests(unittest.TestCase):
    def scenario(self,amount='60',fee='30',zero=False):
        if zero:
            return (rec('fund','DEPOSIT','100'),rec('own','RESERVE','0'),
                    rec('buy','BUY','0',instrument='S',quantity=1,parent='own',series='SYN@1'))
        return (rec('fund','DEPOSIT','100'),rec('own','RESERVE','60'),rec('other','RESERVE','40'),
                rec('fee','CHARGE',fee),rec('buy','BUY',amount,instrument='S',quantity=1,parent='own',series='SYN@1'))
    def check_rejection(self,rs):
        before=reconstruct(rs[:-1],'acct',T);after=reconstruct(rs,'acct',T)
        for name in ('cash','payables','reservations','holdings','receivables','realized','flows','buying_power'):
            self.assertEqual(getattr(after,name),getattr(before,name),name)
        self.assertTrue(after.anomalies)
        self.assertIsNone(value(after,(mark('100'),),T).equity)
        return after
    def test_zero_purchase_has_no_effects(self):
        rs=self.scenario(zero=True);b=self.check_rejection(rs)
        self.assertEqual(b.cash,100);self.assertEqual(b.holdings,())
        self.assertIn('zero-consideration',b.anomalies[0])
    def test_underfunded_purchase_preserves_charge_and_reservations(self):
        b=self.check_rejection(self.scenario())
        self.assertEqual((b.cash,b.payables,b.buying_power),(100,30,-30))
        self.assertEqual(dict(b.reservations),{'own':60,'other':40})
    def test_exact_cash_boundary_and_just_over(self):
        rs=self.scenario(amount='30');b=reconstruct(rs,'acct',T)
        self.assertFalse(b.anomalies);self.assertEqual((b.cash,b.payables,b.buying_power),(70,30,0))
        self.assertEqual(b.reservations,(('other',D(40)),));self.assertEqual(b.holdings[0].basis,30)
        self.assertEqual(value(b,(mark('30'),),T).equity,70)
        self.check_rejection(self.scenario(amount='30.0000000000000000000000000001'))
    def test_own_reservation_not_double_counted(self):
        b=reconstruct(self.scenario(fee='0'),'acct',T)
        self.assertFalse(b.anomalies);self.assertEqual((b.cash,b.buying_power),(40,0))
        self.assertEqual(value(b,(mark('60'),),T).equity,100)
        rs=(rec('f','DEPOSIT','1'),rec('r','RESERVE','1'),rec('b','BUY','0.01',instrument='S',quantity=1,parent='r',series='SYN@1'))
        b=reconstruct(rs,'acct',T);self.assertFalse(b.anomalies);self.assertEqual(b.cash,D('.99'))
    def test_invalid_purchase_duplicates_conflicts_and_restart(self):
        for rs in (self.scenario(),self.scenario(zero=True)):
            with self.subTest(zero=rs[-1].amount==0),TemporaryDirectory() as d:
                path=Path(d)/'j';j=Journal(path,'acct');j.append(rs);j.append((rs[-1],))
                expected=j.balance(T);self.assertEqual(j.records(),rs);j.close()
                j=Journal(path,'acct');self.assertEqual(j.balance(T),expected)
                conflict=replace(rs[-1],amount=D(1));j.append((conflict,))
                b=j.balance(T);self.assertEqual(b.cash,100);self.assertFalse(b.holdings)
                self.assertEqual(len(b.anomalies),2);self.assertEqual(j.records()[-1],conflict);j.close()
                j=Journal(path,'acct');self.assertEqual(j.balance(T),b);j.close()
    def test_valid_purchase_duplicate_and_conflicting_receipt(self):
        rs=self.scenario(amount='30');b=reconstruct(rs,'acct',T)
        dup=reconstruct(rs+(rs[-1],),'acct',T)
        self.assertEqual((dup.cash,dup.holdings,dup.reservations),(b.cash,b.holdings,b.reservations))
        conflict=replace(rs[-1],amount=D(20))
        bad=reconstruct(rs+(conflict,),'acct',T)
        self.assertEqual((bad.cash,bad.holdings,bad.payables),(b.cash,b.holdings,b.payables))
        self.assertTrue(bad.anomalies)
