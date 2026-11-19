"""Fixed synthetic evidence pipeline; no backtest, optimization or execution stages."""
from dataclasses import replace
from config import ConfigError, SealStatus, ResearchManifest, content_hash
from data_records import digest, encoded, IST
from data_fetcher import completed_candle, period_bounds
from execution_engine import require, _signal
from suitability import command
from research_records import RunSpec, InputBundle, Stage, ResearchReport, AttemptEvent
from research_journal import ResearchJournal

LIMITATIONS=('Synthetic evidence is not authenticated provenance or profitability evidence.',
 'Real historical research and holdout evaluation are unsupported.',
 'No review/account journal writes or execution submission bridge.',
 'Ranking alternatives are not an additive basket.',
 'Pattern mining, optimization, calibration and statistical performance metrics are NOT_IMPLEMENTED.')


def preflight(spec):
    require(type(spec) is RunSpec,'typed run specification required')
    spec.validate_engineering_scope()


def validate_inputs(spec,bundle):
    require(type(bundle) is InputBundle,'typed immutable input bundle required')
    require(bundle.fixture_id==spec.fixture_id,'fixture identity mismatch')
    require(digest(bundle)==spec.input_sha256,'input hash mismatch')
    require(content_hash(bundle.config)==spec.config_sha256,'config hash mismatch')
    require(content_hash(bundle.manifest)==spec.manifest_sha256,'manifest hash mismatch')
    # Engineering fixtures are not authorized historical datasets. No sealing bypass.
    require(bundle.manifest==ResearchManifest(),'only empty UNSEALED engineering manifest supported')
    require(bundle.config.strategy.candidate==spec.candidate,'candidate mismatch')
    require((spec.fixture_start,spec.fixture_end)==(bundle.snapshot.calendar.start,bundle.snapshot.calendar.end),'fixture/calendar bounds mismatch')
    require(bundle.snapshot.origin=='SYNTHETIC','non-synthetic snapshot')
    require(bundle.suitability.at==spec.decision_at,'suitability cutoff mismatch')
    require(not bundle.suitability.operational_authorized and not bundle.execution.operational_authorized,'operational evidence prohibited')
    rows=bundle.suitability.ranked+bundle.suitability.other
    for row in rows:
        require(row.at==spec.decision_at and row.request.signal.candidate==spec.candidate,'row candidate/cutoff mismatch')
        require(row.request.signal.config_sha256==spec.config_sha256,'row config mismatch')
        require(row.proposal_id==digest(replace(row,proposal_id='UNBOUND')),'proposal content mismatch')
        require(row.request.signal.available_at<=spec.decision_at and row.request.regime.available_at<=spec.decision_at,'future predictive record')
        require(row.account_sha256==digest(bundle.execution),'account/report mismatch')
    for row in bundle.suitability.ranked:
        _signal(bundle.snapshot,bundle.config,command(row.request,bundle.config,spec.decision_at,1),spec.decision_at)
    require(all(a.command.recorded_at<=spec.decision_at for a in bundle.execution.audit),'future account audit')
    require(all(e.recorded_at<=spec.decision_at for e in bundle.execution.events),'future account event')
    visible_ids=[e.evidence_id for e in bundle.evidence if e.kind=='FEATURE' or e.recorded_at<=spec.evaluation_at]
    require(len(set(visible_ids))==len(visible_ids),'duplicate/conflicting visible evidence ID')
    # A receipt becomes visible at its recording time, including at the cutoff.
    # A repeated identical audit represents one fact. Keep the original tuple intact.
    outcomes = {}
    event_sources = {}
    for audit in bundle.outcomes:
        if audit.command.recorded_at > spec.evaluation_at:
            continue
        identity = audit.command.command_id
        if identity in outcomes and outcomes[identity] != audit:
            raise ConfigError(f'conflicting visible outcome receipts for {identity}')
        if audit.command.event is not None:
            event_id = audit.command.event.event_id
            previous = event_sources.setdefault(event_id, audit)
            # Prompt 6 permits the same fact to be delivered under a new command ID.
            if previous != audit and replace(previous, command=replace(
                    previous.command, command_id=identity)) != audit:
                raise ConfigError(f'conflicting visible event receipts for {event_id}')
        outcomes[identity] = audit

    for e in bundle.evidence:
        if e.kind=='OUTCOME' and e.recorded_at>spec.evaluation_at: continue
        if e.kind=='OUTCOME':
            audit = outcomes.get(e.source_ref)
            require(audit is not None and digest(audit) == e.payload_sha256,
                    'outcome source/hash mismatch')
            observed=audit.command.event.occurred_at if audit.command.event else (audit.command.point.at if audit.command.point else audit.command.recorded_at)
            require(e.observed_at==observed,'outcome occurrence mismatch')
            require(e.available_at>=audit.command.recorded_at,'outcome predates execution evidence')
            require(e.state==('CONFIRMED' if audit.outcome=='APPLIED' else 'UNRESOLVED'),'outcome resolution mismatch')
        if e.kind=='FEATURE':
            require(e.recorded_at<=spec.decision_at,'future feature receipt')
            if e.timeframe=='DAILY':
                sources={'suitability':(bundle.suitability,bundle.suitability.at)}
                for row in rows:
                    sources[row.proposal_id]=(row,row.at)
                    sources[row.request.signal.instrument_id+':signal']=(row.request.signal,row.request.signal.available_at)
                    sources[row.request.signal.instrument_id+':regime']=(row.request.regime,row.request.regime.available_at)
                require(e.source_ref in sources,'unknown predictive source')
                source,available=sources[e.source_ref]
                require(e.observed_at==(source.as_of if hasattr(source,'as_of') else source.at),'predictive observation mismatch')
                require(digest(source)==e.payload_sha256 and e.available_at>=available,'predictive source/hash/timing mismatch')
            if e.timeframe!='DAILY':
                require(e.period_start is not None and e.period_end is not None,'period boundaries missing')
                require(period_bounds(e.period_start,e.timeframe)==(e.period_start,e.period_end),'inconsistent period boundaries')
                # Source ref is the explicit stable instrument ID, never a discovered file path.
                candle=completed_candle(bundle.snapshot,e.source_ref,e.period_start,e.timeframe,spec.decision_at)
                require(e.observed_at==candle.final_session_close and e.available_at>=candle.available_at,'period evidence timing mismatch')
                require(digest(candle)==e.payload_sha256,'candle vintage/hash mismatch')
    return bundle


def assemble(spec,bundle):
    preflight(spec)
    validate_inputs(spec, bundle)
    # Outcomes available later are diagnostics only, never injected into any upstream calculation.
    visible=tuple(sorted((e for e in bundle.evidence if e.recorded_at<=
                        (spec.decision_at if e.kind=='FEATURE' else spec.evaluation_at)),key=lambda e:e.evidence_id))
    missing=tuple('missing/unresolved required evidence:'+name for name in spec.required_evidence
                  if not any(e.evidence_id==name and e.state=='CONFIRMED' for e in visible))
    missing+=tuple('missing profile:'+name for name in ('fee_profile','execution_profile') if getattr(bundle,name) is None)
    if any(e.state!='CONFIRMED' for e in visible) or any(a.outcome!='APPLIED' for a in bundle.execution.audit) or bundle.execution.entry_blocks:
        missing+=('execution has rejected/unresolved facts; no completed-trade inference',)
    stages=(Stage('validate_inputs','PASS',()),Stage('assemble_evidence','PASS',()),
            Stage('validate_consistency','BLOCKED' if missing else 'PASS',missing),
            Stage('render_report','PASS',()),Stage('persist_result','PASS',()),Stage('performance_analysis','NOT_IMPLEMENTED',('outside authorized scope',)),
            Stage('legacy_analyses','DEFERRED',('requires separate authorization',)))
    return ResearchReport(spec.run_id,spec,'INCOMPLETE' if missing else 'PASS',stages,visible,spec.input_sha256,
        digest(bundle.snapshot),bundle.snapshot.calendar.version,tuple(sorted({b.provider+'@'+b.provider_version for b in bundle.snapshot.bars if b.available_at<=spec.decision_at})),bundle.universe_version,bundle.fee_profile,
        bundle.execution_profile,digest(bundle.suitability),digest(bundle.execution),LIMITATIONS+
        (() if bundle.universe_version else ('Historical universe unavailable; not unbiased historical validation.',)))


def execute(spec,journal,attempt_id,recorded_at,load_fixture):
    """Caller-controlled in-memory fixture supplier runs only after preflight.
    No paths, plugins, dynamic imports or historical data loaders are accepted.
    Exceptions from fixture construction are durable FAILED attempts, not successes.
    """
    require(type(journal) is ResearchJournal,'dedicated research journal required')
    prior=journal.attempt(attempt_id)
    start=AttemptEvent(attempt_id+':start',attempt_id,spec.run_id,encoded(spec).decode(),recorded_at,'STARTED',())
    if prior is not None:
        if prior.events[0]!=start: journal.append(start)
        return journal.attempt(attempt_id)  # no implicit rerun; retry needs a new attempt ID
    journal.append(start)
    try:
        preflight(spec)
        require(recorded_at>=spec.evaluation_at,'attempt receipt before evaluation')
    except ConfigError as error:
        journal.append(replace(start,event_id=attempt_id+':end',state='BLOCKED',reasons=(str(error),)))
        return journal.attempt(attempt_id)
    try:
        report=assemble(spec,load_fixture())
        payload=encoded(report).decode()
        journal.append(replace(start,event_id=attempt_id+':end',state=report.status,
            reasons=tuple(r for s in report.stages for r in s.reasons if s.status=='BLOCKED'),
            output_json=payload,output_sha256=digest(report)))
    except Exception as error:
        journal.append(replace(start,event_id=attempt_id+':end',state='FAILED',
            reasons=(type(error).__name__+': '+str(error),)))
    return journal.attempt(attempt_id)
