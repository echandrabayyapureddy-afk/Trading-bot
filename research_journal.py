"""Research-only append journal. Explicit new directory; no arbitrary export paths."""
from pathlib import Path
from dataclasses import dataclass
import json
import sqlite3
import hashlib
from config import ConfigError, from_dict, parse_json
from data_records import encoded, digest
from research_records import AttemptEvent, RunSpec, ResearchReport

APP_ID=0x52533931
MARKER='RESEARCH-1 SYNTHETIC ONLY\n'

@dataclass(frozen=True, slots=True)
class Attempt:
    attempt_id: str
    run_id: str
    status: str
    reasons: tuple[str, ...]
    events: tuple[AttemptEvent, ...]

class ResearchJournal:
    @classmethod
    def create(cls,directory):
        p=cls._path(directory)
        p.mkdir()  # exclusive: never overwrite an existing directory/file
        (p/'research.marker').write_text(MARKER)
        db=sqlite3.connect(p/'research.sqlite')
        db.execute(f'PRAGMA application_id={APP_ID}')
        db.execute('CREATE TABLE events(seq INTEGER PRIMARY KEY,payload TEXT NOT NULL,chain TEXT NOT NULL)')
        db.commit();db.close()
        return cls(p)
    @staticmethod
    def _path(directory):
        p=Path(directory).absolute()
        if p!=p.resolve() or not p.name.startswith('research-') or p.suffix:
            raise ConfigError('explicit non-symlink research-* directory required')
        repo=Path(__file__).resolve().parent
        if p==repo or repo in p.parents: raise ConfigError('research output must be outside source repository')
        return p
    def __init__(self,directory):
        self.directory=self._path(directory)
        marker=self.directory/'research.marker'; path=self.directory/'research.sqlite'
        if marker.is_symlink() or path.is_symlink() or marker.read_text()!=MARKER or path.stat().st_nlink!=1:
            raise ConfigError('not an isolated research store')
        check=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
        try:
            if check.execute('PRAGMA application_id').fetchone()[0]!=APP_ID: raise ConfigError('foreign database')
        finally: check.close()
        self.db=sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,isolation_level=None)
        self.db.execute('PRAGMA synchronous=FULL')
        self.events()  # validate chain before use
    def close(self): self.db.close()
    def events(self):
        chain=''; events=[]
        for payload,stored in self.db.execute('SELECT payload,chain FROM events ORDER BY seq'):
            chain=digest((chain,payload))
            if chain!=stored: raise ConfigError('research journal corruption')
            events.append(from_dict(AttemptEvent,json.loads(payload)))
        return tuple(events)
    def append(self,*events):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            existing=list(self.events());row=self.db.execute('SELECT chain FROM events ORDER BY seq DESC LIMIT 1').fetchone()
            chain=row[0] if row else ''
            for event in events:
                if type(event) is not AttemptEvent: raise ConfigError('typed event required')
                if event in existing: continue
                payload=encoded(event).decode();chain=digest((chain,payload))
                self.db.execute('INSERT INTO events(payload,chain) VALUES (?,?)',(payload,chain));existing.append(event)
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK');raise
    def attempt(self,attempt_id):
        all_events=self.events();events=tuple(e for e in all_events if e.attempt_id==attempt_id)
        if not events: return None
        issues=[];state='INCOMPLETE';start=events[0];last=None
        for i,e in enumerate(events):
            try:
                spec=from_dict(RunSpec,json.loads(e.spec_json))
                if spec.run_id!=e.run_id or e.run_id!=start.run_id: raise ConfigError('run/spec mismatch')
                if any(x.event_id==e.event_id and x!=e for x in all_events): raise ConfigError('conflicting event ID')
                if last is not None and e.recorded_at<last: raise ConfigError('receipt out of order')
                if i==0 and e.state!='STARTED': raise ConfigError('missing start')
                if i>0 and (i!=1 or e.state=='STARTED'): raise ConfigError('conflicting terminal event')
                if e.output_json is not None:
                    if hashlib.sha256(e.output_json.encode()).hexdigest()!=e.output_sha256: raise ConfigError('output hash mismatch')
                    report=from_dict(ResearchReport,parse_json(e.output_json))
                    if report.run_id!=e.run_id or report.spec!=spec or report.status!=e.state: raise ConfigError('output binding mismatch')
                    blocked_reasons = tuple(reason for stage in report.stages if stage.status == 'BLOCKED'
                                            for reason in stage.reasons)
                    if e.reasons != blocked_reasons or e.recorded_at < spec.evaluation_at:
                        raise ConfigError('terminal reasons or receipt inconsistent with report')
                elif e.output_sha256 is not None or e.state in ('PASS','INCOMPLETE'): raise ConfigError('missing report')
                if i==0 and (e.output_json is not None or e.reasons): raise ConfigError('invalid start')
                if i>0: state=e.state
            except (ConfigError,ValueError,TypeError) as error: issues.append(str(error))
            last=e.recorded_at
        return Attempt(attempt_id,start.run_id,'BLOCKED' if issues else state,tuple(issues),events)
