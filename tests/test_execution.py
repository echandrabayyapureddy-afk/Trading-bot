"""Synthetic execution scenarios: no historical outcomes or broker access."""
import unittest
from dataclasses import replace, FrozenInstanceError
from datetime import timedelta
from decimal import Decimal as D, localcontext, ROUND_UP
from fractions import Fraction
from config import BotConfig, ConfigError, content_hash, load_manifest, readiness_issues
from config_contracts import ExecutionEvent, Evidence, PositionRiskContract
from data_records import digest, CorporateAction
from data_validator import daily_as_of
from execution_records import (Capabilities, Funding, PricePoint, Command, DependencyEvidence,
                               REQUIRED_CHECKS)
from execution_engine import replay, exact
from strategy import ExitIntent
import test_strategy as strategy_fixtures
from test_regime_detector import stamp


class FixtureDependencies:
    """Test-only explicit approvals, zero/nonzero fees. NOT a production risk engine."""
    def __init__(self, fee=D(1), slip=D(0), cash=D(10000), approved=True, suspended=False):
        self.fee, self.slip, self.cash = fee, slip, cash
        self.approved, self.suspended = approved, suspended

    def assess(self, state, command, cfg):
        at = command.event.occurred_at
        evidence = Evidence('SYNTHETIC risk input', 'a'*64, at)
        risks = []
        for p in state.positions:
            if not p.quantity:
                continue
            mark = p.entry_price
            metric = exact(Fraction(p.quantity)*(Fraction(mark)-Fraction(p.levels.stop)))
            risks.append(PositionRiskContract(p.trade_id, p.quantity, p.entry_price, mark,
                at, at+timedelta(minutes=1), evidence, p.levels.stop, p.protected_quantity,
                'EXCHANGE_ACTIVE' if p.exit_state == 'ACTIVE' else 'UNKNOWN', p.activation_id,
                D(0), evidence, True, D(0), 'b'*64, 'CONFIRMED', metric, metric, metric))
        return DependencyEvidence(digest(state), cfg, at, 'SYNTHETIC fixed fixture approval',
            self.approved, self.suspended, REQUIRED_CHECKS, self.cash, self.fee, self.slip, tuple(risks))


class ExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        strategy_fixtures.StrategyTests.setUpClass()
        helper = strategy_fixtures.StrategyTests()
        cls.snapshot = helper.stock
        cls.cfg = helper.cfg
        cls.signals = helper.run_strategy()
        cls.selection = cls.signals[1]
        cls.current = cls.signals[2]
        cls.day = cls.selection.opportunity.levels.earliest_session
        cls.open = stamp(cls.day, 9)
        cls.start = cls.selection.as_of
        cls.cap = Capabilities('SYN-v1', cls.snapshot.calendar.available_at,
                               stamp(cls.snapshot.calendar.end), 'SYNTHETIC capabilities', True, True)
        cls.funding = Funding(D(10000), cls.cap.available_at, 'SYNTHETIC settled cash')

    def command(self, name, kind, parent, at, *, role='BUY', order='buy', qty=None,
                price=None, signal=None, point=None, recorded=None, priority=0, protection=None):
        recorded = recorded or at
        evidence = Evidence('SYNTHETIC:'+name, digest(name), at)
        event = ExecutionEvent(name, kind, 'trade', order, parent, self.cfg.config_version,
            content_hash(self.cfg), 'SIMULATED', at, recorded, recorded, (evidence,), qty, price, protection)
        return Command(name, recorded, priority, 'STOCK', 'trade', 'EVENT', role,
                       event=event, signal=signal, point=point)

    def point(self, at=None, price=D(110), kind='OPENING_ASSUMPTION'):
        at = at or self.open
        return PricePoint('STOCK', at, at, price, 'SYN-INDEX', 'v1', 'SYNTHETIC price evidence', kind)

    def chain(self, *, fill=True, price=D(110), qty=2):
        d = self.command('decision', 'DECISION', None, self.start, signal=self.selection)
        a = self.command('approval', 'TRADE_APPROVAL', 'decision', self.start+timedelta(seconds=1))
        s = self.command('submission', 'MANUAL_SUBMISSION', 'approval', self.open-timedelta(minutes=10), qty=qty, signal=self.current)
        ack = self.command('ack', 'ACKNOWLEDGEMENT', 'submission', self.open-timedelta(minutes=9))
        f = self.command('fill', 'FILL', 'submission', self.open, qty=qty, price=price,
                         signal=self.current, point=self.point(price=price))
        return (d,a,s,ack,f) if fill else (d,a,s,ack)

    def protect(self, at=None, quantity=2, stop_type='STOP_MARKET', limit=None):
        at = at or self.open+timedelta(minutes=10)
        d = self.command('pd','DECISION',None,at-timedelta(minutes=3),role='PROTECTIVE',order='stop')
        a = self.command('pa','TRADE_APPROVAL','pd',at-timedelta(minutes=2),role='PROTECTIVE',order='stop')
        s = self.command('ps','MANUAL_SUBMISSION','pa',at-timedelta(minutes=1),role='PROTECTIVE',order='stop',qty=2)
        act = self.command('activation','PROTECTION_ACTIVATION','fill',at,role='PROTECTIVE',order='stop',
                           qty=quantity,price=self.selection.opportunity.levels.stop,protection='EXCHANGE_ACTIVE')
        return (d,a,s,replace(act,stop_type=stop_type,stop_limit=limit))

    def trigger(self, at=None, price=D(90)):
        at = at or self.open+timedelta(minutes=20)
        return Command('trigger',at,0,'STOCK','trade','TRIGGER','PROTECTIVE',point=self.point(at,price,'OBSERVATION'))

    def exit_fill(self, at=None, price=D(90), kind='EXPLICIT_TRADE', role='PROTECTIVE', order='stop', parent='ps'):
        at = at or self.open+timedelta(minutes=21)
        return self.command('exit','FILL',parent,at,role=role,order=order,qty=2,price=price,point=self.point(at,price,kind))

    def run_sim(self, commands=None, *, snapshot=None, adapter='DEFAULT', funding=None, cap=None, as_of=None):
        return replay(snapshot or self.snapshot, self.cfg, funding or self.funding, cap or self.cap,
            self.chain() if commands is None else tuple(commands),
            FixtureDependencies() if adapter=='DEFAULT' else adapter,
            as_of or self.open+timedelta(days=2))

    def reason(self, state, text):
        self.assertTrue(any(text in r for a in state.audit for r in a.reasons), (text,state.audit[-1]))

    def test_open_fill_cash_and_unprotected_exposure(self):
        state = self.run_sim()
        self.assertEqual(state.settled_cash,D(9779))  # 10000 - 2*110 - explicit fee 1
        p=state.positions[0]
        self.assertEqual((p.quantity,p.protected_quantity,p.exit_state),(2,0,'UNPROTECTED'))
        self.assertEqual(p.entry_at,self.open)
        self.assertFalse(state.operational_authorized)

    def test_d1_and_same_close_never_fill(self):
        for at in (self.start, stamp(self.current.session,9)):
            commands=list(self.chain());commands[-1]=replace(commands[-1],recorded_at=at,
                event=replace(commands[-1].event,occurred_at=at,recorded_at=at,notified_at=at),point=self.point(at))
            self.assertFalse(self.run_sim(commands).positions)

    def test_calendar_delay_holiday_special_session(self):
        levels=self.selection.opportunity.levels
        sessions=self.snapshot.calendar.sessions(levels.session+timedelta(days=1),self.snapshot.calendar.end,self.start)
        self.assertEqual(levels.earliest_session,sessions[1].trading_date)
        # Original fixture explicitly includes Jan 6 closure and Jan 11 Saturday.
        jan=self.snapshot.calendar.days
        self.assertFalse(next(d for d in jan if str(d.trading_date)=='2020-01-06').segments)
        self.assertTrue(next(d for d in jan if str(d.trading_date)=='2020-01-11').segments)

    def test_gaps_above_and_at_below_stop(self):
        for price in (D(111),self.selection.opportunity.levels.stop,D(90)):
            state=self.run_sim(self.chain(price=price))
            self.assertFalse(state.positions);self.assertEqual(state.settled_cash,10000)
            self.assertEqual(state.audit[-1].outcome,'REJECTED')

    def test_slippage_not_clipped(self):
        commands=list(self.chain());commands[-1]=replace(commands[-1],event=replace(commands[-1].event,price=D(111)))
        state=self.run_sim(commands,adapter=FixtureDependencies(slip=D(1)))
        self.assertFalse(state.positions);self.reason(state,'slippage breaches')

    def test_unknown_fee_and_zero_cost_explicit(self):
        for adapter in (None,FixtureDependencies(fee=None),FixtureDependencies(slip=None),FixtureDependencies(cash=None)):
            self.assertFalse(self.run_sim(adapter=adapter).positions)
        self.assertEqual(self.run_sim(adapter=FixtureDependencies(fee=D(0))).settled_cash,D(9780))

    def test_risk_missing_or_suspended(self):
        for adapter in (FixtureDependencies(approved=False),FixtureDependencies(suspended=True)):
            self.assertFalse(self.run_sim(adapter=adapter).positions)

    def test_missing_approval_and_causal_inversion(self):
        chain=self.chain()
        self.assertFalse(self.run_sim((chain[0],)+chain[2:]).positions)
        bad=replace(chain[1],event=replace(chain[1].event,occurred_at=self.start-timedelta(seconds=1)))
        self.assertFalse(self.run_sim((chain[0],bad)+chain[2:]).positions)

    def test_late_submission_cannot_backdate_open(self):
        commands=list(self.chain())
        for index in (2,3):
            c=commands[index];at=self.open
            commands[index]=replace(c,recorded_at=at,priority=index,event=replace(c.event,occurred_at=at,recorded_at=at,notified_at=at))
        commands[4]=replace(commands[4],priority=4)
        state=self.run_sim(commands);self.assertFalse(state.positions);self.reason(state,'missed opening')

    def test_delayed_approval_blocks_open(self):
        commands=list(self.chain());a=commands[1];at=self.open+timedelta(minutes=1)
        commands[1]=replace(a,recorded_at=at,event=replace(a.event,occurred_at=at,recorded_at=at,notified_at=at))
        self.assertFalse(self.run_sim(commands).positions)

    def test_late_ack_notification_preserves_fill_time(self):
        commands=list(self.chain());a=commands[3];late=self.open+timedelta(minutes=5)
        commands[3]=replace(a,recorded_at=late,event=replace(a.event,recorded_at=late,notified_at=late))
        state=self.run_sim(commands)
        self.assertEqual(state.positions[0].entry_at,self.open)
        self.assertEqual(next(e for e in state.events if e.kind=='ACKNOWLEDGEMENT').occurred_at,a.event.occurred_at)

    def test_duplicate_idempotence(self):
        commands=self.chain()
        self.assertEqual(self.run_sim(commands),self.run_sim(commands+commands))
        duplicate=replace(commands[-1],command_id='duplicate-fill')
        original=self.run_sim(commands); repeated=self.run_sim(commands+(duplicate,))
        self.assertEqual((original.settled_cash,original.positions,original.orders,original.events),
                         (repeated.settled_cash,repeated.positions,repeated.orders,repeated.events))

    def test_conflicting_event_preserved_and_blocks(self):
        chain=self.chain();conflict=replace(chain[-1],command_id='conflict',priority=1,event=replace(chain[-1].event,price=D(109)))
        state=self.run_sim(chain+(conflict,))
        self.assertEqual(state.positions[0].quantity,2);self.assertTrue(state.entry_blocks)
        self.assertEqual(state.audit[-1].command,conflict)

    def test_actual_isolation(self):
        chain=list(self.chain());chain[0]=replace(chain[0],event=replace(chain[0].event,origin='ACTUAL'))
        state=self.run_sim(chain);self.assertFalse(state.positions);self.reason(state,'ACTUAL')

    def test_protection_is_separate_and_delayed(self):
        commands=self.chain()+self.protect()
        early=self.run_sim(commands,as_of=self.open+timedelta(minutes=5))
        late=self.run_sim(commands)
        self.assertEqual(early.positions[0].protected_quantity,0)
        self.assertEqual(late.positions[0].protected_quantity,2)
        self.assertEqual(late.positions[0].activation_at-self.open,timedelta(minutes=10))

    def test_insufficient_protection_not_completed(self):
        state=self.run_sim(self.chain()+self.protect(quantity=1)+(self.trigger(),self.exit_fill()))
        self.assertEqual(state.positions[0].quantity,2);self.reason(state,'not triggered/covered')

    def test_activation_never_retroactive(self):
        trigger=self.trigger(self.open+timedelta(minutes=1))
        state=self.run_sim(self.chain()+(trigger,)+self.protect())
        self.assertEqual(state.positions[0].exit_state,'ACTIVE');self.assertTrue(state.entry_blocks)
        self.reason(state,'not established after activation')

    def test_stop_market_gap_price_not_trigger(self):
        state=self.run_sim(self.chain()+self.protect()+(self.trigger(),self.exit_fill()))
        self.assertEqual(state.positions[0].quantity,0)
        self.assertEqual(state.unsettled_proceeds,D(179))
        self.assertEqual(state.settled_cash,D(9779))
        self.assertEqual(state.events[-1].price,D(90))

    def test_stop_limit_triggered_unfilled(self):
        state=self.run_sim(self.chain()+self.protect(stop_type='STOP_LIMIT',limit=D(100))+(self.trigger(),self.exit_fill()))
        self.assertEqual(state.positions[0].exit_state,'TRIGGERED_UNFILLED')
        self.assertEqual(state.positions[0].quantity,2);self.assertEqual(state.unsettled_proceeds,0)

    def test_stop_limit_later_explicit_fill(self):
        state=self.run_sim(self.chain()+self.protect(stop_type='STOP_LIMIT',limit=D(100))+(self.trigger(),self.exit_fill(price=D(101))))
        self.assertEqual(state.positions[0].quantity,0);self.assertEqual(state.unsettled_proceeds,201)

    def test_observation_and_touch_do_not_fill(self):
        chain=list(self.chain());chain[-1]=replace(chain[-1],point=self.point(kind='OBSERVATION'))
        self.assertFalse(self.run_sim(chain).positions)
        bar=Command('bar',stamp(self.day),0,'STOCK','trade','BAR','PROTECTIVE',bar_date=self.day)
        state=self.run_sim(self.chain()+self.protect()+(bar,))
        self.assertEqual(state.positions[0].quantity,2);self.assertTrue(state.entry_blocks)
        self.assertEqual(state.audit[-1].outcome,'UNRESOLVED')

    def ordinary(self):
        at=stamp(self.day)
        intent=ExitIntent('intent','STOCK',at,self.day)
        observed=Command('intent',at,0,'STOCK','trade','EXIT_INTENT','ORDINARY',intent=intent)
        d=self.command('od','DECISION',None,at+timedelta(seconds=1),role='ORDINARY',order='ordinary')
        a=self.command('oa','TRADE_APPROVAL','od',at+timedelta(seconds=2),role='ORDINARY',order='ordinary')
        s=self.command('os','MANUAL_SUBMISSION','oa',at+timedelta(seconds=3),role='ORDINARY',order='ordinary',qty=2)
        return (observed,d,a,s)

    def test_ordinary_persists_until_fill_despite_entry_suspension(self):
        commands=self.chain()+self.ordinary()
        state=self.run_sim(commands)
        self.assertIsNone(state.positions[0].intent.resolved_at)
        at=stamp(self.day+timedelta(days=1),9)
        sell=self.exit_fill(at,price=D(108),kind='OPENING_ASSUMPTION',role='ORDINARY',order='ordinary',parent='os')
        class SuspendAfterBuy(FixtureDependencies):
            def assess(inner,account,command,cfg):
                return replace(super().assess(account,command,cfg),entry_suspended=bool(account.positions))
        result=self.run_sim(commands+(sell,),adapter=SuspendAfterBuy())
        self.assertEqual(result.positions[0].intent.resolved_at,at)
        self.assertEqual(result.positions[0].quantity,0)

    def test_same_close_exit_rejected(self):
        cmds=self.chain()+self.ordinary()
        sell=self.exit_fill(stamp(self.day,15),role='ORDINARY',order='ordinary',parent='os')
        self.assertEqual(self.run_sim(cmds+(sell,)).positions[0].quantity,2)

    def test_competing_exits_no_double_sale(self):
        at=stamp(self.day+timedelta(days=1),9)
        ordinary=self.exit_fill(at,price=D(108),kind='OPENING_ASSUMPTION',role='ORDINARY',order='ordinary',parent='os')
        protective=replace(self.exit_fill(at+timedelta(seconds=1)),command_id='second-exit',event=replace(self.exit_fill(at+timedelta(seconds=1)).event,event_id='second-exit'))
        state=self.run_sim(self.chain()+self.protect()+(self.trigger(),)+self.ordinary()+(ordinary,protective))
        self.assertEqual(state.unsettled_proceeds,215);self.assertEqual(state.positions[0].quantity,0)

    def test_partial_entry_and_exit_explicitly_rejected(self):
        commands=list(self.chain());commands[-1]=replace(commands[-1],event=replace(commands[-1].event,quantity=1))
        self.assertFalse(self.run_sim(commands).positions)
        sell=self.exit_fill();sell=replace(sell,event=replace(sell.event,quantity=1))
        state=self.run_sim(self.chain()+self.protect()+(self.trigger(),sell))
        self.assertEqual(state.positions[0].quantity,2);self.reason(state,'partial execution unsupported')

    def test_cash_includes_fee(self):
        state=self.run_sim(funding=replace(self.funding,settled_cash=D(220)))
        self.assertFalse(state.orders);self.reason(state,'insufficient shared settled cash')
        state=self.run_sim(funding=replace(self.funding,settled_cash=D(221)))
        self.assertEqual(state.settled_cash,0)

    def test_wrong_provider_missing_data_and_suspension(self):
        c=list(self.chain());c[-1]=replace(c[-1],point=replace(c[-1].point,provider='OTHER'))
        self.assertFalse(self.run_sim(c).positions)
        for snapshot in (replace(self.snapshot,bars=self.snapshot.bars[1:]),
                         replace(self.snapshot,identities=tuple(replace(i,status='SUSPENDED') for i in self.snapshot.identities))):
            self.assertFalse(self.run_sim(snapshot=snapshot).positions)

    def test_corporate_action_blocks_without_position_corruption(self):
        action=CorporateAction('split','STOCK',self.day,self.open,self.open,'SPLIT',D(2),'SYNTHETIC')
        state=self.run_sim(snapshot=replace(self.snapshot,actions=(action,)))
        self.assertFalse(state.positions);self.assertEqual(state.settled_cash,10000)

    def test_late_revision_cannot_rewrite_fill(self):
        bar=next(b for b in self.snapshot.bars if b.trading_date==self.current.session)
        revision=replace(bar,revision=1,close=D(109),available_at=self.open+timedelta(hours=1))
        appended=replace(self.snapshot,bars=self.snapshot.bars+(revision,))
        self.assertEqual(self.run_sim(),self.run_sim(snapshot=appended))
        before=replace(revision,available_at=self.open-timedelta(minutes=1))
        state=self.run_sim(snapshot=replace(self.snapshot,bars=self.snapshot.bars+(before,)))
        self.assertFalse(state.positions);self.reason(state,'rejected/revised')

    def test_future_append_and_replay_prefix(self):
        commands=self.chain()+self.protect()
        self.assertEqual(self.run_sim(self.chain(),as_of=self.open),self.run_sim(commands,as_of=self.open))
        self.assertEqual(self.run_sim(commands),self.run_sim(tuple(reversed(commands))))
        with self.assertRaises(FrozenInstanceError):self.run_sim().settled_cash=D(0)

    def test_expired_capabilities(self):
        self.assertFalse(self.run_sim(cap=replace(self.cap,valid_until=self.open)).positions)

    def test_missing_open_assumption_no_fill(self):
        self.assertFalse(self.run_sim(cap=replace(self.cap,opening_fill_assumption=False)).positions)

    def test_decimal_context_and_unchanged_config(self):
        before=content_hash(self.cfg);expected=self.run_sim()
        with localcontext() as ctx:
            ctx.prec=3;ctx.rounding=ROUND_UP
            self.assertEqual(self.run_sim(),expected)
        self.assertEqual(content_hash(self.cfg),before)
        self.assertTrue(readiness_issues(self.cfg));self.assertEqual(load_manifest('research_manifest.json').status.value,'UNSEALED')

    def second_instrument(self, number=2):
        name='STOCK'+str(number)
        snapshot=replace(self.snapshot,bars=self.snapshot.bars+tuple(replace(b,instrument_id=name) for b in self.snapshot.bars),
                         identities=self.snapshot.identities+tuple(replace(i,instrument_id=name) for i in self.snapshot.identities))
        def signal(s):
            bars,q=daily_as_of(snapshot,name,s.initialization_start,s.session+timedelta(days=1),s.as_of)
            source=next(b for b in snapshot.bars if b.instrument_id==name and b.trading_date==s.opportunity.levels.session)
            levels=replace(s.opportunity.levels,source_sha256=digest(source))
            ids=tuple(digest(i) for i in snapshot.identities if i.instrument_id==name)
            return replace(s,instrument_id=name,history_lineage=q.lineage,identity_lineage=ids,
                           opportunity=replace(s.opportunity,instrument_id=name,opportunity_id='opp'+str(number),levels=levels))
        commands=[]
        for c in self.chain(fill=False):
            e=c.event
            e=replace(e,event_id=str(number)+e.event_id,parent_id=str(number)+e.parent_id if e.parent_id else None,
                      trade_id='trade'+str(number),order_id='buy'+str(number))
            commands.append(replace(c,command_id=str(number)+c.command_id,instrument_id=name,trade_id=e.trade_id,
                                    event=e,priority=number,signal=signal(c.signal) if c.signal else None))
        return snapshot,tuple(commands)

    def test_shared_cash_priority_atomic_reservation(self):
        snapshot,second=self.second_instrument()
        state=self.run_sim(self.chain(fill=False)+second,snapshot=snapshot,
                           funding=replace(self.funding,settled_cash=D(400)))
        self.assertEqual(len(state.orders),1);self.assertEqual(state.orders[0].instrument_id,'STOCK')
        self.assertEqual(state.orders[0].reservation,221);self.assertEqual(state.settled_cash,400)
        self.reason(state,'insufficient shared settled cash')

    def test_priority_required_for_simultaneous_candidates(self):
        snapshot,second=self.second_instrument()
        with self.assertRaisesRegex(ConfigError,'unique priorities'):
            self.run_sim(self.chain(fill=False)+tuple(replace(c,priority=0) for c in second),snapshot=snapshot)

    def test_one_trade_id_cannot_create_two_pending_positions(self):
        snapshot,second=self.second_instrument()
        second=tuple(replace(c,trade_id='trade',event=replace(c.event,trade_id='trade')) for c in second)
        state=self.run_sim(self.chain(fill=False)+second,snapshot=snapshot)
        self.assertEqual(len(state.orders),1);self.reason(state,'trade id reused')

    def test_unprotected_position_blocks_other_entry(self):
        snapshot,second=self.second_instrument()
        shifted=[]
        for c in second:
            if c.event.kind in ('MANUAL_SUBMISSION','ACKNOWLEDGEMENT'):
                at=self.open+timedelta(minutes=2 if c.event.kind=='MANUAL_SUBMISSION' else 3)
                c=replace(c,recorded_at=at,event=replace(c.event,occurred_at=at,recorded_at=at,notified_at=at))
            shifted.append(c)
        state=self.run_sim(self.chain()+tuple(shifted),snapshot=snapshot)
        self.assertEqual(len(state.orders),1);self.reason(state,'unprotected/triggered')

    def test_protected_position_requires_valid_dual_risk(self):
        snapshot,second=self.second_instrument()
        shifted=[]
        for c in second:
            if c.event.kind in ('MANUAL_SUBMISSION','ACKNOWLEDGEMENT'):
                at=self.open+timedelta(minutes=12 if c.event.kind=='MANUAL_SUBMISSION' else 13)
                c=replace(c,recorded_at=at,event=replace(c.event,occurred_at=at,recorded_at=at,notified_at=at))
            shifted.append(c)
        commands=self.chain()+self.protect()+tuple(shifted)
        good=self.run_sim(commands,snapshot=snapshot)
        self.assertEqual(len(good.orders),3)  # buy, protection, second buy
        class MissingRisk(FixtureDependencies):
            def assess(inner,state,command,cfg):
                return replace(super().assess(state,command,cfg),positions=())
        bad=self.run_sim(commands,snapshot=snapshot,adapter=MissingRisk())
        self.assertEqual(len(bad.orders),2);self.reason(bad,'risk coverage mismatch')

    def test_changed_activation_stop_rejected(self):
        protect=list(self.protect());c=protect[-1]
        protect[-1]=replace(c,event=replace(c.event,price=c.event.price+D(1)))
        state=self.run_sim(self.chain()+tuple(protect))
        self.assertEqual(state.positions[0].protected_quantity,0)

    def test_nonfinite_fractional_and_adjusted_rejected(self):
        with self.assertRaises(ConfigError):replace(self.chain()[-1].event,quantity=D('1.5'))
        with self.assertRaises(ConfigError):replace(self.point(),price=D('NaN'))
        with self.assertRaises(ConfigError):replace(self.point(),basis='SPLIT_ADJUSTED_NONTRADABLE')

    def test_dependency_state_fingerprint_required(self):
        class WrongState(FixtureDependencies):
            def assess(inner,state,command,cfg):
                return replace(super().assess(state,command,cfg),state_sha256='0'*64)
        self.assertFalse(self.run_sim(adapter=WrongState()).positions)

    def test_incomplete_bar_and_stale_signal_rejected(self):
        bar=Command('bar',self.open,0,'STOCK','trade','BAR','PROTECTIVE',bar_date=self.day)
        self.reason(self.run_sim((bar,)),'daily observation rejected')
        commands=list(self.chain());commands[2]=replace(commands[2],signal=self.selection)
        self.assertFalse(self.run_sim(commands).positions)

    def test_ambiguity_blocks_entries_but_exit_remains_available(self):
        bar=Command('bar',stamp(self.day),-1,'STOCK','trade','BAR','PROTECTIVE',bar_date=self.day)
        at=stamp(self.day+timedelta(days=1),9)
        sell=self.exit_fill(at,price=D(108),kind='OPENING_ASSUMPTION',role='ORDINARY',order='ordinary',parent='os')
        state=self.run_sim(self.chain()+(bar,)+self.ordinary()+(sell,))
        self.assertTrue(state.entry_blocks);self.assertEqual(state.positions[0].quantity,0)

    def test_two_pending_positions_use_all_capacity(self):
        snap2,two=self.second_instrument(2);snap3,three=self.second_instrument(3)
        snapshot=replace(snap2,bars=snap2.bars+tuple(b for b in snap3.bars if b.instrument_id=='STOCK3'),
                         identities=snap2.identities+tuple(i for i in snap3.identities if i.instrument_id=='STOCK3'))
        state=self.run_sim(self.chain(fill=False)+two+three,snapshot=snapshot)
        self.assertEqual(len(state.orders),2);self.reason(state,'capacity blocked')

    def test_opening_stop_market_gap_next_session(self):
        at=stamp(self.day+timedelta(days=1),9)
        trigger=replace(self.trigger(at),priority=-1)
        sell=self.exit_fill(at,price=D(80),kind='OPENING_ASSUMPTION')
        state=self.run_sim(self.chain()+self.protect()+(trigger,sell))
        self.assertEqual(state.positions[0].quantity,0);self.assertEqual(state.unsettled_proceeds,159)

    def test_late_state_mutation_is_quarantined(self):
        commands=self.chain()+self.protect()
        late=self.exit_fill(self.open+timedelta(minutes=5))
        late=replace(late,recorded_at=self.open+timedelta(hours=1),event=replace(late.event,
            recorded_at=self.open+timedelta(hours=1),notified_at=self.open+timedelta(hours=1)))
        state=self.run_sim(commands+(late,))
        self.assertEqual(state.positions[0].quantity,2);self.assertTrue(state.entry_blocks)

    def test_trade_point_after_open_requires_explicit_fact(self):
        commands=list(self.chain());at=self.open+timedelta(minutes=1)
        fill=commands[-1]
        commands[-1]=replace(fill,recorded_at=at,event=replace(fill.event,occurred_at=at,recorded_at=at,notified_at=at),
                             point=self.point(at,kind='EXPLICIT_TRADE'),opening=self.point(kind='OBSERVATION'))
        self.assertEqual(self.run_sim(commands).positions[0].entry_at,at)
        commands[-1]=replace(commands[-1],point=self.point(at))
        self.assertFalse(self.run_sim(commands).positions)

    def test_intraday_opening_evidence_and_stop_gap(self):
        commands=list(self.chain());at=self.open+timedelta(minutes=1);fill=commands[-1]
        fill=replace(fill,recorded_at=at,event=replace(fill.event,occurred_at=at,recorded_at=at,notified_at=at),
                     point=self.point(at,kind='EXPLICIT_TRADE'))
        for opening in (None,self.point(price=D(90),kind='OBSERVATION'),
                        self.point(price=self.selection.opportunity.levels.stop,kind='OBSERVATION')):
            self.assertFalse(self.run_sim(commands[:-1]+[replace(fill,opening=opening)]).positions)
        # Above-ceiling open does not invent a fill there; a later explicit trade
        # at the ceiling is separately evidenced and admissible.
        state=self.run_sim(commands[:-1]+[replace(fill,opening=self.point(price=D(115),kind='OBSERVATION'))])
        self.assertEqual(state.positions[0].entry_at,at);self.assertEqual(state.positions[0].entry_price,110)


    def test_late_fill_before_trigger_quarantined_and_direct_guard(self):
        from execution_engine import _sell
        trigger=self.trigger()
        before=self.run_sim(self.chain()+self.protect()+(trigger,))
        p=before.positions[0]
        self.assertEqual(p.trigger_at,trigger.point.at)
        self.assertEqual(p.trigger_command_id,trigger.command_id)
        self.assertEqual(p.trigger_evidence_sha256,digest(trigger.point))
        fill=self.exit_fill(self.open+timedelta(minutes=15))
        receipt=self.open+timedelta(minutes=30)
        fill=replace(fill,recorded_at=receipt,event=replace(fill.event,recorded_at=receipt,notified_at=receipt))
        after=self.run_sim(self.chain()+self.protect()+(trigger,fill))
        self.assertEqual(after.positions,before.positions)
        self.assertEqual(after.settled_cash,before.settled_cash)
        self.assertEqual(after.unsettled_proceeds,0)
        self.assertEqual(after.audit[-1].command,fill)
        self.assertEqual(after.audit[-1].outcome,'REJECTED');self.assertTrue(after.entry_blocks)
        with self.assertRaisesRegex(ConfigError,'precedes trigger'):
            _sell(before,fill,next(o for o in before.orders if o.order_id=='stop'),D(90))

    def test_late_fill_cannot_resolve_future_intent(self):
        from execution_engine import _sell
        commands=self.chain()+self.protect()+(self.trigger(),)+self.ordinary()
        before=self.run_sim(commands)
        fill=self.exit_fill();receipt=stamp(self.day,17)
        fill=replace(fill,recorded_at=receipt,event=replace(fill.event,recorded_at=receipt,notified_at=receipt))
        after=self.run_sim(commands+(fill,))
        self.assertEqual(after.positions,before.positions);self.assertEqual(after.unsettled_proceeds,0)
        self.assertEqual(after.settled_cash,before.settled_cash)
        self.assertIsNone(after.positions[0].intent.resolved_at)
        self.assertEqual(after.audit[-1].command,fill);self.assertTrue(after.entry_blocks)
        with self.assertRaisesRegex(ConfigError,'predates observed intent'):
            _sell(before,fill,next(o for o in before.orders if o.order_id=='stop'),D(90))

    def test_trigger_fill_equal_timestamp_and_valid_late_receipt(self):
        for offset in (0,1):
            trigger=self.trigger();fill=self.exit_fill(trigger.point.at+timedelta(seconds=offset))
            receipt=self.open+timedelta(minutes=30)
            fill=replace(fill,recorded_at=receipt,event=replace(fill.event,recorded_at=receipt,notified_at=receipt))
            commands=self.chain()+self.protect()+(trigger,fill)
            state=self.run_sim(commands)
            self.assertEqual(state.positions[0].quantity,0);self.assertEqual(state.unsettled_proceeds,179)
            self.assertEqual(state.events[-1],fill.event)
            self.assertEqual(state,self.run_sim(commands+(trigger,fill)))
            self.assertEqual(self.run_sim(commands,as_of=trigger.recorded_at),
                             self.run_sim(commands[:-1],as_of=trigger.recorded_at))

    def test_same_timestamp_trigger_requires_prior_receipt_order(self):
        trigger=self.trigger();fill=self.exit_fill(trigger.point.at)
        good=self.run_sim(self.chain()+self.protect()+(replace(trigger,priority=-1),fill))
        self.assertEqual(good.positions[0].quantity,0)
        bad=self.run_sim(self.chain()+self.protect()+(trigger,replace(fill,priority=-1)))
        self.assertEqual(bad.positions[0].quantity,2);self.assertEqual(bad.unsettled_proceeds,0)

    def test_protective_resolution_at_and_after_intent(self):
        from execution_engine import _sell
        commands=self.chain()+self.protect()+(self.trigger(),)+self.ordinary()
        before=self.run_sim(commands)
        observed=before.positions[0].intent.observed_at
        order=next(o for o in before.orders if o.order_id=='stop')
        # Direct transition boundary; the public path separately validates session evidence.
        for at in (observed,observed+timedelta(seconds=1)):
            after=_sell(before,self.exit_fill(at),order,D(90))
            self.assertEqual(after.positions[0].intent.resolved_at,at)
            self.assertEqual(after.positions[0].quantity,0)
            self.assertEqual(after.unsettled_proceeds,179)
            self.assertEqual(after.settled_cash,before.settled_cash)
        fill=self.exit_fill(stamp(self.day+timedelta(days=1),9),kind='OPENING_ASSUMPTION')
        after=self.run_sim(commands+(fill,))
        self.assertEqual(after.positions[0].intent.resolved_at,fill.event.occurred_at)
        self.assertEqual(after.positions[0].quantity,0)
        self.assertEqual(after,self.run_sim(commands+(fill,fill)))

    def test_late_fill_after_unresolved_bar_preserves_account(self):
        bar=Command('bar',stamp(self.day),0,'STOCK','trade','BAR','PROTECTIVE',bar_date=self.day)
        commands=self.chain()+self.protect()+(self.trigger(),bar)
        before=self.run_sim(commands)
        fill=self.exit_fill();receipt=stamp(self.day,17)
        fill=replace(fill,recorded_at=receipt,event=replace(fill.event,recorded_at=receipt,notified_at=receipt))
        after=self.run_sim(commands+(fill,))
        self.assertEqual(after.positions,before.positions)
        self.assertEqual(after.settled_cash,before.settled_cash)
        self.assertEqual(after.unsettled_proceeds,0)
        self.reason(after,'late state-changing occurrence')


if __name__ == '__main__':
    unittest.main()
