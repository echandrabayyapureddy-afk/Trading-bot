"""Predeclared, paired walk-forward method. Its only data source is a generated fixture."""
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
from typing import Literal

from accounting_adapter import AccountingDependencies, project
from config import (BotConfig, Candidate, ConfigError, Validated, content_hash, load_config)
from config_contracts import Evidence, ExecutionEvent
from data_records import digest
from data_validator import daily_as_of, universe_as_of
from execution_engine import replay as execution_replay, require
from execution_records import Account, Command
from ledger import reconstruct
from portfolio import Mark, update_nav, value
from regime_detector import replay as regime_replay
from strategy import EMACrossoverStrategy, MonthlyEvidence
from suitability import Request as PriceRequest, evaluate
from walk_forward_audit import TrialAudit
from walk_forward_fixture import CASES, OPEN_DAY, STOCK, build, instant

BASELINE = '3f82ef80410c7004e2183bd75290c9bb436ee337'
ROOT = Path(__file__).resolve().parent
OWNERS = ('walk_forward', 'walk_forward_fixture', 'walk_forward_audit', 'config',
          'config_contracts', 'data_records', 'data_validator', 'data_fetcher',
          'regime_detector', 'strategy', 'suitability', 'fee_model', 'risk_manager',
          'portfolio', 'ledger', 'accounting_adapter', 'execution_records',
          'execution_engine', 'research_journal', 'research_records')
ACCOUNT = 'SYN-WF-isolated'


@dataclass(frozen=True, slots=True)
class Scope(Validated):
    fixture: str = 'paired'
    origin: str = 'SYNTHETIC'
    purpose: str = 'METHOD_TEST'

    def check(self):
        require(self.origin == 'SYNTHETIC' and self.purpose == 'METHOD_TEST'
                and self.fixture in CASES, 'only named synthetic method fixtures permitted')


@dataclass(frozen=True, slots=True)
class Fold(Validated):
    warmup: date
    train: date
    selection: date
    test: date
    end: date

    def validate(self):
        require(self.warmup < self.train < self.selection < self.test < self.end,
                'empty or overlapping fold intervals')


def default_folds():
    def day(n):
        return date(2020, 11, n)
    return (Fold(date(2020, 1, 1), day(10), day(12), day(13), day(18)),
            Fold(date(2020, 1, 1), day(10), day(18), day(19), day(24)))


@dataclass(frozen=True, slots=True)
class Study(Validated):
    scope: Scope
    folds: tuple[Fold, ...]
    declared_at: datetime
    fixture_sha256: str
    configs: tuple[str, ...]
    source_sha256: str
    baseline: Literal['3f82ef80410c7004e2183bd75290c9bb436ee337'] = BASELINE
    version: Literal['SYN-WF-1'] = 'SYN-WF-1'
    candidates: Literal['A,B'] = 'A,B'
    selection_rule: Literal['RETAIN_BOTH_NO_FIT'] = 'RETAIN_BOTH_NO_FIT'
    training: Literal['EXPANDING_PRIOR_TEST_ALLOWED'] = 'EXPANDING_PRIOR_TEST_ALLOWED'
    account_rule: Literal['RESET_AT_TEST_START'] = 'RESET_AT_TEST_START'
    metric: Literal['PAIRED_B_MINUS_A_NET_NAV_RETURN'] = 'PAIRED_B_MINUS_A_NET_NAV_RETURN'
    measures: Literal['BUY_FILLS,CASH_CLOSES,NET_NAV,MAX_CLOSE_DRAWDOWN'] = 'BUY_FILLS,CASH_CLOSES,NET_NAV,MAX_CLOSE_DRAWDOWN'
    benchmarks: Literal['ZERO_INTEREST_CASH,LOW_TURNOVER_IF_EVIDENCED'] = 'ZERO_INTEREST_CASH,LOW_TURNOVER_IF_EVIDENCED'
    diagnostics: Literal['SHADOW_STREAK_1_3,THU_FRI_OBSERVATIONS,NO_INTERVAL'] = 'SHADOW_STREAK_1_3,THU_FRI_OBSERVATIONS,NO_INTERVAL'


def _configs():
    config = load_config(ROOT / 'config.example.json')
    require(config == BotConfig(), 'approved example/default mismatch')
    return tuple(replace(config, strategy=replace(config.strategy, candidate=c)) for c in Candidate)


def prepare(scope=Scope(), folds=None):
    """Freeze the design and provenance without computing a signal or outcome."""
    require(type(scope) is Scope, 'typed synthetic scope required')
    scope.check()
    fixture = build(scope.fixture)
    calendar = fixture.stock.calendar
    folds = default_folds() if folds is None else folds
    require(type(folds) is tuple and folds and all(type(f) is Fold for f in folds), 'typed folds required')
    known = calendar.available_at
    for i, fold in enumerate(folds):
        require((fold.warmup, fold.train) == (folds[0].warmup, folds[0].train), 'expanding history required')
        if i:
            require(folds[i-1].end <= fold.selection, 'overlapping outcome or selection window')
        for start, end in zip((fold.warmup, fold.train, fold.selection, fold.test),
                              (fold.train, fold.selection, fold.test, fold.end)):
            sessions = calendar.sessions(start, end, known)
            require(sessions and sessions[0].trading_date == start, 'boundary must start an exchange session')
        require(fold.end == calendar.end or calendar.sessions(fold.end, fold.end + timedelta(days=1), known),
                'exclusive end must be a session boundary')
    source = tuple((name, sha256((ROOT / (name + '.py')).read_bytes()).hexdigest()) for name in OWNERS)
    return Study(scope, folds, known, digest(fixture), tuple(content_hash(c) for c in _configs()), digest(source))


@dataclass(frozen=True, slots=True)
class Observation:
    at: datetime
    signal_hash: str
    eligible: bool
    monthly: MonthlyEvidence | None
    regime_candidate: str | None
    shadow_one: bool
    shadow_three: bool
    rebalance_observation: str | None


@dataclass(frozen=True, slots=True)
class Metrics:
    buy_fills: int
    sessions: int
    cash_closes: int
    closing_equity: str
    net_return: str
    max_drawdown: str
    cash_benchmark_return: str = '0'
    low_turnover_benchmark: str = 'UNAVAILABLE: no independent tradable benchmark tape'


@dataclass(frozen=True, slots=True)
class AccountClose:
    at: datetime
    account_sha256: str
    settled_cash: Decimal
    buying_power: Decimal
    charges: Decimal
    held: int
    protected: int
    pending_orders: int
    marked_equity: Decimal | None


@dataclass(frozen=True, slots=True)
class Trial:
    trial_id: str
    candidate: Candidate
    fold: Fold
    status: str
    reasons: tuple[str, ...]
    decisions: tuple[Observation, ...] = ()
    closes: tuple[AccountClose, ...] = ()
    metrics: Metrics | None = None


@dataclass(frozen=True, slots=True)
class Comparison:
    study_sha256: str
    trials: tuple[Trial, ...]
    paired_net_differences: tuple[str | None, ...]
    origin: Literal['SYNTHETIC'] = 'SYNTHETIC'


def _decisions(fixture, config, fold):
    cal = fixture.stock.calendar
    days = cal.sessions(fold.train, fold.end, cal.available_at)
    cutoffs = tuple(instant(d.trading_date, 16) for d in days)
    regimes = regime_replay(fixture.index, config, fixture.binding, fold.warmup, cutoffs)
    signals = EMACrossoverStrategy().replay(fixture.stock, config, STOCK, fold.warmup, cutoffs,
        benchmark_snapshot=fixture.index, benchmark=fixture.binding, benchmark_start=fold.warmup,
        regimes=regimes, tick=fixture.tick)
    return tuple(zip(days, cutoffs, regimes, signals))


def _observations(decisions):
    observations = []
    last, streak = None, 0
    for day, at, regime, signal in decisions:
        candidate = regime.candidate if regime.status == 'READY' else None
        streak = (streak + 1 if candidate == last else 1) if candidate else 0
        last = candidate
        weekday = day.trading_date.weekday()
        label = {3: 'THURSDAY_SHADOW', 4: 'FRIDAY_REFERENCE'}.get(weekday)
        observations.append(Observation(at, digest(signal), signal.signal_eligible, signal.monthly,
                                        candidate, streak >= 1, streak >= 3, label))
    return tuple(observations)


def _receipt(config, kind, when, parent=None, *, signal=None, quantity=None, point=None):
    identifier = kind.lower()
    evidence = Evidence('synthetic manual receipt ' + identifier, digest((identifier, when)), when)
    event = ExecutionEvent(identifier, kind, 'study-trade', 'study-order', parent,
                           config.config_version, content_hash(config), 'SIMULATED',
                           when, when, when, (evidence,), quantity, point.price if point else None, None)
    return Command(identifier, when, 0, STOCK, 'study-trade', 'EVENT', 'BUY',
                   event=event, signal=signal, point=point)


def _opening_receipts(config, fixture, previous, approved, adapter):
    """A pre-scripted manual scenario, independent of human review/account journals."""
    at = fixture.opening.at
    if not previous or not approved:
        return (), ()
    signal, regime = previous
    if not signal.signal_eligible or signal.opportunity != approved:
        return (), ()
    submission = at - timedelta(minutes=10)
    for cutoff in (submission, at):
        universe = universe_as_of(fixture.stock, OPEN_DAY, cutoff)
        require(universe.members == (STOCK,), 'opening universe unavailable')
    pending = (_receipt(config, 'MANUAL_SUBMISSION', submission, 'trade_approval',
                        signal=signal, quantity=fixture.quantity),
               _receipt(config, 'ACKNOWLEDGEMENT', at - timedelta(minutes=9), 'manual_submission'))
    # Prompt 8 evaluates independent alternatives against the pre-order account. Its row
    # cannot supply a manual receipt. Prompt 6 rechecks the actual pending reservation.
    row = evaluate(fixture.stock, config, Account(fixture.cash.settled_cash), adapter,
                   fixture.capabilities, PriceRequest(signal, regime, fixture.opening,
                   at + timedelta(minutes=10)), at)
    if row.quantity < fixture.quantity:
        return pending, row.reasons or ('insufficient affordable whole shares',)
    if not fixture.fill_receipt:
        return pending, ('opening execution receipt unavailable',)
    fill = _receipt(config, 'FILL', at, 'manual_submission', signal=signal,
                    quantity=fixture.quantity, point=fixture.opening)
    return pending + (fill,), ()


def _trial(trial_id, fixture, fold, config):
    arm = config.strategy.candidate
    decisions = _decisions(fixture, config, fold)
    observations = _observations(decisions)
    marks = []
    tape = ()
    approved = previous = None
    baseline = reconstruct(project(Account(fixture.cash.settled_cash), fixture.cash, ACCOUNT),
                           ACCOUNT, fixture.cash.available_at)
    nav = update_nav(None, value(baseline, (), fixture.cash.available_at))
    peak_loss = Fraction(0)
    cash_closes = 0
    closes, issues = [], []
    for day, at, regime, signal in decisions:
        # Training/selection can initialize features. Neither can contribute a trade,
        # a valuation, a manual approval or a session to this fold's test account.
        universe = universe_as_of(fixture.stock, day.trading_date, at)
        require(universe.members == (STOCK,), 'incompatible synthetic universe')
        fixture.fees.check(at, at)
        require(fixture.costs.available_at <= at < fixture.costs.valid_until, 'cost evidence unavailable')
        require(signal.data_status == 'VALID' and regime.data_status == 'VALID', 'incomplete daily inputs')
        require(regime.status == 'READY', 'regime indicator evidence unavailable')
        require('frozen_proposal_unavailable' not in signal.reasons, 'frozen levels unavailable')
        if arm == Candidate.B:
            require(signal.monthly is not None, 'completed monthly evidence unavailable')
        if day.trading_date < fold.test:
            continue
        adapter = AccountingDependencies(config, fixture.cash, ACCOUNT, fixture.fees, marks, fixture.costs)
        if day.trading_date == OPEN_DAY:
            receipts, reasons = _opening_receipts(config, fixture, previous, approved, adapter)
            tape += receipts
            issues.extend(reasons)
        if signal.signal_eligible and signal.opportunity.selected_at == at:
            if signal.opportunity.levels.earliest_session == OPEN_DAY:
                tape += (_receipt(config, 'DECISION', at, signal=signal),
                         _receipt(config, 'TRADE_APPROVAL', at + timedelta(seconds=1), 'decision'))
                approved = signal.opportunity
        previous = (signal, regime)
        if not (fixture.case == 'missing-mark' and day.trading_date == OPEN_DAY):
            bars, quality = daily_as_of(fixture.stock, STOCK, day.trading_date,
                                        day.trading_date + timedelta(days=1), at)
            require(quality.status == 'VALID' and len(bars) == 1, 'daily mark rejected')
            bar = bars[0]
            marks.append(Mark(STOCK, bar.close, bar.session_close, bar.available_at,
                              at + timedelta(hours=1), bar.provider + '@' + bar.provider_version, digest(bar)))
        state = execution_replay(fixture.stock, config, fixture.cash, fixture.capabilities, tape, adapter, at)
        issues.extend(reason for a in state.audit if a.outcome != 'APPLIED' for reason in a.reasons)
        issues.extend(state.entry_blocks)
        if any(o.state == 'PENDING' for o in state.orders):
            issues.append('pending order; execution unresolved')
        balance = reconstruct(project(state, fixture.cash, ACCOUNT), ACCOUNT, at)
        valuation = value(balance, marks, at)
        issues.extend(valuation.issues)
        closes.append(AccountClose(at, digest(state), balance.cash, balance.buying_power,
                                   balance.charges, sum(h.quantity for h in balance.holdings),
                                   sum(p.protected_quantity for p in state.positions),
                                   sum(o.state == 'PENDING' for o in state.orders), valuation.equity))
        if balance.holdings and signal.exit_intent and not signal.exit_intent.resolved_at:
            issues.append('ordinary exit needs independent execution evidence')
        if issues:
            break
        nav = update_nav(nav, valuation, policy=config.risk)
        peak_loss = max(peak_loss, nav.drawdown)
        cash_closes += int(not balance.holdings)
    if issues:
        return Trial(trial_id, arm, fold, 'INCONCLUSIVE', tuple(dict.fromkeys(issues)), observations, tuple(closes))
    buys = sum(a.outcome == 'APPLIED' and a.command.role == 'BUY' and a.command.event is not None
               and a.command.event.kind == 'FILL' for a in state.audit)
    metrics = Metrics(buys, len(closes), cash_closes, str(valuation.equity), str(nav.nav - 1), str(peak_loss))
    return Trial(trial_id, arm, fold, 'COMPLETE', (), observations, tuple(closes), metrics)


def run(study, audit, attempt):
    """Replay a registered study. An explicit attempt label distinguishes reruns."""
    require(type(study) is Study and type(study.scope) is Scope, 'typed study required')
    study.scope.check()
    require(type(audit) is TrialAudit and type(attempt) is str and bool(attempt.strip()), 'audit/attempt required')
    require(study == prepare(study.scope, study.folds), 'study inputs, software or design changed')
    fingerprint = digest(study)
    # One directory is one declaration. Reusing it never replaces the study.
    audit._append(('study',), study)
    configs = _configs()
    plan = [(digest((fingerprint, fold, c.strategy.candidate)), fold, c) for fold in study.folds for c in configs]
    for trial_id, fold, config in plan:
        audit._append((trial_id, 'PLANNED'), dict(study=fingerprint, fold=fold, config=content_hash(config),
                      candidate=config.strategy.candidate, declared_at=study.declared_at,
                      selection_end_exclusive=instant(fold.test, 0), test_end_exclusive=instant(fold.end, 0)))
    fixture = build(study.scope.fixture)
    require(digest(fixture) == study.fixture_sha256, 'fixture mismatch at evaluation')
    trials = []
    for trial_id, fold, config in plan:
        audit._append((trial_id, attempt, 'STARTED'), dict(study=fingerprint, input=study.fixture_sha256))
        try:
            result = _trial(trial_id, fixture, fold, config)
        except ConfigError as exc:
            result = Trial(trial_id, config.strategy.candidate, fold, 'BLOCKED', (str(exc),))
        except Exception as exc:
            result = Trial(trial_id, config.strategy.candidate, fold, 'FAILED', (type(exc).__name__, str(exc)))
        audit._append((trial_id, attempt, 'RESULT'), result)
        trials.append(result)
    differences = tuple(str(Fraction(b.metrics.net_return) - Fraction(a.metrics.net_return))
                        if a.metrics and b.metrics else None for a, b in zip(trials[::2], trials[1::2]))
    return Comparison(fingerprint, tuple(trials), differences)
