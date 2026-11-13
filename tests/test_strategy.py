"""Offline synthetic Prompt 5 expectations. No outcome research."""
import unittest
from dataclasses import replace, FrozenInstanceError
from datetime import date, timedelta
from decimal import Decimal as D, localcontext
from config import BotConfig, Candidate, ConfigError, content_hash
from data_records import Snapshot, Identity, CorporateAction, digest
from regime_detector import replay, NUMERIC
from strategy import (EMACrossoverStrategy, TickEvidence, ema, atr_series, latest_period,
                      monthly_evidence, planned_levels, entry_price_issues, ExitResolution)
from test_regime_detector import fixture, stamp


class MathTests(unittest.TestCase):
    def test_ema_independent_linear_seed(self):
        v=ema(tuple(D(i) for i in range(1,24)),9)
        self.assertIsNone(v[7]);self.assertEqual(v[8],5);self.assertEqual(v[9],6)
        self.assertEqual(v[-1],19)
        self.assertEqual(ema((D(100),)*25,21)[20:],(D(100),)*5)
        self.assertEqual(ema((),21),())
    def test_atr_seed(self):
        _,_,b=fixture(16)
        a=atr_series(b,14)
        self.assertIsNone(a[13]);self.assertEqual(a[14],2);self.assertEqual(a[15],2)
    def test_context_isolation(self):
        data=tuple(D(i) for i in range(1,30))
        expected=ema(data,9)
        with localcontext() as c:
            c.prec=6
            self.assertEqual(ema(data,9),expected)


class StrategyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bench,cls.binding,cls.bb=fixture(255)
        # Cross from flat to above at Monday, index 223 (2020-11-09).
        cls.cross=next(i for i,b in enumerate(cls.bb) if i>220 and b.trading_date.weekday()==0)
        bars=[]
        for i,b in enumerate(cls.bb):
            p=D(100 if i<cls.cross else 110)
            bars.append(replace(b,instrument_id='STOCK',symbol='SYN-STOCK',open=p,high=p+1,low=p-1,close=p,volume=D(10)))
        cls.stock=Snapshot(cls.bench.calendar,tuple(bars),(replace(cls.bench.identities[0],instrument_id='STOCK',symbol='SYN-STOCK'),))
        cls.bars=tuple(bars);cls.day=cls.bars[cls.cross+4].trading_date
        cls.decisions=tuple(stamp(cls.bb[i].trading_date) for i in range(cls.cross+3,cls.cross+7))
        cls.cfg=BotConfig()
        cls.tick=TickEvidence('STOCK',D('.05'),cls.bench.calendar.start,cls.bench.calendar.end,cls.bench.calendar.available_at,'SYNTHETIC')
        cls.regimes=replay(cls.bench,cls.cfg,cls.binding,cls.bench.calendar.start,cls.decisions)
    def run_strategy(self,stock=None,decisions=None,cfg=None,regimes=None,tick='DEFAULT',resolutions=()):
        cfg=cfg or self.cfg; decisions=decisions or self.decisions
        regimes=regimes if regimes is not None else (self.regimes if decisions==self.decisions and cfg==self.cfg else replay(self.bench,cfg,self.binding,self.bench.calendar.start,decisions))
        return EMACrossoverStrategy().replay(stock or self.stock,cfg,'STOCK',self.stock.calendar.start,decisions,
            benchmark_snapshot=self.bench,benchmark=self.binding,benchmark_start=self.bench.calendar.start,
            regimes=regimes,tick=self.tick if tick=='DEFAULT' else tick,resolutions=resolutions)
    def test_week_cross_and_duplicate_and_frozen(self):
        r=self.run_strategy();self.assertIsNone(r[0].opportunity)
        o=r[1].opportunity
        self.assertEqual(o.crossover_date,self.bars[self.cross].trading_date)
        self.assertEqual(o.selected_at,self.decisions[1]);self.assertEqual(o.state,'ACTIVE')
        self.assertTrue(r[1].signal_eligible)
        self.assertEqual(r[-1].opportunity,o)
        d=(self.decisions[0],self.decisions[1],self.decisions[1])
        rr=self.run_strategy(decisions=d);self.assertEqual(rr[1].opportunity,rr[2].opportunity)
        with self.assertRaises(FrozenInstanceError):o.state='RETIRED'
        self.assertFalse(r[-1].operational_authorized)
    def test_state_without_event_not_selected(self):
        bars=tuple(replace(b,open=D(100+i),high=D(101+i),low=D(99+i),close=D(100+i)) for i,b in enumerate(self.bars))
        self.assertIsNone(self.run_strategy(replace(self.stock,bars=bars))[-1].opportunity)
    def test_flat_equality_no_opportunity(self):
        bars=tuple(replace(b,open=D(100),high=D(101),low=D(99),close=D(100)) for b in self.bars)
        r=self.run_strategy(replace(self.stock,bars=bars))[-1]
        self.assertEqual(r.fast,r.slow);self.assertIsNone(r.opportunity);self.assertIsNotNone(r.exit_intent)
    def changed(self,index,value):
        return replace(self.stock,bars=tuple(replace(b,open=D(value),high=D(value)+1,low=D(value)-1,close=D(value)) if i==index else b for i,b in enumerate(self.bars)))
    def test_reversal_before_week_end(self):
        self.assertIsNone(self.run_strategy(self.changed(self.cross+4,50))[1].opportunity)
    def test_retirement_no_revival_and_exit_persists(self):
        r=self.run_strategy(self.changed(self.cross+5,50))
        self.assertEqual(r[2].opportunity.state,'RETIRED');self.assertEqual(r[3].opportunity.state,'RETIRED')
        self.assertEqual(r[2].exit_intent,r[3].exit_intent);self.assertFalse(r[3].signal_eligible)
        resolution=ExitResolution(r[2].exit_intent.intent_id,self.decisions[3],'SYNTHETIC resolution')
        rr=self.run_strategy(self.changed(self.cross+5,50),resolutions=(resolution,))
        self.assertEqual(rr[-1].exit_intent.resolved_at,self.decisions[3])
    def test_revision_retires_and_future_invariance(self):
        b=self.bars[30];rev=replace(b,revision=1,available_at=self.decisions[2],close=b.close+D('.1'))
        revised=replace(self.stock,bars=self.stock.bars+(rev,))
        a=self.run_strategy();r=self.run_strategy(revised)
        self.assertEqual(a[:2],r[:2]);self.assertEqual(r[2].opportunity.state,'RETIRED')
        self.assertFalse(r[3].signal_eligible)
    def test_missing_late_recovery(self):
        b=self.bars[self.cross+5]
        stock=replace(self.stock,bars=tuple(replace(x,available_at=self.decisions[3]) if x==b else x for x in self.stock.bars))
        r=self.run_strategy(stock)
        self.assertEqual(r[2].data_status,'REJECTED');self.assertFalse(r[2].signal_eligible)
        self.assertEqual(r[3].data_status,'VALID')
    def test_mixed_provider_rejected(self):
        stock=replace(self.stock,bars=(replace(self.stock.bars[0],provider='OTHER'),)+self.stock.bars[1:])
        r=self.run_strategy(stock)[-1];self.assertEqual(r.data_status,'REJECTED');self.assertIsNone(r.fast)
    def test_rejected_ohlc(self):
        stock=replace(self.stock,bars=(replace(self.stock.bars[0],low=D(0)),)+self.stock.bars[1:])
        self.assertEqual(self.run_strategy(stock)[-1].data_status,'REJECTED')
    def test_regime_flag_forgery_and_stale(self):
        for regime in (replace(self.regimes[1],entry_eligible=False),replace(self.regimes[1],as_of=self.decisions[0])):
            rr=(self.regimes[0],regime)+self.regimes[2:]
            with self.assertRaisesRegex(ConfigError,'causal replay'):self.run_strategy(regimes=rr)
    def test_initial_regime_unknown_blocks(self):
        r=self.run_strategy(decisions=(self.decisions[1],))[-1]
        self.assertFalse(r.signal_eligible);self.assertIn('regime_entry_blocked',r.reasons)
    def test_monthly_daily_snapshot(self):
        cfg=replace(self.cfg,strategy=replace(self.cfg.strategy,candidate=Candidate.B))
        r=self.run_strategy(cfg=cfg)[1];m=r.monthly
        self.assertEqual(m.final_session,date(2020,10,30));self.assertTrue(m.passes)
        # Linear benchmark 100+i: daily EMA200 = close-99.5 exactly.
        self.assertLess(abs(m.daily_ema200-(m.close-D('99.5'))),D('1e-45'))
        self.assertTrue(r.signal_eligible)
    def test_monthly_warmup_missing(self):
        with self.assertRaises(ConfigError):monthly_evidence(self.bench,self.cfg,self.binding,self.bars[100].trading_date,self.decisions[1])
    def test_monthly_equality_fails(self):
        flat=replace(self.bench,bars=tuple(replace(b,open=D(100),high=D(101),low=D(99),close=D(100)) for b in self.bench.bars))
        self.assertFalse(monthly_evidence(flat,self.cfg,self.binding,flat.calendar.start,self.decisions[1]).passes)
    def test_tick_and_price_delay(self):
        bar=replace(self.bars[self.cross+4],close=D('110.03'))
        levels=planned_levels(self.stock,self.cfg,bar,D(2),self.decisions[1],self.tick)
        self.assertEqual(levels.stop,D('106.03'));self.assertEqual(levels.ceiling,110)
        self.assertEqual(levels.earliest_session,self.bars[self.cross+6].trading_date)
        self.assertIn('above_entry_ceiling',entry_price_issues(levels,D(111),levels.earliest_session))
        self.assertIn('at_or_below_protective_level',entry_price_issues(levels,levels.stop,levels.earliest_session))
        self.assertIn('intervening_session_not_completed',entry_price_issues(levels,D(109),self.bars[self.cross+5].trading_date))
        self.assertEqual(entry_price_issues(levels,D(109),levels.earliest_session),())
    def test_missing_tick_fails_without_retroactive_proposal(self):
        r=self.run_strategy(tick=None);self.assertFalse(r[1].signal_eligible);self.assertIsNone(r[1].opportunity.levels)
    def test_invalid_stop(self):
        with self.assertRaises(ConfigError):planned_levels(self.stock,self.cfg,self.bars[self.cross+4],D(100),self.decisions[1],self.tick)
    def test_known_action_blocks_raw_arithmetic(self):
        day=self.bars[self.cross].trading_date
        action=CorporateAction('split','STOCK',day,stamp(day),stamp(day),'SPLIT',D(2),'SYNTHETIC')
        self.assertEqual(self.run_strategy(replace(self.stock,actions=(action,)))[1].data_status,'REJECTED')
    def test_prefix_and_future_rows(self):
        full=self.run_strategy();self.assertEqual(full[:2],self.run_strategy(decisions=self.decisions[:2]))
        short=replace(self.stock,bars=tuple(b for b in self.bars if b.available_at<=self.decisions[1]))
        self.assertEqual(full[:2],self.run_strategy(short,decisions=self.decisions[:2]))
        self.assertEqual(full,self.run_strategy())
    def test_config_unchanged_and_unapproved_parameters(self):
        before=content_hash(self.cfg);self.run_strategy();self.assertEqual(before,content_hash(self.cfg))
        with self.assertRaises(ConfigError):self.run_strategy(cfg=replace(self.cfg,strategy=replace(self.cfg.strategy,fast_ema=8)))
    def test_unfinished_week_calendar(self):
        first,end=latest_period(self.stock.calendar,self.decisions[0],'WEEKLY')
        self.assertLess(end,self.day)
    def test_special_session_and_holiday_calendar(self):
        with self.assertRaises(ConfigError):
            latest_period(self.stock.calendar,stamp(date(2020,1,10)),'WEEKLY')
        first,end=latest_period(self.stock.calendar,stamp(date(2020,1,11)),'WEEKLY')
        self.assertEqual(first,date(2020,1,6))
        self.assertEqual(len(self.stock.calendar.sessions(first,end,stamp(date(2020,1,11)))),5)

    def test_missing_month_bar_no_older_fallback(self):
        missing=replace(self.bench,bars=tuple(b for b in self.bench.bars if b.trading_date!=date(2020,10,15)))
        with self.assertRaisesRegex(ConfigError,'incomplete/invalid'):
            monthly_evidence(missing,self.cfg,self.binding,missing.calendar.start,self.decisions[1])
    def test_delayed_reversal_cannot_hide_in_recovery(self):
        stock=self.changed(self.cross+5,50)
        stock=replace(stock,bars=tuple(replace(b,available_at=self.decisions[3]) if b.trading_date==self.bars[self.cross+5].trading_date else b for b in stock.bars))
        r=self.run_strategy(stock)
        self.assertEqual(r[2].data_status,'REJECTED')
        self.assertEqual(r[3].opportunity.state,'RETIRED')
    def test_exit_despite_regime_and_monthly_block(self):
        cfg=replace(self.cfg,strategy=replace(self.cfg.strategy,candidate=Candidate.B))
        r=self.run_strategy(self.changed(self.cross+4,50),decisions=(self.decisions[1],),cfg=cfg)[0]
        self.assertFalse(r.signal_eligible);self.assertIsNotNone(r.exit_intent)
    def test_out_of_order_and_naive(self):
        for decisions in (tuple(reversed(self.decisions)),(self.decisions[0].replace(tzinfo=None),)):
            with self.assertRaises(ConfigError):self.run_strategy(decisions=decisions)
    def test_tick_future_evidence_and_nan(self):
        r=self.run_strategy(tick=replace(self.tick,available_at=self.decisions[-1]))
        self.assertIsNone(r[1].opportunity.levels)
        levels=self.run_strategy()[1].opportunity.levels
        self.assertEqual(entry_price_issues(levels,D('NaN'),levels.earliest_session),('invalid_price',))
    def test_adjusted_input_not_supported(self):
        from data_fetcher import split_adjusted_view
        view=split_adjusted_view(self.stock,self.bars[0],self.decisions[0])
        view.require_as_of(self.decisions[0])
        with self.assertRaises(ConfigError):replace(self.stock,bars=(view,))
    def test_future_action_does_not_rewrite_history(self):
        day=self.bars[-1].trading_date
        action=CorporateAction('future','STOCK',day,stamp(day),stamp(day),'SPLIT',D(2),'SYNTHETIC')
        self.assertEqual(self.run_strategy(),self.run_strategy(replace(self.stock,actions=(action,))))
    def test_unfinished_month_uses_previous_completed_month(self):
        m=monthly_evidence(self.bench,self.cfg,self.binding,self.bench.calendar.start,self.decisions[-1])
        self.assertEqual(m.month_start,date(2020,10,1))
        self.assertEqual(m.month_end,date(2020,11,1))
    def test_cross_outside_selected_week(self):
        decisions=(stamp(self.bars[self.cross+9].trading_date),)
        self.assertIsNone(self.run_strategy(decisions=decisions)[0].opportunity)
    def test_actual_immediate_veto_not_label_permission(self):
        day=self.bars[self.cross+4].trading_date
        bench=replace(self.bench,bars=tuple(replace(b,high=b.high+D(100)) if b.trading_date==day else b for b in self.bench.bars))
        regimes=replay(bench,self.cfg,self.binding,bench.calendar.start,self.decisions)
        self.assertTrue(regimes[1].immediate_veto)
        r=EMACrossoverStrategy().replay(self.stock,self.cfg,'STOCK',self.stock.calendar.start,self.decisions,
            benchmark_snapshot=bench,benchmark=self.binding,benchmark_start=bench.calendar.start,
            regimes=regimes,tick=self.tick)
        self.assertIsNotNone(r[1].opportunity);self.assertFalse(r[1].signal_eligible)
    def test_config_and_benchmark_binding_isolation(self):
        binding=replace(self.binding,evidence='different synthetic binding')
        with self.assertRaisesRegex(ConfigError,'causal replay'):
            EMACrossoverStrategy().replay(self.stock,self.cfg,'STOCK',self.stock.calendar.start,self.decisions,
                benchmark_snapshot=self.bench,benchmark=binding,benchmark_start=self.bench.calendar.start,
                regimes=self.regimes,tick=self.tick)

    def test_exact_ceiling_end_to_end(self):
        price=D('109.'+'9'*60)
        stock=replace(self.stock,bars=tuple(replace(b,close=price) if b.trading_date==self.day else b for b in self.stock.bars))
        r=self.run_strategy(stock)
        levels=r[1].opportunity.levels
        self.assertEqual(levels.close,price)
        self.assertEqual(levels.ceiling,D('109.95'))
        self.assertTrue(r[1].signal_eligible)
        self.assertEqual(r[-1].opportunity.levels,levels)
        self.assertIn('above_entry_ceiling',entry_price_issues(levels,D(110),levels.earliest_session))

    def test_exact_ceiling_direct_boundaries_contexts(self):
        from fractions import Fraction
        from decimal import ROUND_UP, ROUND_DOWN, Inexact, Rounded
        from strategy import exact_tick_floor
        cases=[('109.'+'9'*60,'0.05','109.95'),
               ('110','0.05','110'),('110.'+'0'*59+'1','0.05','110'),
               ('0.0299999999999999999999999999999999999999999999999999999999999','0.01','0.02'),
               ('1.2499999999999999999999999999999999999999999999999999999999999','0.125','1.125'),
               ('1.25','0.125','1.25'),('1.2500000000000000000000000000000000000000000000000000000000001','0.125','1.25'),
               ('123456789012345678901234567890.123456789','0.000000001','123456789012345678901234567890.123456789'),
               ('199','1E+2','100')]
        for precision in (2,28,50,100):
            for rounding in (ROUND_UP,ROUND_DOWN):
                for price,tick,expected in cases:
                    with self.subTest(precision=precision,rounding=rounding,price=price):
                        with localcontext() as ctx:
                            ctx.prec=precision;ctx.rounding=rounding
                            ctx.traps[Inexact]=True;ctx.traps[Rounded]=True
                            ceiling=exact_tick_floor(D(price),D(tick))
                        self.assertEqual(ceiling,D(expected))
                        p,t,c=map(Fraction,(D(price),D(tick),ceiling))
                        self.assertLessEqual(c,p);self.assertGreater(c+t,p)
                        self.assertEqual((c/t).denominator,1)
        levels=planned_levels(self.stock,self.cfg,replace(self.bars[self.cross+4],close=D(cases[0][0])),D(2),self.decisions[1],self.tick)
        self.assertEqual(levels.ceiling,D('109.95'))
