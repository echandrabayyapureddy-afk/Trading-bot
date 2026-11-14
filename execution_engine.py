"""One offline synthetic account and exit state machine. No broker or ledger I/O."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D
from fractions import Fraction
from config import BotConfig, ConfigError, content_hash
from config_contracts import event_issues
from data_records import Snapshot, IST, digest
from data_validator import daily_as_of
from strategy import entry_price_issues
from execution_records import (Account, Audit, Capabilities, Command, DependencyEvidence,
                               Funding, Order, Position, REQUIRED_CHECKS)


def exact(value):
    """Finite-decimal rational to Decimal, without ambient rounding."""
    value = Fraction(value)
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        raise ConfigError('nonterminating account amount')
    scale = max(twos, fives)
    coefficient = abs(value.numerator) * 2**(scale-twos) * 5**(scale-fives)
    return D((int(value < 0), D(coefficient).as_tuple().digits, -scale))


def require(condition, reason):
    if not condition:
        raise ConfigError(reason)


def _session(snapshot, at):
    day = at.astimezone(IST).date()
    sessions = snapshot.calendar.sessions(day, day+timedelta(days=1), at)
    require(bool(sessions), 'not an exchange session')
    return sessions[0]


def _identity(snapshot, instrument, at):
    day = at.astimezone(IST).date()
    identities = tuple(i for i in snapshot.identities if i.instrument_id == instrument and
                       i.start <= day < i.end and i.available_at <= at)
    require(len(identities) == 1 and identities[0].status == 'LISTED', 'identity unavailable/suspended')
    require(not any(a.instrument_id == instrument and a.known_at <= at and
                    a.effective_date <= day for a in snapshot.actions), 'corporate action unsupported')
    return tuple(digest(i) for i in identities)


def _point(snapshot, config, command, capabilities, *, observation=None):
    point = observation if observation is not None else command.point
    require(point is not None, 'timestamped price evidence missing; touch is not a fill')
    at = command.event.occurred_at if command.event and observation is None else point.at
    require(point.instrument_id == command.instrument_id and point.at == at and
            point.available_at <= command.recorded_at, 'price evidence timing/identity mismatch')
    session = _session(snapshot, at)
    require(any(s.opens <= at <= s.closes for s in session.segments), 'price outside session segments')
    require(capabilities.available_at <= at < capabilities.valid_until, 'capabilities unavailable/expired')
    for key in ('provider', 'provider_version'):
        pin = getattr(config.data, key)
        require(pin is None or pin == getattr(point, key), 'price provider pin mismatch')
    lineage = _identity(snapshot, command.instrument_id, at)
    if point.kind == 'OPENING_ASSUMPTION':
        require(capabilities.opening_fill_assumption and at == session.segments[0].opens,
                'opening assumption unavailable or missed open')
    elif point.kind == 'EXPLICIT_TRADE':
        require(capabilities.explicit_trade_facts, 'explicit execution unsupported')
    return session, lineage + (digest(point), digest(capabilities))


def _signal(snapshot, config, command, at, levels=None):
    signal = command.signal
    require(signal is not None and signal.opportunity is not None, 'strategy evidence missing')
    opportunity = signal.opportunity
    require(signal.instrument_id == command.instrument_id and signal.config_sha256 == content_hash(config)
            and signal.calendar_sha256 == digest(snapshot.calendar), 'strategy binding mismatch')
    require(signal.signal_eligible and signal.data_status == 'VALID' and not signal.reasons and
            opportunity.state == 'ACTIVE' and opportunity.levels is not None,
            'strategy revalidation blocked')
    require(signal.available_at <= at and signal.as_of <= at and opportunity.selected_at <= at,
            'future strategy evidence')
    end = at.astimezone(IST).date()+timedelta(days=1)
    sessions = snapshot.calendar.sessions(signal.initialization_start, end, at)
    complete = tuple(s for s in sessions if s.segments[-1].closes <= at)
    require(bool(complete) and signal.session == complete[-1].trading_date, 'stale strategy evidence')
    bars, quality = daily_as_of(snapshot, command.instrument_id, signal.initialization_start,
                                signal.session+timedelta(days=1), at)
    require(quality.status == 'VALID' and quality.lineage == signal.history_lineage,
            'strategy data rejected/revised')
    ids = tuple(digest(i) for i in snapshot.identities if i.instrument_id == command.instrument_id and
                i.available_at <= at and any(i.start <= b.trading_date < i.end for b in bars))
    require(ids == signal.identity_lineage, 'strategy identity revised')
    require(levels is None or opportunity.levels == levels, 'frozen proposal changed')
    proposal = opportunity.levels
    require(proposal.proposal_at == opportunity.selected_at and proposal.ceiling <= proposal.close,
            'proposal binding/ceiling invalid')
    original, q = daily_as_of(snapshot, command.instrument_id, proposal.session,
                             proposal.session+timedelta(days=1), proposal.proposal_at)
    require(q.status == 'VALID' and len(original) == 1 and digest(original[0]) == proposal.source_sha256
            and original[0].close == proposal.close and original[0].session_close <= proposal.proposal_at,
            'proposal source mismatch')
    future = snapshot.calendar.sessions(proposal.session+timedelta(days=1), snapshot.calendar.end,
                                         proposal.proposal_at)
    require(len(future) >= 2 and proposal.earliest_session == future[1].trading_date,
            'D+2 calendar mismatch')
    return proposal


def _dependency(adapter, state, command, cfg, buying):
    gate = adapter.assess(state, command, content_hash(cfg)) if adapter is not None else None
    require(type(gate) is DependencyEvidence, 'dependency evidence unavailable')
    at = command.event.occurred_at
    require(gate.at == at and gate.state_sha256 == digest(state) and gate.config_sha256 == content_hash(cfg)
            and bool(gate.evidence), 'dependency evidence binding mismatch')
    require(gate.fee is not None and gate.adverse_slippage is not None, 'unknown fee/slippage')
    if buying:
        require(not state.entry_blocks, 'account blocked for reconciliation')
        require(not gate.entry_suspended, 'drawdown suspension requires documented clearance')
        require(gate.risk_approved and set(gate.checked_policies) == set(REQUIRED_CHECKS),
                'fixed-policy risk approval missing')
        require(gate.spendable_cash is not None, 'settlement/cash evidence missing')
        live = tuple(p for p in state.positions if p.quantity)
        require(len(gate.positions) == len(live) and {p.position_id for p in gate.positions} ==
                {p.trade_id for p in live}, 'position risk coverage mismatch')
        for position in live:
            require(position.exit_state == 'ACTIVE' and position.protected_quantity >= position.quantity,
                    'unprotected/triggered exposure blocks entries')
            risk = next(p for p in gate.positions if p.position_id == position.trade_id)
            require(not risk.issues(at), 'existing-position risk unresolved')
            require((risk.remaining_quantity, risk.entry_price, risk.protective_trigger,
                     risk.protective_quantity, risk.protection_event_id) ==
                    (position.quantity, position.entry_price, position.levels.stop,
                     position.protected_quantity, position.activation_id), 'position risk facts mismatch')
    return gate


def _replace_position(state, position):
    return replace(state, positions=tuple(position if p.trade_id == position.trade_id else p
                                         for p in state.positions))


def _exit_transition(state, command, snapshot, config, capabilities):
    """The sole owner of activation, triggering, exit intents and sell quantities."""
    position = next((p for p in state.positions if p.trade_id == command.trade_id), None)
    require(position is not None and position.quantity > 0 and position.instrument_id == command.instrument_id,
            'no remaining position')
    if command.action == 'EXIT_INTENT':
        intent = command.intent
        require(intent is not None and intent.instrument_id == position.instrument_id and
                intent.resolved_at is None and intent.observed_at <= command.recorded_at,
                'invalid/unavailable exit intent')
        sessions = snapshot.calendar.sessions(intent.session, intent.session+timedelta(days=1), command.recorded_at)
        require(bool(sessions) and intent.observed_at >= sessions[0].segments[-1].closes,
                'exit intent before completed close')
        require(position.intent is None or position.intent == intent, 'unresolved exit intent cannot be replaced')
        return _replace_position(state, replace(position, intent=intent)), ()
    if command.action == 'TRIGGER':
        _, lineage = _point(snapshot, config, command, capabilities)
        require(position.activation_at is not None and position.activation_at <= command.point.at and
                position.exit_state == 'ACTIVE' and command.point.price <= position.levels.stop,
                'protective trigger not established after activation')
        require((position.provider, position.provider_version) ==
                (command.point.provider, command.point.provider_version), 'position price series mismatch')
        return _replace_position(state, replace(position, exit_state='TRIGGERED_UNFILLED',
            trigger_at=command.point.at, trigger_command_id=command.command_id,
            trigger_evidence_sha256=digest(command.point))), lineage
    event = command.event
    require(event.kind == 'PROTECTION_ACTIVATION', 'unsupported exit transition')
    session = _session(snapshot, event.occurred_at)
    require(any(s.opens <= event.occurred_at <= s.closes for s in session.segments), 'activation outside session')
    _identity(snapshot, command.instrument_id, event.occurred_at)
    require(position.activation_at is None and event.parent_id == position.entry_event_id and
            event.price == position.levels.stop and event.quantity <= position.quantity,
            'activation does not match frozen remaining position')
    order = next((o for o in state.orders if o.order_id == event.order_id), None)
    require(order is not None and order.role == 'PROTECTIVE' and order.trade_id == position.trade_id and
            order.submitted_at <= event.occurred_at, 'protective submission missing')
    require(command.stop_type in ('STOP_MARKET', 'STOP_LIMIT'), 'explicit stop capability required')
    require(config.execution.protective_order_type is None or
            config.execution.protective_order_type == command.stop_type, 'configured stop type mismatch')
    require((command.stop_type == 'STOP_MARKET' and command.stop_limit is None) or
            (command.stop_type == 'STOP_LIMIT' and command.stop_limit is not None and
             0 < command.stop_limit <= event.price), 'invalid stop limit')
    return _replace_position(state, replace(position, protected_quantity=event.quantity,
        activation_at=event.occurred_at, activation_id=event.event_id, protective_order_id=event.order_id,
        stop_type=command.stop_type, stop_limit=command.stop_limit, exit_state='ACTIVE')), ()


def _sell(state, command, order, price):
    """Authoritative all-or-none exit: called only after causal/price validation."""
    position = next((p for p in state.positions if p.trade_id == command.trade_id), None)
    require(position is not None and position.quantity > 0, 'already closed/no position')
    event = command.event
    require(event.quantity == position.quantity == order.quantity, 'partial execution unsupported')
    require((command.point.provider, command.point.provider_version) ==
            (position.provider, position.provider_version), 'exit price series mismatch')
    if order.role == 'ORDINARY':
        require(position.intent is not None and position.intent.resolved_at is None and
                event.occurred_at > position.intent.observed_at, 'ordinary exit before/at signal close')
    else:
        require(position.exit_state == 'TRIGGERED_UNFILLED' and position.protected_quantity >= event.quantity
                and order.order_id == position.protective_order_id, 'protection not triggered/covered')
        require(position.trigger_at is not None and position.activation_at is not None and
                position.activation_at <= position.trigger_at <= event.occurred_at and
                position.trigger_command_id is not None and position.trigger_evidence_sha256 is not None,
                'protective fill precedes trigger or trigger evidence missing')
        if position.stop_type == 'STOP_LIMIT':
            require(price >= position.stop_limit, 'stop-limit remains unfilled below limit')
    proceeds = exact(Fraction(price)*event.quantity-Fraction(order.fee))
    require(proceeds >= 0, 'exit fee exceeds proceeds; external settlement required')
    intent = position.intent
    if intent is not None:
        require(event.occurred_at >= intent.observed_at, 'fill predates observed intent; reconciliation required')
        intent = replace(intent, resolved_at=event.occurred_at, resolution_evidence='SYNTHETIC:'+event.event_id)
    closed = replace(position, quantity=0, protected_quantity=0, exit_state='CLOSED', intent=intent)
    state = _replace_position(state, closed)
    # No uncertain or unsettled exit proceeds are ever credited to spendable cash.
    return replace(state, unsettled_proceeds=exact(Fraction(state.unsettled_proceeds)+Fraction(proceeds)),
                   orders=tuple(replace(o, state='FILLED' if o.order_id == order.order_id else 'CANCELLED')
                                if o.trade_id == order.trade_id and o.state == 'PENDING' else o for o in state.orders))


def _mutation_at(command):
    """Occurrence cutoff for accepted account transitions, not notification time."""
    if command.event and command.event.kind in ('FILL', 'PROTECTION_ACTIVATION'):
        return command.event.occurred_at
    if command.action == 'TRIGGER' and command.point:
        return command.point.at
    if command.action == 'EXIT_INTENT' and command.intent:
        return command.intent.observed_at
    if command.action == 'BAR':
        return command.recorded_at  # uncertainty first becomes known here
    return None


def _event(state, command, snapshot, config, capabilities, adapter):
    event = command.event
    lineage = (digest(capabilities),)
    require(event.origin == 'SIMULATED', 'ACTUAL events cannot enter synthetic account')
    require((event.trade_id, event.recorded_at, event.config_sha256, event.config_version) ==
            (command.trade_id, command.recorded_at, content_hash(config), config.config_version),
            'event wrapper/config mismatch')
    require(capabilities.available_at <= event.occurred_at < capabilities.valid_until, 'capabilities unavailable/expired')
    causal_issues = event_issues(state.events+(event,), command.recorded_at)
    require(not causal_issues, 'causal event contract rejected: '+ '; '.join(causal_issues))
    parent_command = next((a.command for a in state.audit if a.outcome == 'APPLIED' and
                           a.command.event and a.command.event.event_id == event.parent_id), None)
    if parent_command:
        require(parent_command.instrument_id == command.instrument_id, 'linked instrument mismatch')
        if event.kind != 'PROTECTION_ACTIVATION':
            require(parent_command.role == command.role, 'linked order role mismatch')
    if event.kind == 'DECISION' and command.role == 'BUY':
        levels = _signal(snapshot, config, command, event.occurred_at)
        require(levels.proposal_at == event.occurred_at, 'decision must match proposal time')
    if event.kind == 'MANUAL_SUBMISSION':
        require(event.quantity is not None, 'explicit order quantity required')
        require(not any(o.order_id == event.order_id for o in state.orders), 'order identifier reused')
        buying = command.role == 'BUY'
        gate = _dependency(adapter, state, command, config, buying)
        lineage += (digest(gate),)
        levels = None
        reservation = D(0)
        if buying:
            levels = _signal(snapshot, config, command, event.occurred_at)
            # All descendants of a buy decision bind the same frozen proposal.
            ancestor = parent_command
            while ancestor and ancestor.event.kind != 'DECISION':
                ancestor = next((a.command for a in state.audit if a.outcome == 'APPLIED' and a.command.event
                                 and a.command.event.event_id == ancestor.event.parent_id), None)
            require(ancestor is not None and ancestor.signal.opportunity.levels == levels,
                    'submission proposal changed')
            occupied = {p.instrument_id for p in state.positions if p.quantity} | {
                o.instrument_id for o in state.orders if o.role == 'BUY' and o.state == 'PENDING'}
            require(command.instrument_id not in occupied and len(occupied) < config.risk.max_positions,
                    'pyramiding/capacity blocked')
            require(not any(p.trade_id == command.trade_id for p in state.positions) and
                    not any(o.trade_id == command.trade_id and o.role == 'BUY' for o in state.orders), 'trade id reused')
            reservation = exact(Fraction(levels.ceiling)*event.quantity+Fraction(gate.fee))
            reserved = sum((Fraction(o.reservation) for o in state.orders if o.state == 'PENDING'), Fraction(0))
            require(reservation <= min(Fraction(state.settled_cash), Fraction(gate.spendable_cash))-reserved,
                    'insufficient shared settled cash including costs')
        else:
            position = next((p for p in state.positions if p.trade_id == command.trade_id and p.quantity), None)
            require(position is not None and position.instrument_id == command.instrument_id,
                    'exit submission without position')
            require(event.quantity == position.quantity, 'partial execution unsupported')
            if command.role == 'ORDINARY':
                require(position.intent is not None and position.intent.resolved_at is None and
                        event.occurred_at >= position.intent.observed_at, 'ordinary intent missing')
        order = Order(event.order_id, command.trade_id, command.instrument_id, command.role, event.quantity,
                      event.occurred_at, reservation, gate.fee, levels)
        state = replace(state, orders=state.orders+(order,))
    if event.kind == 'PROTECTION_ACTIVATION':
        state, lineage = _exit_transition(state, command, snapshot, config, capabilities)
        return replace(state, events=state.events+(event,)), lineage
    if event.kind == 'FILL':
        order = next((o for o in state.orders if o.order_id == event.order_id), None)
        require(order is not None and order.state == 'PENDING' and order.role == command.role,
                'fill without pending matching order')
        require(event.quantity == order.quantity, 'partial execution unsupported')
        require(not any(a.outcome in ('APPLIED', 'UNRESOLVED') and
                        _mutation_at(a.command) is not None and
                        _mutation_at(a.command) > event.occurred_at for a in state.audit),
                'late state-changing occurrence needs reconciliation')
        session, lineage = _point(snapshot, config, command, capabilities)
        require(command.point.kind != 'OBSERVATION', 'observation is not execution evidence')
        buying = order.role == 'BUY'
        gate = _dependency(adapter, state, command, config, buying)
        lineage += (digest(gate),)
        require(gate.fee == order.fee, 'fee changed since reservation')
        price = exact(Fraction(command.point.price)+(1 if buying else -1)*Fraction(gate.adverse_slippage))
        require(price > 0 and price == event.price, 'fill price does not match explicit slippage assumption')
        if command.point.kind == 'OPENING_ASSUMPTION':
            require(order.submitted_at < session.segments[0].opens, 'missed opening opportunity')
        require(order.submitted_at < event.occurred_at, 'submission cutoff missed')
        if buying:
            _signal(snapshot, config, command, event.occurred_at, order.levels)
            opening = command.point if command.point.kind == 'OPENING_ASSUMPTION' else command.opening
            require(opening is not None, 'opening price evidence required for intraday entry')
            _, opening_lineage = _point(snapshot, config, command, capabilities, observation=opening)
            require(opening.at == session.segments[0].opens and
                    (opening.provider, opening.provider_version) ==
                    (command.point.provider, command.point.provider_version), 'opening evidence mismatch')
            require(opening.price > order.levels.stop, 'session opened at/below frozen stop')
            lineage += opening_lineage
            source, quality = daily_as_of(snapshot, command.instrument_id, command.signal.session,
                command.signal.session+timedelta(days=1), event.occurred_at)
            require(quality.status == 'VALID' and len(source) == 1 and
                    (source[0].provider, source[0].provider_version) ==
                    (command.point.provider, command.point.provider_version), 'execution source differs from signal')
            require(not entry_price_issues(order.levels, command.point.price, session.trading_date),
                    'opening/execution price violates ceiling, stop or D+2')
            require(not entry_price_issues(order.levels, price, session.trading_date), 'slippage breaches frozen levels')
            require(not any(p.quantity and p.instrument_id == command.instrument_id for p in state.positions), 'duplicate position')
            spend = exact(Fraction(price)*event.quantity+Fraction(order.fee))
            other = sum((Fraction(o.reservation) for o in state.orders if o.state == 'PENDING' and o != order), Fraction(0))
            require(Fraction(spend)+other <= min(Fraction(state.settled_cash), Fraction(gate.spendable_cash)), 'cash no longer available')
            position = Position(command.trade_id, command.instrument_id, event.quantity, price, event.occurred_at,
                                event.event_id, order.levels, command.point.provider, command.point.provider_version)
            state = replace(state, settled_cash=exact(Fraction(state.settled_cash)-Fraction(spend)),
                            positions=state.positions+(position,), orders=tuple(replace(o, state='FILLED') if o == order else o for o in state.orders))
        else:
            state = _sell(state, command, order, price)
        return replace(state, events=state.events+(event,)), lineage
    return replace(state, events=state.events+(event,)), lineage


def replay(snapshot: Snapshot, config: BotConfig, funding: Funding, capabilities: Capabilities,
           commands: tuple[Command, ...], dependencies, as_of) -> Account:
    """Replay visible receipts; return immutable journal/state. No external state accepted."""
    require(type(snapshot) is Snapshot and type(config) is BotConfig and type(funding) is Funding
            and type(capabilities) is Capabilities and type(commands) is tuple and
            all(type(c) is Command for c in commands), 'typed synthetic inputs required')
    require(as_of.utcoffset() is not None and funding.available_at <= as_of, 'funding/cutoff unavailable')
    config.validate()
    require(config.execution.operator_delay_sessions == 1, 'approved delay only')
    for expected, actual in ((config.data.calendar_version, snapshot.calendar.version),
                             (config.data.snapshot_sha256, digest(snapshot))):
        require(expected is None or expected == actual, 'data pin mismatch')
    state = Account(funding.settled_cash)
    visible = sorted((c for c in commands if c.recorded_at <= as_of), key=lambda c:(c.recorded_at, c.priority, c.command_id))
    priorities = {}
    for c in visible:
        if c.event and c.role == 'BUY' and c.event.kind == 'MANUAL_SUBMISSION':
            key = (c.recorded_at, c.priority)
            require(key not in priorities or priorities[key] == c, 'distinct simultaneous candidates need explicit unique priorities')
            priorities[key] = c
    seen = {}
    for command in visible:
        if command.command_id in seen and command == seen[command.command_id]:
            continue
        before = state
        try:
            require(command.recorded_at >= funding.available_at, 'command before funding evidence')
            if command.event:
                require(command.event.occurred_at >= funding.available_at, 'occurrence before funding evidence')
            require(command.command_id not in seen, 'conflicting command identifier')
            if command.event:
                old = next((a.command for a in state.audit if a.command.event and
                            a.command.event.event_id == command.event.event_id), None)
                if old is not None:
                    require(replace(old, command_id=command.command_id) == command, 'conflicting event identifier')
                    continue
            if command.action == 'EVENT':
                state, lineage = _event(state, command, snapshot, config, capabilities, dependencies)
            elif command.action in ('TRIGGER', 'EXIT_INTENT'):
                state, lineage = _exit_transition(state, command, snapshot, config, capabilities)
            else:
                require(command.bar_date is not None, 'bar date required')
                bars, q = daily_as_of(snapshot, command.instrument_id, command.bar_date,
                                     command.bar_date+timedelta(days=1), command.recorded_at)
                require(q.status == 'VALID' and len(bars) == 1, 'daily observation rejected/unavailable')
                _identity(snapshot, command.instrument_id, command.recorded_at)
                # Deliberately never derive fills, trigger times or account branches from OHLC.
                lineage = q.lineage
                state = replace(state, entry_blocks=state.entry_blocks+('daily OHLC ordering/execution unresolved',))
                state = replace(state, audit=state.audit+(Audit(command, 'UNRESOLVED', ('daily OHLC is not execution evidence',), lineage),))
                seen[command.command_id] = command
                continue
            state = replace(state, audit=state.audit+(Audit(command, 'APPLIED', (), lineage),))
        except ConfigError as exc:
            reason = str(exc)
            # No failed transition partly consumes cash/quantity. Preserve its original facts.
            blocks = before.entry_blocks
            if ('conflicting' in reason or 'causal' in reason or 'drawdown' in reason or
                command.action in ('TRIGGER', 'BAR') or (command.event and command.event.kind in ('FILL', 'PROTECTION_ACTIVATION'))):
                blocks += (reason,)
            state = replace(before, entry_blocks=blocks, audit=before.audit+(Audit(command, 'REJECTED', (reason,)),))
        seen.setdefault(command.command_id, command)
    return state
