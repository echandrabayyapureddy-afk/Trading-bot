"""Offline fixture ingestion and completed candles; no network or outcome research."""
from datetime import date, datetime, timedelta, time
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
from typing import Protocol
from config import BotConfig, ConfigError, content_hash, authorize_development_window
from data_records import Snapshot, Candle, AdjustedView, digest, IST
from data_validator import daily_as_of, batch_issues


class ProviderUnavailable(ConfigError):
    pass


class DailyProvider(Protocol):
    def fetch(self) -> Snapshot: ...


class FixtureProvider:
    """Only SYNTHETIC snapshots are accepted by the current record schema."""
    def __init__(self, snapshot: Snapshot):
        if type(snapshot) is not Snapshot:
            raise ConfigError('typed snapshot required')
        self.snapshot = snapshot

    def fetch(self):
        return self.snapshot


class UnverifiedProvider:
    def fetch(self):
        raise ProviderUnavailable('real ingestion UNVERIFIED; no network fallback')


def fetch_daily(provider: DailyProvider, config: BotConfig):
    if type(config) is not BotConfig:
        raise ConfigError('validated BotConfig required')
    config.validate()
    snapshot = provider.fetch()
    if type(snapshot) is not Snapshot:
        raise ConfigError('typed snapshot required')
    # Explicit pins are binding even in offline engineering. No config mutation.
    for expected, actual, name in (
        (config.data.calendar_version, snapshot.calendar.version, 'calendar'),
        (config.data.snapshot_sha256, digest(snapshot), 'snapshot')):
        if expected is not None and expected != actual:
            raise ConfigError(name + ' pin mismatch')
    for b in snapshot.bars:
        for expected, actual in ((config.data.provider, b.provider), (config.data.provider_version, b.provider_version)):
            if expected is not None and expected != actual:
                raise ConfigError('provider pin mismatch')
    if config.data.universe_version is not None and any(u.version != config.data.universe_version for u in snapshot.universes):
        raise ConfigError('universe version mismatch')
    if config.data.universe_version is not None and not snapshot.universes:
        raise ConfigError('pinned universe missing')
    return snapshot


def ingest_ordered_fixture(calendar, bars, identities, *, actions=(), universes=()):
    issues = batch_issues(bars)
    if issues:
        raise ConfigError(', '.join(issues))
    return Snapshot(calendar, tuple(bars), tuple(identities), tuple(actions), tuple(universes))


def period_bounds(day, timeframe):
    if type(day) is not date:
        raise ConfigError('trading date required')
    if timeframe == 'WEEKLY':
        start = day - timedelta(days=day.weekday())
        return start, start + timedelta(days=7)
    if timeframe == 'MONTHLY':
        start = day.replace(day=1)
        return start, date(day.year + (day.month == 12), day.month % 12 + 1, 1)
    raise ConfigError('unsupported timeframe')


def completed_candle(snapshot, instrument_id, day, timeframe, decision):
    start, end = period_bounds(day, timeframe)
    sessions = snapshot.calendar.sessions(start, end, decision)
    if not sessions or sessions[-1].segments[-1].closes > decision:
        raise ConfigError('period has not completed')
    bars, quality = daily_as_of(snapshot, instrument_id, start, end, decision)
    if quality.reasons or len(bars) != len(sessions):
        raise ConfigError('incomplete/invalid period: ' + ', '.join(quality.reasons))
    # Provider/version consistency prevents summing incompatible daily inputs.
    if len({(b.provider, b.provider_version, b.price_basis, b.volume_basis) for b in bars}) != 1:
        raise ConfigError('inconsistent contributing basis/provider')
    with localcontext() as ctx:
        ctx.prec = max(b.volume.adjusted() for b in bars) - min(b.volume.as_tuple().exponent for b in bars) + len(str(len(bars))) + 2
        ctx.rounding = ROUND_HALF_EVEN
        volume = sum((b.volume for b in bars), Decimal(0))
    identities = tuple(i for i in snapshot.identities if i.instrument_id == instrument_id and
                       any(i.start <= b.trading_date < i.end for b in bars) and i.available_at <= decision)
    return Candle(instrument_id, timeframe, start, end, sessions[-1].segments[-1].closes,
                  max(snapshot.calendar.available_at, *(b.available_at for b in bars),
                      *(i.available_at for i in snapshot.identities if i.instrument_id == instrument_id and
                        any(i.start <= b.trading_date < i.end for b in bars) and i.available_at <= decision)),
                  bars[0].open, max(b.high for b in bars), min(b.low for b in bars), bars[-1].close,
                  volume, digest(snapshot.calendar), quality.lineage, tuple(digest(i) for i in identities))


def split_adjusted_view(snapshot, bar, decision):
    """Back-adjust to decision date using available effective split evidence only.

    Decimal arithmetic uses 50 significant digits (ROUND_HALF_EVEN). Raw data is
    never changed. No dividends, mergers, rights issues or total-return support.
    """
    if bar not in snapshot.bars:
        raise ConfigError('bar is not in snapshot')
    selected, q = daily_as_of(snapshot, bar.instrument_id, bar.trading_date,
                              bar.trading_date + timedelta(days=1), decision)
    if q.reasons or selected != (bar,):
        raise ConfigError('bar not valid/current revision at decision')
    # Date-only synthetic convention, not an asserted exchange/broker event time.
    def effective_time(action):
        return datetime.combine(action.effective_date, time.min, IST)

    effective = [a for a in snapshot.actions if a.instrument_id == bar.instrument_id and
                 bar.trading_date < a.effective_date and effective_time(a) <= decision and a.known_at <= decision]
    # Missing evidence for an already effective action blocks adjusted views.
    if any(a.available_at > decision or a.kind != 'SPLIT' for a in effective):
        raise ConfigError('adjustment evidence unavailable or action unsupported')
    if len({a.action_id for a in effective}) != len(effective):
        raise ConfigError('duplicate/conflicting corporate action')
    with localcontext() as ctx:
        ctx.prec = 50
        ctx.rounding = ROUND_HALF_EVEN
        factor = Decimal(1)
        for a in effective:
            factor *= a.new_per_old
        identities = tuple(i for i in snapshot.identities if i.instrument_id == bar.instrument_id and
                           i.start <= bar.trading_date < i.end and i.available_at <= decision)
        return AdjustedView(digest(bar), tuple(digest(a) for a in effective),
                            digest(snapshot.calendar), tuple(digest(i) for i in identities),
                            max([bar.available_at, snapshot.calendar.available_at] +
                                [a.available_at for a in effective] + [i.available_at for i in identities] +
                                [effective_time(a) for a in effective]),
                            decision, tuple(effective_time(a) for a in effective),
                            *(v / factor for v in (bar.open, bar.high, bar.low, bar.close)), bar.volume * factor)


def authorize_actual_research(config, manifest, start, end, *, authorization_at: datetime,
                              verification_profiles: tuple, expected_manifest_sha256: str):
    """Explicit current cutoff required; caller supplies current approval records.

    This wrapper grants no data access and cannot prove revocation-feed freshness.
    """
    if type(authorization_at) is not datetime or authorization_at.utcoffset() is None:
        raise ConfigError('explicit aware authorization cutoff required')
    return authorize_development_window(config, manifest, start, end,
        authorization_at=authorization_at, verification_profiles=verification_profiles,
        expected_manifest_sha256=expected_manifest_sha256)


def snapshot_metadata(snapshot, config):
    return {'schema_version': '1.0', 'origin': 'SYNTHETIC', 'snapshot_sha256': digest(snapshot),
            'config_sha256': content_hash(config), 'calendar_sha256': digest(snapshot.calendar),
            'calendar_version': snapshot.calendar.version, 'records': len(snapshot.bars),
            'unbiased_historical_validation': False,
            'limitations': ['synthetic_only', 'real_provider_unverified', 'real_calendar_unverified',
                            'corporate_action_completeness_unverified', 'no_research_authorization']}
