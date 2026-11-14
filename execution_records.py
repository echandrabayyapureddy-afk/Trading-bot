"""Synthetic execution contracts; never actual broker facts or a durable ledger."""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal as D
from typing import Literal, Protocol
from config import Validated, ConfigError
from config_contracts import ExecutionEvent, PositionRiskContract
from strategy import StrategyResult, PlannedLevels, ExitIntent


@dataclass(frozen=True, slots=True)
class Capabilities(Validated):
    version: str
    available_at: datetime
    valid_until: datetime
    evidence: str
    opening_fill_assumption: bool
    explicit_trade_facts: bool
    submission_cutoff: Literal['STRICTLY_BEFORE_EXECUTION'] = 'STRICTLY_BEFORE_EXECUTION'
    origin: Literal['SYNTHETIC'] = 'SYNTHETIC'

    def validate(self):
        if not self.version or not self.evidence or self.available_at >= self.valid_until:
            raise ConfigError('invalid synthetic capability evidence')


@dataclass(frozen=True, slots=True)
class Funding(Validated):
    settled_cash: D
    available_at: datetime
    evidence: str
    origin: Literal['SYNTHETIC'] = 'SYNTHETIC'

    def validate(self):
        if self.settled_cash < 0 or not self.evidence:
            raise ConfigError('explicit nonnegative synthetic funding required')


@dataclass(frozen=True, slots=True)
class PricePoint(Validated):
    instrument_id: str
    at: datetime
    available_at: datetime
    price: D
    provider: str
    provider_version: str
    evidence: str
    kind: Literal['OPENING_ASSUMPTION', 'EXPLICIT_TRADE', 'OBSERVATION']
    basis: Literal['RAW'] = 'RAW'
    origin: Literal['SYNTHETIC'] = 'SYNTHETIC'

    def validate(self):
        if self.price <= 0 or self.available_at < self.at or not all((self.instrument_id, self.provider, self.provider_version, self.evidence)):
            raise ConfigError('invalid synthetic price point')


@dataclass(frozen=True, slots=True)
class Command(Validated):
    command_id: str
    recorded_at: datetime
    priority: int
    instrument_id: str
    trade_id: str
    action: Literal['EVENT', 'BAR', 'TRIGGER', 'EXIT_INTENT']
    role: Literal['BUY', 'ORDINARY', 'PROTECTIVE']
    event: ExecutionEvent | None = None
    signal: StrategyResult | None = None
    point: PricePoint | None = None
    bar_date: date | None = None
    intent: ExitIntent | None = None

    stop_type: Literal['STOP_MARKET', 'STOP_LIMIT'] | None = None
    stop_limit: D | None = None
    opening: PricePoint | None = None
    origin: Literal['SYNTHETIC'] = 'SYNTHETIC'

    def validate(self):
        if not self.command_id or not self.instrument_id or not self.trade_id:
            raise ConfigError('command identifiers required')
        if self.action == 'EVENT' and self.event is None:
            raise ConfigError('event required')
        if self.action != 'EVENT' and self.event is not None:
            raise ConfigError('event only on EVENT command')


@dataclass(frozen=True, slots=True)
class Order(Validated):
    order_id: str
    trade_id: str
    instrument_id: str
    role: Literal['BUY', 'ORDINARY', 'PROTECTIVE']
    quantity: int
    submitted_at: datetime
    reservation: D
    fee: D
    levels: PlannedLevels | None
    state: Literal['PENDING', 'FILLED', 'CANCELLED'] = 'PENDING'


@dataclass(frozen=True, slots=True)
class Position(Validated):
    trade_id: str
    instrument_id: str
    quantity: int
    entry_price: D
    entry_at: datetime
    entry_event_id: str
    levels: PlannedLevels
    provider: str
    provider_version: str
    protected_quantity: int = 0
    activation_at: datetime | None = None
    activation_id: str | None = None
    protective_order_id: str | None = None
    stop_type: Literal['STOP_MARKET', 'STOP_LIMIT'] | None = None
    stop_limit: D | None = None
    exit_state: Literal['UNPROTECTED', 'ACTIVE', 'TRIGGERED_UNFILLED', 'CLOSED'] = 'UNPROTECTED'
    intent: ExitIntent | None = None
    trigger_at: datetime | None = None
    trigger_command_id: str | None = None
    trigger_evidence_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class Audit(Validated):
    command: Command
    outcome: Literal['APPLIED', 'REJECTED', 'UNRESOLVED']
    reasons: tuple[str, ...]
    lineage: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Account(Validated):
    settled_cash: D
    unsettled_proceeds: D = D(0)
    orders: tuple[Order, ...] = ()
    positions: tuple[Position, ...] = ()
    events: tuple[ExecutionEvent, ...] = ()
    audit: tuple[Audit, ...] = ()
    entry_blocks: tuple[str, ...] = ()
    origin: Literal['SYNTHETIC'] = 'SYNTHETIC'
    operational_authorized: Literal[False] = False


# Gate must attest every fixed policy using the exact config and account state.
# The simulator does not calculate equity, drawdown or size quantities.
REQUIRED_CHECKS = ('trade_risk', 'stock_allocation', 'gross_exposure', 'max_positions',
                   'total_stop_risk', 'drawdown_review', 'drawdown_hard', 'reconciliation')


@dataclass(frozen=True, slots=True)
class DependencyEvidence(Validated):
    state_sha256: str
    config_sha256: str
    at: datetime
    evidence: str
    risk_approved: bool
    entry_suspended: bool
    checked_policies: tuple[str, ...]
    spendable_cash: D | None
    fee: D | None
    adverse_slippage: D | None
    positions: tuple[PositionRiskContract, ...] = ()
    origin: Literal['SYNTHETIC'] = 'SYNTHETIC'

    def validate(self):
        for x in (self.spendable_cash, self.fee, self.adverse_slippage):
            if x is not None and x < 0:
                raise ConfigError('negative dependency amount')


class Dependencies(Protocol):
    def assess(self, account: Account, command: Command, config_sha256: str) -> DependencyEvidence | None:
        """Pure adapter; bind current account, cutoff, costs and fixed-policy decision."""
        ...
