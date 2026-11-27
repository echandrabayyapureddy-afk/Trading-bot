"""Read exact daily objects from a custodian-supplied synthetic development directory FD."""
from dataclasses import dataclass, replace
from datetime import date, datetime
import errno
import hashlib
import os
import stat

from config import ConfigError, Validated, from_dict, parse_json, utc_instant
from data_fetcher import authorize_actual_research
from data_records import DailyBar, IST, Snapshot, digest
from data_validator import batch_issues, daily_as_of, universe_as_of


@dataclass(frozen=True)
class DayObject(Validated):
    day: date
    sha256: str


@dataclass(frozen=True)
class Partition(Validated):
    snapshot_id: str
    snapshot_sha256: str
    device: int
    inode: int
    metadata: Snapshot
    objects: tuple[DayObject, ...]

    def validate(self):
        if self.metadata.bars or self.metadata.origin != 'SYNTHETIC':
            raise ConfigError('synthetic metadata without rows required')
        days = tuple(obj.day for obj in self.objects)
        if days != tuple(sorted(set(days))):
            raise ConfigError('duplicate or unordered development objects')


def read_development(config, manifest, partition: Partition, directory_fd: int, *,
                     expected_manifest_sha256: str, expected_partition_sha256: str,
                     warmup_start: date, start: date, end: date, decision_at: datetime,
                     authorization_at: datetime, verification_profiles: tuple, trace: list):
    """Return raw point-in-time rows atomically. The trace also survives rejection."""
    trace.append(('request', warmup_start, start, end, decision_at, authorization_at))
    if type(start) is not date or type(warmup_start) is not date or type(end) is not date or not warmup_start <= start < end:
        raise ConfigError('invalid warmup/development interval')
    authorize_actual_research(config, manifest, warmup_start, end, authorization_at=authorization_at,
                              verification_profiles=verification_profiles,
                              expected_manifest_sha256=expected_manifest_sha256)
    if (type(partition) is not Partition or digest(partition) != expected_partition_sha256
            or partition.snapshot_id != manifest.snapshot_id or partition.snapshot_sha256 != manifest.snapshot_sha256):
        raise ConfigError('development partition identity mismatch')
    directory = os.fstat(directory_fd)
    if not stat.S_ISDIR(directory.st_mode) or (directory.st_dev, directory.st_ino) != (partition.device, partition.inode):
        raise ConfigError('development directory identity mismatch')
    if (config.data.provider != 'SYNTHETIC' or type(decision_at) is not datetime
            or decision_at.utcoffset() is None or utc_instant(decision_at) > utc_instant(authorization_at)
            or not start <= decision_at.astimezone(IST).date() < end):
        raise ConfigError('synthetic provider and valid decision cutoff required')
    # Compare metadata visibility on the timeline while retaining the original request trace.
    decision_at = utc_instant(decision_at)
    metadata = partition.metadata
    if metadata.calendar.version != manifest.calendar_version:
        raise ConfigError('calendar mismatch')
    objects = {obj.day: obj for obj in partition.objects}
    if any(not manifest.development_start <= day < manifest.development_end for day in objects):
        raise ConfigError('catalog includes non-development object')
    sessions = metadata.calendar.sessions(warmup_start, end, decision_at)
    if any(day.trading_date not in objects or day.segments[-1].closes > decision_at for day in sessions):
        raise ConfigError('missing object or incomplete session')
    for day in sessions:
        membership = universe_as_of(metadata, day.trading_date, decision_at)
        stocks = set(manifest.instruments) - {config.regime.benchmark}
        if membership.version != manifest.universe_version or not stocks.issubset(membership.members):
            raise ConfigError('dated development universe unavailable or incompatible')
    rows = []
    for day in sessions:
        obj = objects[day.trading_date]
        name = obj.day.isoformat() + '.json'
        checked = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if stat.S_ISLNK(checked.st_mode):
            raise OSError(errno.ELOOP, 'development object is a symlink', name)
        if not stat.S_ISREG(checked.st_mode) or checked.st_nlink != 1:
            raise ConfigError('single-link regular file required')
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
        with os.fdopen(fd, 'rb') as file:
            trace.append(('opened', name))
            info = os.fstat(file.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ConfigError('single-link regular file required')
            if not os.path.samestat(checked, info):
                raise ConfigError('development object changed during open')
            payload = file.read()
        if hashlib.sha256(payload).hexdigest() != obj.sha256:
            raise ConfigError('development object content mismatch')
        doc = parse_json(payload.decode('utf-8'))
        if (set(doc) != {'snapshot_id', 'day', 'rows'} or doc['snapshot_id'] != manifest.snapshot_id
                or doc['day'] != obj.day.isoformat() or type(doc['rows']) is not list):
            raise ConfigError('development object header mismatch')
        bars = tuple(from_dict(DailyBar, row) for row in doc['rows'])
        for bar in bars:
            if (bar.trading_date != obj.day or bar.instrument_id not in manifest.instruments
                    or (bar.provider, bar.provider_version) != (config.data.provider, manifest.provider_version)):
                raise ConfigError('row outside pinned partition or series')
        issues = batch_issues(tuple(bar for bar in bars if bar.available_at <= decision_at))
        if issues:
            raise ConfigError(', '.join(issues))
        rows.extend(bars)
    snapshot = replace(metadata, bars=tuple(rows))
    selected = []
    for instrument in manifest.instruments:
        series, quality = daily_as_of(snapshot, instrument, warmup_start, end, decision_at)
        if quality.status != 'VALID':
            raise ConfigError(', '.join(quality.reasons))
        selected.extend(series)
    trace.append(('returned', tuple((b.instrument_id, b.trading_date, b.revision) for b in selected)))
    return tuple(selected)
