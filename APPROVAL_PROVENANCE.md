# Approval provenance

Primary: chinmaymr37/Trading-bot main.
Verified baseline: 57dd136a596f7850f316f82e0d892c22d4c53406.
Eswar main matched that commit and tree before editing. Source bytes were obtained
from the matching public mirror and verified by commit/tree, then local origin was
set to the primary. Neither remote has been mutated.

Authority for these changes: user's explicit “bounded Prompt 2 correction package”
in this conversation, sections 1–9. This authorizes local configuration/contracts/
validation/tests/docs only, not commits, pushes, synchronization or Prompt 3.

POLICY: unchanged numerical constraints (0.5%, 1%, 40%, 80%, 2, 5%/8%, zero leverage),
manual approval/placement, completed bars, two completed-session confirmation and
holdout isolation are preserved under the explicit instruction. The conservative
MAX_ENTRY_AND_MARK rule and formula/expense/protection requirements are newly
explicitly approved in section 2. Event/profile fail-closed contracts follow sections
3–5. Parameter labels remain exactly POLICY / BASELINE HYPOTHESIS / EXPERIMENTAL.

BASELINE HYPOTHESIS: indicator defaults are retained from the baseline; retention
is not empirical validation or approval for live trading.

EXPERIMENTAL: Candidate A/B, stop/ranking/filter semantics and operator delay retain
the baseline values as requested by section 6. The monthly comparison remains
month-end close versus the same month-end DAILY EMA200, not a monthly EMA200.
No experimental default is relabelled as an approved operational rule.

The complete path/default/category mapping is parameter_catalog.json. All retained
entries derive from the baseline above; new profile pins and operational-delay block
are requirements of sections 4–6. Actual account, broker, fee, slippage, adverse
allowance, evidence validity and deployment trust are NOT approved by this package.
Do not infer earlier approvals beyond this explicit preservation instruction.


Focused follow-up authorization: user's explicit request to correct mark-at/below-
trigger checks, execution-profile bindings and historical/approval time separation.
Continued in the existing local working tree; no remote checkout replaced it.
Schema 3.0 / default 0.3.0 makes the new required profile fields explicit; old
approvals cannot silently cover the new document hashes. Safety values and strategy
defaults are unchanged. Retrospective research labels are required disclosures,
not approval to inspect holdout data or tune performance.

## Prompt 2 closure and publication authorization — 2026-11-10

The user approved closure following independent review (reported 108 passing tests)
and authorized committing the reviewed package to chinmaymr37/Trading-bot main,
then synchronizing the same commit and history to echandrabayyapureddy-afk/Trading-bot
main. No force push or overwrite of divergent work is authorized. This supersedes
earlier local-only restrictions for this package. Prompt 3 and operational trading
remain unauthorized. Publication preparation changes documentation only; it grants
no new parameter, profile, dataset or operational approval.


## Prompt 3 closure and publication authorization — 2026-11-10

The user explicitly approved Prompt 3 closure after independent review reporting
177 tests passed and focused split-boundary/mixed-series probes. The subsequent
instruction "Now push the project till prompt 3 to both the github accounts"
authorizes publication to chinmaymr37/Trading-bot main and synchronization to
echandrabayyapureddy-afk/Trading-bot main. Preserve independent history and never
force-push. This supersedes earlier Prompt 3 status/publication restrictions.
No Prompt 4 implementation, operational approval or research authorization follows.
