"""Synthetic benchmark engineering only. No legacy code or market outcomes."""
import unittest
from dataclasses import replace, FrozenInstanceError
from datetime import date, datetime, timedelta
from decimal import Decimal as D, localcontext
from config import BotConfig, ConfigError, content_hash, readiness_issues, load_manifest
from data_records import Snapshot, DailyBar, Identity, ExchangeCalendar, TradingDay, Segment, IST, digest
from regime_detector import (BenchmarkBinding, Indicators, Confirmation, replay, classify,
                             _indicator_series, _advance, NUMERIC)


def stamp(day, hour=16):
    return datetime(day.year,day.month,day.day,hour,tzinfo=IST)


def fixture(count=225, *, flat=False):
    start=date(2020,1,1);days=[];bars=[];day=start
    while len(bars)<count:
        # Explicit synthetic holiday and Saturday session, not real NSE coverage.
        opened=(day.weekday()<5 and day!=date(2020,1,6)) or day==date(2020,1,11)
        seg=(Segment(stamp(day,9),stamp(day,15)),) if opened else ()
        days.append(TradingDay(day,seg,'SYNTHETIC'))
        if opened:
            p=D(100 if flat else 100+len(bars))
            bars.append(DailyBar('SYN-NIFTY50','SYN-N50',day,stamp(day,15),stamp(day),
                                'SYN-INDEX','v1',0,'SYNTHETIC',p,p+1,p-1,p,D(0)))
        day+=timedelta(days=1)
    cal=ExchangeCalendar('SYN-CAL',stamp(start)-timedelta(days=1),start,day,tuple(days),'SYNTHETIC')
    identity=Identity('SYN-NIFTY50','SYN-N50',start,day,cal.available_at,'LISTED','SYNTHETIC INDEX')
    binding=BenchmarkBinding('SYN-NIFTY50','SYN-INDEX','v1','SYNTHETIC NIFTY50 proxy fixture',cal.available_at)
    return Snapshot(cal,tuple(bars),(identity,)),binding,tuple(bars)


def measured(**kw):
    values=dict(close=D(110),ema=D(100),slope=D(1),atr=D(2),plus_di=D(50),minus_di=D(0),
                dx=D(100),adx=D(30),atr_reference=D(2),atr_ratio=D(1),recent_vol=D('.1'),
                reference_vol=D('.1'),vol_ratio=D(1))
    values.update(kw)
    return Indicators(**values)


class IndicatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.s,cls.binding,cls.bars=fixture()

    def test_ema_seed_recurrence_slope_first_indices(self):
        v=_indicator_series(self.bars,BotConfig().regime)
        self.assertIsNone(v[198].ema)
        self.assertEqual(v[199].ema,D('199.5'))  # mean(100..299)
        self.assertEqual(v[200].ema,D('200.5'))
        self.assertIsNone(v[208].slope)
        self.assertEqual(v[209].slope,D(1))

    def test_wilder_seeds_and_first_indices(self):
        v=_indicator_series(self.bars,BotConfig().regime)
        self.assertIsNone(v[13].atr);self.assertEqual(v[14].atr,D(2))
        self.assertEqual(v[14].plus_di,D(50));self.assertEqual(v[14].minus_di,D(0))
        self.assertEqual(v[14].dx,D(100));self.assertIsNone(v[26].adx)
        self.assertEqual(v[27].adx,D(100));self.assertEqual(v[28].adx,D(100))

    def test_atr_previous_only_reference_and_spike_recurrence(self):
        bars=list(self.bars[:78]);bars[-1]=replace(bars[-1],high=bars[-1].close+100,low=bars[-1].close-100)
        v=_indicator_series(tuple(bars),BotConfig().regime)
        self.assertIsNone(v[76].atr_reference);self.assertEqual(v[77].atr_reference,D(2))
        with localcontext(NUMERIC):expected=D(226)/14
        self.assertEqual(v[77].atr,expected)
        self.assertGreater(v[77].atr_ratio,D(2))

    def test_directional_movement_down_and_tie(self):
        down=tuple(replace(b,open=D(500-i),close=D(500-i),high=D(501-i),low=D(499-i)) for i,b in enumerate(self.bars[:30]))
        v=_indicator_series(down,BotConfig().regime)
        self.assertEqual(v[14].plus_di,0);self.assertEqual(v[14].minus_di,50)
        tied=tuple(replace(b,open=D(100),close=D(100),high=D(101+i),low=D(99-i)) for i,b in enumerate(self.bars[:30]))
        v=_indicator_series(tied,BotConfig().regime)
        self.assertEqual(v[14].plus_di,0);self.assertEqual(v[14].minus_di,0);self.assertEqual(v[27].adx,0)

    def test_log_return_windows_independent_expected_values(self):
        # 63 preceding returns alternate ln(2),0; 20 recent alternate ln(4),0.
        bars=[];p=D(100)
        for i,b in enumerate(self.bars[:84]):
            if i and i<=63:p*=2 if i%2 else 1
            elif i:p*=4 if (i-64)%2==0 else 1
            bars.append(replace(b,open=p,high=p,low=p,close=p))
        v=_indicator_series(tuple(bars),BotConfig().regime)
        self.assertIsNone(v[19].recent_vol);self.assertIsNotNone(v[20].recent_vol)
        self.assertIsNone(v[82].reference_vol)
        with localcontext(NUMERIC):
            ref=D(2).ln()*(D(32*31)/D(63*62)).sqrt()
            recent=D(4).ln()*(D(10*10)/D(20*19)).sqrt()
            self.assertLess(abs(v[83].reference_vol-ref),D('1e-45'))
            self.assertLess(abs(v[83].recent_vol-recent),D('1e-45'))

    def test_flat_and_zero_range(self):
        s,b,raw=fixture(flat=True)
        raw=tuple(replace(x,high=x.close,low=x.close) for x in raw)
        v=_indicator_series(raw,BotConfig().regime)[-1]
        self.assertEqual((v.atr,v.plus_di,v.minus_di,v.dx,v.adx,v.recent_vol,v.reference_vol),(D(0),)*7)
        self.assertIsNone(v.atr_ratio);self.assertIsNone(v.vol_ratio)
        self.assertIsNone(classify(v,BotConfig().regime)[0])

    def test_empty(self):self.assertEqual(_indicator_series((),BotConfig().regime),())

    def test_nonfinite_rejected(self):
        with self.assertRaises(ConfigError):replace(self.bars[0],close=D('NaN'))

    def test_numeric_context_isolation(self):
        expected=_indicator_series(self.bars,BotConfig().regime)
        with localcontext() as ctx:
            ctx.prec=3
            actual=_indicator_series(self.bars,BotConfig().regime)
        self.assertEqual(actual,expected)


class ClassificationTests(unittest.TestCase):
    def test_up_down_sideways_and_conflict(self):
        for kw,expected in [({},'TRENDING_UP'),({'close':D(90),'slope':D(-1)},'TRENDING_DOWN'),
                            ({'close':D(110),'slope':D(-1)},'SIDEWAYS'),({'close':D(90),'slope':D(1)},'SIDEWAYS')]:
            with self.subTest(kw=kw):self.assertEqual(classify(measured(**kw),BotConfig().regime)[0],expected)

    def test_equalities(self):
        for kw in ({'adx':D(19)},{'adx':D(20)},{'adx':D(25)},{'close':D(100)},{'slope':D(0)}):
            with self.subTest(kw=kw):self.assertEqual(classify(measured(**kw),BotConfig().regime)[0],'SIDEWAYS')
        for field in ('atr_ratio','vol_ratio'):
            self.assertEqual(classify(measured(**{field:D(2)}),BotConfig().regime)[:2],('HIGH_RISK',True))
            self.assertFalse(classify(measured(**{field:D('1.999')}),BotConfig().regime)[1])

    def test_independent_veto_with_other_unknown(self):
        for kw in ({'atr_ratio':D(2),'vol_ratio':None,'ema':None},{'atr_ratio':None,'vol_ratio':D(2),'adx':None}):
            candidate,veto,missing=classify(measured(**kw),BotConfig().regime)
            self.assertEqual(candidate,'HIGH_RISK');self.assertTrue(veto);self.assertTrue(missing)

    def test_unknown_not_sideways(self):
        self.assertIsNone(classify(Indicators(),BotConfig().regime)[0])


class ConfirmationTests(unittest.TestCase):
    def test_initial_and_transition(self):
        state=_advance(Confirmation(),'TRENDING_UP',consecutive=False)
        self.assertEqual(state,Confirmation(None,'TRENDING_UP',1))
        state=_advance(state,'TRENDING_UP',consecutive=True)
        self.assertEqual(state,Confirmation('TRENDING_UP'))
        state=_advance(state,'SIDEWAYS',consecutive=True)
        self.assertEqual(state,Confirmation('TRENDING_UP','SIDEWAYS',1))
        self.assertEqual(_advance(state,'SIDEWAYS',consecutive=True),Confirmation('SIDEWAYS'))

    def test_unknown_interruption_and_duplicate(self):
        state=Confirmation('SIDEWAYS','TRENDING_UP',1)
        self.assertEqual(_advance(state,None,consecutive=True),Confirmation(diagnostic_previous='SIDEWAYS'))
        self.assertEqual(_advance(state,'TRENDING_UP',consecutive=False),state)
        self.assertEqual(_advance(state,'TRENDING_UP',consecutive=True,same_session=True),state)


class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.s,cls.binding,cls.bars=fixture()

    def run_replay(self,indices=(209,210),s=None,binding=None,config=None,decisions=None,start=None):
        return replay(s or self.s,config or BotConfig(),binding or self.binding,start or self.s.calendar.start,
                      decisions if decisions is not None else tuple(self.bars[i].available_at for i in indices))

    def test_initial_confirmed_up_and_repeat(self):
        a,b=self.run_replay()
        self.assertEqual(a.status,'READY');self.assertFalse(a.entry_eligible)
        self.assertEqual(b.confirmation.confirmed,'TRENDING_UP');self.assertTrue(b.entry_eligible)
        self.assertFalse(b.trade_authorized)
        self.assertEqual(self.run_replay(),self.run_replay())

    def test_duplicate_same_session(self):
        out=self.run_replay(indices=(209,209,210))
        self.assertEqual(out[0].confirmation,out[1].confirmation)
        self.assertEqual(out[2].confirmation.confirmed,'TRENDING_UP')

    def test_skipped_decision_breaks_pending(self):
        out=self.run_replay(indices=(209,211))
        self.assertIsNone(out[-1].confirmation.confirmed);self.assertEqual(out[-1].confirmation.count,1)

    def test_missing_scheduled_bar_rejected_not_compressed(self):
        s=replace(self.s,bars=tuple(b for b in self.s.bars if b.trading_date!=self.bars[205].trading_date))
        out=self.run_replay(s=s)[-1]
        self.assertEqual(out.data_status,'REJECTED');self.assertEqual(out.indicators,Indicators())
        self.assertEqual(out.confirmation.count,0)

    def test_delayed_availability_and_unknown_reset(self):
        date209=self.bars[209].trading_date
        s=replace(self.s,bars=tuple(replace(b,available_at=self.bars[211].available_at) if b.trading_date==date209 else b for b in self.s.bars))
        out=self.run_replay(indices=(208,209,210),s=s)
        self.assertEqual(out[-1].status,'UNKNOWN');self.assertFalse(out[-1].entry_eligible)

    def test_future_append_and_revision_invariance(self):
        decisions=tuple(self.bars[i].available_at for i in (209,210))
        prefix=replace(self.s,bars=tuple(b for b in self.s.bars if b.available_at<=decisions[-1]))
        future=replace(self.bars[50],revision=1,close=self.bars[50].close+D('.5'),available_at=self.bars[220].available_at)
        revised=replace(self.s,bars=self.s.bars+(future,))
        self.assertEqual(self.run_replay(s=prefix),self.run_replay(s=revised))
        self.assertEqual(self.run_replay(),self.run_replay(indices=(209,210,211))[:2])

    def test_visible_revision_resets_state(self):
        b=self.bars[50];rev=replace(b,revision=1,close=b.close+D('.5'),available_at=self.bars[210].available_at)
        out=self.run_replay(s=replace(self.s,bars=self.s.bars+(rev,)))
        self.assertIn('consumed_history_changed_reset_required',out[-1].rejection_reasons)
        self.assertEqual(out[-1].confirmation.count,0)

    def test_mixed_provider_rejected(self):
        s=replace(self.s,bars=tuple(replace(b,provider='OTHER') if b.trading_date==self.bars[50].trading_date else b for b in self.s.bars))
        result=self.run_replay(s=s)[0]
        self.assertIn('incompatible_series_provider',result.rejection_reasons)
        self.assertEqual(result.indicators,Indicators())

    def test_no_stock_substitution_and_binding_availability(self):
        with self.assertRaises(ConfigError):replace(self.binding,benchmark='STOCK')
        out=self.run_replay(binding=replace(self.binding,available_at=self.bars[220].available_at))[0]
        self.assertEqual(out.status,'UNKNOWN');self.assertFalse(out.entry_eligible)
        out=self.run_replay(binding=replace(self.binding,instrument_id='ETF'))[0]
        self.assertEqual(out.data_status,'REJECTED')

    def test_immediate_veto_before_warmup(self):
        b=self.bars[77];spike=replace(b,high=b.close+100,low=b.close-100)
        s=replace(self.s,bars=tuple(spike if x.trading_date==b.trading_date else x for x in self.s.bars))
        out=self.run_replay(indices=(77,),s=s)[0]
        self.assertTrue(out.immediate_veto);self.assertEqual(out.candidate,'HIGH_RISK')
        self.assertEqual(out.status,'UNKNOWN');self.assertIsNone(out.confirmation.confirmed)

    def test_veto_during_up_confirmation(self):
        b=self.bars[211];s=replace(self.s,bars=tuple(replace(x,high=x.close+100,low=x.close-100) if x.trading_date==b.trading_date else x for x in self.s.bars))
        out=self.run_replay(indices=(209,210,211),s=s)[-1]
        self.assertEqual(out.confirmation.confirmed,'TRENDING_UP')
        self.assertEqual(out.confirmation.pending,'HIGH_RISK');self.assertTrue(out.immediate_veto);self.assertFalse(out.entry_eligible)

    def test_special_sessions_and_closures(self):
        saturday=next(i for i,b in enumerate(self.bars) if b.trading_date==date(2020,1,11))
        out=self.run_replay(indices=(saturday,))
        self.assertEqual(out[0].session,date(2020,1,11))
        out=self.run_replay(decisions=(stamp(date(2020,1,11)),stamp(date(2020,1,12))))
        self.assertEqual(out[0].session,out[1].session);self.assertEqual(out[0].confirmation,out[1].confirmation)

    def test_out_of_order_and_empty_decisions(self):
        with self.assertRaises(ConfigError):self.run_replay(indices=(210,209))
        self.assertEqual(self.run_replay(decisions=()),())

    def test_no_completed_session(self):
        out=self.run_replay(decisions=(stamp(self.s.calendar.start,8),))[0]
        self.assertIsNone(out.session);self.assertEqual(out.status,'UNKNOWN')

    def test_history_and_configuration_fingerprints(self):
        first=self.run_replay(indices=(220,))[0]
        other=self.run_replay(indices=(220,),start=self.bars[1].trading_date)[0]
        self.assertNotEqual(first.history_sha256,other.history_sha256)
        c=replace(BotConfig(),config_version='0.3.1')
        self.assertNotEqual(first.config_sha256,self.run_replay(indices=(220,),config=c)[0].config_sha256)
        with self.assertRaises(ConfigError):self.run_replay(config=replace(BotConfig(),regime=replace(BotConfig().regime,ema_period=201)))

    def test_config_and_operational_state_unchanged(self):
        c=BotConfig();before=content_hash(c);self.run_replay(config=c)
        self.assertEqual(before,content_hash(c));self.assertIn('operational_trust_not_provisioned',readiness_issues(c))
        self.assertEqual(load_manifest('research_manifest.json').status.value,'UNSEALED')
        with self.assertRaises(FrozenInstanceError):self.run_replay()[0].status='READY'

    def test_output_evidence_and_adjusted_inputs_unsupported(self):
        r=self.run_replay()[0]
        self.assertEqual(r.available_at,r.as_of);self.assertTrue(r.source_lineage);self.assertTrue(r.identity_lineage)
        from data_fetcher import split_adjusted_view
        v=split_adjusted_view(self.s,self.bars[0],self.bars[209].available_at)
        with self.assertRaises(ConfigError):_indicator_series((v,),BotConfig().regime)





class AdditionalRegimeTests(unittest.TestCase):
    def test_wilder_adx_nonconstant_recurrence(self):
        s,b,raw=fixture(30)
        changed=list(raw[:29])
        changed[28]=replace(changed[28],open=D(125),close=D(125),high=D(126),low=D(124))
        v=_indicator_series(tuple(changed),BotConfig().regime)
        # Old TR=2, +DM=1, -DM=0. New TR=3, up=-2, down=2.
        # Smoothed TR=29/14, +DM=13/14, -DM=2/14; DX=100*11/15.
        with localcontext(NUMERIC):
            expected_dx=D(100)*11/15
            expected_adx=(D(1300)+expected_dx)/14
        self.assertLess(abs(v[28].dx-expected_dx),D('1e-45'))
        self.assertLess(abs(v[28].adx-expected_adx),D('1e-45'))

    def test_zero_vol_reference_nonzero_current_blocks(self):
        s,b,raw=fixture(90,flat=True)
        raw=list(raw);raw[-1]=replace(raw[-1],open=D(101),close=D(101),high=D(102),low=D(100))
        v=_indicator_series(tuple(raw),BotConfig().regime)[-1]
        self.assertGreater(v.recent_vol,0);self.assertEqual(v.reference_vol,0)
        self.assertIsNone(v.vol_ratio)

    def test_replay_prefix_with_trimmed_input_each_decision(self):
        s,b,raw=fixture(213);decisions=tuple(raw[i].available_at for i in (209,210,211))
        full=replay(s,BotConfig(),b,s.calendar.start,decisions)
        for i,cutoff in enumerate(decisions):
            prefix=replace(s,bars=tuple(x for x in s.bars if x.available_at<=cutoff))
            result=replay(prefix,BotConfig(),b,s.calendar.start,decisions[:i+1])
            self.assertEqual(full[:i+1],result)
        self.assertEqual(full[1].previous_result_sha256,digest(full[0]))

    def test_unknown_session_clears_current_confirmation(self):
        state=Confirmation('TRENDING_UP','HIGH_RISK',1)
        self.assertEqual(_advance(state,None,consecutive=True),Confirmation(diagnostic_previous='TRENDING_UP'))

    def test_two_ready_high_risk_sessions_confirm(self):
        s,b,raw=fixture(214)
        days={raw[211].trading_date,raw[212].trading_date}
        s=replace(s,bars=tuple(replace(x,high=x.close+100,low=x.close-100) if x.trading_date in days else x for x in s.bars))
        out=replay(s,BotConfig(),b,s.calendar.start,tuple(raw[i].available_at for i in (209,210,211,212)))
        self.assertEqual(out[-1].confirmation.confirmed,'HIGH_RISK')
        self.assertTrue(out[-2].immediate_veto);self.assertTrue(out[-1].immediate_veto)

    def test_config_pins_calendar_and_identity_availability(self):
        s,b,raw=fixture(212);c=BotConfig()
        for data in (replace(c.data,provider='OTHER'),replace(c.data,calendar_version='OTHER')):
            out=replay(s,replace(c,data=data),b,s.calendar.start,(raw[209].available_at,))[0]
            self.assertEqual(out.status,'UNKNOWN')
        s=replace(s,identities=(replace(s.identities[0],available_at=raw[211].available_at),))
        self.assertEqual(replay(s,c,b,s.calendar.start,(raw[209].available_at,))[0].data_status,'REJECTED')

    def test_import_has_no_io(self):
        import subprocess,sys
        code="import socket,pathlib; socket.socket=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('network')); pathlib.Path.write_text=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('write')); import regime_detector"
        p=subprocess.run([sys.executable,'-B','-c',code],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)





class FinalBoundaryTests(unittest.TestCase):
    def test_true_range_gap_and_zero_reference(self):
        s,b,raw=fixture(85,flat=True)
        bars=tuple(replace(x,high=x.close,low=x.close) for x in raw)
        bars=bars[:-1]+(replace(bars[-1],open=D(114),high=D(114),low=D(114),close=D(114)),)
        v=_indicator_series(bars,BotConfig().regime)[-1]
        self.assertEqual(v.atr,D(1))  # gap TR=14, prior smoothed ATR=0
        self.assertEqual(v.atr_reference,0);self.assertIsNone(v.atr_ratio)

    def test_invalid_and_mixed_version_do_not_reach_indicators(self):
        s,b,raw=fixture(212)
        for kw,reason in (({'close':D(-1)},'nonpositive_price'),({'provider_version':'other'},'incompatible_series_provider_version')):
            changed=replace(raw[20],**kw)
            snap=replace(s,bars=tuple(changed if x.trading_date==changed.trading_date else x for x in s.bars))
            out=replay(snap,BotConfig(),b,s.calendar.start,(raw[209].available_at,))[0]
            self.assertEqual(out.indicators,Indicators());self.assertFalse(out.entry_eligible)
            self.assertTrue(any(reason in r for r in out.rejection_reasons))

    def test_ready_closure_does_not_count_as_confirmation(self):
        s,b,raw=fixture(225)
        friday=next(x for x in raw[209:220] if x.trading_date.weekday()==4)
        sunday=friday.available_at+timedelta(days=2)
        monday=friday.available_at+timedelta(days=3)
        out=replay(s,BotConfig(),b,s.calendar.start,(friday.available_at,sunday,monday))
        self.assertEqual(out[0].confirmation.count,1)
        self.assertEqual(out[1].confirmation.count,1)
        self.assertEqual(out[2].confirmation.confirmed,'TRENDING_UP')





class FocusedReviewRegressions(unittest.TestCase):
    def test_geometric_returns_exact_zero_and_small_real_variance(self):
        s,b,raw=fixture(215)
        with localcontext() as ctx:
            ctx.prec=500
            prices=[D(100)*D('1.01')**i for i in range(len(raw))]
        bars=tuple(replace(x,open=p,high=p+D(1),low=p-D(1),close=p)
                   for x,p in zip(raw,prices))
        values=_indicator_series(bars,BotConfig().regime)
        self.assertEqual(values[-1].recent_vol,D(0))
        self.assertEqual(values[-1].reference_vol,D(0))
        self.assertIsNone(values[-1].vol_ratio)
        snap=replace(s,bars=bars)
        decisions=(bars[209].available_at,bars[210].available_at)
        out=replay(snap,BotConfig(),b,s.calendar.start,decisions)
        self.assertEqual(out[-1].status,'UNKNOWN')
        self.assertFalse(out[-1].entry_eligible)
        with localcontext() as ctx:
            ctx.prec=500
            prices[-1]+=D('1e-30')
        changed=bars[:-1]+(replace(bars[-1],open=prices[-1],high=prices[-1]+1,
                                  low=prices[-1]-1,close=prices[-1]),)
        self.assertGreater(_indicator_series(changed,BotConfig().regime)[-1].recent_vol,0)

    def test_revision_and_unknown_require_fresh_two_sessions(self):
        s,b,raw=fixture(215)
        rev=replace(raw[50],revision=1,close=raw[50].close+D('.5'),
                    available_at=raw[211].available_at)
        revised=replace(s,bars=s.bars+(rev,))
        decisions=tuple(raw[i].available_at for i in (209,210,211,212,213))
        out=replay(revised,BotConfig(),b,s.calendar.start,decisions)
        self.assertTrue(out[1].entry_eligible)
        self.assertIn('consumed_history_changed_reset_required',out[2].rejection_reasons)
        self.assertIsNone(out[2].confirmation.confirmed)
        self.assertEqual(out[2].confirmation.diagnostic_previous,'TRENDING_UP')
        self.assertFalse(out[3].entry_eligible)
        self.assertEqual(out[3].confirmation.count,1)
        self.assertTrue(out[4].entry_eligible)
        unavailable=replace(s,bars=tuple(replace(x,available_at=raw[212].available_at)
                         if x.trading_date==raw[211].trading_date else x for x in raw))
        out=replay(unavailable,BotConfig(),b,s.calendar.start,decisions)
        self.assertTrue(out[1].entry_eligible)
        self.assertEqual(out[2].status,'UNKNOWN')
        self.assertFalse(out[3].entry_eligible)
        self.assertTrue(out[4].entry_eligible)


class RejectedStatusTests(unittest.TestCase):
    def test_rejected_status_blocks_even_without_reasons(self):
        from unittest.mock import patch
        from data_records import QualityResult
        s,b,raw=fixture(211)
        q=QualityResult('REJECTED',(),tuple(digest(x) for x in raw))
        with patch('regime_detector.daily_as_of',return_value=(raw,q)):
            out=replay(s,BotConfig(),b,s.calendar.start,(raw[-1].available_at,))[0]
        self.assertIn('daily_quality_rejected',out.rejection_reasons)
        self.assertEqual(out.indicators,Indicators())


if __name__=='__main__':unittest.main()
