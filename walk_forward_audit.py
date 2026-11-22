"""Isolated append-only Prompt 10 trial receipts. Each fact is atomically installed once."""
import json
import os
from pathlib import Path
import tempfile

from config import ConfigError
from data_records import digest, encoded
from research_journal import ResearchJournal


class TrialAudit:
    """Exclusive research directory. Readers can reopen and verify all receipts."""
    marker = b'SYNTHETIC WALK FORWARD 1\n'

    @classmethod
    def create(cls, directory):
        path = ResearchJournal._path(directory)
        path.mkdir()
        (path / 'walk-forward.marker').write_bytes(cls.marker)
        return cls(path)

    def __init__(self, directory):
        self.path = ResearchJournal._path(directory)
        marker = self.path / 'walk-forward.marker'
        if marker.is_symlink() or marker.read_bytes() != self.marker:
            raise ConfigError('foreign study store')
        self.receipts()

    @staticmethod
    def _read(path):
        if path.is_symlink() or not path.is_file():
            raise ConfigError('invalid receipt file')
        fact = json.loads(path.read_bytes())
        if (path.stem != digest(fact['key']) or
                fact['sha256'] != digest((fact['key'], fact['value']))):
            raise ConfigError('corrupted trial receipt')
        return fact

    def receipts(self):
        return tuple(self._read(p) for p in sorted(self.path.glob('*.json')))

    def _append(self, key, value):
        payload = encoded(dict(key=key, value=value, sha256=digest((key, value))))
        destination = self.path / (digest(key) + '.json')
        with tempfile.NamedTemporaryFile(dir=self.path) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
            try:
                os.link(stream.name, destination)
            except FileExistsError:
                self._read(destination)
                if destination.read_bytes() != payload:
                    raise ConfigError('conflicting trial receipt; original retained')
            else:
                fd = os.open(self.path, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
