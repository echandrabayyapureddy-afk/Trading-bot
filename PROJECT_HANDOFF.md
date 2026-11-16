# Prompt 7 — approved closure and authorized release

2026-11-16: the user approved Prompt 7 closure following a separate independent
read-only GO review (66 focused / 380 complete tests). This release preserves all
six reviewed source/test hashes in REVIEW_MANIFEST.json. That manifest remains an
immutable record of the reviewed local candidate; its status is historical.

Release verification reproduced 66 focused tests (4.087s) and 380 complete tests
(60.707s), zero failures/skips and no emitted warnings. Whitespace checks passed.
Primary baseline: ffb38ef4c11987fe508113443e58747c1db6ea5e.
Secondary baseline: 941212a5e36632e52ddbb53f2b3bdccb75f08350.
Both remote heads were verified at tree 3deb71e7ed29305f443d3a44ef99046612c0b7c0.
Publication is authorized to both main branches, preserving separate parents and
using an identical release tree. Final remote commit/tree verification belongs in
the release completion report; this pre-publication record does not assert success.

Operational readiness remains blocked, real profiles remain unverified and the
research manifest remains UNSEALED. Manual approval/manual broker placement,
fixed safety limits and legacy files are unchanged. Production integration and
unsupported workflows remain bounded by ACCOUNTING_RISK_LAYER.md.
Prompt 8 requires separate authorization. Earlier status entries below are historical.

---

# Prompt 7 purchase-conservation corrections — re-review required

2026-11-16: verified baseline ffb38ef4c11987fe508113443e58747c1db6ea5e and all
six source/test hashes before editing. Preserved the existing local candidate.
Corrected MEDIUM zero-cost BUY and HIGH competing-reservation cash defects in
ledger.py only. Both checks run before any holding, cash or reservation mutation.
Original representable BUY records survive in the journal as blocking anomalies.
The prior paid-fee/refund and side-aware fee corrections are unchanged.

Tests cover both reproductions, exact/just-over boundaries, valid positive purchases,
own-versus-other reservations, duplicate/conflicting receipts and durable restart.
Read the newest TEST_RESULTS.md entry for actual results; REVIEW_MANIFEST.json
contains regenerated source/test hashes. Final verification: 66 focused and 380
total tests passed, zero failures/skips/warnings; diff check passed.
Prompt 7 is NOT closed or published.
Next: separate independent read-only re-review. No Prompt 8 authorization.

---

# Prompt 7 focused corrections — independent re-review required

Baseline verified: ffb38ef4c11987fe508113443e58747c1db6ea5e, main.
All six pre-correction REVIEW_MANIFEST.json hashes matched the local candidate.
Existing Prompt 7 work was preserved. Prompt 7 is NOT approved for closure.

Both separate-review findings reproduced before editing:
F1 (HIGH): paid estimate reduction consumed an unrelated payable, and ADJUST
could book a second benefit. F2 (MEDIUM): an opposite-side quote reversed a
previously accrued side-only scoped charge. Both are corrected locally.

ledger.py now attributes due/paid balances to individual CHARGE IDs. PAY parents
are explicit in the projector; legacy unlinked payments require unique attribution.
ACTUAL_CHARGE affects only its own charge and creates a nonspendable receivable
for excess payments. REFUND receipts consume that receivable once. Generic ADJUST
and sale SETTLE cannot bypass this workflow. Ambiguities retain facts with anomalies.

fee_model.py now exposes ScopeTotals with scope identity and separate BUY/SELL
turnovers, plus bound cumulative FeeQuote.accrued/previous state. Opposite-side
quotes preserve accruals. Unbound charged tuples and ambiguous dependent bases
are rejected. Explicit correction evidence permits tested negative revisions.
One-shot scalar estimates remain supported; they cannot seed incremental quotes.
The execution adapter still rejects unsupported cross-order fee scopes.

Read ACCOUNTING_RISK_LAYER.md for correction workflow and limitations. Exact new
source/test hashes are in regenerated REVIEW_MANIFEST.json. Final actual tests
are recorded at the top of TEST_RESULTS.md. No published source/configuration,
safety values, manual placement or operational gate changed. Manifest UNSEALED.
No commit, push, broker connection, holdout access, research or Prompt 8.
Next: separate independent read-only re-review of F1/F2 and the complete candidate.
Correction verification: 60 focused and 374 complete tests passed, zero failures/
skips/warnings; git diff --check passed. Earlier counts/status below are historical,
not closure approval.

---

# Current handoff — Prompt 7 local review candidate, 2026-11-15

Primary main baseline ffb38ef4c11987fe508113443e58747c1db6ea5e; secondary main
941212a5e36632e52ddbb53f2b3bdccb75f08350; both remotes verified at common tree
3deb71e7ed29305f443d3a44ef99046612c0b7c0 before editing. Local tree was clean.
Baseline reproduced: 314 tests passed in 86.460s, zero failures/skips/warnings.

Read ACCOUNTING_RISK_LAYER.md, then fee_model.py, ledger.py, portfolio.py,
risk_manager.py, accounting_adapter.py and tests/test_accounting_risk.py.
No new dependencies; standard-library SQLite provides atomic local journal storage.
REVIEW_MANIFEST.json records exact source/test hashes for subsequent release checks.
Final verification: 45 focused and 359 total tests passed, zero failures/skips/
warnings; git diff --check passed. Exact commands appear in TEST_RESULTS.md.

Ownership: Prompt 6 remains the only exit/fill engine; accepted audit facts project
into one accounting reducer and optional durable journal. Entry checks reconcile
that projection with the simulator before computing risk approval. No published
execution/configuration/strategy files changed. Real manifest stays UNSEALED.
No legacy imports, holdout access, performance research, commit or push.

Outstanding: real broker/rate approval, production provider/evidence authentication,
complete historical marks, deployment storage security and scalability. Prompt 6
settlement/flow/resumption injection, partial execution, order replacement and
cross-order fee-scope integration remain explicitly unsupported. Standalone journal
settlement/flows/clearance must not be presented as supported simulator resumption.
Review focus: conservation, exactly-once projection, worst-price costs, own versus
other reservations, mark vintage, NAV flows/clearance and late receipt quarantine.

Next action: separate independent read-only Prompt 7 review and user approval.
Prompt 7 is NOT closed. Prompt 8 is NOT authorized. Earlier handoffs are historical.

---

# Current handoff — Prompt 6 approved closure and release

2026-11-14: the user reports a separate planning-chat read-only review with GO,
54 focused and 314 complete tests passing, and explicitly approves Prompt 6 closure
and publication to both repositories. Both causal corrections are included.
Release preparation independently reran 54 focused and 314 complete tests with
zero failures/skips/warnings; git diff --check passed. See TEST_RESULTS.md.

Primary main was verified at f4146432e662c37028e411e33d4496e3021cd51f;
secondary main at 907c8f06bb6d3b3f1d1dce82214c26cfa1a33567. Both baseline trees
were fc3521fab33b4ed38892f024c4f12ffe1e911438. Neither remote had advanced.
The release preserves separate parent histories and publishes identical trees.
Final remote commit IDs and tree verification are recorded in the publication
completion report after branch updates; this text does not claim an unexecuted push.

Only release-status documentation changed during publication preparation. No saved
checksum from the separate review was supplied; exact identity to that review
cannot independently be attested. Current source/tests were inspected and rerun.
No unrelated implementation changes were identified. Synthetic source/test hashes:
- execution_records.py: 2cbee4bc506d4cdd176fcad34986a88428a099896c8112ebdf034792de9a7691
- execution_engine.py: a3ced383435d2f7346a383a34dd900ca95a084349f9031358fab897366bc41af
- tests/test_execution.py: b4f4882456f801c1c5f62317a7ac5c2f608c73755c4f5111b659052b0ec54ab0

Operational prerequisites remain blocked: real providers/calendar/broker evidence,
production dependency adapters, settlement, durable ledger and reconciliation.
Partial execution and in-place reconciliation/resumption remain unsupported.
Safety policy/manual placement are unchanged; the real manifest remains UNSEALED.
Prompt 7 requires separate authorization. Historical review records below are
superseded only as to closure/publication status.

---

# Historical Prompt 6 local implementation and correction handoff

2026-11-14 correction: read-only review found a protective fill accepted before
its trigger and an intent resolved before observation. Trigger occurrence/evidence
are now retained; direct sell guards and the expanded late-mutation guard quarantine
both reproductions. TRIGGER, EXIT_INTENT and unresolved BAR transitions participate.
Original facts remain in audit; no impossible account effects are applied. Equal
timestamp semantics are documented in EXECUTION_LAYER.md. Re-review is required.
Baseline and prior local work preserved; no commit/push or Prompt 7.
Correction verification: 54 focused and 314 complete-suite tests passed, zero
failures/skips and no warnings emitted; git diff --check passed. Both reproductions
are rejected without account effects. Next: independent read-only re-review of
trigger evidence, late mutation quarantine, equal-time ordering and intent resolution.
The remote verification and 48/308 counts below describe the original implementation,
not this correction's verification. See the latest TEST_RESULTS.md entry for current
local results. Remotes were not reverified during this correction.

Verified primary main/local baseline: f4146432e662c37028e411e33d4496e3021cd51f.
Verified secondary main: 907c8f06bb6d3b3f1d1dce82214c26cfa1a33567.
Both remote trees: fc3521fab33b4ed38892f024c4f12ffe1e911438. Working tree was clean.
Prompt 5 is approved, closed and published, including exact tick-floor correction.
Baseline reproduced: 260 tests passed, 0 failed/skipped in 70.614 seconds.

Prompt 6 user authorization is local implementation/tests/docs only. New files:
execution_records.py (immutable synthetic contracts/dependency protocol),
execution_engine.py (shared account, reservation, receipt replay and sole exit path),
tests/test_execution.py and EXECUTION_LAYER.md. README.md, TEST_RESULTS.md and this
handoff updated. No new dependencies; Python 3.12+ standard library.

Read EXECUTION_LAYER.md first, then records, engine, tests and Prompt 2/3/5 contracts.
Run `PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p test_execution.py -q`,
`PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -q`, and `git diff --check`.
Actual checks are recorded in TEST_RESULTS.md. All fixtures are synthetic.
Final verification: 48 focused tests and 308 complete-suite tests passed, zero
failures/skips/warnings; git diff --check passed. Both remotes remain at the above
Prompt 5 commits. Self-review corrected the intraday opening-evidence gap and its
temporary validation-wrapper regression; details and intermediate failures are logged.

Review focus: entry D+2 and missed opens; source availability; risk/cash dependency
binding; atomic multi-instrument reservations; no implicit protection; trigger/fill
separation; stop-limit nonexecution; late notifications; idempotence and competing
exits. Daily-OHLC commands deliberately remain unresolved, never account fills.
Partial execution, cancellation/replacement, settlement credits, in-place ambiguity
clearance and drawdown resumption are unsupported. Existing exits remain available.
Production risk sizing/fees/equity/drawdown/ledger belong to Prompt 7, not this engine.
Production data/calendar/broker/evidence integration and performance remain UNVERIFIED.

Fixed policies, prior source, configuration, real UNSEALED manifest and legacy files
are unchanged. No outcomes/holdout access or broker connection. No commit or push.
Next action: independent read-only Prompt 6 review, then user approval. Prompt 6 is
not closed and Prompt 7 has not begun. Historical handoffs below are superseded.

---

# Historical Prompt 5 approved closure and publication — 2026-11-12

The user reports an independent re-review GO and explicitly approves Prompt 5
closure and publication to both main branches. The exact tick-floor correction
is included. Preserve separate repository histories with identical release trees;
no force-push. Prompt 6 requires separate authorization and has not begun.
Real integration remains UNVERIFIED, operational readiness blocked and the manifest
UNSEALED. The release report records resulting remote SHAs after verification.
Earlier review-status sections below are historical and superseded by this approval.

# Prompt 5 focused correction — independent re-review required

Continued on local main 416f87ab74283302e2c27cc9f9c5ea1fa194ad89;
preserved the six existing uncommitted Prompt 5 files. Independent review issued
NO-GO for rounded tick-floor arithmetic (MEDIUM). Replaced quotient flooring and
tick-multiple reconstruction with exact integer arithmetic and Decimal constructors.
Added direct boundary/context/invariant tests and a full replay regression proving
109.(60 nines) gives ceiling 109.95, rejects 110, and preserves frozen levels.
No config, safety policy, earlier-phase source or legacy files changed. No holdout
access, commit, push or Prompt 6. Correction checks: 38 focused / 260 total passed, zero failures/skips/warnings;
git diff --check passed. Read TEST_RESULTS.md for exact commands.
Next action: independent read-only review of the correction and existing package;
prior implementation PASS is not closure approval.

---

# Current handoff — Prompt 5 local review candidate

Primary main baseline: 416f87ab74283302e2c27cc9f9c5ea1fa194ad89.
Secondary main: b61ea6de48373b6fb49788c8aaf17e875af4ca54.
Both remotely verified before implementation at identical tree
1ca1e3e3bdda1a38726f03ceba49c0a200afe689. Local main was clean.
Prompt 4 is approved, closed and published. Baseline rerun: 222 passed,
0 failed, 0 skipped in 38.675 seconds, no warnings emitted.

User authorized Prompt 5 local implementation only on 2026-11-12. Read
STRATEGY_LAYER.md, strategy.py and tests/test_strategy.py first, followed by
REGIME_LAYER.md, DATA_LAYER.md and CONTRACTS.md. No additional dependencies.
This phase implements daily EMA9/21 weekly event selection, daily retirement,
Candidate B monthly daily-EMA200 evidence, frozen proposal levels, D+2 necessary
conditions, persistent ordinary exit intents and auditable deterministic replay.
Regime evidence is checked against Prompt 4 replay; all operational gates remain
blocked. No ranking, sizing, fees, execution simulator or broker integration.
Known effective actions block raw strategy histories; adjusted views unsupported.
Real data, calendar, ticks, universe and benchmark authenticity remain UNVERIFIED.
Research manifest remains UNSEALED. No performance research or holdout access.

Run the focused and full unittest commands in STRATEGY_LAYER.md; actual final
results are in TEST_RESULTS.md: 36 focused / 258 full passed, zero failed/skipped,
no warnings; git diff --check passed. Independent reviewer should challenge selection
identity/lifecycle, late missing-data recovery and revisions, monthly cutoff basis,
exit resolution, frozen levels and supplied regime evidence authenticity boundaries.
All changes remain local, uncommitted and unpushed. Next authorized action is
independent read-only Prompt 5 review. Prompt 6 requires separate user approval.
Historical sections below describe earlier phases and do not override this status.

---

# Historical Prompt 4 closure/publication handoff

# Current handoff — Prompt 4 approved closure

Primary main/local baseline: f53204c75dc2b6f1274eb9196a28d4f9211f95f2.
Secondary main: 8ec7a0d785a11263b88818423ac1af4488f5ca6a.
Both verified at tree e60912f5cefd8b3e2d6ebb57e86661960d14e40a before editing.
No repository had advanced; the primary checkout was clean. Existing 177 tests
passed before implementation. No archive or legacy implementation was used.

Read REGIME_LAYER.md, regime_detector.py and tests/test_regime_detector.py first,
then TEST_RESULTS.md. Python 3.12+ standard library, no installation required.
Run `PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -q` and
`git diff --check` from the repository root.

Completed locally: required daily regime indicators, raw synthetic index binding,
causal vintage replay, explicit warmup/zero handling, independent immediate veto,
two-session confirmation and immutable results with initialization/evidence hashes.
Real index identity/provider/calendar integration remains UNVERIFIED. Research
manifest remains UNSEALED; live readiness remains blocked. Prompt 2/3 code and
configurations are unchanged. No indicators for trade signals or strategy evaluation.

Reviewer focus: indicator indexing and seeds; non-overlapping returns; prior-only
ATR reference; inclusive spike convention; unknown/reset behavior; same-session
retries; revised-history rejection; confirmation chain and configuration isolation.
All semantics and remaining limitations are documented in REGIME_LAYER.md.

Independent Prompt 4 review reproduced 220 passing tests but found two HIGH defects.
The local corrections use exact rational close ratios to recognize geometric
prices as zero volatility and pairwise return differences to preserve genuine
small variance. UNKNOWN or incompatible-history revision now clears current
confirmation; diagnostic_previous separately records the prior label. Eligibility
requires two fresh consecutive valid completed sessions after recovery.
Two new end-to-end regressions cover both defects and ordinary UNKNOWN recovery.
Corrected full verification: 222 tests passed, 0 failed / 0 skipped; see
TEST_RESULTS.md for actual commands and timings. A subsequent independent read-only review ran 45 focused and 222 complete tests,
0 failed / 0 skipped, verified the two corrections with independent probes, and
recommended GO. The user approved Prompt 4 closure on 2026-11-11. Real integration
and production throughput remain unverified.

The user authorized publication of the approved Prompt 4 package to both main
branches on 2026-11-11. Publication preserves each repository’s existing history
and identical release trees; no force-push is permitted. The release report records
the resulting commit SHAs after remote verification. Prompt 5 has not begun and
requires separate authorization. Operational prerequisites above remain blocked.

---

# Historical Prompt 3 release handoff

# Current handoff — Prompt 3 approved release

Primary repository: chinmaymr37/Trading-bot, branch main.
Implementation baseline commit: 8af831aa8e0da840671fa9e1dbb9975953a1cec7.
The primary remote main was verified at this commit before implementation.
Prompt 3 closure and publication to both repositories are explicitly approved.
Publication baseline: primary 8af831aa8e0da840671fa9e1dbb9975953a1cec7;
secondary 6961d9a985e53ce69f5200a52b780a8174c7ffb8. Their trees matched.
Publish identical file trees while preserving each repository history. Commit IDs
may differ; primary remains authoritative. Consult remote refs for release SHAs.

Read DATA_LAYER.md, SYNTHETIC_DATA_REPORT.json and TEST_RESULTS.md first, then
data_records.py, data_validator.py, data_fetcher.py, data_cache.py and
tests/test_data_layer.py. No dependency installation: Python 3.12+ standard library.

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p test_data_layer.py -q
git diff --check
```

Completed: immutable revision-aware synthetic daily data, explicit calendar vintages,
validation/rejection reporting, completed raw weekly/monthly aggregation, split-only
nontradable views, dated identity/universe records, content-addressed cache and
snapshot metadata. All 108 Prompt 2 tests and 69 data-layer tests pass (177 total).
No performance research, strategy algorithms, holdout reads or operational ingestion.
Real manifest remains UNSEALED. Prompt 2 code/configuration/safety policies unchanged.

Outstanding: approved real provider and sourced NSE calendar; verified point-in-time
action-feed completeness and historical universe; production evidence/authentication;
cache durability/access controls and isolation; current approval/revocation feeds.
Synthetic metadata is never evidence of unbiased historical validation.

Independent reviewer should challenge period completeness, as-of revision selection,
calendar vintage selection, unknown/late action evidence, identity availability,
canonical cache hashing and the explicit research authorization cutoff. Review the
limitations in DATA_LAYER.md before authorizing any actual data integration.

Focused review follow-up: both confirmed findings corrected locally. Date-only
split effectivity is explicitly midnight Asia/Kolkata, inclusive; AdjustedView v2
records the decision/effectivity basis and has a cutoff reuse guard. Daily queries
reject incompatible selected series while retaining diagnostic records.
Read tests/test_prompt3_corrections.py (11 passing regressions) and the focused
correction section in DATA_LAYER.md. Synthetic fixture/report hash is unchanged.

The user explicitly approved Prompt 3 closure after independent review reporting
177 passing tests and additional split-boundary and mixed-series probes. A local
verification on 2026-11-10 again ran 177 tests successfully; `git diff --check`
passed. This approval supersedes the earlier review-candidate status above.

Publication authorization: on 2026-11-10 the user instructed, "Now push the
project till prompt 3 to both the github accounts". Release preparation updates
documentation only. Publication must verify both remote trees after branch updates.
Next development phase: Prompt 4, after publication and receipt of its exact scope.
Prompt 4 implementation has not begun. Stop for independent review after that phase.

---

# Historical Prompt 2 handoff (superseded phase-status text below)

# Prompt 2 — approved closure

Primary: chinmaymr37/Trading-bot, main.
Baseline: 57dd136a596f7850f316f82e0d892c22d4c53406.
Both remote main branches were verified at this baseline before publication.
The user approved Prompt 2 closure following independent review and authorized
publication to the primary repository, then the identical commit/history to
echandrabayyapureddy-afk/Trading-bot main, without force or overwriting divergence.
Consult the publication report and Git history for the final verified remote SHA.

Read README.md, APPROVAL_PROVENANCE.md, CONTRACTS.md and TEST_RESULTS.md first.
Then review config.py, config_contracts.py and tests/test_contracts.py alongside
existing tests/test_config.py. Generated schemas/examples/catalog are updated.
Python 3.12+, standard library only; no dependency installation required.

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v
git diff --check
```

108 passed / 0 failed / 0 skipped in the final run. No historical/live data used.

F1: corrected dual-risk input/formula validation, protection coverage and unknowns.
F2: immutable linked event records; late notifications preserve actual occurrence;
anomalies retained as reconciliation issues. No persistence/order processor.
F3: evidence-backed profile contracts, hash/approval/purpose/validity checks and
configuration pins. Authenticating evidence remains external.
F4: operational entry points deny all readiness while trust is unprovisioned;
non-authorizing signature tests cannot enable operations. No bypass flag exists.
F5: stale documentation corrected; schema 3.0 explicitly rejects old approvals.
F6: precise experimental D/D+1/D+2 delay documented; operational approval remains
false pending broker timing evidence and explicit operational workflow decision.

Unresolved operational prerequisites: real account/data/provider/calendar/universe;
verified broker/fees/slippage/adverse allowance profiles; mark validity and expense
basis; authentic protection/reconciliation; trusted operational credentials and
runtime deployment isolation. Keep blocked; do not invent data or approvals.

Holdout manifest remains UNSEALED. No outcome research, tuning, holdout reads,
legacy edits or broker orders. Portfolio sizing/capacity/ledger engines are not
implemented. Fixed policy and Candidate A/B timing/EMA semantics are preserved.

Old artifacts/*.zip and *.bundle intentionally remain historical, not corrected
releases. Do not use them in place of current working files.

Prompt 2 is closed by user approval following the reported independent 108-test
review. Release verification reran all 108 tests successfully. Recommendation: GO
for Prompt 2 closure only; operational trading remains blocked. Prompt 3 requires
separate approval and has not begun. Before future development, verify checkout
and both remote SHAs against the publication report; do not use historical archives.


Focused review follow-up: all three additional findings corrected locally.
- Marks <= trigger now block position and combined new-entry checks without mutation.
- Broker version and duplicated typed execution inputs bind explicitly to config.
- Historical applicability is distinct from evidence/approval cutoff and approval
  expiry/revocation. Retrospective execution assumptions are explicitly labelled.
Read CONTRACTS.md temporal semantics before calling research authorization.
New regression module: tests/test_review_regressions.py (19 passing tests).
Full suite: 108 passed, 0 failed, 0 skipped. Schema 3.0 / config 0.3.0.
The closure authorization supersedes the earlier local-only publication restriction.
No source changes were made during publication preparation; only closure, approval
provenance and test-result documentation was updated. There is no retained review
hash manifest, so exact byte identity to the independent review cannot be attested.
Current code was inspected and its 108-test result reproduced; no unrelated changes
were identified. Prompt 3 remains behind a separate approval gate.
