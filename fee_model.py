"""Versioned synthetic fee schedules; no real tariff or operational approval."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal as D
from fractions import Fraction as F
from typing import Literal
from config import Validated, ConfigError
from execution_engine import exact, require
from data_records import digest

COMPONENTS = ('brokerage','stt','stamp','exchange','regulatory','gst','dp')

@dataclass(frozen=True, slots=True)
class FeeRule(Validated):
    name: str
    side: Literal['BUY','SELL','BOTH']
    scope: Literal['FILL','ORDER','INSTRUMENT_DAY','ACCOUNT_EVENT']
    rate: D
    fixed: D
    minimum: D
    maximum: D | None
    quantum: D
    rounding: Literal['UP','HALF_UP','DOWN']
    base_components: tuple[str, ...]
    source: str

    def validate(self):
        require(self.name in COMPONENTS and bool(self.source), 'fee component/source missing')
        require(min(self.rate,self.fixed,self.minimum)>=0 and self.quantum>0, 'invalid fee values')
        require(self.maximum is None or self.maximum>=self.minimum, 'invalid fee cap')

def rounded(value, quantum, mode):
    v=F(value)/F(quantum); q,r=divmod(v.numerator,v.denominator)
    if mode=='UP' and r: q+=1
    if mode=='HALF_UP' and 2*r>=v.denominator: q+=1
    return exact(q*F(quantum))

@dataclass(frozen=True, slots=True)
class FeeSchedule(Validated):
    version: str
    effective_start: datetime
    effective_end: datetime
    available_at: datetime
    approved_at: datetime
    approval_until: datetime
    evidence: str
    rules: tuple[FeeRule, ...]
    status: Literal['VERIFIED','UNVERIFIED'] = 'UNVERIFIED'
    purpose: Literal['SYNTHETIC'] = 'SYNTHETIC'

    def validate(self):
        require(bool(self.version and self.evidence), 'fee provenance missing')
        require(self.effective_start<self.effective_end and self.available_at<=self.approved_at<self.approval_until,'fee intervals invalid')
        require(sorted(r.name for r in self.rules)==sorted(COMPONENTS),'all seven fee components required')
        prior=set()
        for rule in self.rules:
            require(set(rule.base_components)<=prior,'fee base must reference earlier components')
            for name in rule.base_components:
                base=next(r for r in self.rules if r.name==name)
                require(base.scope==rule.scope and (rule.side=='BOTH' or rule.side==base.side),
                        'ambiguous dependent component scope/side')
            prior.add(rule.name)

    def check(self, occurrence, authorization_at):
        require(self.status=='VERIFIED' and self.effective_start<=occurrence<self.effective_end,
                'fee schedule unverified/not historically applicable')
        require(self.approved_at<=authorization_at<self.approval_until and self.available_at<=occurrence,
                'fee evidence/approval unavailable or expired')

@dataclass(frozen=True, slots=True)
class ScopeTotals(Validated):
    scope_id: str
    buy: D
    sell: D
    def validate(self):
        require(bool(self.scope_id) and min(self.buy,self.sell)>=0,'invalid side-aware scope totals')

@dataclass(frozen=True, slots=True)
class FeeQuote:
    items: tuple[tuple[str,D], ...]
    profile_sha256: str
    accrued: tuple[tuple[str,D], ...] = ()
    scope_totals: tuple[tuple[str,ScopeTotals], ...] = ()
    correction_evidence: str | None = None
    @property
    def total(self): return exact(sum((F(v) for _,v in self.items),F(0)))

def quote(schedule, side, turnover, occurrence, authorization_at, *, scopes=None,
          charged=(), previous=None, correction_evidence=None):
    """ScopeTotals binds separate side turnovers to an explicit scope identity.
    Legacy scalar scopes remain one-shot estimates only. Incremental quotes require
    a previous bound quote, never an unbound tuple of prior charge amounts.
    Negative revisions require explicit correction evidence; ordinary totals only grow.
    """
    schedule.check(occurrence,authorization_at)
    require(side in ('BUY','SELL') and F(turnover)>=0,'invalid fee request')
    require(not charged,'unbound charged items ambiguous; supply previous bound quote')
    require(correction_evidence is None or bool(correction_evidence.strip()),'correction evidence missing')
    scopes=scopes or {}; items=[]; totals={}; bound={}
    required={r.scope for r in schedule.rules}
    require(set(scopes)<=required,'unknown fee scope')
    for scope in required:
        raw=scopes.get(scope,turnover if scope=='FILL' else None)
        require(raw is not None,'cumulative fee scope missing')
        if type(raw) is ScopeTotals: bound[scope]=raw
        else:
            require(previous is None and correction_evidence is None,'incremental/corrected quotes require side-aware scopes')
            require(F(raw)>=0,'negative scope turnover')
            bound[scope]=ScopeTotals('ONE_SHOT:'+scope,exact(F(raw)) if side=='BUY' else D(0),
                                    exact(F(raw)) if side=='SELL' else D(0))
    old={}
    if previous is not None:
        require(type(previous) is FeeQuote and previous.profile_sha256==digest(schedule),'previous quote profile mismatch')
        prior=dict(previous.scope_totals)
        require(set(prior)==required and len(previous.scope_totals)==len(required),'previous scopes missing')
        for scope,now in bound.items():
            before=prior[scope]
            require(not before.scope_id.startswith('ONE_SHOT:') and now.scope_id==before.scope_id,'fee scope identity mismatch')
            if correction_evidence is None:
                require(now.buy>=before.buy and now.sell>=before.sell,'decreasing turnover requires correction evidence')
                require((now.sell==before.sell if side=='BUY' else now.buy==before.buy),
                        'opposite-side turnover changed without correction evidence')
        # Recalculate prior accrued totals; do not trust editable caller amounts.
        checked=quote(schedule,side,D(0),occurrence,authorization_at,scopes=prior)
        require(previous.accrued==checked.accrued,'previous accrual mismatch')
        old=dict(previous.accrued)
    else:
        require(correction_evidence is None,'correction requires previous bound quote')
    for r in schedule.rules:
        scope=bound[r.scope]
        applicable=F(scope.buy) if r.side=='BUY' else F(scope.sell) if r.side=='SELL' else F(scope.buy)+F(scope.sell)
        if applicable==0: target=D(0)
        else:
            base=applicable
            if r.base_components: base=sum((F(totals[n]) for n in r.base_components),F(0))
            value=max(base*F(r.rate)+F(r.fixed),F(r.minimum))
            if r.maximum is not None: value=min(value,F(r.maximum))
            target=rounded(value,r.quantum,r.rounding)
        totals[r.name]=target
        items.append((r.name,exact(F(target)-F(old.get(r.name,D(0))))))
    return FeeQuote(tuple(items),digest(schedule),tuple(totals.items()),tuple(sorted(bound.items())),correction_evidence)
