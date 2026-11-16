"""Synthetic, read-only recommendation alternatives; never trading authorization."""
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal as D
from fractions import Fraction as F
from typing import Literal
from config import Validated, ConfigError, Candidate, content_hash, canonical_json
from data_records import digest, IST
from data_validator import daily_as_of
from strategy import StrategyResult, latest_period, entry_price_issues
from regime_detector import RegimeResult
from execution_records import Command, Account, Capabilities, PricePoint
from config_contracts import ExecutionEvent, Evidence
from execution_engine import _signal, _identity, _point, _dependency, exact, require
from accounting_adapter import AccountingDependencies, CostEvidence
from fee_model import quote, FeeSchedule

@dataclass(frozen=True, slots=True)
class Request(Validated):
    signal: StrategyResult
    regime: RegimeResult
    price: PricePoint
    expires_at: datetime

@dataclass(frozen=True, slots=True)
class FeeItem(Validated):
    name: str
    amount: D

@dataclass(frozen=True, slots=True)
class Row(Validated):
    proposal_id: str
    at: datetime
    expires_at: datetime
    status: Literal['BUY-CANDIDATE', 'WATCH', 'SKIP']
    reasons: tuple[str, ...]
    request: Request
    quantity: int
    cash_use: D | None
    fees: tuple[FeeItem, ...]
    planned_risk: D | None
    aggregate_risk: D | None
    median_turnover: D | None
    account_sha256: str
    dependencies_sha256: str
    origin: Literal['SYNTHETIC'] = 'SYNTHETIC'
    target: None = None
    operational_authorized: Literal[False] = False

@dataclass(frozen=True, slots=True)
class Report(Validated):
    at: datetime
    week: tuple[date, date]
    ranked: tuple[Row, ...]
    other: tuple[Row, ...]
    message: str
    operational_authorized: Literal[False] = False


def command(request, config, at, quantity):
    s=request.signal
    e=ExecutionEvent('report-check','MANUAL_SUBMISSION','report-check','report-check','not-submitted',
        config.config_version,content_hash(config),'SIMULATED',at,at,at,
        (Evidence('SYNTHETIC report calculation',digest(s),at),),quantity,None,None)
    return Command('report-check',at,0,s.instrument_id,'report-check','EVENT','BUY',event=e,signal=s)


def evaluate(snapshot, config, account, adapter, capabilities, request, at):
    """Only the concrete Prompt 7 adapter is supported. No fact enters execution."""
    s=request.signal; reasons=[]; q=0; cash=risk=aggregate=score=None; items=(); dep='UNVERIFIED'
    expiry=request.expires_at
    try:
        require(type(adapter) is AccountingDependencies,'computed accounting adapter required')
        require(type(adapter.costs) is CostEvidence and type(adapter.schedule) is FeeSchedule,'cost/fee evidence missing')
        require(adapter.config==config,'adapter configuration mismatch')
        require(type(account) is Account and type(capabilities) is Capabilities,'synthetic contracts required')
        expiry=min(expiry,capabilities.valid_until,adapter.costs.valid_until,adapter.schedule.approval_until,
                   adapter.schedule.effective_end)
        require(at<expiry,'proposal expired')
        require(capabilities.available_at<=at<capabilities.valid_until,'capabilities unavailable')
        future_sessions=snapshot.calendar.sessions(at.astimezone(IST).date(),snapshot.calendar.end,at)
        closes=[x.segments[-1].closes for x in future_sessions if x.segments[-1].closes>at]
        require(bool(closes),'evidence expiry calendar unavailable')
        expiry=min(expiry,closes[0])
        c=command(request,config,at,1)
        levels=_signal(snapshot,config,c,at)
        _identity(snapshot,s.instrument_id,at)
        require(s.candidate==config.strategy.candidate,'candidate mismatch')
        r=request.regime
        require(digest(r)==s.regime_sha256 and r.config_sha256==content_hash(config) and
                r.as_of==s.as_of and r.available_at<=at and r.entry_eligible and not r.immediate_veto,
                'regime unavailable or blocked')
        week=latest_period(snapshot.calendar,at,'WEEKLY')
        require((s.opportunity.week_start,s.opportunity.week_end)==week,'opportunity not from last completed week')
        if s.candidate==Candidate.B:
            m=s.monthly; month=latest_period(snapshot.calendar,s.as_of,'MONTHLY')
            require(m is not None and m.passes and m.available_at<=s.as_of and
                    (m.month_start,m.month_end)==month,'completed monthly evidence missing/stale')
        p=request.price
        _point(snapshot,config,c,capabilities,observation=p)
        require(p.instrument_id==s.instrument_id and p.at==at and p.available_at<=at,'current price unavailable')
        require(not entry_price_issues(levels,p.price,at.astimezone(IST).date()),'price outside entry band or operator delay')
        bars,quality=daily_as_of(snapshot,s.instrument_id,s.initialization_start,s.session+timedelta(days=1),at)
        require(quality.status=='VALID','ranking data rejected')
        require(all((b.price_basis,b.volume_basis,b.corporate_action_treatment)==('RAW','RAW_SHARES','UNADJUSTED') for b in bars),'raw tradable series required')
        require((p.provider,p.provider_version)==(bars[-1].provider,bars[-1].provider_version),'price source mismatch')
        n=config.strategy.ranking_sessions
        require(len(bars)>=n,'insufficient ranking history')
        values=sorted(F(b.close)*F(b.volume) for b in bars[-n:])
        score=exact((values[(n-1)//2]+values[n//2])/2)
        # Scan through the authoritative computed adapter, including fees, NAV and pending orders.
        for quantity in range(int(F(account.settled_cash)/F(levels.ceiling)),0,-1):
            c=command(request,config,at,quantity)
            try: gate=_dependency(adapter,account,c,config,True)
            except ConfigError as error:
                reasons=[str(error)]; continue
            require(F(p.price)+F(gate.adverse_slippage)<=F(levels.ceiling),'adverse price exceeds ceiling')
            fees=quote(adapter.schedule,'BUY',exact(F(levels.ceiling)*quantity),at,at,
                       scopes={x.scope:exact(F(levels.ceiling)*quantity) for x in adapter.schedule.rules})
            require(fees.total==gate.fee,'fee binding mismatch')
            q=quantity; items=tuple(FeeItem(n,v) for n,v in fees.items); cash=exact(F(levels.ceiling)*q+F(fees.total))
            risk=exact(q*(F(levels.ceiling)-F(levels.stop)+F(adapter.costs.remaining_exit_cost_per_share)+F(adapter.costs.adverse_per_share))+F(fees.total))
            pending=sum((o.quantity*(F(o.levels.ceiling)-F(o.levels.stop)+F(adapter.costs.remaining_exit_cost_per_share)+F(adapter.costs.adverse_per_share))+F(o.fee)
                         for o in account.orders if o.role=='BUY' and o.state=='PENDING'),F(0))
            aggregate=exact(F(risk)+pending+sum((F(x.r_position) for x in gate.positions),F(0)))
            dep=digest((gate.evidence,adapter.schedule,adapter.costs,capabilities)); reasons=[]; break
        if not q: reasons=reasons or ['no affordable shares']
    except ConfigError as error: reasons=[str(error)]
    status='BUY-CANDIDATE' if q and not reasons else ('WATCH' if s.opportunity and s.opportunity.state=='ACTIVE' else 'SKIP')
    if reasons: q=0;cash=risk=aggregate=None;items=()
    row=Row('UNBOUND',at,expiry,status,tuple(reasons),request,q,cash,items,risk,aggregate,score,digest(account),dep)
    return replace(row,proposal_id=digest(row))


def weekly_report(snapshot,config,account,adapter,capabilities,requests,at):
    visible=[r for r in requests if r.signal.available_at<=at and r.signal.as_of<=at]
    require(len({r.signal.instrument_id for r in visible})==len(visible),'duplicate/conflicting report instruments')
    rows=[evaluate(snapshot,config,account,adapter,capabilities,r,at) for r in visible]
    ranked=tuple(sorted((r for r in rows if r.status=='BUY-CANDIDATE'),key=lambda r:(-F(r.median_turnover),r.request.signal.instrument_id)))
    other=tuple(sorted((r for r in rows if r.status!='BUY-CANDIDATE'),key=lambda r:r.request.signal.instrument_id))
    return Report(at,latest_period(snapshot.calendar,at,'WEEKLY'),ranked,other,
                  'SYNTHETIC alternatives; human review required; NOT live authorization' if ranked else 'NO TRADE')


def revalidation_issues(proposal,current):
    """Refresh with evaluate at the actual cutoff; changed evidence requires a new review."""
    return tuple(reason for bad,reason in (
        (current.status!='BUY-CANDIDATE','current gates blocked'),
        (current.at>=proposal.expires_at,'approval expired'),
        (current.account_sha256!=proposal.account_sha256,'account changed'),
        (current.dependencies_sha256!=proposal.dependencies_sha256,'dependency evidence changed'),
        (current.quantity!=proposal.quantity or current.cash_use!=proposal.cash_use,'quantity/cash changed'),
        (current.request.signal!=proposal.request.signal,'strategy evidence changed'),
        (current.request.price.price!=proposal.request.price.price,'price changed')) if bad)


def render_report(report):
    """Canonical JSON includes every nested evidence field; suitable for offline review."""
    return canonical_json(report)
