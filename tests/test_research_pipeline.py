"""Synthetic integration and independent journal/boundary expectations."""
import unittest
import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock
from config import ConfigError, ResearchManifest, Candidate, content_hash, from_dict
from data_records import digest, encoded
from research_records import RunSpec, InputBundle, EvidenceItem, AttemptEvent, ResearchReport
from research_pipeline import execute
from research_journal import ResearchJournal
import test_suitability as sf

BASE='85c5df8f0f975bbf888357cd2663c4dc5b60880e'

class ResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sf.SuitabilityTests.setUpClass();f=sf.SuitabilityTests();cls.f=f;cls.at=f.at
        report=f.report(); e=EvidenceItem('report','FEATURE',cls.at,cls.at,cls.at,'suitability',digest(report),'CONFIRMED')
        cls.bundle=InputBundle('SYNTHETIC:p9',f.f.cfg,ResearchManifest(),f.f.snapshot,report,f.account,(e,),
                              digest(f.adapter.schedule),digest(f.f.cap),None)
    def setUp(self):
        self.tmp=TemporaryDirectory();self.path=Path(self.tmp.name)/'research-run';self.j=ResearchJournal.create(self.path)
    def tearDown(self):self.j.close();self.tmp.cleanup()
    def spec(self,b=None,**changes):
        b=b or self.bundle
        s=RunSpec(b.fixture_id,'SYNTHETIC','ENGINEERING',b.config.strategy.candidate,
                  self.at.date(),self.at.date()+timedelta(days=1),b.snapshot.calendar.start,b.snapshot.calendar.end,
                  self.at,self.at,BASE,digest(tuple((p,__import__('hashlib').sha256(Path(p).read_bytes()).hexdigest()) for p in ('research_records.py','research_pipeline.py','research_journal.py','tests/test_research_pipeline.py'))),content_hash(b.config),content_hash(b.manifest),digest(b),('report',))
        return replace(s,**changes)
    def run_attempt(self,b=None,**spec):
        b=b or self.bundle
        return execute(self.spec(b,**spec),self.j,'attempt',self.at+timedelta(days=2),lambda:b)
    def result(self,a):return from_dict(ResearchReport,json.loads(a.events[-1].output_json))
    def test_complete_genuine_integration(self):
        a=self.run_attempt();self.assertEqual(a.status,'PASS',a.reasons)
        r=self.result(a);self.assertEqual(r.status,'PASS');self.assertFalse(r.operational_authorized)
        self.assertEqual([s.name for s in r.stages[:4]],['validate_inputs','assemble_evidence','validate_consistency','render_report'])
        self.assertEqual(r.suitability_sha256,digest(self.bundle.suitability))
    def test_optional_deferred_honest(self):
        r=self.result(self.run_attempt());self.assertEqual(r.stages[-2].status,'NOT_IMPLEMENTED');self.assertEqual(r.stages[-1].status,'DEFERRED')
    def test_required_missing_incomplete(self):
        a=self.run_attempt(required_evidence=('absent',));self.assertEqual(a.status,'INCOMPLETE');self.assertEqual(self.result(a).status,'INCOMPLETE')
    def test_missing_profile_incomplete(self):self.assertEqual(self.run_attempt(replace(self.bundle,fee_profile=None)).status,'INCOMPLETE')
    def test_real_before_loading(self):
        spy=Mock(side_effect=AssertionError('must not load'))
        a=execute(self.spec(origin='REAL'),self.j,'real',self.at,spy)
        self.assertEqual(a.status,'BLOCKED');spy.assert_not_called();self.assertIsNone(a.events[-1].output_json)
    def test_historical_unsealed_before_loading(self):
        spy=Mock();a=execute(self.spec(purpose='HISTORICAL'),self.j,'hist',self.at,spy)
        self.assertEqual(a.status,'BLOCKED');spy.assert_not_called()
    def test_holdout_before_loading(self):
        spy=Mock();a=execute(self.spec(purpose='HOLDOUT'),self.j,'holdout',self.at,spy)
        self.assertEqual(a.status,'BLOCKED');spy.assert_not_called()
    def test_invalid_interval_before_loading(self):
        for i,s in enumerate((self.spec(end=self.at.date()),self.spec(start=self.bundle.snapshot.calendar.start-timedelta(days=1)),self.spec(evaluation_at=self.at-timedelta(seconds=1)))):
            spy=Mock();self.assertEqual(execute(s,self.j,str(i),self.at,spy).status,'BLOCKED');spy.assert_not_called()
    def test_wrong_input_hash(self): self.assertEqual(self.run_attempt(input_sha256='0'*64).status,'FAILED')
    def test_wrong_config_hash(self):self.assertEqual(self.run_attempt(config_sha256='0'*64).status,'FAILED')
    def test_duplicate_evidence(self): self.assertEqual(self.run_attempt(replace(self.bundle,evidence=self.bundle.evidence*2)).status,'FAILED')
    def test_future_feature(self):
        e=replace(self.bundle.evidence[0],available_at=self.at+timedelta(seconds=1),recorded_at=self.at+timedelta(seconds=1))
        self.assertEqual(self.run_attempt(replace(self.bundle,evidence=(e,))).status,'FAILED')
    def test_feature_hash_mismatch(self):
        e=replace(self.bundle.evidence[0],payload_sha256='0'*64)
        self.assertEqual(self.run_attempt(replace(self.bundle,evidence=(e,))).status,'FAILED')
    def test_revised_history(self):
        b=self.bundle.snapshot.bars[0];snap=replace(self.bundle.snapshot,bars=(replace(b,provider='OTHER'),)+self.bundle.snapshot.bars[1:])
        self.assertEqual(self.run_attempt(replace(self.bundle,snapshot=snap)).status,'FAILED')
    def test_week_month_incomplete(self):
        from data_fetcher import period_bounds
        for i,tf in enumerate(('WEEKLY','MONTHLY')):
            start,end=period_bounds(self.at.date(),tf)
            e=replace(self.bundle.evidence[0],source_ref='STOCK',timeframe=tf,period_start=start,period_end=end)
            b=replace(self.bundle,evidence=(e,));a=execute(self.spec(b),self.j,str(i),self.at,lambda:b)
            self.assertEqual(a.status,'FAILED')
    def test_future_snapshot_append_visible_evidence_invariant(self):
        r=self.result(self.run_attempt());b=self.bundle.snapshot.bars[-1]
        snap=replace(self.bundle.snapshot,bars=self.bundle.snapshot.bars+(replace(b,revision=1,available_at=b.available_at+timedelta(days=2)),))
        bundle=replace(self.bundle,snapshot=snap)
        a=execute(self.spec(bundle),self.j,'future',self.at,lambda:bundle)
        self.assertEqual(a.status,'PASS');self.assertEqual(r.evidence,self.result(a).evidence)
    def test_candidate_mismatch(self):self.assertEqual(self.run_attempt(candidate=Candidate.B).status,'FAILED')
    def test_retry_and_replay(self):
        a=self.run_attempt();spy=Mock()
        self.assertEqual(execute(self.spec(),self.j,'attempt',self.at+timedelta(days=2),spy),a);spy.assert_not_called()
        b=execute(self.spec(),self.j,'retry',self.at+timedelta(days=3),lambda:self.bundle)
        self.assertNotEqual(a.attempt_id,b.attempt_id);self.assertEqual(a.run_id,b.run_id)
        self.assertEqual(a.events[-1].output_json,b.events[-1].output_json)
    def test_conflicting_attempt(self):
        self.run_attempt();a=execute(self.spec(required_evidence=('other',)),self.j,'attempt',self.at+timedelta(days=2),Mock())
        self.assertEqual(a.status,'BLOCKED');self.assertEqual(len(a.events),3)
    def test_restart(self):
        a=self.run_attempt();self.j.close();self.j=ResearchJournal(self.path);self.assertEqual(self.j.attempt('attempt'),a)
    def test_crash_incomplete(self):
        s=self.spec();e=AttemptEvent('x:start','x',s.run_id,encoded(s).decode(),self.at,'STARTED',())
        self.j.append(e);self.j.close();self.j=ResearchJournal(self.path)
        self.assertEqual(self.j.attempt('x').status,'INCOMPLETE')
    def test_transaction_rollback(self):
        s=self.spec();e=AttemptEvent('x:start','x',s.run_id,encoded(s).decode(),self.at,'STARTED',())
        with self.assertRaises(ConfigError):self.j.append(e,object())
        self.assertEqual(self.j.events(),())
    def test_failure_durable(self):
        def fail():raise ValueError('synthetic failure')
        a=execute(self.spec(),self.j,'fail',self.at,fail);self.assertEqual(a.status,'FAILED');self.assertIn('synthetic failure',a.events[-1].reasons[0])
    def test_corruption(self):
        self.run_attempt();self.j.db.execute("UPDATE events SET chain='bad' WHERE seq=1")
        with self.assertRaises(ConfigError):self.j.events()
    def test_protected_paths(self):
        for path in (Path('config.example.json'),Path('research_manifest.json'),self.path,self.path/'account.sqlite',Path(__file__).resolve().parents[1]/'research-bad'):
            with self.assertRaises((ConfigError,FileExistsError)):ResearchJournal.create(path)
    def test_foreign_database(self):
        self.j.db.execute('PRAGMA application_id=0')
        with self.assertRaises(ConfigError):ResearchJournal(self.path)
    def test_source_and_manifest_unchanged(self):
        paths=['config.example.json','parameter_catalog.json','research_manifest.json','human_review.py','ledger.py','P8_REVIEW_MANIFEST.json','REVIEW_MANIFEST.json']
        before={p:Path(p).read_bytes() for p in paths};account=digest(self.bundle.execution)
        self.run_attempt()
        self.assertEqual(before,{p:Path(p).read_bytes() for p in paths});self.assertEqual(account,digest(self.bundle.execution))
    def test_malformed_types(self):
        with self.assertRaises(ConfigError):replace(self.spec(),decision_at='bad')
        with self.assertRaises(ConfigError):replace(self.spec(),schema_version='RESEARCH-2')
    def test_import_no_io(self):
        import subprocess,sys
        code="""import research_records,research_pipeline,research_journal,importlib
from unittest.mock import patch
with patch('builtins.open',side_effect=AssertionError('open')),patch('sqlite3.connect',side_effect=AssertionError('db')),patch('socket.socket',side_effect=AssertionError('network')):
 for m in (research_records,research_pipeline,research_journal): importlib.reload(m)
"""
        subprocess.run([sys.executable,'-B','-c',code],check=True,capture_output=True)
    def test_nonempty_manifest_pin_before_loading(self):
        spy=Mock();a=execute(self.spec(manifest_sha256='0'*64),self.j,'manifest',self.at,spy)
        self.assertEqual(a.status,'BLOCKED');spy.assert_not_called()
    def test_future_outcome_not_predictive(self):
        a=self.f.f.run_sim().audit[-1]
        later=self.at+timedelta(days=1)
        e=EvidenceItem('outcome','OUTCOME',a.command.event.occurred_at,later,later,a.command.command_id,digest(a),'CONFIRMED')
        bundle=replace(self.bundle,evidence=self.bundle.evidence+(e,),outcomes=(a,))
        result=self.result(self.run_attempt(bundle));self.assertEqual(result.evidence,self.bundle.evidence)
        after=execute(self.spec(bundle,evaluation_at=later),self.j,'later',later,lambda:bundle)
        self.assertEqual(after.status,'PASS');self.assertEqual(len(self.result(after).evidence),2)
        self.assertEqual(result.suitability_sha256,self.result(after).suitability_sha256)
    def test_unresolved_fact_stays_unresolved(self):
        from execution_records import Command
        cmd=Command('ambiguous',self.at,0,'STOCK','trade','BAR','PROTECTIVE',bar_date=self.at.date())
        account=self.f.f.run_sim(self.f.f.chain()+self.f.f.protect()+(replace(cmd,recorded_at=self.at+timedelta(hours=8)),),as_of=self.at+timedelta(days=1))
        audit=next(a for a in account.audit if a.command.command_id=='ambiguous')
        self.assertNotEqual(audit.outcome,'APPLIED')
        later=self.at+timedelta(days=1)
        e=EvidenceItem('unresolved','OUTCOME',audit.command.recorded_at,later,later,'ambiguous',digest(audit),'UNRESOLVED')
        b=replace(self.bundle,evidence=self.bundle.evidence+(e,),outcomes=(audit,))
        a=execute(self.spec(b,evaluation_at=later),self.j,'unresolved',later,lambda:b)
        self.assertEqual(a.status,'INCOMPLETE');self.assertEqual(self.result(a).evidence[-1].state,'UNRESOLVED')
        bad=replace(b,evidence=self.bundle.evidence+(replace(e,state='CONFIRMED'),))
        self.assertEqual(execute(self.spec(bad,evaluation_at=later),self.j,'wrong',later,lambda:bad).status,'FAILED')
    def test_candidate_b_independent(self):
        import test_strategy as strategy_fixture
        from regime_detector import replay
        from accounting_adapter import AccountingDependencies
        from suitability import weekly_report
        f=strategy_fixture.StrategyTests();cfg=replace(self.bundle.config,strategy=replace(self.bundle.config.strategy,candidate=Candidate.B))
        regimes=replay(f.bench,cfg,f.binding,f.bench.calendar.start,f.decisions)
        signal=f.run_strategy(cfg=cfg,regimes=regimes)[2]
        adapter=AccountingDependencies(cfg,self.f.f.funding,'acct',self.f.adapter.schedule,(),self.f.adapter.costs)
        request=replace(self.f.request,signal=signal,regime=regimes[2])
        report=weekly_report(self.bundle.snapshot,cfg,self.bundle.execution,adapter,self.f.f.cap,(request,),self.at)
        e=replace(self.bundle.evidence[0],payload_sha256=digest(report))
        b=replace(self.bundle,config=cfg,suitability=report,evidence=(e,))
        a=self.run_attempt();other=execute(self.spec(b),self.j,'B',self.at,lambda:b)
        self.assertEqual(other.status,'PASS');self.assertNotEqual(a.run_id,other.run_id)
        self.assertEqual(self.result(other).spec.candidate,Candidate.B)
    def test_order_independent_evidence_assembly(self):
        from research_pipeline import assemble
        r=self.bundle.suitability.ranked[0]
        e=replace(self.bundle.evidence[0],evidence_id='row',source_ref=r.proposal_id,payload_sha256=digest(r))
        a=replace(self.bundle,evidence=(e,)+self.bundle.evidence);b=replace(a,evidence=tuple(reversed(a.evidence)))
        self.assertEqual(assemble(self.spec(a),a).evidence,assemble(self.spec(b),b).evidence)
    def test_symlink_store_rejected(self):
        path=Path(self.tmp.name)/'research-link';path.symlink_to(self.path,target_is_directory=True)
        with self.assertRaises(ConfigError):ResearchJournal(path)
    def test_future_conflict_does_not_rewrite_prefix(self):
        later=self.at+timedelta(days=1)
        future=EvidenceItem('report','OUTCOME',later,later,later,'future-source',digest('future'),'UNRESOLVED')
        b=replace(self.bundle,evidence=self.bundle.evidence+(future,))
        a=self.run_attempt(b);self.assertEqual(a.status,'PASS')
        self.assertEqual(self.result(a).evidence,self.bundle.evidence)
        observed=execute(self.spec(b,evaluation_at=later),self.j,'conflict',later,lambda:b)
        self.assertEqual(observed.status,'FAILED')

    def fill_receipts(self, delay=timedelta(), *, distinct_command=False):
        commands = self.f.f.chain()
        fill = commands[-1]
        receipt = fill.recorded_at + delay
        changed = replace(fill, command_id='fill-receipt' if distinct_command else 'fill', priority=1, recorded_at=receipt,
                          event=replace(fill.event, price=fill.event.price - 1,
                                        recorded_at=receipt, notified_at=receipt))
        account = self.f.f.run_sim(commands + (changed,), as_of=receipt)
        pair = tuple(a for a in account.audit if a.command.command_id in ('fill', 'fill-receipt'))
        self.assertEqual([a.outcome for a in pair], ['APPLIED', 'REJECTED'])
        expected = 'conflicting event identifier' if distinct_command else 'conflicting command identifier'
        self.assertIn(expected, pair[1].reasons)
        evidence = EvidenceItem('fill-proof', 'OUTCOME', fill.event.occurred_at,
                                fill.recorded_at, fill.recorded_at, 'fill',
                                digest(pair[0]), 'CONFIRMED')
        return replace(self.bundle, outcomes=pair, evidence=self.bundle.evidence + (evidence,))

    def test_conflicting_fill_sources(self):
        bundle = self.fill_receipts()
        for n, receipts in enumerate((bundle.outcomes, bundle.outcomes[::-1])):
            candidate = replace(bundle, outcomes=receipts)
            attempt = execute(self.spec(candidate), self.j, str(n), self.at, lambda: candidate)
            self.assertEqual(attempt.status, 'FAILED')
            self.assertIn('conflicting visible outcome', attempt.events[-1].reasons[0])

    def test_duplicate_fill_source(self):
        bundle = self.fill_receipts()
        applied = bundle.outcomes[0]
        for n, receipts in enumerate(((applied,), (applied, applied))):
            candidate = replace(bundle, outcomes=receipts)
            attempt = execute(self.spec(candidate), self.j, str(n), self.at, lambda: candidate)
            self.assertEqual(attempt.status, 'PASS')
            self.assertEqual(len(self.result(attempt).evidence), 2)

    def test_late_fill_conflict_boundary(self):
        delay = timedelta(minutes=10)
        bundle = self.fill_receipts(delay)
        receipt = self.at + delay
        for n, (cutoff, expected) in enumerate(((receipt-timedelta(microseconds=1), 'PASS'), (receipt, 'FAILED'))):
            attempt = execute(self.spec(bundle, evaluation_at=cutoff), self.j, str(n), cutoff, lambda: bundle)
            self.assertEqual(attempt.status, expected)

    def test_rehashed_invalid_report_after_restart(self):
        import hashlib
        start, end = self.run_attempt().events
        for key in ('input hash', 'blocked stage', 'missing evidence', 'missing profile',
                    'duplicate stage', 'missing stage', 'optional status', 'future evidence',
                    'duplicate evidence', 'unresolved evidence', 'invalid snapshot hash', 'run identity',
                    'suitability feature hash', 'suitability report hash'):
            with self.subTest(key=key):
                doc = json.loads(end.output_json)
                if key == 'suitability feature hash': doc['evidence'][0]['payload_sha256'] = '0'*64
                if key == 'suitability report hash': doc['suitability_sha256'] = '0'*64
                if key == 'input hash': doc['input_sha256'] = '0'*64
                if key == 'blocked stage': doc['stages'][2].update(status='BLOCKED', reasons=['blocked'])
                if key == 'missing evidence': doc['evidence'] = []
                if key == 'missing profile': doc['fee_profile'] = None
                if key == 'duplicate stage': doc['stages'].append(doc['stages'][0])
                if key == 'missing stage': doc['stages'].pop(1)
                if key == 'optional status': doc['stages'][-1]['status'] = 'PASS'
                if key == 'future evidence': doc['evidence'][0]['recorded_at'] = (self.at+timedelta(days=1)).isoformat()
                if key == 'duplicate evidence': doc['evidence'] *= 2
                if key == 'unresolved evidence': doc['evidence'][0]['state'] = 'UNRESOLVED'
                if key == 'invalid snapshot hash': doc['snapshot_sha256'] = 'invalid'
                if key == 'run identity': doc['run_id'] = '0'*64
                payload = json.dumps(doc, sort_keys=True, separators=(',', ':'))
                altered = replace(end, output_json=payload, output_sha256=hashlib.sha256(payload.encode()).hexdigest())
                directory = Path(self.tmp.name)/('research-'+key)
                store = ResearchJournal.create(directory)
                try:
                    store.append(start, altered)
                    result = store.attempt(start.attempt_id)
                finally:
                    store.close()
                store = ResearchJournal(directory)
                try:
                    self.assertEqual(store.attempt(start.attempt_id), result)
                    self.assertEqual(store.events(), (start, altered))
                    self.assertEqual(result.status, 'BLOCKED')
                    self.assertTrue(result.reasons)
                finally:
                    store.close()
                with self.assertRaises(ConfigError):
                    from_dict(ResearchReport, doc)

    def test_incomplete_with_optional_stages_survives_restart(self):
        attempt = self.run_attempt(replace(self.bundle, execution_profile=None))
        self.assertEqual(attempt.status, 'INCOMPLETE')
        report = self.result(attempt)
        stages = {stage.name: stage.status for stage in report.stages}
        self.assertEqual(stages['validate_consistency'], 'BLOCKED')
        self.assertEqual(stages['legacy_analyses'], 'DEFERRED')
        self.assertEqual(stages['performance_analysis'], 'NOT_IMPLEMENTED')
        self.j.close()
        self.j = ResearchJournal(self.path)
        self.assertEqual(self.j.attempt(attempt.attempt_id), attempt)

    def test_visible_fill_event_conflict(self):
        delay = timedelta(minutes=4)
        bundle = self.fill_receipts(delay, distinct_command=True)
        for order, receipts in enumerate((bundle.outcomes, bundle.outcomes[::-1])):
            candidate = replace(bundle, outcomes=receipts)
            for micros, expected in ((-1, 'PASS'), (0, 'FAILED'), (1, 'FAILED')):
                at = self.at + delay + timedelta(microseconds=micros)
                result = execute(self.spec(candidate, evaluation_at=at), self.j,
                                 f'boundary-{order}-{micros}', at, lambda: candidate)
                self.assertEqual(result.status, expected)
                if expected == 'FAILED':
                    self.assertIn('conflicting visible event', result.events[-1].reasons[0])

    def test_distinct_events_and_identical_redelivery(self):
        audits = self.f.f.run_sim().audit
        fill = audits[-1]
        bundle = replace(self.bundle, outcomes=audits+(fill, fill))
        attempt = self.run_attempt(bundle)
        self.assertEqual(attempt.status, 'PASS')
        report = self.result(attempt)
        self.assertEqual(report.evidence[0].source_ref, 'suitability')
        self.assertEqual(report.evidence[0].payload_sha256, report.suitability_sha256)
