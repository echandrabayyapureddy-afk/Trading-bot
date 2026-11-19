# Prompt 9 — isolated synthetic evidence infrastructure (approved Prompt 9 release)

Baseline: primary `85c5df8f0f975bbf888357cd2663c4dc5b60880e`, secondary
`3bca79977d7448cef138df68a5e19d2a784eca7a`, identical tree
`989e8b1e2aa6e8c15fbf4e5a9c1a6a8a8e8412e7`. Both heads verified through GitHub.
The old prompt2-corrections directory was actually at Prompt 6 with uncommitted
Prompt 7 files. It was preserved. Work is in the separate `prompt9-research` checkout,
branch `prompt9-research`, based on the verified primary release. Primary CLI fetch
was unavailable (authentication); the public secondary supplied identical tree objects,
and exact primary commit objects were obtained through the authenticated connector,
reconstructed and SHA-verified. Existing primary history was fetched read-only from
the old checkout. No source files were copied from its uncommitted candidate.

Prompt 8 is approved/published; old local-status prose and P7/P8 review manifests are
historical. Their source/test hashes remain untouched; their historical documentation
hashes intentionally predate release documentation. The user approved Prompt 9 closure and publication on both main branches.
P9_REVIEW_MANIFEST.json records the reviewed bytes before closure documentation edits.

## Ownership and fixed flow

RunSpec + explicit immutable fixture bundle → preflight → validate input bindings →
assemble visible evidence → validate consistency → render canonical JSON → atomically
persist terminal status/report in the dedicated research journal. STARTED is committed
before the fixture supplier is invoked. Interruptions leave INCOMPLETE, never PASS.
No configurable stage registry, source paths, pickle, dynamic imports, eval/exec/runpy,
network, CSV discovery, performance runner, indicator or fee calculations are added.

Prompt 6 exclusively owns execution/exit facts. Prompt 7 owns fees/accounting/risk.
Prompt 8 owns suitability/review. This layer consumes their genuine immutable records;
it never writes their stores, emits approvals, manufactures fills or promotes config.
The fixture supplier is a caller-provided, zero-argument in-memory constructor. It is
invoked only after synthetic/purpose/manifest/interval checks. It is NOT a sandbox for
untrusted Python. Deployment must prevent arbitrary loaders from gaining data/network
or production write access; frozen objects and hashes do not provide process isolation.

## Contracts and interfaces

- research_records.py: RunSpec, InputBundle, EvidenceItem, Stage, ResearchReport,
  AttemptEvent. All are immutable typed records using the existing strict validator.
- research_pipeline.py: preflight, validate_inputs, assemble, execute.
- research_journal.py: ResearchJournal.create, append, events, attempt, close.

RunSpec declares fixture ID, origin/purpose, A/B candidate, [start,end), fixture
coverage, decision and evaluation cutoffs, full source commit, dirty-source fingerprint,
config/manifest/input hashes, required evidence IDs and RESEARCH-1 software/schema.
The run ID hashes the entire spec. Attempts have independent explicit caller IDs and
wall-clock recorded_at; these diagnostics are excluded from deterministic report bytes.
Supply the actual source fingerprint (canonical, explicitly ordered path + SHA-256 pairs), not a
claim that the baseline alone identifies dirty code. Hashes bind content, not authorship.

Preflight permits only SYNTHETIC ENGINEERING with a SYNTHETIC: fixture ID, coherent
intervals/cutoffs and the exact hash of the empty ResearchManifest() template. REAL,
HISTORICAL and HOLDOUT purposes reject before supplier access or outcome-report creation.
An UNSEALED manifest never authorizes historical evaluation. No historical authorization
entry point exists here; later actual research must use existing authorization contracts
with actual authorization_at and current approval/revocation evidence. The real manifest
is never loaded or modified by this pipeline, and no real holdout boundaries are inferred.

Loaded bundles must match the predeclared digest, fixture/calendar coverage, config,
manifest and candidate. They include actual Snapshot, suitability Report and execution
Account records, separate optional later outcome Audit records, explicit evidence,
fee/execution profile identifiers and optional universe version. Missing required
profiles/evidence give INCOMPLETE, not a successful empty analysis. Profile IDs identify
supplied synthetic evidence; this layer does not authenticate or approve real profiles.
Universe absence is reported as unsuitable for unbiased historical validation.

Daily predictive links must hash an exact supplied suitability report, proposal,
StrategyResult or RegimeResult. Ranked rows reuse Prompt 6's _signal validation of the
source vintage; no alternate signal calculation exists. Rejected diagnostic rows are
not converted into eligible trades. Weekly/monthly evidence must link the exact Prompt 3
completed_candle at the decision cutoff, with correct boundaries and occurrence/availability.
Missing scheduled bars and incomplete periods fail through that existing interface.
Future predictive receipts reject; no future data is silently treated as earlier-visible.

Outcome evidence links a genuine execution Audit by command ID and content hash,
retains occurrence, availability and recording times and is visible only by evaluation_at.
An APPLIED audit is a confirmed event, not necessarily a filled/completed trade; no trade
count, return or performance statistic is derived. Non-APPLIED audits stay UNRESOLVED.
Unresolved visible evidence makes the report INCOMPLETE. Duplicate/conflicting outcome IDs are checked only once their receipts are visible.
Future outcomes are omitted
until their receipt cutoff and never enter a predictive calculation. Each new input
bundle has its own identity; appending future data may change lineage/run hashes, but
must not change earlier visible evidence or upstream decision content.

Reports retain spec, exact input/snapshot/report/account hashes, calendar/provider/universe
versions, profile IDs, ordered evidence/source references, stage outcomes and limitations.
Evidence sorts by ID; canonical JSON normalizes timestamps/Decimals through data_records.
A/B runs remain separate. PASS means complete requested synthetic evidence assembly only.
Performance analysis is explicitly NOT_IMPLEMENTED; legacy analyses DEFERRED. They are
not zero-result successes or claims of profitability. No learned score, winning-candidate
selection, optimization, threshold sweep, feature mining or calibration is implemented.

## Durable attempts and output isolation

Create a NEW explicit research-* directory outside the source checkout, with no suffix,
symlinks or preexisting path. Creation is exclusive. Reopen only that application's
marker and database with matching SQLite application_id; reject symlinks/hardlinked DBs
and foreign stores. There is no arbitrary report-export destination API: report JSON is
inside the research journal and returned read-only in attempt records. Production account,
review/config/manifest paths cannot be passed as output destinations through these APIs.

The SQLite append transaction uses FULL synchronous mode and a hash chain. Exact repeated
events are no-ops; conflicting IDs are retained and make reconstruction BLOCKED. Start,
terminal order, monotonic receipt timestamps, run/spec hashes and report hashes/status are
validated on reconstruction. A repeated execute with the same attempt/start returns its
existing state without running again. Retry with a new attempt ID; never overwrite failed
attempts. A different spec or start receipt under the same ID is a retained conflict.
Malformed primitive objects fail before ingestion; a durable arbitrary raw-message archive
is not implemented. parseable blocked/failed/incomplete runs are retained.

An interrupted run remains INCOMPLETE. A failed atomic append rolls back that entire batch;
a separately committed STARTED survives. Result rendering precedes terminal persistence,
but a result is returned only after the terminal transaction succeeds. Restart checks all
stored hashes. This detects accidental corruption, not malicious rewriting of the entire
chain. Filesystem ACLs, actor authentication, multi-process adversarial races, production
backup/recovery/load certification and a process sandbox remain deployment responsibilities.
Imports do not open stores, construct fixtures, run experiments or change config/global state.

## Offline synthetic example

No dependencies beyond the Python standard library. From the checkout run:

```
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests python -m unittest test_research_pipeline.ResearchTests.test_complete_genuine_integration -v
```

This constructs genuine upstream Prompt 5/6/7/8 fixture-derived records, runs the fixed
pipeline in a temporary research store and verifies the complete canonical report.
The full suite includes Candidate B, delayed/unresolved outcomes and restart examples.
Use ResearchTests fixture construction as a reproducible engineering example, not an
actual market dataset. The journal carries the complete input spec and final report;
callers retain the immutable input bundle separately under its bound hash.

## Corrections following independent review

The evaluation cutoff includes receipts recorded exactly at that instant. The pipeline
groups visible outcome audits by the simulator command ID before matching evidence
digests. Identical audit receipts contribute one source fact. Distinct visible audits
sharing an ID fail input validation regardless of tuple order or evidence selection.
The attempt retains its failure diagnostic and input hash. The caller retains the
original bundle, including both the applied fill and the rejected conflicting receipt.
The existing uniqueness rule for evidence item IDs is separate from audit redelivery.

ResearchReport construction and decoding on journal replay both enforce the RESEARCH-1
stage sequence, statuses and reasons, run/spec/input bindings, digest formats and
visibility of unique, ordered evidence. PASS requires confirmed evidence and the two
required profile identifiers. INCOMPLETE carries a blocked consistency stage. Optional
analyses keep their declared deferred statuses. The terminal receipt must cover the
evaluation cutoff and its reasons must agree with the report. Replay retains original
terminal bytes and reports BLOCKED with diagnostics if those checks fail, including
for older inconsistent receipts whose byte-level checksum is correct. Source bundle
verification occurs during pipeline execution. Journal replay checks internal
consistency and integrity independently of source authentication.

### Fill event identity and daily suitability evidence

Outcome validation checks both command ID and the underlying simulator event ID
across all audits received by the evaluation cutoff. Redelivery of the same audit
is idempotent. For an event carried under a different command ID, the remaining
command fields and the audit result must agree. A contradiction fails validation
from the conflicting receipt timestamp onward, independent of input tuple order.
The input bundle retains both original receipts.

A daily FEATURE referencing the whole suitability report must carry the same
payload hash as the report's suitability_sha256. ResearchReport checks this when
constructed, including when decoded during journal replay. A terminal receipt
with contradictory hashes is retained unchanged for diagnosis and reconstructs
as BLOCKED even when its outer checksum is correct.

## Legacy static disposition

No explicit selective implementation-reuse approval was established. All eight listed
files were read as text/AST only, never imported/executed. Concepts are reimplemented
cleanly; no code was adapted. The paths below are in the uploaded project source directory
`/workspace/scratch/36d4b58ef0cb/project_sources/`. All are available; approval evidence
for implementation reuse is NONE. Actual SHA-256 values identify the inspected versions.

| Path | SHA-256 | Useful concept | Unsafe coupling / scope | Decision |
|---|---|---|---|---|
| `13-research_pipeline-Copy.py` | `defe92116c776addca1a8be098cc0519c86466dded5b39039b13e35aac77b542` | stage/evidence records | mutable registry, dynamic engine discovery, shared backtest cache and exports | REFERENCE ONLY |
| `24-feature_robustness_engine.py` | `b15b1fa13ef0185f5a1858207dbc4d1afb5fab55196982c6431916f253643f79` | explicit diagnostic limitations | runpy strategy execution, global context cache, warning suppression, stdout/export effects | DEFER |
| `12-pattern_discovery_engine-Copy.py` | `90a97d69c78d655d6baf37f325b99f4cb73c7a94a0b331d2733e1fe743e19231` | traceable evidence IDs | import-time registry mutation; feature mining and threshold searches outside scope | DEFER |
| `19-evidence_synthesis_engine.py` | `2f85aee7ff20d544676b82eefa6b5c08315d9ec69e0abd7c1623c7c47f81c557` | source-linked evidence summaries | glob/CSV discovery and legacy pattern/research_core dependencies | REFERENCE ONLY |
| `18-score_calibration_engine.py` | `32494fa0f619c60874e44623c17e2d7e5045c2fd1515783d9accaca21b9138e9` | versioned diagnostic artifacts | legacy synthesis dependency, score calibration, JSON discovery/persistence | DEFER |
| `17-configuration_validation_engine.py` | `0de0068f160218e9d3733a9d82873695ce597c7f89a6a15dd7dd44baf9b49fc8` | version/hash checks | runpy configuration injection, legacy evaluator coupling and active config persistence | REFERENCE ONLY |
| `23-trade_suitability_report.py` | `3af387c622870eb1c801367a25dc86b8457d3c779c3d2b484277738942cfc411` | explicit rejection reporting | mutable dataframe cache and legacy numpy/pandas reporting conventions | REFERENCE ONLY |
| `03-master_pipeline.py` | `0f0c2921ad682c4d12635cf1f21c8680ec617bd2e926aa8ca7558e256f79323c` | explicit orchestration ownership | composes legacy calibration/mining/execution contexts and cached namespaces | REFERENCE ONLY |

Legacy dependencies include numpy, pandas, matplotlib and research_core. No research_core source was found among the supplied project files; copied filenames also do not establish a valid import package. Dependencies were not installed or fabricated. No approval for bounded ADAPT was identified.
