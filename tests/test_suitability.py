"""Prompt 8 offline synthetic report and review regressions."""
import unittest
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D
from pathlib import Path
from tempfile import TemporaryDirectory
from config import ConfigError, canonical_json, Candidate
from data_records import Universe, digest
from execution_records import Account
from accounting_adapter import AccountingDependencies, CostEvidence
from suitability import Request, evaluate, weekly_report, revalidation_issues
from human_review import ReviewFact, ReviewJournal
import test_execution as ef
import test_accounting_risk as af
import test_strategy as sf

class SuitabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ef.ExecutionTests.setUpClass(); cls.f=ef.ExecutionTests()
        cal = cls.f.snapshot.calendar
        members = Universe('synthetic-members', cal.start, cal.end, cal.available_at,
                           ('AAA', 'STOCK'), 'synthetic dated fixture')
        cls.f.snapshot = replace(cls.f.snapshot, universes=(members,))
        cls.at=cls.f.open
        cls.account=Account(D(10000))
        cls.adapter=AccountingDependencies(cls.f.cfg,cls.f.funding,'acct',af.schedule(cls.at),(),
            CostEvidence(cls.f.cap.available_at,cls.f.cap.valid_until,D(0),D(0),D(0),'SYNTHETIC explicit zero'))
        cls.request=Request(cls.f.current,sf.StrategyTests.regimes[2],cls.f.point(),cls.at+timedelta(hours=1))
    def row(self,request=None,account=None,adapter=None,snapshot=None):
        return evaluate(snapshot or self.f.snapshot,self.f.cfg,account or self.account,adapter or self.adapter,
                        self.f.cap,request or self.request,self.at)
    def report(self,requests=None):
        return weekly_report(self.f.snapshot,self.f.cfg,self.account,self.adapter,self.f.cap,
                             (self.request,) if requests is None else requests,self.at)
    def test_eligible_independent_values(self):
        r=self.row();self.assertEqual(r.status,'BUY-CANDIDATE',r.reasons)
        self.assertGreater(r.quantity,0);self.assertEqual(r.cash_use,r.quantity*D(110))
        self.assertLessEqual(r.planned_risk,D(50));self.assertEqual(r.aggregate_risk,r.planned_risk)
        self.assertEqual(r.median_turnover,D(1000));self.assertEqual(len(r.fees),7)
        self.assertFalse(r.operational_authorized);self.assertIsNone(r.target)
    def test_empty(self): self.assertEqual(self.report(()).message,'NO TRADE')
    def test_deterministic(self): self.assertEqual(self.report(),self.report())
    def test_future_row(self):
        future=replace(self.request,signal=replace(self.request.signal,as_of=self.at+timedelta(days=2)))
        self.assertEqual(self.report(),self.report((future,self.request)))
    def test_conflicting_rows(self):
        with self.assertRaises(ConfigError): self.report((self.request,self.request))
    def test_gap(self):
        r=self.row(replace(self.request,price=replace(self.request.price,price=D(111))))
        self.assertEqual(r.quantity,0);self.assertTrue(r.reasons)
    def test_missing_costs(self):
        a=AccountingDependencies(self.f.cfg,self.f.funding,'acct',replace(self.adapter.schedule,status='UNVERIFIED'),(),self.adapter.costs)
        self.assertEqual(self.row(adapter=a).quantity,0)
    def test_no_cash(self): self.assertEqual(self.row(account=Account(D(0))).quantity,0)
    def test_entry_suspension(self):
        a=replace(self.account,entry_blocks=('reconcile',));self.assertEqual(self.row(account=a).quantity,0)
        self.assertEqual(a.positions,()) # report never calls exit engine or mutates state
    def test_rejected_data(self):
        s=replace(self.request.signal,data_status='REJECTED',reasons=('missing',))
        self.assertEqual(self.row(replace(self.request,signal=s)).quantity,0)
    def test_revised_data(self):
        b=self.f.snapshot.bars[0];s=replace(self.f.snapshot,bars=(replace(b,provider='OTHER'),)+self.f.snapshot.bars[1:])
        self.assertEqual(self.row(snapshot=s).quantity,0)
    def test_b_missing_month(self):
        s=replace(self.request.signal,candidate=Candidate.B,monthly=None)
        self.assertEqual(self.row(replace(self.request,signal=s)).quantity,0)
    def test_revalidation(self):
        r=self.row();self.assertFalse(revalidation_issues(r,r))
        self.assertTrue(revalidation_issues(r,replace(r,account_sha256='changed')))
        self.assertTrue(revalidation_issues(r,replace(r,at=r.expires_at)))
    def test_future_bar_invariance(self):
        b=self.f.snapshot.bars[-1]
        s=replace(self.f.snapshot,bars=self.f.snapshot.bars+(replace(b,revision=1,available_at=b.available_at+timedelta(days=2)),))
        self.assertEqual(self.row(),self.row(snapshot=s))
    def test_price_source(self):
        self.assertEqual(self.row(replace(self.request,price=replace(self.request.price,provider='OTHER'))).quantity,0)
    def fact(self,row,state,i=0,**kw):
        at=self.at+timedelta(seconds=i)
        return replace(ReviewFact(str(i),row.proposal_id,canonical_json(row),state,at,at,at,'operator','SYNTHETIC evidence'),**kw)
    def test_review_restart_and_duplicates(self):
        r=self.row()
        with TemporaryDirectory() as d:
            path=Path(d)/'review.sqlite';j=ReviewJournal(path)
            for i,s in enumerate(('PROPOSED','REVIEWED','APPROVED')):
                f=self.fact(r,s,i);j.append(f);j.append(f)
            state=j.state(r,self.at+timedelta(minutes=1));self.assertEqual(state.state,'APPROVED');self.assertFalse(state.issues)
            self.assertEqual(len(j.facts()),3);j.close();j=ReviewJournal(path)
            self.assertEqual(j.state(r,self.at+timedelta(minutes=1)),state);j.close()
    def test_conflicting_approval_retained(self):
        r=self.row();j=ReviewJournal(':memory:')
        for i,s in enumerate(('PROPOSED','REVIEWED','APPROVED')):j.append(self.fact(r,s,i))
        j.append(self.fact(r,'APPROVED',2,actor='other'))
        self.assertTrue(j.state(r,self.at+timedelta(minutes=1)).issues)
        self.assertNotEqual(j.state(r,self.at+timedelta(minutes=1)).state,'APPROVED');self.assertEqual(len(j.facts()),4);j.close()
    def test_late_receipt_and_expiry(self):
        r=self.row();j=ReviewJournal(':memory:')
        for i,s in enumerate(('PROPOSED','REVIEWED')):j.append(self.fact(r,s,i))
        j.append(self.fact(r,'APPROVED',2,recorded_at=r.expires_at,notified_at=r.expires_at))
        self.assertEqual(j.state(r,self.at+timedelta(minutes=1)).state,'REVIEWED')
        self.assertEqual(j.state(r,r.expires_at).state,'EXPIRED');self.assertTrue(j.state(r,r.expires_at).issues);j.close()
    def test_rejection_terminal(self):
        r=self.row();j=ReviewJournal(':memory:')
        for i,s in enumerate(('PROPOSED','REJECTED','APPROVED')):j.append(self.fact(r,s,i))
        st=j.state(r,self.at+timedelta(minutes=1));self.assertEqual(st.state,'REJECTED');self.assertTrue(st.issues);j.close()
    def test_out_of_order(self):
        r=self.row();j=ReviewJournal(':memory:');j.append(self.fact(r,'REVIEWED'));j.append(self.fact(r,'PROPOSED',1))
        self.assertTrue(j.state(r,self.at+timedelta(minutes=1)).issues);j.close()
    def test_rank_tie_and_input_order(self):
        helper=sf.StrategyTests()
        stock=replace(helper.stock,bars=tuple(replace(b,instrument_id='AAA') for b in helper.stock.bars),
                      identities=tuple(replace(i,instrument_id='AAA') for i in helper.stock.identities))
        from strategy import EMACrossoverStrategy
        signals=EMACrossoverStrategy().replay(stock,self.f.cfg,'AAA',stock.calendar.start,helper.decisions,
            benchmark_snapshot=helper.bench,benchmark=helper.binding,benchmark_start=helper.bench.calendar.start,
            regimes=helper.regimes,tick=replace(helper.tick,instrument_id='AAA'))
        req=replace(self.request,signal=signals[2],price=replace(self.request.price,instrument_id='AAA'))
        combined=replace(self.f.snapshot,bars=self.f.snapshot.bars+stock.bars,identities=self.f.snapshot.identities+stock.identities)
        def run(rs):return weekly_report(combined,self.f.cfg,self.account,self.adapter,self.f.cap,rs,self.at)
        a=run((self.request,req));self.assertEqual(a,run((req,self.request)))
        self.assertEqual([r.request.signal.instrument_id for r in a.ranked],['AAA','STOCK'])
    def test_candidate_b_completed_month(self):
        helper=sf.StrategyTests();cfg=replace(self.f.cfg,strategy=replace(self.f.cfg.strategy,candidate=Candidate.B))
        from regime_detector import replay
        regimes=replay(helper.bench,cfg,helper.binding,helper.bench.calendar.start,helper.decisions)
        signal=helper.run_strategy(cfg=cfg,regimes=regimes)[2]
        adapter=AccountingDependencies(cfg,self.f.funding,'acct',self.adapter.schedule,(),self.adapter.costs)
        req=replace(self.request,signal=signal,regime=regimes[2])
        good=evaluate(self.f.snapshot,cfg,self.account,adapter,self.f.cap,req,self.at)
        self.assertEqual(good.status,'BUY-CANDIDATE',good.reasons)
        bad=replace(req,signal=replace(signal,monthly=None))
        self.assertEqual(evaluate(self.f.snapshot,cfg,self.account,adapter,self.f.cap,bad,self.at).quantity,0)
    def test_fee_cost_reduces_size(self):
        schedule=replace(self.adapter.schedule,rules=(replace(self.adapter.schedule.rules[0],fixed=D(10)),)+self.adapter.schedule.rules[1:])
        adapter=AccountingDependencies(self.f.cfg,self.f.funding,'acct',schedule,(),self.adapter.costs)
        r=self.row(adapter=adapter);self.assertLess(r.quantity,self.row().quantity)
        self.assertEqual(r.cash_use,r.quantity*D(110)+10)
    def test_existing_pending_commitment(self):
        # A real Prompt 6 pending reservation is visible through the computed adapter.
        state=self.f.run_sim(self.f.chain(fill=False),adapter=self.adapter,as_of=self.at)
        self.assertTrue(state.orders)
        r=self.row(account=state);self.assertEqual(r.quantity,0) # no pyramiding into pending STOCK
    def test_incomplete_week_not_promoted(self):
        s=self.request.signal;o=s.opportunity
        req=replace(self.request,signal=replace(s,opportunity=replace(o,week_start=o.week_start+timedelta(days=7),week_end=o.week_end+timedelta(days=7))))
        self.assertEqual(self.row(req).quantity,0)
    def test_stale_signal_and_price(self):
        req=replace(self.request,price=replace(self.request.price,at=self.at-timedelta(days=1)))
        self.assertEqual(self.row(req).quantity,0)
        req=replace(self.request,signal=replace(self.request.signal,session=self.request.signal.session-timedelta(days=1)))
        self.assertEqual(self.row(req).quantity,0)
    def test_late_valid_receipt(self):
        r=self.row();j=ReviewJournal(':memory:')
        for i,s in enumerate(('PROPOSED','REVIEWED','APPROVED')):
            j.append(self.fact(r,s,i,notified_at=self.at+timedelta(seconds=i+10),recorded_at=self.at+timedelta(seconds=i+10)))
        self.assertEqual(j.state(r,self.at+timedelta(seconds=11)).state,'REVIEWED')
        self.assertEqual(j.state(r,self.at+timedelta(seconds=12)).state,'APPROVED');j.close()
    def test_submission_never_authorized(self):
        from human_review import submission_issues
        r=self.row();j=ReviewJournal(':memory:')
        for i,s in enumerate(('PROPOSED','REJECTED')):j.append(self.fact(r,s,i))
        self.assertTrue(submission_issues(j,r,r,self.at+timedelta(seconds=2)));j.close()
    def test_renderer_and_unchanged_config(self):
        from suitability import render_report
        from config import BotConfig, load_manifest, readiness_issues
        self.assertIn('SYNTHETIC',render_report(self.report()))
        self.assertEqual(self.f.cfg,BotConfig())
        self.assertFalse(self.report().operational_authorized)
    def test_backdated_receipt_preserves_prefix(self):
        r=self.row();j=ReviewJournal(':memory:');j.append(self.fact(r,'PROPOSED'))
        before=j.state(r,self.at)
        j.append(self.fact(r,'REVIEWED',10));j.append(self.fact(r,'APPROVED',1))
        self.assertEqual(j.state(r,self.at),before)
        self.assertTrue(j.state(r,self.at+timedelta(seconds=11)).issues);j.close()
    def test_missing_cost_object(self):
        adapter=AccountingDependencies(self.f.cfg,self.f.funding,'acct',self.adapter.schedule,(),None)
        self.assertEqual(self.row(adapter=adapter).quantity,0)
    def test_incomplete_month_rejected(self):
        # Candidate B evidence cannot be relabelled as a later incomplete calendar month.
        helper=sf.StrategyTests();cfg=replace(self.f.cfg,strategy=replace(self.f.cfg.strategy,candidate=Candidate.B))
        from regime_detector import replay
        regimes=replay(helper.bench,cfg,helper.binding,helper.bench.calendar.start,helper.decisions)
        s=helper.run_strategy(cfg=cfg,regimes=regimes)[2]
        s=replace(s,monthly=replace(s.monthly,month_end=s.monthly.month_end+timedelta(days=30)))
        adapter=AccountingDependencies(cfg,self.f.funding,'acct',self.adapter.schedule,(),self.adapter.costs)
        r=evaluate(self.f.snapshot,cfg,self.account,adapter,self.f.cap,replace(self.request,signal=s,regime=regimes[2]),self.at)
        self.assertEqual(r.quantity,0)
    def test_exits_continue_during_suspension(self):
        state=self.f.run_sim(self.f.chain()+self.f.protect()+
            (self.f.trigger(),self.f.exit_fill()),adapter=ef.FixtureDependencies())
        self.assertEqual(state.positions[0].quantity,0)
        # Reporting a blocked entry never changes the original immutable execution account.
        blocked=replace(state,entry_blocks=('suspended',))
        self.assertEqual(self.row(account=blocked).quantity,0)
        self.assertEqual(blocked.positions[0].quantity,0)

    def test_dated_membership_controls_row_and_rank(self):
        snap = self.f.snapshot
        member, = snap.universes
        future = replace(member, members=('OTHER',), available_at=self.at+timedelta(microseconds=1))
        for records, eligible in (((member,), True), ((member, future), True),
                                  ((replace(member, members=('OTHER',)),), False),
                                  ((future,), False), ((), False)):
            with self.subTest(records=records):
                snapshot = replace(snap, universes=records)
                row = self.row(snapshot=snapshot)
                report = weekly_report(snapshot, self.f.cfg, self.account, self.adapter, self.f.cap,
                                       (self.request,), self.at)
                self.assertEqual(row.status == 'BUY-CANDIDATE', eligible)
                self.assertEqual(report.ranked, (row,) if eligible else ())
                if not eligible:
                    self.assertEqual(row.quantity, 0)
                    self.assertIn('universe', str(row.reasons))
