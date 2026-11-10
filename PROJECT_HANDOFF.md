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
