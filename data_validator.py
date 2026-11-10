"""Rejection reports and point-in-time selection. Never forward fills."""
from datetime import timedelta
from config import ConfigError
from data_records import DailyBar, Snapshot, QualityResult, digest, IST


def validate_daily(bar: DailyBar, calendar):
    reasons = []
    if min(bar.open, bar.high, bar.low, bar.close) <= 0:
        reasons.append('nonpositive_price')
    if bar.volume < 0:
        reasons.append('negative_volume')
    if not bar.low <= min(bar.open, bar.close) <= max(bar.open, bar.close) <= bar.high:
        reasons.append('inconsistent_ohlc')
    if bar.available_at < bar.session_close:
        reasons.append('available_before_completion')
    day = next((d for d in calendar.days if d.trading_date == bar.trading_date), None)
    if day is None or not day.segments:
        reasons.append('unexpected_session')
    elif bar.session_close != day.segments[-1].closes:
        reasons.append('session_completion_mismatch')
    if bar.session_close.astimezone(IST).date() != bar.trading_date:
        reasons.append('trading_date_mismatch')
    return QualityResult('REJECTED' if reasons else 'VALID', tuple(reasons), (digest(bar),))


def batch_issues(bars):
    """Input stream ordering is checked before Snapshot canonicalizes storage."""
    reasons = []
    keys = [(b.instrument_id, b.trading_date, b.revision) for b in bars]
    if keys != sorted(keys):
        reasons.append('unordered_input')
    seen = {}
    for b, k in zip(bars, keys):
        if k in seen:
            reasons.append('duplicate_record' if seen[k] == b else 'conflicting_revision')
        seen[k] = b
    return tuple(sorted(set(reasons)))


def daily_as_of(snapshot: Snapshot, instrument_id, start, end, decision, *, require_current=False):
    sessions = snapshot.calendar.sessions(start, end, decision)
    expected = {d.trading_date: d for d in sessions}
    visible = [b for b in snapshot.bars if b.instrument_id == instrument_id and
               start <= b.trading_date < end and b.available_at <= decision]
    groups = {}
    for b in visible:
        groups.setdefault(b.trading_date, []).append(b)
    selected, issues = [], []
    for day, records in sorted(groups.items()):
        if day not in expected:
            issues.append('unexpected_session:' + str(day))
            continue
        revisions = {}
        for b in records:
            revisions.setdefault(b.revision, []).append(b)
        if any(len(v) != 1 for v in revisions.values()):
            issues.append('duplicate_or_conflict:' + str(day))
            continue
        ordered = [revisions[k][0] for k in sorted(revisions)]
        if any(a.available_at >= b.available_at for a, b in zip(ordered, ordered[1:])):
            issues.append('revision_availability_order:' + str(day))
            continue
        b = ordered[-1]  # A bad latest revision blocks; never fall back silently.
        q = validate_daily(b, snapshot.calendar)
        if q.reasons:
            issues.extend(f'{r}:{day}' for r in q.reasons)
            continue
        identities = [i for i in snapshot.identities if i.instrument_id == instrument_id and
                      i.start <= day < i.end and i.available_at <= decision]
        if len(identities) != 1 or identities[0].symbol != b.symbol or identities[0].status != 'LISTED':
            issues.append('identity_unavailable_conflicting_or_suspended:' + str(day))
            continue
        if b.session_close <= decision:
            selected.append(b)
    # Check only selected, valid, complete records visible at this decision.
    # Retain incompatible records and lineage for diagnostics; never normalize.
    for field in ('provider', 'provider_version', 'price_basis', 'volume_basis',
                  'corporate_action_treatment'):
        if len({getattr(b, field) for b in selected}) > 1:
            issues.append('incompatible_series_' + field)
    observed = {b.trading_date for b in selected}
    for day, d in expected.items():
        if d.segments[-1].closes <= decision and day not in observed:
            issues.append('missing_scheduled_bar:' + str(day))
    if require_current:
        # A current query must cover the decision's exchange date, not an old window.
        if end != decision.astimezone(IST).date() + timedelta(days=1):
            issues.append('stale_query_window')
        completed = [d.trading_date for d in sessions if d.segments[-1].closes <= decision]
        if not completed or not selected or selected[-1].trading_date != max(completed):
            issues.append('stale_observation')
    result = QualityResult('REJECTED' if issues else 'VALID', tuple(sorted(set(issues))), tuple(digest(b) for b in selected))
    return tuple(selected), result


def universe_as_of(snapshot, day, decision):
    if decision.utcoffset() is None:
        raise ConfigError('naive decision')
    records = [u for u in snapshot.universes if u.start <= day < u.end and u.available_at <= decision]
    if len(records) != 1:
        raise ConfigError('historical_universe_unavailable: survivorship bias; unbiased validation blocked')
    return records[0]


def synthetic_quality_report(snapshot, instrument_id, start, end, decision):
    """Engineering diagnostics, never evidence of unbiased research suitability."""
    bars, quality = daily_as_of(snapshot, instrument_id, start, end, decision)
    try:
        universe_as_of(snapshot, start, decision)
        universe_status = 'SYNTHETIC_MEMBERSHIP_ONLY'
    except ConfigError:
        universe_status = 'UNAVAILABLE_SURVIVORSHIP_BIAS'
    return {'origin': 'SYNTHETIC', 'snapshot_sha256': digest(snapshot),
            'decision_at': decision.isoformat(), 'start': start.isoformat(), 'end': end.isoformat(),
            'instrument_id': instrument_id, 'valid_visible_daily_records': len(bars),
            'status': quality.status, 'rejection_reasons': list(quality.reasons),
            'universe_status': universe_status, 'suitable_for_unbiased_historical_validation': False,
            'limitations': ['real ingestion UNVERIFIED', 'calendar SYNTHETIC',
                            'corporate-action feed completeness UNVERIFIED',
                            'no outcome research or holdout authorization']}
