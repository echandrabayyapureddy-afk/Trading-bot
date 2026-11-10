"""Immutable content-addressed synthetic snapshots. Retrieval time is not content."""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
from config import ConfigError, from_dict, parse_json
from data_records import Snapshot, digest, encoded


@dataclass(frozen=True, slots=True)
class CacheRead:
    snapshot: Snapshot
    retrieved_at: datetime


class LocalCache:
    def __init__(self, directory):
        self.directory = Path(directory)

    def put(self, snapshot: Snapshot):
        if type(snapshot) is not Snapshot:
            raise ConfigError('typed snapshot required')
        key = digest(snapshot)
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / (key + '.json')
        data = encoded(snapshot)
        try:
            # Exclusive creation: no overwrite. Interrupted writes fail on read.
            with path.open('xb') as stream:
                stream.write(data)
        except FileExistsError:
            if path.read_bytes() != data:
                raise ConfigError('corrupt existing cache object')
        return key

    def get(self, key, *, retrieved_at):
        if type(key) is not str or not re.fullmatch('[0-9a-f]{64}', key):
            raise ConfigError('invalid cache key')
        if type(retrieved_at) is not datetime or retrieved_at.utcoffset() is None:
            raise ConfigError('aware retrieval timestamp required')
        try:
            data = (self.directory / (key + '.json')).read_bytes()
        except FileNotFoundError as e:
            raise ConfigError('cache miss; no stale/network substitution') from e
        try:
            snapshot = from_dict(Snapshot, parse_json(data.decode('utf-8')))
            if digest(snapshot) != key or encoded(snapshot) != data:
                raise ConfigError('cache hash/content mismatch')
        except (ValueError, TypeError, UnicodeError) as e:
            raise ConfigError('corrupt cache: ' + str(e)) from e
        return CacheRead(snapshot, retrieved_at)
