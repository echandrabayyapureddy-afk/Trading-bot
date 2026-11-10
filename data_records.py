"""Data contracts v1. Synthetic engineering only; no approved production sources."""
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json
from typing import Literal
from zoneinfo import ZoneInfo
from config import Validated, ConfigError

IST = ZoneInfo('Asia/Kolkata')


def canonical(value):
    """Canonical JSON: UTC instants, exact normalized decimals, explicit list order."""
    if is_dataclass(value):
        return {f.name: canonical(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, datetime):
        if value.utcoffset() is None:
            raise ConfigError('naive timestamp')
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ConfigError('nonfinite decimal')
        s = format(value, 'f')
        return (s.rstrip('0').rstrip('.') if '.' in s else s) if value else '0'
    if isinstance(value, (tuple, list)):
        return [canonical(x) for x in value]
    if isinstance(value, dict):
        return {k: canonical(v) for k, v in value.items()}
    return value


def encoded(value):
    return json.dumps(canonical(value), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return sha256(encoded(value)).hexdigest()


@dataclass(frozen=True, slots=True)
class Segment(Validated):
    opens: datetime
    closes: datetime

    def validate(self):
        if self.opens >= self.closes:
            raise ConfigError('invalid session segment')


@dataclass(frozen=True, slots=True)
class TradingDay(Validated):
    trading_date: date
    segments: tuple[Segment, ...]
    reason: str  # Explicit closure reason when segments is empty.

    def validate(self):
        if not self.reason.strip():
            raise ConfigError('session/closure reason required')
        for i, seg in enumerate(self.segments):
            if any(t.astimezone(IST).date() != self.trading_date for t in (seg.opens, seg.closes)):
                raise ConfigError('segment outside exchange trading date')
            if i and self.segments[i-1].closes >= seg.opens:
                raise ConfigError('segments unordered or overlapping')


@dataclass(frozen=True, slots=True)
class ExchangeCalendar(Validated):
    version: str
    available_at: datetime
    start: date
    end: date
    days: tuple[TradingDay, ...]
    evidence: str
    origin: Literal['SYNTHETIC'] = 'SYNTHETIC'
    exchange: Literal['NSE_CASH'] = 'NSE_CASH'
    timezone_name: Literal['Asia/Kolkata'] = 'Asia/Kolkata'

    def validate(self):
        expected = tuple(self.start + timedelta(days=i) for i in range((self.end-self.start).days))
        if not expected or tuple(d.trading_date for d in self.days) != expected:
            raise ConfigError('calendar requires every date, ordered, in [start,end)')
        if not self.version.strip() or not self.evidence.strip():
            raise ConfigError('calendar provenance required')

    def sessions(self, start, end, decision):
        if decision.utcoffset() is None:
            raise ConfigError('naive decision')
        if self.available_at > decision or not self.start <= start < end <= self.end:
            raise ConfigError('calendar unavailable or incomplete coverage')
        return tuple(d for d in self.days if start <= d.trading_date < end and d.segments)


@dataclass(frozen=True, slots=True)
class Identity(Validated):
    instrument_id: str
    symbol: str
    start: date
    end: date
    available_at: datetime
    status: Literal['LISTED', 'SUSPENDED', 'UNAVAILABLE']
    evidence: str

    def validate(self):
        if self.start >= self.end or not all(x.strip() for x in (self.instrument_id, self.symbol, self.evidence)):
            raise ConfigError('invalid identity interval/provenance')


@dataclass(frozen=True, slots=True)
class DailyBar(Validated):
    instrument_id: str
    symbol: str
    trading_date: date
    session_close: datetime
    available_at: datetime
    provider: str
    provider_version: str
    revision: int
    evidence: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    exchange: Literal['NSE_CASH'] = 'NSE_CASH'
    price_basis: Literal['RAW'] = 'RAW'
    volume_basis: Literal['RAW_SHARES'] = 'RAW_SHARES'
    corporate_action_treatment: Literal['UNADJUSTED'] = 'UNADJUSTED'
    origin: Literal['SYNTHETIC'] = 'SYNTHETIC'

    def validate(self):
        if self.revision < 0 or not all(x.strip() for x in (self.instrument_id, self.symbol, self.provider, self.provider_version, self.evidence)):
            raise ConfigError('missing provenance or invalid revision')
        # Bad finite OHLC facts remain representable for rejection reports.


@dataclass(frozen=True, slots=True)
class CorporateAction(Validated):
    action_id: str
    instrument_id: str
    effective_date: date
    available_at: datetime
    known_at: datetime
    kind: Literal['SPLIT', 'UNSUPPORTED']
    new_per_old: Decimal
    evidence: str

    def validate(self):
        if self.known_at > self.available_at or self.new_per_old <= 0 or not all(x.strip() for x in (self.action_id, self.instrument_id, self.evidence)):
            raise ConfigError('invalid action/evidence')


@dataclass(frozen=True, slots=True)
class Universe(Validated):
    version: str
    start: date
    end: date
    available_at: datetime
    members: tuple[str, ...]
    evidence: str

    def validate(self):
        if self.start >= self.end or tuple(sorted(set(self.members))) != self.members or any(not m.strip() for m in self.members) or not self.evidence.strip() or not self.version.strip():
            raise ConfigError('invalid dated universe')


@dataclass(frozen=True, slots=True)
class Snapshot(Validated):
    calendar: ExchangeCalendar
    bars: tuple[DailyBar, ...]
    identities: tuple[Identity, ...]
    actions: tuple[CorporateAction, ...] = ()
    universes: tuple[Universe, ...] = ()
    schema_version: Literal['1.0'] = '1.0'
    origin: Literal['SYNTHETIC'] = 'SYNTHETIC'

    def validate(self):
        # These are unordered record sets. Canonicalize order, never erase revisions.
        for name in ('bars', 'identities', 'actions', 'universes'):
            object.__setattr__(self, name, tuple(sorted(getattr(self, name), key=encoded)))


@dataclass(frozen=True, slots=True)
class QualityResult:
    status: Literal['VALID', 'REJECTED']
    reasons: tuple[str, ...]
    lineage: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Candle:
    instrument_id: str
    timeframe: Literal['WEEKLY', 'MONTHLY']
    start: date
    end: date
    final_session_close: datetime
    available_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    calendar_sha256: str
    lineage: tuple[str, ...]
    identity_lineage: tuple[str, ...]
    price_basis: str = 'RAW'
    volume_basis: str = 'RAW_SHARES'


@dataclass(frozen=True, slots=True)
class AdjustedView:
    raw_sha256: str
    action_lineage: tuple[str, ...]
    calendar_sha256: str
    identity_lineage: tuple[str, ...]
    available_at: datetime
    as_of: datetime
    applied_effective_at: tuple[datetime, ...]
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    schema_version: str = '2.0'
    effective_time_convention: str = 'EFFECTIVE_DATE_MIDNIGHT_ASIA_KOLKATA'
    basis: str = 'SPLIT_ADJUSTED_NONTRADABLE'

    def require_as_of(self, decision):
        """A derived view is pinned to one decision; recompute for other cutoffs."""
        if type(decision) is not datetime or decision.utcoffset() is None or decision != self.as_of:
            raise ConfigError('adjusted view as-of mismatch; recompute for requested decision')
        if self.available_at > decision:
            raise ConfigError('adjusted view unavailable at decision')
        return self


def calendar_as_of(calendars, decision):
    """Select an immutable published calendar vintage; retain all old versions."""
    if decision.utcoffset() is None:
        raise ConfigError('naive decision')
    visible = [c for c in calendars if c.available_at <= decision]
    if not visible:
        raise ConfigError('calendar unavailable')
    if len({c.version for c in visible}) != len(visible):
        raise ConfigError('calendar version reused')
    latest = max(c.available_at for c in visible)
    choices = [c for c in visible if c.available_at == latest]
    if len(choices) != 1:
        raise ConfigError('ambiguous calendar publication')
    return choices[0]
