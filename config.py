"""Configuration only. Standard library; no downloads, orders, or research runs.

All intervals are [start, end). Decimal JSON values are strings. Approval keys
must be provisioned outside the research process; see README for trust limits.
"""
from __future__ import annotations

import calendar
import hashlib
import hmac
import json
import re
import types
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints
from zoneinfo import ZoneInfo


class ConfigError(ValueError):
    """Invalid configuration, provenance, boundary, or readiness."""


class Provenance(str, Enum):
    POLICY = "POLICY"
    BASELINE = "BASELINE HYPOTHESIS"
    EXPERIMENTAL = "EXPERIMENTAL"


class Candidate(str, Enum):
    A = "A"
    B = "B"


class SealStatus(str, Enum):
    UNSEALED = "UNSEALED"
    SEALED = "SEALED"


def parameter(default: Any, category: Provenance, reason: str):
    return field(default=default, metadata={"provenance": category.value, "reason": reason})


P, B, X = Provenance.POLICY, Provenance.BASELINE, Provenance.EXPERIMENTAL
D = Decimal


class Validated:
    __slots__ = ()

    def __post_init__(self):
        _validate_types(self)
        self.validate()

    def validate(self):
        pass


@dataclass(frozen=True, slots=True)
class AccountConfig(Validated):
    account_id: str | None = parameter(None, P, "Required actual account identifier; never a credential.")
    capital_inr: Decimal | None = parameter(None, P, "Actual configured capital, not an assumed 5000/10000 balance.")
    currency: Literal["INR"] = parameter("INR", P, "NSE cash account currency.")
    market: Literal["NSE_CASH_EQUITY"] = parameter("NSE_CASH_EQUITY", P, "Cash equity only.")
    long_only: Literal[True] = parameter(True, P, "No short selling.")
    delivery_intended: Literal[True] = parameter(True, P, "Delivery-intended trades; protection remains active.")

    def validate(self):
        if self.capital_inr is not None and self.capital_inr <= 0:
            raise ConfigError("account.capital_inr must be positive")


@dataclass(frozen=True, slots=True)
class DataConfig(Validated):
    provider: str | None = parameter(None, P, "Unverified until selected explicitly.")
    provider_version: str | None = parameter(None, P, "Reproducible source version.")
    snapshot_sha256: str | None = parameter(None, P, "Actual data fingerprint; never inferred.")
    calendar_version: str | None = parameter(None, P, "Effective-dated NSE cash sessions including special sessions.")
    universe_version: str | None = parameter(None, P, "Point-in-time universe definition.")
    point_in_time_verified: bool = parameter(False, P, "False blocks outcome-based research until verified.")
    availability_verified: bool = parameter(False, P, "Historical availability timestamps must be verified.")
    adjustment_semantics: Literal["POINT_IN_TIME_SIGNALS_RAW_FILLS"] = parameter(
        "POINT_IN_TIME_SIGNALS_RAW_FILLS", P, "Explicit adjustment conversion; no future corporate actions.")
    missing_data: Literal["BLOCK_NEW_ENTRIES"] = parameter("BLOCK_NEW_ENTRIES", P, "Do not fill gaps with synthetic prices.")

    def validate(self):
        if self.snapshot_sha256 is not None:
            _sha(self.snapshot_sha256, "data.snapshot_sha256")


@dataclass(frozen=True, slots=True)
class TimeframeConfig(Validated):
    timezone: Literal["Asia/Kolkata"] = parameter("Asia/Kolkata", P, "Exchange trading-date timezone.")
    canonical: Literal["DAILY"] = parameter("DAILY", P, "Validated daily OHLCV is authoritative.")
    weekly_period: Literal["MONDAY_SUNDAY_EXCHANGE_DATES"] = parameter("MONDAY_SUNDAY_EXCHANGE_DATES", P, "Includes special sessions.")
    monthly_period: Literal["CALENDAR_MONTH"] = parameter("CALENDAR_MONTH", P, "Aggregate daily bars directly.")
    completed_only: Literal[True] = parameter(True, P, "No incomplete higher-timeframe decisions.")
    require_available_at: Literal[True] = parameter(True, P, "Availability must precede each decision.")
    selection_frequency: Literal["WEEKLY"] = parameter("WEEKLY", X, "Predeclared schedule, no forced trades.")
    monitor_frequency: Literal["DAILY"] = parameter("DAILY", P, "Existing exits and reconciliation remain active.")


@dataclass(frozen=True, slots=True)
class RegimeConfig(Validated):
    benchmark: Literal["NIFTY_50"] = parameter("NIFTY_50", B, "Broad market context, not a tradable instrument here.")
    adx_period: int = parameter(14, B, "Initial baseline; no optimization.")
    ema_period: int = parameter(200, B, "Daily EMA baseline.")
    ema_slope_sessions: int = parameter(10, B, "Completed daily intervals.")
    atr_period: int = parameter(14, B, "Wilder ATR baseline.")
    vol_recent_returns: int = parameter(20, B, "Sample standard deviation of log returns.")
    vol_reference_returns: int = parameter(63, B, "Immediately preceding non-overlapping returns.")
    adx_trending: Decimal = parameter(D("25"), B, "Trending requires strictly greater than this value.")
    adx_sideways: Decimal = parameter(D("20"), B, "Below this is sideways; 20..25 is transitional sideways.")
    atr_spike_ratio: Decimal = parameter(D("2.0"), B, "Compared with mean of previous 63 ATR values.")
    vol_spike_ratio: Decimal = parameter(D("2.0"), B, "Immediate new-entry veto at or above ratio.")
    confirmation_sessions: Literal[2] = parameter(2, P, "Exactly two completed daily trading sessions.")
    volatility_definition: Literal["LOG_SD_DDOF1_NONOVERLAPPING"] = parameter("LOG_SD_DDOF1_NONOVERLAPPING", X, "20 returns versus previous 63; unknown blocks entries.")
    regime_mapping: Literal["HIGH_RISK_PRIORITY_ADX_PRICE_SLOPE_ELSE_SIDEWAYS"] = parameter("HIGH_RISK_PRIORITY_ADX_PRICE_SLOPE_ELSE_SIDEWAYS", X, "Directional labels require ADX>25 and matching price/EMA slope direction.")
    unknown_behavior: Literal["BLOCK_AND_RESET_PENDING"] = parameter("BLOCK_AND_RESET_PENDING", P, "Never label missing data sideways.")
    ema_seed: Literal["SMA_N"] = parameter("SMA_N", B, "Deterministic initialization.")
    atr_adx_smoothing: Literal["WILDER_SMA_SEED"] = parameter("WILDER_SMA_SEED", B, "Independent implementation in later phase.")

    def validate(self):
        for n in ("adx_period", "ema_period", "ema_slope_sessions", "atr_period", "vol_recent_returns", "vol_reference_returns"):
            if getattr(self, n) < 2:
                raise ConfigError(f"regime.{n} must be >=2")
        if not 0 < self.adx_sideways < self.adx_trending < 100:
            raise ConfigError("ADX thresholds must satisfy 0 < sideways < trending < 100")
        if min(self.atr_spike_ratio, self.vol_spike_ratio) <= 1:
            raise ConfigError("spike ratios must exceed 1")


@dataclass(frozen=True, slots=True)
class StrategyConfig(Validated):
    candidate: Candidate = parameter(Candidate.A, X, "A baseline; B differs only by month-end filter.")
    fast_ema: int = parameter(9, B, "Daily bars, not weekly periods.")
    slow_ema: int = parameter(21, B, "Daily bars, not weekly periods.")
    weekly_eligibility: Literal["CROSS_WITHIN_WEEK_STILL_ABOVE"] = parameter("CROSS_WITHIN_WEEK_STILL_ABOVE", X, "Previous fast<=slow, current fast>slow; final week bar still above.")
    daily_revalidation: Literal["FAST_ABOVE_SLOW_ELSE_RETIRE"] = parameter("FAST_ABOVE_SLOW_ELSE_RETIRE", X, "Retire invalidated opportunity until a later weekly selection.")
    entry_regime: Literal["TRENDING_UP"] = parameter("TRENDING_UP", X, "Confirmed benchmark regime plus independent safety gates.")
    stop_atr_multiple: Decimal = parameter(D("2"), X, "Fixed prior-close minus two prior available ATRs, not an active order.")
    stop_method: Literal["PROPOSAL_CLOSE_MINUS_ATR_FIXED"] = parameter("PROPOSAL_CLOSE_MINUS_ATR_FIXED", X, "Freeze proposal values; never retroactively update stops.")
    entry_ceiling: Literal["PROPOSAL_CLOSE_TICK_FLOOR"] = parameter("PROPOSAL_CLOSE_TICK_FLOOR", X, "A price limit does not guarantee any fill.")
    ordinary_exit: Literal["DAILY_FAST_LE_SLOW_PERSIST_UNTIL_RESOLVED"] = parameter("DAILY_FAST_LE_SLOW_PERSIST_UNTIL_RESOLVED", X, "No trailing stop, profit target, or time-based liquidation.")
    ranking: Literal["MEDIAN_RAW_CLOSE_TIMES_RAW_VOLUME_DESC_ID_ASC"] = parameter("MEDIAN_RAW_CLOSE_TIMES_RAW_VOLUME_DESC_ID_ASC", X, "Single liquidity proxy, no optimized weights.")
    ranking_sessions: int = parameter(20, X, "Completed sessions available at weekly selection.")
    monthly_filter: Literal["MONTH_CLOSE_GT_SAME_MONTH_END_DAILY_EMA200"] = parameter("MONTH_CLOSE_GT_SAME_MONTH_END_DAILY_EMA200", X, "Only Candidate B gates entries; missing required month blocks B.")
    force_trades: Literal[False] = parameter(False, P, "Cash is acceptable.")
    pyramid: Literal[False] = parameter(False, P, "One position per instrument.")

    def validate(self):
        if not 1 < self.fast_ema < self.slow_ema:
            raise ConfigError("strategy requires 1 < fast_ema < slow_ema")
        if self.stop_atr_multiple <= 0 or self.ranking_sessions < 1:
            raise ConfigError("stop multiple and ranking window must be positive")


@dataclass(frozen=True, slots=True)
class RiskConfig(Validated):
    trade_risk: Decimal = parameter(D("0.005"), P, "0.5% planned risk, not guaranteed maximum loss.")
    stock_allocation: Decimal = parameter(D("0.40"), P, "40% equity cap including commitments.")
    gross_exposure: Decimal = parameter(D("0.80"), P, "80% equity cap including commitments.")
    max_positions: int = parameter(2, P, "Held and committed position slots.")
    total_stop_risk: Decimal = parameter(D("0.01"), P, "1% aggregate planned stop-risk cap.")
    drawdown_review: Decimal = parameter(D("0.05"), P, "Latch entry pause until documented review.")
    drawdown_hard: Decimal = parameter(D("0.08"), P, "Latch suspension requiring explicit authorization.")
    leverage: Decimal = parameter(D("0"), P, "No borrowed buying power.")
    minimum_shares: Literal[1] = parameter(1, P, "Whole shares only; zero affordable shares means skip.")
    whole_shares: Literal[True] = parameter(True, P, "No fractional quantities.")
    flow_adjustment: Literal["UNITIZED_NAV"] = parameter("UNITIZED_NAV", P, "Cash flows alter units, not investment return.")
    automatic_resume: Literal[False] = parameter(False, P, "Recovery alone cannot clear a latch.")
    liquidate_on_drawdown: Literal[False] = parameter(False, P, "Existing exits/protection/reconciliation continue.")
    open_risk_basis: Literal["ENTRY_TO_STOP", "MARK_TO_STOP"] | None = parameter(None, P, "Unresolved decision; blocks executable recommendations.")
    resume_rule: Literal["RECOVERY_AND_DOCUMENTED_CLEARANCE"] = parameter("RECOVERY_AND_DOCUMENTED_CLEARANCE", P, "Both gates independent; high-water mark never resets to permit entries.")

    def validate(self):
        if not 0 < self.trade_risk <= self.total_stop_risk < 1:
            raise ConfigError("inconsistent trade/portfolio risk")
        if not 0 < self.stock_allocation <= self.gross_exposure <= 1:
            raise ConfigError("inconsistent allocation/exposure")
        if not 0 < self.drawdown_review < self.drawdown_hard < 1:
            raise ConfigError("invalid drawdown thresholds")
        for n, expected in {"trade_risk": D(".005"), "stock_allocation": D(".4"),
                            "gross_exposure": D(".8"), "max_positions": 2,
                            "total_stop_risk": D(".01"), "drawdown_review": D(".05"),
                            "drawdown_hard": D(".08"), "leverage": D("0")}.items():
            if getattr(self, n) != expected:
                raise ConfigError(f"risk.{n} differs from fixed POLICY-1.0.0")


@dataclass(frozen=True, slots=True)
class ExecutionConfig(Validated):
    manual_approval: Literal[True] = parameter(True, P, "Explicit version-bound human approval.")
    manual_placement: Literal[True] = parameter(True, P, "Human places every broker order.")
    broker_submission_api: Literal[False] = parameter(False, P, "No automated order transmission in V1.")
    operator_delay_sessions: int = parameter(1, X, "One complete exchange session after decision, then eligible opportunity.")
    guaranteed_fills: Literal[False] = parameter(False, P, "Price touches, approval and acceptance are not fills.")
    protection_activation: Literal["BROKER_CONFIRMED_TIMESTAMP"] = parameter("BROKER_CONFIRMED_TIMESTAMP", P, "Separate from planned stops and entry fill.")
    ambiguous_intraday: Literal["UNRESOLVED_OR_CONSERVATIVE_BOUNDS"] = parameter("UNRESOLVED_OR_CONSERVATIVE_BOUNDS", P, "Daily bars cannot establish within-bar activation order.")
    broker_profile_version: str | None = parameter(None, P, "Requires verified session/order/validity rules.")
    broker_rules_verified: bool = parameter(False, P, "No executable recommendations before verification.")
    order_cutoff_rule: str | None = parameter(None, P, "Versioned broker-specific timing convention; no invented cutoff.")
    protective_order_type: Literal["STOP_MARKET", "STOP_LIMIT"] | None = parameter(None, P, "Actual supported behavior; no silent substitution.")
    fee_model_version: str | None = parameter(None, P, "No current rates or historical schedules fabricated.")
    fee_source_reference: str | None = parameter(None, P, "Dated authoritative schedule reference.")
    fee_effective_start: date | None = parameter(None, P, "Coverage start inclusive.")
    fee_effective_end: date | None = parameter(None, P, "Coverage end exclusive.")
    fee_schedule_verified: bool = parameter(False, P, "Phase 7 implements actual fee schedules and accounting.")
    slippage_bps: Decimal | None = parameter(None, X, "Explicit estimate, not a guaranteed gap-loss allowance.")
    fixed_execution_allowance_inr: Decimal | None = parameter(None, X, "Explicit nonnegative allowance; not a loss guarantee.")

    def validate(self):
        if self.operator_delay_sessions < 1:
            raise ConfigError("operator delay must include at least one complete session")
        for n in ("slippage_bps", "fixed_execution_allowance_inr"):
            if getattr(self, n) is not None and getattr(self, n) < 0:
                raise ConfigError(f"execution.{n} cannot be negative")
        if (self.fee_effective_start is None) != (self.fee_effective_end is None):
            raise ConfigError("both fee coverage endpoints are required")
        if self.fee_effective_start is not None and self.fee_effective_start >= self.fee_effective_end:
            raise ConfigError("invalid fee coverage")


@dataclass(frozen=True, slots=True)
class BacktestConfig(Validated):
    candidates: tuple[Candidate, ...] = parameter((Candidate.A, Candidate.B), X, "Only predefined A and B, isolated replay accounts.")
    holdout_months: Literal[12] = parameter(12, P, "Final twelve calendar months of sealed snapshot.")
    holdout_evaluations: Literal[1] = parameter(1, P, "Future final-gate authorization required; unavailable here.")
    interval_convention: Literal["START_INCLUSIVE_END_EXCLUSIVE"] = parameter("START_INCLUSIVE_END_EXCLUSIVE", P, "Prevents shared train/test boundary observations.")
    auto_promote: Literal[False] = parameter(False, P, "Research cannot promote live settings.")
    optimize_safety_policy: Literal[False] = parameter(False, P, "Safety limits are not search parameters.")

    def validate(self):
        if self.candidates != (Candidate.A, Candidate.B):
            raise ConfigError("only ordered candidates A and B are supported")


@dataclass(frozen=True, slots=True)
class ReportingConfig(Validated):
    daily: Literal[True] = parameter(True, P, "Daily positions and reconciliation.")
    weekly: Literal[True] = parameter(True, P, "Weekly ranked opportunities, including NO TRADE.")
    monthly: Literal[True] = parameter(True, P, "Completed-month context.")
    rejection_reasons: Literal[True] = parameter(True, P, "Explain all blocked entries.")
    audit_events: Literal[True] = parameter(True, P, "Version, provenance and operator events required.")
    actual_vs_simulated: Literal[True] = parameter(True, P, "Never merge real and hypothetical fills.")
    paper_minimum_weeks: Literal[12] = parameter(12, P, "Operational minimum, not statistical proof.")


def _sha(value: str, label: str):
    if re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ConfigError(f"{label} must be a lowercase SHA-256 hex digest")


def _validate_types(obj: Any):
    for name, annotation in get_type_hints(type(obj)).items():
        _typed(getattr(obj, name), annotation, name, decode=False)


def _typed(value: Any, annotation: Any, path: str, *, decode: bool):
    origin, args = get_origin(annotation), get_args(annotation)
    if origin in (Union, types.UnionType):
        for option in args:
            try:
                return _typed(value, option, path, decode=decode)
            except ConfigError:
                pass
        raise ConfigError(f"{path}: invalid optional/union value")
    if origin is Literal:
        if not any(type(value) is type(a) and value == a for a in args):
            raise ConfigError(f"{path}: must be one of {args}")
        return value
    if origin is tuple:
        if type(value) is not (list if decode else tuple):
            raise ConfigError(f"{path}: expected {'JSON array' if decode else 'tuple'}")
        return tuple(_typed(v, args[0], f"{path}[{i}]", decode=decode) for i, v in enumerate(value))
    if annotation is type(None):
        if value is not None:
            raise ConfigError(f"{path}: expected null")
        return None
    if is_dataclass(annotation):
        if decode:
            return from_dict(annotation, value)
        if type(value) is not annotation:
            raise ConfigError(f"{path}: wrong nested configuration type")
        _validate_types(value)
        value.validate()
        return value
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        if decode:
            try:
                return annotation(value)
            except (ValueError, TypeError):
                raise ConfigError(f"{path}: invalid enum") from None
        if type(value) is not annotation:
            raise ConfigError(f"{path}: expected {annotation.__name__}")
        return value
    if decode and annotation is Decimal:
        if type(value) is not str or not re.fullmatch(r"-?\d+(\.\d+)?", value):
            raise ConfigError(f"{path}: decimal must be a finite decimal string")
        value = D(value)
    if decode and annotation in (date, datetime):
        if type(value) is not str:
            raise ConfigError(f"{path}: expected ISO date/time string")
        try:
            if annotation is date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError()
            value = annotation.fromisoformat(value)
        except ValueError:
            raise ConfigError(f"{path}: invalid ISO date/time") from None
    if type(value) is not annotation:
        raise ConfigError(f"{path}: expected {annotation.__name__}, got {type(value).__name__}")
    if annotation is str and (not value.strip() or value != value.strip()):
        raise ConfigError(f"{path}: blank or padded string")
    if annotation is Decimal and not value.is_finite():
        raise ConfigError(f"{path}: nonfinite decimal")
    if annotation is datetime and (value.tzinfo is None or value.utcoffset() is None):
        raise ConfigError(f"{path}: timezone-aware timestamp required")
    return value



@dataclass(frozen=True, slots=True)
class BotConfig(Validated):
    schema_version: Literal["1.0"] = parameter("1.0", P, "Strict schema version; unknown versions rejected.")
    config_version: str = parameter("0.1.0", P, "Version bound to content hash and external approval.")
    policy_version: Literal["POLICY-1.0.0"] = parameter("POLICY-1.0.0", P, "Fixed initial safety limits.")
    account: AccountConfig = parameter(AccountConfig(), P, "Actual account input.")
    data: DataConfig = parameter(DataConfig(), P, "Required data conventions.")
    timeframes: TimeframeConfig = parameter(TimeframeConfig(), P, "Timeframe contracts.")
    regime: RegimeConfig = parameter(RegimeConfig(), B, "Unvalidated indicator baseline.")
    strategy: StrategyConfig = parameter(StrategyConfig(), X, "Predeclared strategy hypotheses.")
    risk: RiskConfig = parameter(RiskConfig(), P, "Fixed safety policy.")
    execution: ExecutionConfig = parameter(ExecutionConfig(), P, "Manual workflow and explicit assumptions.")
    backtesting: BacktestConfig = parameter(BacktestConfig(), P, "Research isolation.")
    reporting: ReportingConfig = parameter(ReportingConfig(), P, "Auditability.")

    def validate(self):
        if re.fullmatch(r"\d+\.\d+\.\d+", self.config_version) is None:
            raise ConfigError("config_version must be MAJOR.MINOR.PATCH")
        if self.strategy.slow_ema > self.regime.ema_period:
            raise ConfigError("strategy slow EMA exceeds long-context EMA")


@dataclass(frozen=True, slots=True)
class ResearchManifest(Validated):
    schema_version: Literal["1.0"] = parameter("1.0", P, "Manifest schema.")
    status: SealStatus = parameter(SealStatus.UNSEALED, P, "Templates cannot authorize historical research.")
    snapshot_id: str | None = parameter(None, P, "Exact immutable dataset identifier.")
    snapshot_sha256: str | None = parameter(None, P, "Exact dataset hash.")
    snapshot_created_at: datetime | None = parameter(None, P, "Timezone-aware snapshot creation timestamp.")
    sealed_at: datetime | None = parameter(None, P, "Timezone-aware sealing timestamp.")
    instruments: tuple[str, ...] = parameter((), P, "Exact instrument identities, not a guessed basket.")
    provider_version: str | None = parameter(None, P, "Snapshot provider provenance.")
    calendar_version: str | None = parameter(None, P, "Snapshot calendar provenance.")
    universe_version: str | None = parameter(None, P, "Snapshot universe provenance.")
    fee_model_version: str | None = parameter(None, P, "Cost assumptions bound to research.")
    software_commit: str | None = parameter(None, P, "Actual commit if available; never invented.")
    config_sha256: str | None = parameter(None, P, "Exact configuration content bound to seal.")
    snapshot_start: date | None = parameter(None, P, "Inclusive coverage start.")
    snapshot_end: date | None = parameter(None, P, "Exclusive coverage end.")
    development_start: date | None = parameter(None, P, "Inclusive development start.")
    development_end: date | None = parameter(None, P, "Exclusive development end.")
    holdout_start: date | None = parameter(None, P, "Inclusive final twelve-month start.")
    holdout_end: date | None = parameter(None, P, "Exclusive final twelve-month end.")

    def validate(self):
        for n in ("snapshot_sha256", "config_sha256"):
            if getattr(self, n) is not None:
                _sha(getattr(self, n), n)
        if self.software_commit is not None and not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", self.software_commit):
            raise ConfigError("software_commit must be a full git object id")
        if len(set(self.instruments)) != len(self.instruments):
            raise ConfigError("duplicate manifest instruments")
        endpoints = (self.snapshot_start, self.snapshot_end, self.development_start,
                     self.development_end, self.holdout_start, self.holdout_end)
        if any(x is not None for x in endpoints):
            if any(x is None for x in endpoints):
                raise ConfigError("all research interval endpoints must be supplied together")
            ss, se, ds, de, hs, he = endpoints
            if not ss == ds < de == hs < he == se:
                raise ConfigError("development and holdout must exactly partition snapshot, without overlap")
            expected = date(he.year - 1, he.month, min(he.day, calendar.monthrange(he.year - 1, he.month)[1]))
            if hs != expected:
                raise ConfigError("holdout must be exactly the final twelve calendar months")
        if self.status is SealStatus.SEALED:
            for f in fields(self):
                if f.name != "software_commit" and getattr(self, f.name) in (None, ()):
                    raise ConfigError(f"sealed manifest missing {f.name}")
            if self.snapshot_created_at > self.sealed_at:
                raise ConfigError("snapshot cannot be created after sealing")



def from_dict(cls: type, document: dict):
    if type(document) is not dict:
        raise ConfigError(f"{cls.__name__}: expected object")
    names = {f.name for f in fields(cls)}
    if set(document) != names:
        raise ConfigError(f"{cls.__name__}: missing={sorted(names-set(document))}, unknown={sorted(set(document)-names)}")
    hints = get_type_hints(cls)
    return cls(**{n: _typed(v, hints[n], n, decode=True) for n, v in document.items()})


def _pairs(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise ConfigError(f"duplicate JSON key: {k}")
        result[k] = v
    return result


def parse_json(text: str) -> dict:
    def bad_constant(v):
        raise ConfigError(f"nonfinite JSON value: {v}")
    try:
        result = json.loads(text, object_pairs_hook=_pairs, parse_constant=bad_constant)
    except json.JSONDecodeError as e:
        raise ConfigError(str(e)) from e
    if type(result) is not dict:
        raise ConfigError("JSON root must be an object")
    return result


def load_config(path: str | Path) -> BotConfig:
    return from_dict(BotConfig, parse_json(Path(path).read_text(encoding="utf-8")))


def load_manifest(path: str | Path) -> ResearchManifest:
    return from_dict(ResearchManifest, parse_json(Path(path).read_text(encoding="utf-8")))


def to_dict(value):
    if is_dataclass(value):
        return {f.name: to_dict(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        # Decimal.normalize() can round under the caller's decimal context.
        # Canonical hashing must preserve every digit, irrespective of context.
        text = format(value, "f")
        return (text.rstrip("0").rstrip(".") if "." in text else text) if value else "0"
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, tuple):
        return [to_dict(v) for v in value]
    return value


def canonical_json(obj) -> str:
    return json.dumps(to_dict(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def content_hash(obj) -> str:
    return hashlib.sha256(canonical_json(obj).encode()).hexdigest()


def parameter_catalog(cls=BotConfig, prefix="") -> list[dict]:
    result = []
    hints = get_type_hints(cls)
    for f in fields(cls):
        path = prefix + f.name
        if is_dataclass(hints[f.name]):
            result.extend(parameter_catalog(hints[f.name], path + "."))
        else:
            result.append({"path": path, "provenance": f.metadata["provenance"],
                           "reason": f.metadata["reason"], "default": to_dict(f.default)})
    return result


def readiness_issues(config: BotConfig) -> tuple[str, ...]:
    """Explicit prerequisites; no zero-filled costs or guessed operator settings."""
    _validate_types(config)
    config.validate()
    required = {"account": ("account_id", "capital_inr"),
                "data": ("provider", "provider_version", "snapshot_sha256", "calendar_version", "universe_version", "point_in_time_verified", "availability_verified"),
                "risk": ("open_risk_basis",),
                "execution": ("broker_profile_version", "broker_rules_verified", "order_cutoff_rule", "protective_order_type", "fee_model_version", "fee_source_reference", "fee_effective_start", "fee_effective_end", "fee_schedule_verified", "slippage_bps", "fixed_execution_allowance_inr")}
    return tuple(f"{section}.{name}" for section, names in required.items() for name in names
                 if getattr(getattr(config, section), name) is None or getattr(getattr(config, section), name) is False)


def require_ready(config: BotConfig):
    issues = readiness_issues(config)
    if issues:
        raise ConfigError("not executable/research-ready: " + ", ".join(issues))


def authorize_development_window(config: BotConfig, manifest: ResearchManifest,
                                 start: date, end: date, *, expected_manifest_sha256: str):
    """Configuration guard only; never reads data or authorizes the final holdout."""
    _validate_types(manifest)
    manifest.validate()
    _sha(expected_manifest_sha256, "externally pinned manifest hash")
    if not hmac.compare_digest(content_hash(manifest), expected_manifest_sha256):
        raise ConfigError("manifest hash mismatch")
    if manifest.status is not SealStatus.SEALED:
        raise ConfigError("UNSEALED manifest: outcome-based research prohibited")
    require_ready(config)
    if manifest.config_sha256 != content_hash(config):
        raise ConfigError("configuration differs from sealed research configuration")
    for n in ("snapshot_sha256", "provider_version", "calendar_version", "universe_version"):
        if getattr(manifest, n) != getattr(config.data, n):
            raise ConfigError(f"manifest/config mismatch: {n}")
    if manifest.fee_model_version != config.execution.fee_model_version:
        raise ConfigError("fee version mismatch")
    if type(start) is not date or type(end) is not date or not manifest.development_start <= start < end <= manifest.development_end:
        raise ConfigError("window is outside development boundaries; holdout access denied")
    if not config.execution.fee_effective_start <= start < end <= config.execution.fee_effective_end:
        raise ConfigError("research window not covered by fee profile")


@dataclass(frozen=True, slots=True)
class ApprovalReceipt(Validated):
    config_version: str
    config_sha256: str
    approved_at: datetime
    reviewers: tuple[str, ...]
    purpose: Literal["MANUAL_LIVE_SETTINGS"]
    signature: str

    def validate(self):
        _sha(self.config_sha256, "approval config hash")
        _sha(self.signature, "approval signature")
        if len(set(self.reviewers)) < 2:
            raise ConfigError("two distinct reviewers required")


def approval_payload(receipt: ApprovalReceipt) -> bytes:
    payload = to_dict(receipt)
    del payload["signature"]
    return canonical_json(payload).encode()


def load_approved_live(config_path: str | Path, receipt_path: str | Path, *,
                       approval_key: bytes, expected_version: str,
                       expected_config_sha256: str, as_of: datetime) -> BotConfig:
    """Read-only verification; no signing, saving, promotion, or automatic fallback.

    Expected version/hash and key MUST come from operator-controlled storage,
    never from the research output or adjacent editable config file itself.
    """
    if type(approval_key) is not bytes or len(approval_key) < 32:
        raise ConfigError("external approval key must be at least 32 bytes")
    _typed(as_of, datetime, "as_of", decode=False)
    _sha(expected_config_sha256, "trusted config hash")
    config = load_config(config_path)
    receipt = from_dict(ApprovalReceipt, parse_json(Path(receipt_path).read_text(encoding="utf-8")))
    expected_signature = hmac.new(approval_key, approval_payload(receipt), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_signature, receipt.signature):
        raise ConfigError("invalid approval signature")
    if receipt.approved_at > as_of:
        raise ConfigError("approval is not yet available at decision time")
    actual = content_hash(config)
    if not (config.config_version == receipt.config_version == expected_version and
            hmac.compare_digest(actual, receipt.config_sha256) and
            hmac.compare_digest(actual, expected_config_sha256)):
        raise ConfigError("approved version/hash mismatch")
    require_ready(config)
    exchange_date = as_of.astimezone(ZoneInfo("Asia/Kolkata")).date()
    if not config.execution.fee_effective_start <= exchange_date < config.execution.fee_effective_end:
        raise ConfigError("fee profile is not effective on the decision date")
    return config
