"""Prompt 4: synthetic daily regime contracts. No trade or research authorization."""
from dataclasses import dataclass, fields
from datetime import date, datetime, timedelta
from decimal import Decimal as D, Context, localcontext, DecimalException
from typing import Literal
from config import BotConfig, RegimeConfig, Validated, ConfigError, content_hash
from data_records import Snapshot, DailyBar, IST, digest
from data_validator import daily_as_of

Regime = Literal['TRENDING_UP', 'TRENDING_DOWN', 'SIDEWAYS', 'HIGH_RISK']
# Numerical implementation convention; independent of ambient Decimal settings.
NUMERIC = Context(prec=50)
# Prompt 4 explicitly specifies this window; Prompt 2 has no distinct field for it.
ATR_REFERENCE_SESSIONS = 63


@dataclass(frozen=True, slots=True)
class BenchmarkBinding(Validated):
    instrument_id: str
    provider: str
    provider_version: str
    evidence: str
    available_at: datetime
    benchmark: Literal['NIFTY_50'] = 'NIFTY_50'
    kind: Literal['SYNTHETIC_INDEX_LEVEL'] = 'SYNTHETIC_INDEX_LEVEL'

    def validate(self):
        if not all(x.strip() for x in (self.instrument_id, self.provider, self.provider_version, self.evidence)):
            raise ConfigError('explicit benchmark identity/provenance required')


@dataclass(frozen=True, slots=True)
class Indicators(Validated):
    close: D | None = None
    ema: D | None = None
    slope: D | None = None
    atr: D | None = None
    plus_di: D | None = None
    minus_di: D | None = None
    dx: D | None = None
    adx: D | None = None
    atr_reference: D | None = None
    atr_ratio: D | None = None
    recent_vol: D | None = None
    reference_vol: D | None = None
    vol_ratio: D | None = None


@dataclass(frozen=True, slots=True)
class Confirmation(Validated):
    confirmed: Regime | None = None
    pending: Regime | None = None
    count: int = 0
    diagnostic_previous: Regime | None = None


def _advance(state, candidate, *, consecutive, same_session=False):
    if candidate is None:
        return Confirmation(diagnostic_previous=state.confirmed or state.diagnostic_previous)
    if same_session:
        return state
    if candidate == state.confirmed:
        return Confirmation(state.confirmed)
    count = state.count + 1 if consecutive and state.pending == candidate else 1
    return Confirmation(candidate) if count == 2 else Confirmation(state.confirmed, candidate, count, state.diagnostic_previous)


@dataclass(frozen=True, slots=True)
class RegimeResult(Validated):
    as_of: datetime
    session: date | None
    data_status: Literal['VALID', 'REJECTED']
    status: Literal['READY', 'UNKNOWN']
    rejection_reasons: tuple[str, ...]
    indicators: Indicators
    candidate: Regime | None
    confirmation: Confirmation
    immediate_veto: bool
    entry_eligible: bool
    blocking_reasons: tuple[str, ...]
    initialization_start: date
    history_sha256: str
    source_lineage: tuple[str, ...]
    identity_lineage: tuple[str, ...]
    calendar_sha256: str
    benchmark_sha256: str
    config_sha256: str
    available_at: datetime
    previous_result_sha256: str | None
    price_basis: Literal['RAW_SYNTHETIC_INDEX_LEVEL'] = 'RAW_SYNTHETIC_INDEX_LEVEL'
    schema_version: Literal['1.0'] = '1.0'
    trade_authorized: Literal[False] = False


def _smooth(values, period):
    """SMA seed followed by Wilder averages; values contains no unavailable slots."""
    out = [None] * len(values)
    if len(values) >= period:
        out[period-1] = sum(values[:period], D(0)) / period
        for i in range(period, len(values)):
            out[i] = (out[i-1] * (period-1) + values[i]) / period
    return out


def _sample_sd(values):
    # Pairwise differences avoid a rounded mean inventing variance for equal values.
    n = len(values)
    return (sum(((a-b)**2 for i,a in enumerate(values) for b in values[i+1:]), D(0)) / (n*(n-1))).sqrt()


def _geometric(closes):
    """Compare exact rational price ratios before Decimal division or logarithms."""
    if len(closes) < 3:
        return True
    a, b = closes[0].as_integer_ratio(), closes[1].as_integer_ratio()
    numerator, denominator = b[0]*a[1], b[1]*a[0]
    for first, second in zip(closes[1:], closes[2:]):
        x, y = first.as_integer_ratio(), second.as_integer_ratio()
        if y[0]*x[1]*denominator != y[1]*x[0]*numerator:
            return False
    return True


def _volatility(values, closes):
    # Compare the represented prices exactly; Decimal ln may round identical
    # returns differently, regardless of their scale or the working precision.
    return D(0) if _geometric(closes) else _sample_sd(values)


def _indicator_series(bars, cfg):
    """Internal numeric kernel. Public replay must first pass Prompt 3 quality gate."""
    if not bars:
        return ()
    if any(type(b) is not DailyBar for b in bars):
        raise ConfigError('raw DailyBar input required; adjusted views unsupported')
    with localcontext(NUMERIC):
        closes = [b.close for b in bars]
        ema = [None] * len(bars)
        n = cfg.ema_period
        if len(bars) >= n:
            ema[n-1] = sum(closes[:n], D(0)) / n
            alpha = D(2) / (n+1)
            for i in range(n, len(bars)):
                ema[i] = alpha * closes[i] + (1-alpha) * ema[i-1]
        tr, plus, minus = [], [], []
        # First bar has no preceding close/high/low: no TR/DM at index zero.
        for prev, b in zip(bars, bars[1:]):
            tr.append(max(b.high-b.low, abs(b.high-prev.close), abs(b.low-prev.close)))
            up, down = b.high-prev.high, prev.low-b.low
            plus.append(up if up > 0 and up > down else D(0))
            minus.append(down if down > 0 and down > up else D(0))
        atr = [None] + _smooth(tr, cfg.atr_period)
        atr_di = [None] + _smooth(tr, cfg.adx_period)
        pdm = [None] + _smooth(plus, cfg.adx_period)
        mdm = [None] + _smooth(minus, cfg.adx_period)
        pdi, mdi, dx = [None]*len(bars), [None]*len(bars), [None]*len(bars)
        for i, value in enumerate(atr_di):
            if value is not None:
                pdi[i] = D(100)*pdm[i]/value if value else D(0)
                mdi[i] = D(100)*mdm[i]/value if value else D(0)
                total = pdi[i]+mdi[i]
                dx[i] = D(100)*abs(pdi[i]-mdi[i])/total if total else D(0)
        adx = [None]*cfg.adx_period + _smooth(dx[cfg.adx_period:], cfg.adx_period)
        returns = [(b/a).ln() for a,b in zip(closes, closes[1:])]
        output = []
        for i, close in enumerate(closes):
            slope = ((ema[i]-ema[i-cfg.ema_slope_sessions])/cfg.ema_slope_sessions
                     if i >= n-1+cfg.ema_slope_sessions else None)
            prior = atr[max(0,i-ATR_REFERENCE_SESSIONS):i]
            ref = sum(prior,D(0))/len(prior) if len(prior)==ATR_REFERENCE_SESSIONS and None not in prior else None
            ratio = atr[i]/ref if ref is not None and ref > 0 else None
            recent = reference = vol_ratio = None
            r, w = cfg.vol_recent_returns, cfg.vol_reference_returns
            if i >= r:
                recent = _volatility(returns[i-r:i], closes[i-r:i+1])
            if i >= r+w:
                reference = _volatility(returns[i-r-w:i-r], closes[i-r-w:i-r+1])
                vol_ratio = recent/reference if reference > 0 else None
            output.append(Indicators(close,ema[i],slope,atr[i],pdi[i],mdi[i],dx[i],adx[i],ref,ratio,recent,reference,vol_ratio))
        return tuple(output)


def classify(values: Indicators, cfg: RegimeConfig):
    """Candidate and independent veto; missing values never become SIDEWAYS."""
    veto = ((values.atr_ratio is not None and values.atr_ratio >= cfg.atr_spike_ratio) or
            (values.vol_ratio is not None and values.vol_ratio >= cfg.vol_spike_ratio))
    missing = tuple('unavailable_' + f.name for f in fields(values) if getattr(values,f.name) is None)
    if veto:
        return 'HIGH_RISK', True, missing
    if missing:
        return None, False, missing
    if values.adx > cfg.adx_trending:
        if values.close > values.ema and values.slope > 0:
            return 'TRENDING_UP', False, ()
        if values.close < values.ema and values.slope < 0:
            return 'TRENDING_DOWN', False, ()
    return 'SIDEWAYS', False, ()


def replay(snapshot: Snapshot, config: BotConfig, benchmark: BenchmarkBinding,
           initialization_start: date, decisions: tuple[datetime, ...]) -> tuple[RegimeResult, ...]:
    """Pure replay: each cutoff queries its own vintage; no imported mutable state.

    Supply every intended session decision. Missing evaluations break pending
    confirmation. Revisions of already consumed history reject continuation once
    and reset pending state. Subsequent sessions may begin fresh confirmation.
    """
    if type(snapshot) is not Snapshot or type(config) is not BotConfig or type(benchmark) is not BenchmarkBinding:
        raise ConfigError('typed snapshot/config/benchmark required')
    if type(initialization_start) is not date or type(decisions) is not tuple:
        raise ConfigError('explicit initialization date and tuple of decisions required')
    if config.regime != RegimeConfig():
        raise ConfigError('Prompt 4 supports approved regime baseline only; no tuning')
    config.validate()
    if config.data.snapshot_sha256 is not None and config.data.snapshot_sha256 != digest(snapshot):
        raise ConfigError('snapshot pin mismatch')
    for value in decisions:
        if type(value) is not datetime or value.utcoffset() is None:
            raise ConfigError('aware decision timestamps required')
    if any(a > b for a,b in zip(decisions,decisions[1:])):
        raise ConfigError('out-of-order decisions; replay chronologically')
    results, state = [], Confirmation()
    last_session, last_sources, last_ids = None, (), ()
    cfg_hash, cal_hash, binding_hash = content_hash(config), digest(snapshot.calendar), digest(benchmark)
    for decision in decisions:
        reasons, bars, identities = [], (), ()
        session, ordinal = None, None
        try:
            end = decision.astimezone(IST).date()+timedelta(days=1)
            sessions = snapshot.calendar.sessions(initialization_start,end,decision)
            complete = [s for s in sessions if s.segments[-1].closes <= decision]
            if not complete:
                raise ConfigError('no_completed_session')
            session, ordinal = complete[-1].trading_date, len(complete)-1
            bars, quality = daily_as_of(snapshot,benchmark.instrument_id,initialization_start,
                                        session+timedelta(days=1),decision)
            if quality.status != 'VALID':
                reasons.append('daily_quality_rejected')
            reasons.extend(quality.reasons)
            if benchmark.available_at > decision:
                reasons.append('benchmark_evidence_unavailable')
            if config.data.calendar_version is not None and config.data.calendar_version != snapshot.calendar.version:
                reasons.append('calendar_pin_mismatch')
            for b in bars:
                if (b.price_basis,b.volume_basis,b.corporate_action_treatment) != ('RAW','RAW_SHARES','UNADJUSTED'):
                    reasons.append('unsupported_benchmark_basis')
                if (b.provider,b.provider_version) != (benchmark.provider,benchmark.provider_version):
                    reasons.append('benchmark_source_mismatch')
                for key in ('provider','provider_version'):
                    pin = getattr(config.data,key)
                    if pin is not None and pin != getattr(b,key):
                        reasons.append('config_'+key+'_mismatch')
            identities = tuple(i for i in snapshot.identities if i.instrument_id==benchmark.instrument_id and
                               i.available_at<=decision and any(i.start<=b.trading_date<i.end for b in bars))
            # Reject any known action affecting this synthetic index history; no implicit adjustment.
            if any(a.instrument_id==benchmark.instrument_id and a.known_at<=decision and
                   initialization_start < a.effective_date<=session for a in snapshot.actions):
                reasons.append('benchmark_action_requires_unsupported_basis')
        except ConfigError as exc:
            reasons.append(str(exc))
        sources = tuple(digest(b) for b in bars)
        ids = tuple(digest(i) for i in identities)
        if last_sources and (sources[:len(last_sources)] != last_sources or ids != last_ids):
            reasons.append('consumed_history_changed_reset_required')
        values = Indicators()
        if not reasons:
            try:
                values = _indicator_series(bars,config.regime)[-1]
            except (DecimalException, IndexError) as exc:
                reasons.append('numerical_unavailable:'+type(exc).__name__)
        candidate, veto, missing = classify(values,config.regime)
        ready = not reasons and not missing
        same = session is not None and session==last_session
        consecutive = bool(results and ordinal is not None and last_session is not None and
                           ordinal > 0 and complete[ordinal-1].trading_date==last_session)
        # Unknown input resets pending even if a partial measurement proves a veto.
        state = _advance(state,candidate if ready else None,consecutive=consecutive,same_session=same)
        blocking = list(reasons)+list(missing)
        if veto: blocking.append('immediate_severe_risk_veto')
        if candidate!='TRENDING_UP': blocking.append('candidate_not_trending_up')
        if state.confirmed!='TRENDING_UP': blocking.append('no_confirmed_trending_up')
        available = max([decision] + [b.available_at for b in bars] + [i.available_at for i in identities])
        # decision is the conservative availability of this audited evaluation, incl. confirmation history.
        results.append(RegimeResult(decision,session,'REJECTED' if reasons else 'VALID',
            'READY' if ready else 'UNKNOWN',tuple(sorted(set(reasons+list(missing)))), values,
            candidate,state,veto,not blocking,tuple(sorted(set(blocking))),initialization_start,
            digest((initialization_start,sources,ids,cal_hash,binding_hash,cfg_hash)),sources,ids,
            cal_hash,binding_hash,cfg_hash,available,digest(results[-1]) if results else None))
        last_session, last_sources, last_ids = session, sources, ids
    return tuple(results)
