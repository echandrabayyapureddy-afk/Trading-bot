"""Journal-derived valuation and exact rational unitized NAV; never order execution."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal as D
from fractions import Fraction as F
from typing import Literal
from config import Validated, RiskConfig
from data_records import digest
from execution_engine import exact, require

@dataclass(frozen=True, slots=True)
class Mark(Validated):
    instrument: str
    price: D
    at: datetime
    available_at: datetime
    valid_until: datetime
    series: str
    evidence: str
    basis: Literal['RAW'] = 'RAW'
    origin: Literal['SYNTHETIC'] = 'SYNTHETIC'
    def validate(self):
        require(self.price>0 and self.at<=self.available_at<self.valid_until and bool(self.instrument and self.series and self.evidence),'invalid mark')

def select_mark(marks,instrument,series,at):
    visible=[m for m in marks if m.instrument==instrument and m.available_at<=at and m.at<=at]
    require(bool(visible),'missing mark')
    latest=max(m.at for m in visible); candidates=[m for m in visible if m.at==latest]
    require(len(set(candidates))==1,'conflicting mark')
    m=candidates[0]
    require(m.valid_until>at and m.series==series,'stale/incompatible mark')
    return m

@dataclass(frozen=True, slots=True)
class Valuation:
    account_id: str
    at: datetime
    equity: D | None
    gross: D | None
    unrealized: D | None
    realized: D
    flows: D
    journal_sha256: str
    marks: tuple[Mark, ...]
    issues: tuple[str, ...]


def value(balance,marks,at):
    chosen=[]; issues=list(balance.anomalies); gross=F(0); basis=F(0)
    from config import ConfigError
    for h in balance.holdings:
        try:
            m=select_mark(marks,h.instrument,h.series,at); chosen.append(m)
            gross+=F(m.price)*h.quantity; basis+=F(h.basis)
        except ConfigError as e: issues.append(h.instrument+': '+str(e))
    equity=F(balance.cash)+sum((F(v) for _,v in balance.receivables),F(0))-F(balance.payables)+gross
    return Valuation(balance.account_id,at,None if issues else exact(equity),None if issues else exact(gross),
                     None if issues else exact(gross-basis),balance.realized,balance.flows,
                     balance.journal_sha256,tuple(chosen),tuple(issues))

@dataclass(frozen=True, slots=True)
class Clearance(Validated):
    account_id: str
    at: datetime
    state_sha256: str
    reason: str
    evidence: str
    origin: Literal['SYNTHETIC'] = 'SYNTHETIC'

@dataclass(frozen=True, slots=True)
class Nav:
    account_id: str
    at: datetime
    units: F
    nav: F
    peak: F
    drawdown: F
    latch: int
    flows: F
    lineage: str


def update_nav(previous, valuation, *, pre_flow=None, clearance=None, policy=None):
    """Initial NAV=1. Flow changes require a same-cutoff pre-flow valuation.
    Recovery convention: drawdown strictly below the 5% pause threshold for either latch.
    Clearance binds the recovered, still-latched state hash; peak is never reset.
    """
    policy=policy or RiskConfig(); policy.validate()
    require(not valuation.issues and valuation.equity is not None,'NAV needs complete valuation')
    e=F(valuation.equity); flow=F(valuation.flows)
    if previous is None:
        require(e>0 and flow==e,'initialize from positive cash-only funding')
        state=Nav(valuation.account_id,valuation.at,e,F(1),F(1),F(0),0,flow,digest(valuation))
    else:
        require(previous.account_id==valuation.account_id and valuation.at>=previous.at,'NAV account/time mismatch')
        require(previous.units>0 and e>0,'depleted equity/zero units blocks NAV and resumption')
        units=previous.units; delta=flow-previous.flows
        if delta:
            require(pre_flow is not None and not pre_flow.issues and pre_flow.account_id==valuation.account_id and
                    pre_flow.at==valuation.at and F(pre_flow.flows)==previous.flows and
                    F(pre_flow.equity)+delta==e and pre_flow.equity>0,'missing/inconsistent pre-flow valuation')
            before=F(pre_flow.equity)/units
            units+=delta/before
            require(units>0,'full withdrawal/zero units unsupported')
        nav=e/units; peak=max(previous.peak,nav); dd=1-nav/peak
        latch=max(previous.latch,2 if dd>=F(policy.drawdown_hard) else 1 if dd>=F(policy.drawdown_review) else 0)
        state=Nav(previous.account_id,valuation.at,units,nav,peak,dd,latch,flow,digest((previous.lineage,valuation,pre_flow)))
    if clearance:
        require(clearance.account_id==state.account_id and clearance.at==state.at and
                clearance.state_sha256==nav_hash(state) and bool(clearance.reason and clearance.evidence), 'clearance mismatch/stale')
        require(state.latch>0 and state.drawdown<F(policy.drawdown_review),'premature clearance')
        from dataclasses import replace
        state=replace(state,latch=0,lineage=digest((state.lineage,clearance)))
    return state

def nav_hash(state):
    # Fraction serialization is explicit, no Decimal approximation of thresholds.
    return digest((state.account_id,state.at,tuple((x.numerator,x.denominator) for x in
        (state.units,state.nav,state.peak,state.drawdown,state.flows)),state.latch,state.lineage))

def journal_nav(records, account_id, as_of):
    """Replay durable journal marks, cash flows and clearances. No mutable NAV cache.
    Each cash flow uses the complete valuation immediately before that record.
    Missing/stale marks stop reconstruction; no confident NAV is invented.
    """
    from ledger import reconstruct
    prefix=[]; marks=[]; state=None; seen={}
    for r in records:
        if r.recorded_at>as_of: continue
        if r.event_id in seen and seen[r.event_id]==r: continue
        seen[r.event_id]=r
        before=value(reconstruct(tuple(prefix),account_id,r.recorded_at),tuple(marks),r.recorded_at)
        prefix.append(r)
        b=reconstruct(tuple(prefix),account_id,r.recorded_at)
        require(not b.anomalies,'journal reconciliation blocks NAV')
        if r.kind=='CLEARANCE':
            require(state is not None,'clearance without NAV history')
            c=Clearance(account_id,r.recorded_at,r.parent,r.source,r.evidence)
            state=update_nav(state,before,clearance=c)
            continue
        if r.kind=='MARK':
            marks.append(Mark(r.instrument,r.amount,r.occurred_at,r.recorded_at,r.valid_until,r.series,r.evidence))
        v=value(b,tuple(marks),r.recorded_at)
        state=update_nav(state,v,pre_flow=before if state and r.kind in ('DEPOSIT','WITHDRAW') else None)
    require(state is not None,'empty NAV history')
    return state
