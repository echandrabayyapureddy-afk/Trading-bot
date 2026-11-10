"""Immutable input contracts only: no portfolio engine, orders or event persistence.

Semantic validation is authoritative; JSON Schemas are structural. An actual
anomalous event is retained as a record; reconciliation issues deny new entries.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal as D, localcontext
from typing import Literal
from config import Validated, ConfigError, _sha, _typed, content_hash

Purpose = Literal['SYNTHETIC', 'RESEARCH', 'OPERATIONAL']
Protection = Literal['UNKNOWN', 'PLANNED', 'SUBMITTED', 'BROKER_HELD_CONDITIONAL',
                     'EXCHANGE_ACTIVE', 'TRIGGERED_UNFILLED', 'CANCELLED', 'EXPIRED']

@dataclass(frozen=True, slots=True)
class Evidence(Validated):
    reference: str
    sha256: str
    available_at: datetime

    def validate(self):
        _sha(self.sha256, 'evidence hash')

@dataclass(frozen=True, slots=True)
class ExecutionAssumptions(Validated):
    """Typed duplicated inputs; narrative specification is not an executable model."""
    order_cutoff_rule: str | None = None
    protective_order_type: Literal['STOP_MARKET', 'STOP_LIMIT'] | None = None
    fee_source_reference: str | None = None
    slippage_bps: D | None = None
    fixed_execution_allowance_inr: D | None = None

    def validate(self):
        for value in (self.slippage_bps, self.fixed_execution_allowance_inr):
            if value is not None and value < 0:
                raise ConfigError('negative execution assumption')

@dataclass(frozen=True, slots=True)
class ProfileBody(Validated):
    kind: Literal['BROKER', 'FEES', 'SLIPPAGE', 'ADVERSE_EXECUTION']
    version: str
    purpose: Purpose
    status: Literal['UNVERIFIED', 'VERIFIED', 'UNSUPPORTED']
    evidence: tuple[Evidence, ...]
    verified_at: datetime | None
    effective_start: datetime | None
    effective_end: datetime | None
    validity_basis: Evidence | None
    # Immutable content, not merely an external mutable URL.
    specification: str | None
    assumptions: ExecutionAssumptions | None = None
    knowledge_basis: Literal['UNVERIFIED', 'POINT_IN_TIME', 'RETROSPECTIVE_RESEARCH'] = 'UNVERIFIED'

    def validate(self):
        if (self.effective_start is None) != (self.effective_end is None):
            raise ConfigError('both profile validity endpoints required')
        if self.effective_start is not None and self.effective_start >= self.effective_end:
            raise ConfigError('empty profile validity')
        if self.verified_at and any(e.available_at > self.verified_at for e in self.evidence):
            raise ConfigError('verification predates evidence')

@dataclass(frozen=True, slots=True)
class ProfileApproval(Validated):
    version: str
    content_sha256: str
    purpose: Purpose
    approved_at: datetime
    reviewers: tuple[str, ...]
    evidence: Evidence
    validity_mode: Literal['UNVERIFIED', 'EXPIRES', 'NO_SCHEDULED_EXPIRY'] = 'UNVERIFIED'
    valid_until: datetime | None = None
    validity_evidence: Evidence | None = None
    revoked_at: datetime | None = None

    def validate(self):
        if self.validity_mode == 'EXPIRES' and (self.valid_until is None or self.valid_until <= self.approved_at):
            raise ConfigError('approval expiry must follow approval')
        if self.validity_mode != 'EXPIRES' and self.valid_until is not None:
            raise ConfigError('expiry requires EXPIRES mode')
        if self.revoked_at is not None and self.revoked_at < self.approved_at:
            raise ConfigError('revocation precedes approval')
        _sha(self.content_sha256, 'approved profile hash')
        if len(set(self.reviewers)) < 2:
            raise ConfigError('two distinct profile reviewers required')
        if self.evidence.available_at > self.approved_at:
            raise ConfigError('approval evidence unavailable')

@dataclass(frozen=True, slots=True)
class VerificationProfile(Validated):
    body: ProfileBody
    content_sha256: str
    approval: ProfileApproval | None

    def validate(self):
        _sha(self.content_sha256, 'profile hash')
        if content_hash(self.body) != self.content_sha256:
            raise ConfigError('altered profile')
        if self.approval and (self.approval.version != self.body.version or
                self.approval.content_sha256 != self.content_sha256 or
                self.approval.purpose != self.body.purpose):
            raise ConfigError('profile approval mismatch')

    def issues(self, as_of: datetime, purpose: Purpose, *,
               historical_start: datetime | None = None,
               historical_end: datetime | None = None) -> tuple[str, ...]:
        """as_of is the evidence/approval cutoff, not historical applicability.

        No historical window means point-in-time use at as_of. Research windows
        are [start,end); retrospective assumptions are explicitly labelled.
        """
        _typed(as_of, datetime, 'as_of', decode=False)
        _typed(purpose, Purpose, 'purpose', decode=False)
        historical = historical_start is not None or historical_end is not None
        if historical:
            _typed(historical_start, datetime, 'historical_start', decode=False)
            _typed(historical_end, datetime, 'historical_end', decode=False)
            if purpose != 'RESEARCH' or not historical_start < historical_end <= as_of:
                raise ConfigError('invalid historical research window/cutoff')
        b, a = self.body, self.approval
        result = []
        if b.purpose != purpose: result.append('profile purpose mismatch')
        if b.status != 'VERIFIED': result.append('profile not verified')
        if not b.evidence or b.specification is None: result.append('missing evidence/content')
        if b.verified_at is None or b.verified_at > as_of: result.append('verification unavailable')
        if b.validity_basis is None or b.validity_basis.available_at > as_of:
            result.append('applicability basis unavailable')
        if b.effective_start is None or (historical and not
                b.effective_start <= historical_start < historical_end <= b.effective_end) or (
                not historical and not b.effective_start <= as_of < b.effective_end):
            result.append('profile outside applicability')
        if any(e.available_at > as_of for e in b.evidence): result.append('future evidence')
        if b.knowledge_basis == 'UNVERIFIED': result.append('knowledge basis unverified')
        if b.knowledge_basis == 'RETROSPECTIVE_RESEARCH' and purpose != 'RESEARCH':
            result.append('retrospective assumptions are research-only')
        if historical and b.knowledge_basis == 'POINT_IN_TIME':
            sources = b.evidence + (() if b.validity_basis is None else (b.validity_basis,))
            if any(e.available_at > historical_start for e in sources):
                result.append('point-in-time source unavailable at historical start')
        if a is None or a.approved_at > as_of: result.append('approval unavailable')
        else:
            if b.verified_at is None or a.approved_at < b.verified_at: result.append('approval before verification')
            if a.validity_mode == 'UNVERIFIED' or a.validity_evidence is None:
                result.append('approval validity unverified')
            elif a.validity_evidence.available_at > min(as_of, a.approved_at):
                result.append('approval validity evidence unavailable')
            if a.valid_until is not None and as_of >= a.valid_until: result.append('approval expired')
            if a.revoked_at is not None and as_of >= a.revoked_at: result.append('approval revoked')
        return tuple(result)

@dataclass(frozen=True, slots=True)
class ExecutionEvent(Validated):
    event_id: str
    kind: Literal['DECISION', 'TRADE_APPROVAL', 'MANUAL_SUBMISSION', 'ACKNOWLEDGEMENT',
                  'FILL', 'PROTECTION_ACTIVATION']
    trade_id: str
    order_id: str | None
    parent_id: str | None
    config_version: str
    config_sha256: str
    origin: Literal['ACTUAL', 'SIMULATED']
    occurred_at: datetime
    recorded_at: datetime
    notified_at: datetime | None
    evidence: tuple[Evidence, ...]
    quantity: int | None
    price: D | None
    protection_state: Protection | None

    def validate(self):
        _sha(self.config_sha256, 'event config hash')
        if not self.evidence: raise ConfigError('event evidence required')
        if self.quantity is not None and self.quantity <= 0: raise ConfigError('positive whole quantity required')
        if self.price is not None and self.price <= 0: raise ConfigError('positive price required')
        if self.kind == 'FILL' and (self.quantity is None or self.price is None):
            raise ConfigError('actual fill terms required')
        if self.kind == 'PROTECTION_ACTIVATION' and (self.quantity is None or self.price is None or self.protection_state is None):
            raise ConfigError('explicit activation terms required')
        if self.origin == 'SIMULATED' and self.recorded_at < self.occurred_at:
            raise ConfigError('simulated recording precedes occurrence')


def event_issues(events: tuple[ExecutionEvent, ...], as_of: datetime) -> tuple[str, ...]:
    """Read-only batch validation; never sort away, rewrite or discard actual facts."""
    _typed(events, tuple[ExecutionEvent, ...], 'events', decode=False)
    _typed(as_of, datetime, 'as_of', decode=False)
    result = []
    by_id = {e.event_id:e for e in events}
    if len(by_id) != len(events): result.append('duplicate event identifiers')
    parent_kinds = {'TRADE_APPROVAL': ('DECISION',), 'MANUAL_SUBMISSION': ('TRADE_APPROVAL',),
                    'ACKNOWLEDGEMENT': ('MANUAL_SUBMISSION',), 'FILL': ('MANUAL_SUBMISSION',),
                    'PROTECTION_ACTIVATION': ('FILL',)}
    for e in events:
        if e.recorded_at < e.occurred_at or (e.notified_at is not None and
                not e.occurred_at <= e.notified_at <= e.recorded_at):
            result.append(e.event_id + ': anomalous observation timing')
        if max(e.occurred_at, e.recorded_at) > as_of or any(x.available_at > min(as_of, e.recorded_at) for x in e.evidence):
            result.append(e.event_id + ': unavailable at decision')
        if e.kind == 'DECISION':
            if e.parent_id is not None: result.append(e.event_id + ': decision has parent')
            continue
        p = by_id.get(e.parent_id)
        if p is None or p.kind not in parent_kinds[e.kind]:
            result.append(e.event_id + ': missing/invalid causal parent')
            continue
        if (e.trade_id, e.config_version, e.config_sha256, e.origin) != (p.trade_id, p.config_version, p.config_sha256, p.origin):
            result.append(e.event_id + ': inconsistent linked identity')
        if e.occurred_at < p.occurred_at: result.append(e.event_id + ': causal inversion')
        if e.kind in ('MANUAL_SUBMISSION', 'ACKNOWLEDGEMENT', 'FILL', 'PROTECTION_ACTIVATION') and e.order_id is None:
            result.append(e.event_id + ': order id missing')
        if e.kind in ('ACKNOWLEDGEMENT', 'FILL') and e.order_id != p.order_id:
            result.append(e.event_id + ': order mismatch')
        if e.kind == 'PROTECTION_ACTIVATION':
            if e.protection_state != 'EXCHANGE_ACTIVE':
                result.append(e.event_id + ': protection is not exchange active')
            filled = sum(f.quantity for f in events if f.kind == 'FILL' and
                         (f.trade_id, f.origin, f.config_sha256) == (e.trade_id, e.origin, e.config_sha256)
                         and f.occurred_at <= e.occurred_at)
            if e.quantity > filled:
                result.append(e.event_id + ': activation exceeds preceding fills')
    return tuple(result)

@dataclass(frozen=True, slots=True)
class PositionRiskContract(Validated):
    position_id: str
    remaining_quantity: int
    entry_price: D
    current_mark: D | None
    mark_at: datetime | None
    mark_valid_until: datetime | None
    mark_validity_evidence: Evidence | None
    protective_trigger: D | None
    protective_quantity: int | None
    protection_state: Protection
    protection_event_id: str | None
    remaining_expenses: D | None
    expense_basis: Evidence | None
    expenses_exclude_booked: bool
    adverse_allowance: D | None
    adverse_profile_sha256: str | None
    reconciliation: Literal['UNRESOLVED', 'CONFIRMED']
    r_entry: D | None
    r_mark: D | None
    r_position: D | None

    def validate(self):
        if self.remaining_quantity <= 0 or self.entry_price <= 0: raise ConfigError('invalid remaining position')
        for n in ('current_mark', 'protective_trigger'):
            if getattr(self,n) is not None and getattr(self,n) <= 0: raise ConfigError('invalid price')
        for n in ('remaining_expenses', 'adverse_allowance', 'protective_quantity'):
            if getattr(self,n) is not None and getattr(self,n) < 0: raise ConfigError('negative risk input')
        if self.adverse_profile_sha256 is not None: _sha(self.adverse_profile_sha256, 'allowance profile')
        numbers=(self.entry_price,self.current_mark,self.protective_trigger,self.remaining_expenses,self.adverse_allowance)
        metrics=(self.r_entry,self.r_mark,self.r_position)
        if any(v is not None and v < 0 for v in metrics): raise ConfigError('negative reported risk')
        if all(v is not None for v in numbers) and all(v is not None for v in metrics):
            # Validate supplied arithmetic, never size/aggregate a portfolio.
            with localcontext() as ctx:
                ctx.prec=sum(len(v.as_tuple().digits)+abs(v.as_tuple().exponent) for v in numbers)+len(str(self.remaining_quantity))+10
                entry=self.remaining_quantity*max(self.entry_price-self.protective_trigger,D(0))+self.remaining_expenses+self.adverse_allowance
                mark=self.remaining_quantity*max(self.current_mark-self.protective_trigger,D(0))+self.remaining_expenses+self.adverse_allowance
                if metrics != (entry,mark,max(entry,mark)):
                    raise ConfigError('reported dual risk violates approved formula')
        if self.mark_at and self.mark_valid_until and self.mark_at >= self.mark_valid_until:
            raise ConfigError('invalid mark validity')

    def issues(self, as_of: datetime) -> tuple[str, ...]:
        _typed(as_of, datetime, 'as_of', decode=False)
        result=[]
        if any(v is None for v in (self.r_entry,self.r_mark,self.r_position)): result.append('dual risk measurements missing')
        if self.protection_state != 'EXCHANGE_ACTIVE' or self.protection_event_id is None or self.protective_trigger is None:
            result.append('protection unresolved')
        if self.protective_quantity is None or self.protective_quantity < self.remaining_quantity:
            result.append('insufficient protection quantity')
        if self.current_mark is not None and self.protective_trigger is not None and self.current_mark <= self.protective_trigger:
            result.append('mark at/below protective trigger; reconcile before new entries')
        if self.current_mark is None or self.mark_at is None or self.mark_valid_until is None or not self.mark_at <= as_of < self.mark_valid_until:
            result.append('mark missing/stale')
        if self.mark_validity_evidence is None or self.mark_validity_evidence.available_at > as_of:
            result.append('mark validity unverified')
        if self.remaining_expenses is None or self.expense_basis is None or not self.expenses_exclude_booked:
            result.append('remaining expenses unresolved')
        elif self.expense_basis.available_at > as_of: result.append('expense evidence unavailable')
        if self.adverse_allowance is None or self.adverse_profile_sha256 is None: result.append('allowance unresolved')
        if self.reconciliation != 'CONFIRMED': result.append('reconciliation unresolved')
        return tuple(result)

    @property
    def unprotected_quantity(self) -> int:
        covered = self.protective_quantity or 0
        if self.protection_state != 'EXCHANGE_ACTIVE' or self.protection_event_id is None or self.protective_trigger is None:
            covered = 0
        return max(self.remaining_quantity - covered, 0)

    @property
    def marked_capital_exposure(self) -> D | None:
        # Raw reported exposure; freshness must be checked using issues(as_of).
        return None if self.current_mark is None else self.remaining_quantity * self.current_mark


def entry_contract_issues(positions: tuple[PositionRiskContract, ...],
                          events: tuple[ExecutionEvent, ...],
                          profiles: tuple[VerificationProfile, ...], as_of: datetime,
                          config_version: str, config_sha256: str,
                          purpose: Purpose, expected_profile_sha256: tuple[str, ...]) -> tuple[str, ...]:
    """Necessary input checks only; passing is NOT portfolio/trading readiness."""
    _typed(positions, tuple[PositionRiskContract, ...], 'positions', decode=False)
    _typed(profiles, tuple[VerificationProfile, ...], 'profiles', decode=False)
    _sha(config_sha256, 'expected config hash')
    _typed(purpose, Purpose, 'purpose', decode=False)
    _typed(config_version, str, 'config version', decode=False)
    _typed(expected_profile_sha256, tuple[str, ...], 'profile pins', decode=False)
    result=list(event_issues(events, as_of))
    if len(expected_profile_sha256) != 4 or set(expected_profile_sha256) != {p.content_sha256 for p in profiles}:
        result.append('configuration profile pins mismatch')
    kinds=[p.body.kind for p in profiles]
    if sorted(kinds) != sorted(('BROKER','FEES','SLIPPAGE','ADVERSE_EXECUTION')):
        result.append('exactly four distinct verification profiles required')
    for profile in profiles: result.extend(profile.issues(as_of, purpose))
    if len({p.position_id for p in positions}) != len(positions): result.append('duplicate positions')
    by_id={e.event_id:e for e in events}
    for e in events:
        if (e.config_version,e.config_sha256)!=(config_version,config_sha256): result.append('event configuration mismatch')
        if purpose == 'OPERATIONAL' and e.origin != 'ACTUAL': result.append('simulated operational event')
    for p in positions:
        result.extend(p.issues(as_of))
        e=by_id.get(p.protection_event_id)
        if e is None or e.kind!='PROTECTION_ACTIVATION' or e.protection_state!='EXCHANGE_ACTIVE' or e.quantity!=p.protective_quantity or e.price!=p.protective_trigger or e.trade_id!=p.position_id:
            result.append(p.position_id+': protection evidence mismatch')
        if not any(v.body.kind=='ADVERSE_EXECUTION' and v.content_sha256==p.adverse_profile_sha256 for v in profiles):
            result.append(p.position_id+': allowance profile mismatch')
    return tuple(result)
