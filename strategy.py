"""Prompt 5 synthetic signal contracts. No orders, sizing or research authority."""
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal as D, localcontext, DecimalException
from typing import Literal, Protocol
from config import BotConfig, StrategyConfig, RegimeConfig, Candidate, Validated, ConfigError, content_hash
from data_records import Snapshot, IST, digest
from data_validator import daily_as_of
from data_fetcher import period_bounds, completed_candle
from regime_detector import BenchmarkBinding, RegimeResult, replay as regime_replay, NUMERIC


@dataclass(frozen=True, slots=True)
class TickEvidence(Validated):
    instrument_id: str
    tick: D
    start: date
    end: date
    available_at: datetime
    evidence: str
    basis: Literal['RAW'] = 'RAW'
    origin: Literal['SYNTHETIC'] = 'SYNTHETIC'

    def validate(self):
        if self.tick <= 0 or self.start >= self.end or not self.evidence.strip():
            raise ConfigError('invalid tick evidence')


@dataclass(frozen=True, slots=True)
class PlannedLevels(Validated):
    proposal_at: datetime
    session: date
    close: D
    atr: D
    stop: D
    ceiling: D
    tick_sha256: str
    source_sha256: str
    earliest_session: date
    basis: Literal['RAW'] = 'RAW'
    active_protection: Literal[False] = False


@dataclass(frozen=True, slots=True)
class Opportunity(Validated):
    opportunity_id: str
    instrument_id: str
    candidate: Candidate
    crossover_date: date
    week_start: date
    week_end: date
    selected_at: datetime
    state: Literal['ACTIVE', 'RETIRED']
    levels: PlannedLevels | None
    retirement_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ExitIntent(Validated):
    intent_id: str
    instrument_id: str
    observed_at: datetime
    session: date
    resolved_at: datetime | None = None
    resolution_evidence: str | None = None


@dataclass(frozen=True, slots=True)
class ExitResolution(Validated):
    intent_id: str
    at: datetime
    evidence: str

    def validate(self):
        if not self.evidence.strip():
            raise ConfigError('resolution evidence required')


@dataclass(frozen=True, slots=True)
class MonthlyEvidence(Validated):
    month_start: date
    month_end: date
    final_session: date
    close: D
    daily_ema200: D
    available_at: datetime
    lineage: str
    passes: bool


@dataclass(frozen=True, slots=True)
class StrategyResult(Validated):
    instrument_id: str
    candidate: Candidate
    as_of: datetime
    session: date | None
    data_status: Literal['VALID', 'REJECTED']
    reasons: tuple[str, ...]
    fast: D | None
    slow: D | None
    atr: D | None
    opportunity: Opportunity | None
    exit_intent: ExitIntent | None
    monthly: MonthlyEvidence | None
    regime_sha256: str
    signal_eligible: bool
    history_lineage: tuple[str, ...]
    identity_lineage: tuple[str, ...]
    calendar_sha256: str
    config_sha256: str
    initialization_start: date
    available_at: datetime
    strategy_version: Literal['EMA_CROSS_1.0'] = 'EMA_CROSS_1.0'
    basis: Literal['RAW'] = 'RAW'
    downstream_checks: tuple[str, ...] = ('portfolio_cash_risk', 'approval', 'manual_placement',
        'broker_profiles', 'protection_reconciliation', 'operator_delay_operational_unapproved')
    operational_authorized: Literal[False] = False


class Strategy(Protocol):
    def replay(self, snapshot: Snapshot, config: BotConfig, instrument_id: str,
               initialization_start: date, decisions: tuple[datetime, ...], *,
               benchmark_snapshot: Snapshot, benchmark: BenchmarkBinding,
               benchmark_start: date, regimes: tuple[RegimeResult, ...],
               tick: TickEvidence | None, resolutions: tuple[ExitResolution, ...] = ()) -> tuple[StrategyResult, ...]: ...


def ema(closes, period):
    """SMA first N closes at index N-1; alpha=2/(N+1), no partial seed."""
    with localcontext(NUMERIC):
        out = [None]*len(closes)
        if len(closes) >= period:
            out[period-1] = sum(closes[:period], D(0))/period
            alpha = D(2)/(period+1)
            for i in range(period, len(closes)):
                out[i] = alpha*closes[i]+(1-alpha)*out[i-1]
        return tuple(out)


def atr_series(bars, period):
    with localcontext(NUMERIC):
        tr = [max(b.high-b.low, abs(b.high-a.close), abs(b.low-a.close)) for a,b in zip(bars,bars[1:])]
        out = [None]*len(bars)
        if len(tr) >= period:
            out[period] = sum(tr[:period],D(0))/period
            for i in range(period+1,len(bars)):
                out[i] = (out[i-1]*(period-1)+tr[i-1])/period
        return tuple(out)


def latest_period(calendar, decision, timeframe):
    """Choose by calendar completion, NEVER by which bars happen to be present."""
    day = decision.astimezone(IST).date()
    start,end = period_bounds(day,timeframe)
    sessions = calendar.sessions(start,end,decision)
    if not sessions or sessions[-1].segments[-1].closes > decision:
        start,end = period_bounds(start-timedelta(days=1),timeframe)
        sessions = calendar.sessions(start,end,decision)
    if not sessions or sessions[-1].segments[-1].closes > decision:
        raise ConfigError('no completed period')
    return start,end


def _history(snapshot, config, instrument, start, end, decision):
    bars,q = daily_as_of(snapshot,instrument,start,end,decision)
    if q.status != 'VALID' or not bars:
        raise ConfigError('daily_rejected:'+','.join(q.reasons))
    for key,actual in (('calendar_version',snapshot.calendar.version),('snapshot_sha256',digest(snapshot))):
        pin=getattr(config.data,key)
        if pin is not None and pin != actual: raise ConfigError(key+'_pin_mismatch')
    for b in bars:
        for key in ('provider','provider_version'):
            pin=getattr(config.data,key)
            if pin is not None and pin != getattr(b,key): raise ConfigError(key+'_pin_mismatch')
        if (b.price_basis,b.volume_basis,b.corporate_action_treatment)!=('RAW','RAW_SHARES','UNADJUSTED'):
            raise ConfigError('unsupported_price_basis')
    if any(a.instrument_id==instrument and a.known_at<=decision and
           start<a.effective_date<=bars[-1].trading_date for a in snapshot.actions):
        raise ConfigError('corporate_action_requires_unsupported_conversion')
    return bars


def monthly_evidence(snapshot, config, binding, start, decision):
    if binding.available_at>decision: raise ConfigError('benchmark_unavailable')
    first,end=latest_period(snapshot.calendar,decision,'MONTHLY')
    candle=completed_candle(snapshot,binding.instrument_id,first,'MONTHLY',decision)
    bars=_history(snapshot,config,binding.instrument_id,start,
                  candle.final_session_close.astimezone(IST).date()+timedelta(days=1),decision)
    if any((b.provider,b.provider_version)!=(binding.provider,binding.provider_version) for b in bars):
        raise ConfigError('benchmark_provider_mismatch')
    value=ema(tuple(b.close for b in bars),config.regime.ema_period)[-1]
    if value is None: raise ConfigError('monthly_ema_warmup')
    return MonthlyEvidence(first,end,bars[-1].trading_date,candle.close,value,decision,
                           digest((candle,tuple(digest(b) for b in bars),digest(binding),start)),candle.close>value)


def exact_tick_floor(price: D, tick: D) -> D:
    """Integer quotient and exact Decimal tuple construction, independent of context."""
    if type(price) is not D or type(tick) is not D or not price.is_finite() or not tick.is_finite() or price < 0 or tick <= 0:
        raise ConfigError('finite nonnegative price and positive tick required')
    pn, pd = price.as_integer_ratio()
    tn, td = tick.as_integer_ratio()
    count = (pn * td) // (pd * tn)
    parts = tick.as_tuple()
    coefficient = 0
    for digit in parts.digits:
        coefficient = coefficient * 10 + digit
    # Decimal(int) and Decimal(tuple) are exact constructors: no multiply,
    # divide, scaleb or quantize operation can round the reconstructed multiple.
    digits = D(count * coefficient).as_tuple().digits
    return D((0, digits, parts.exponent))


def planned_levels(snapshot, config, bar, atr, decision, tick):
    if tick is None or tick.instrument_id!=bar.instrument_id or tick.available_at>decision or not tick.start<=bar.trading_date<tick.end:
        raise ConfigError('tick_evidence_missing_or_inapplicable')
    if atr is None: raise ConfigError('atr_warmup')
    with localcontext(NUMERIC):
        stop=bar.close-config.strategy.stop_atr_multiple*atr
    ceiling=exact_tick_floor(bar.close,tick.tick)
    if not 0<stop<ceiling: raise ConfigError('invalid_planned_levels')
    future=snapshot.calendar.sessions(bar.trading_date+timedelta(days=1),snapshot.calendar.end,decision)
    if len(future)<2: raise ConfigError('delay_calendar_coverage_missing')
    return PlannedLevels(decision,bar.trading_date,bar.close,atr,stop,ceiling,digest(tick),digest(bar),future[1].trading_date)


def entry_price_issues(levels, price, session):
    """Price/date necessary conditions only; no fill, timing or order inference."""
    if type(price) is not D or not price.is_finite() or price<=0: return ('invalid_price',)
    issues=[]
    if session<levels.earliest_session: issues.append('intervening_session_not_completed')
    if price>levels.ceiling: issues.append('above_entry_ceiling')
    if price<=levels.stop: issues.append('at_or_below_protective_level')
    return tuple(issues)


class EMACrossoverStrategy:
    def replay(self, snapshot, config, instrument_id, initialization_start, decisions, *,
               benchmark_snapshot, benchmark, benchmark_start, regimes, tick, resolutions=()):
        if type(snapshot) is not Snapshot or type(config) is not BotConfig:
            raise ConfigError('typed snapshot and config required')
        config.validate()
        if config.strategy!=replace(StrategyConfig(),candidate=config.strategy.candidate) or config.regime!=RegimeConfig() or config.execution.operator_delay_sessions!=1:
            raise ConfigError('approved baseline only')
        # Bind supplied evidence to an independently reproducible Prompt 4 replay,
        # including confirmation history, benchmark, config, vintage and cutoff.
        expected=regime_replay(benchmark_snapshot,config,benchmark,benchmark_start,decisions)
        if type(regimes) is not tuple or regimes!=expected:
            raise ConfigError('regime evidence does not match causal replay')
        if type(resolutions) is not tuple or any(type(r) is not ExitResolution for r in resolutions):
            raise ConfigError('typed resolutions required')
        out=[]; opportunity=None; intent=None; consumed=(); last_valid=None; last_week=None; consumed_ids=()
        for decision,regime in zip(decisions,regimes):
            reasons=[]; bars=(); ids=(); fast=slow=atr=None; monthly=None; session=None
            data_status='VALID'
            try:
                end=decision.astimezone(IST).date()+timedelta(days=1)
                sessions=snapshot.calendar.sessions(initialization_start,end,decision)
                complete=[s for s in sessions if s.segments[-1].closes<=decision]
                if not complete: raise ConfigError('no_completed_session')
                session=complete[-1].trading_date
                bars=_history(snapshot,config,instrument_id,initialization_start,session+timedelta(days=1),decision)
                ids=tuple(digest(i) for i in snapshot.identities if i.instrument_id==instrument_id and
                          i.available_at<=decision and any(i.start<=b.trading_date<i.end for b in bars))
                lineage=tuple(digest(b) for b in bars)
                changed=bool(consumed and (lineage[:len(consumed)]!=consumed or ids!=consumed_ids))
                f=ema(tuple(b.close for b in bars),config.strategy.fast_ema)
                s=ema(tuple(b.close for b in bars),config.strategy.slow_ema)
                a=atr_series(bars,config.regime.atr_period)
                fast,slow,atr=f[-1],s[-1],a[-1]
                if slow is None: raise ConfigError('ema_warmup')
                # Inspect all intervening completed sessions, including late recovery.
                invalid=[b for i,b in enumerate(bars) if s[i] is not None and f[i]<=s[i] and
                         (b.trading_date >= (last_valid if last_valid is not None else session))]
                if intent and intent.resolved_at is None:
                    matches=[r for r in resolutions if r.intent_id==intent.intent_id and intent.observed_at<=r.at<=decision]
                    if len(matches)>1: raise ConfigError('conflicting_exit_resolutions')
                    if matches: intent=replace(intent,resolved_at=matches[0].at,resolution_evidence=matches[0].evidence)
                if invalid and (intent is None or (intent.resolved_at is not None and invalid[-1].session_close>intent.resolved_at)):
                    b=invalid[-1];intent=ExitIntent(digest((instrument_id,b.trading_date,decision)),instrument_id,decision,b.trading_date)
                if opportunity and opportunity.state=='ACTIVE' and (changed or any(b.trading_date>=opportunity.crossover_date for b in invalid)):
                    opportunity=replace(opportunity,state='RETIRED',retirement_reason='history_revision' if changed else 'daily_fast_le_slow')
                consumed=lineage;consumed_ids=ids;last_valid=session
                if changed: reasons.append('history_revision_requires_later_selection')
                first,end=latest_period(snapshot.calendar,decision,'WEEKLY')
                completed_candle(snapshot,instrument_id,first,'WEEKLY',decision)
                indices=[i for i,b in enumerate(bars) if first<=b.trading_date<end]
                crosses=[i for i in indices if i>0 and s[i-1] is not None and f[i-1]<=s[i-1] and f[i]>s[i]]
                # Selection identity is consumed once, including a no-event week.
                if changed: last_week=first
                if first!=last_week and not changed:
                    last_week=first
                    if crosses and f[indices[-1]]>s[indices[-1]]:
                        cross=bars[crosses[-1]].trading_date
                        levels=None
                        try: levels=planned_levels(snapshot,config,bars[-1],atr,decision,tick)
                        except ConfigError as exc: reasons.append(str(exc))
                        opportunity=Opportunity(digest((instrument_id,config.strategy.candidate,first,content_hash(config),initialization_start)),
                            instrument_id,config.strategy.candidate,cross,first,end,decision,'ACTIVE',levels)
                        # Later daily invalidation cannot be hidden by a late selection.
                        if any(b.trading_date>cross and s[i] is not None and f[i]<=s[i] for i,b in enumerate(bars)):
                            opportunity=replace(opportunity,state='RETIRED',retirement_reason='daily_fast_le_slow')
            except (ConfigError,DecimalException) as exc:
                data_status='REJECTED';reasons.append(str(exc))
            if config.strategy.candidate==Candidate.B:
                try:
                    monthly=monthly_evidence(benchmark_snapshot,config,benchmark,benchmark_start,decision)
                    if not monthly.passes: reasons.append('monthly_filter_failed')
                except (ConfigError,DecimalException) as exc: reasons.append('monthly_unavailable:'+str(exc))
            if not regime.entry_eligible: reasons.append('regime_entry_blocked')
            if regime.session!=session: reasons.append('regime_session_mismatch')
            if opportunity is None or opportunity.state!='ACTIVE': reasons.append('no_active_opportunity')
            elif opportunity.levels is None: reasons.append('frozen_proposal_unavailable')
            elif bars and bars[-1].close<=opportunity.levels.stop: reasons.append('at_or_below_frozen_stop')
            if intent and intent.resolved_at is None: reasons.append('unresolved_ordinary_exit')
            out.append(StrategyResult(instrument_id,config.strategy.candidate,decision,session,data_status,
                tuple(sorted(set(reasons))),fast,slow,atr,opportunity,intent,monthly,digest(regime),not reasons,
                tuple(digest(b) for b in bars),ids,digest(snapshot.calendar),content_hash(config),initialization_start,decision))
        return tuple(out)
