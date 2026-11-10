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
