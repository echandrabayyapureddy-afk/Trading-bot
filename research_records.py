"""Immutable synthetic evidence contracts, never research/live authorization."""
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
import re
from config import Validated, Candidate, BotConfig, ResearchManifest, ConfigError, _sha, content_hash
from data_records import Snapshot, digest, IST
from execution_engine import require
from suitability import Report
from execution_records import Account, Audit

VERSION='RESEARCH-1'

@dataclass(frozen=True, slots=True)
class RunSpec(Validated):
    fixture_id: str
    origin: Literal['SYNTHETIC','REAL']
    purpose: Literal['ENGINEERING','HISTORICAL','HOLDOUT']
    candidate: Candidate
    start: date
    end: date
    fixture_start: date
    fixture_end: date
    decision_at: datetime
    evaluation_at: datetime
    source_commit: str
    dirty_source_sha256: str
    config_sha256: str
    manifest_sha256: str
    input_sha256: str
    required_evidence: tuple[str, ...]
    schema_version: Literal['RESEARCH-1'] = VERSION
    def validate(self):
        if not re.fullmatch('[0-9a-f]{40}',self.source_commit): raise ConfigError('full source commit required')
        for n in ('dirty_source_sha256','config_sha256','manifest_sha256','input_sha256'): _sha(getattr(self,n),n)
        if len(set(self.required_evidence))!=len(self.required_evidence): raise ConfigError('duplicate required evidence')
    def validate_engineering_scope(self):
        require(self.origin=='SYNTHETIC' and self.purpose=='ENGINEERING','real/historical/holdout requests blocked')
        require(self.manifest_sha256==content_hash(ResearchManifest()),'only unsealed engineering template allowed; historical authorization unavailable')
        require(self.fixture_id.startswith('SYNTHETIC:'),'explicit synthetic fixture identity required')
        require(self.fixture_start<=self.start<self.end<=self.fixture_end,'requested interval outside fixture')
        require(self.decision_at<=self.evaluation_at,'evaluation before decision')
        require(self.start<=self.decision_at.astimezone(IST).date()<self.end,'decision outside requested interval')

    @property
    def run_id(self): return digest(self)

@dataclass(frozen=True, slots=True)
class EvidenceItem(Validated):
    evidence_id: str
    kind: Literal['FEATURE','OUTCOME']
    observed_at: datetime
    available_at: datetime
    recorded_at: datetime
    source_ref: str
    payload_sha256: str
    state: Literal['CONFIRMED','UNRESOLVED','MISSING']
    period_start: date | None = None
    period_end: date | None = None
    timeframe: Literal['DAILY','WEEKLY','MONTHLY'] = 'DAILY'
    origin: Literal['SYNTHETIC'] = 'SYNTHETIC'
    def validate(self):
        _sha(self.payload_sha256,'evidence payload')
        if not self.observed_at<=self.available_at<=self.recorded_at: raise ConfigError('evidence causal times')
        if (self.period_start is None)!=(self.period_end is None): raise ConfigError('both period endpoints required')

@dataclass(frozen=True, slots=True)
class InputBundle(Validated):
    fixture_id: str
    config: BotConfig
    manifest: ResearchManifest
    snapshot: Snapshot
    suitability: Report
    execution: Account
    evidence: tuple[EvidenceItem, ...]
    fee_profile: str | None
    execution_profile: str | None
    universe_version: str | None
    outcomes: tuple[Audit, ...] = ()
    origin: Literal['SYNTHETIC'] = 'SYNTHETIC'

@dataclass(frozen=True, slots=True)
class Stage(Validated):
    name: str
    status: Literal['PASS','BLOCKED','DEFERRED','NOT_IMPLEMENTED']
    reasons: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class ResearchReport(Validated):
    run_id: str
    spec: RunSpec
    status: Literal['PASS','INCOMPLETE']
    stages: tuple[Stage, ...]
    evidence: tuple[EvidenceItem, ...]
    input_sha256: str
    snapshot_sha256: str
    calendar_version: str
    provider_versions: tuple[str, ...]
    universe_version: str | None
    fee_profile: str | None
    execution_profile: str | None
    suitability_sha256: str
    execution_sha256: str
    limitations: tuple[str, ...]
    schema_version: Literal['RESEARCH-1'] = VERSION
    label: Literal['SYNTHETIC / NON-OPERATIONAL'] = 'SYNTHETIC / NON-OPERATIONAL'
    operational_authorized: Literal[False] = False

    def validate(self):
        self.spec.validate_engineering_scope()
        for name in ('run_id', 'input_sha256', 'snapshot_sha256', 'suitability_sha256', 'execution_sha256'):
            _sha(getattr(self, name), name)
        require(self.run_id == self.spec.run_id, 'report run identity mismatch')
        require(self.input_sha256 == self.spec.input_sha256, 'report input hash mismatch')

        layout = (
            ('validate_inputs', 'PASS'),
            ('assemble_evidence', 'PASS'),
            ('validate_consistency', 'PASS' if self.status == 'PASS' else 'BLOCKED'),
            ('render_report', 'PASS'),
            ('persist_result', 'PASS'),
            ('performance_analysis', 'NOT_IMPLEMENTED'),
            ('legacy_analyses', 'DEFERRED'),
        )
        require(tuple((s.name, s.status) for s in self.stages) == layout,
                'report stages inconsistent with fixed pipeline or terminal status')
        for stage in self.stages:
            require(bool(stage.reasons) == (stage.status != 'PASS'), 'inconsistent stage reasons')

        ids = tuple(e.evidence_id for e in self.evidence)
        require(ids == tuple(sorted(set(ids))), 'duplicate or unordered report evidence')
        sources = {}
        for item in self.evidence:
            cutoff = self.spec.decision_at if item.kind == 'FEATURE' else self.spec.evaluation_at
            require(item.recorded_at <= cutoff, 'evidence outside report cutoff')
            if (item.kind, item.timeframe, item.source_ref) == ('FEATURE', 'DAILY', 'suitability'):
                require(item.payload_sha256 == self.suitability_sha256,
                        'daily suitability evidence hash differs from report suitability hash')
            if item.kind == 'OUTCOME':
                fact = (item.payload_sha256, item.observed_at, item.state)
                require(sources.setdefault(item.source_ref, fact) == fact,
                        'contradictory reported outcome source')
        if self.status == 'PASS':
            require(set(self.spec.required_evidence) <= set(ids), 'required evidence missing')
            require(all(item.state == 'CONFIRMED' for item in self.evidence),
                    'unresolved report evidence')
            require(self.fee_profile is not None and self.execution_profile is not None,
                    'required profile missing')


@dataclass(frozen=True, slots=True)
class AttemptEvent(Validated):
    event_id: str
    attempt_id: str
    run_id: str
    spec_json: str
    recorded_at: datetime
    state: Literal['STARTED','PASS','BLOCKED','FAILED','INCOMPLETE']
    reasons: tuple[str, ...]
    output_json: str | None = None
    output_sha256: str | None = None
    schema_version: Literal['RESEARCH-1'] = VERSION
    def validate(self):
        _sha(self.run_id,'run ID')
        if self.output_sha256 is not None: _sha(self.output_sha256,'output hash')
