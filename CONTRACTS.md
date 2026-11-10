# Prompt 2 contract semantics — version 3.0

## Existing positions

For each remaining position, required inputs are q (remaining whole quantity),
P (average entry execution price), M (valid current mark), S (confirmed protective
trigger), C (remaining unbooked expenses) and G (approved adverse-execution allowance).

- R_entry = q × max(P − S, 0) + C + G
- R_mark = q × max(M − S, 0) + C + G
- R_position = max(R_entry, R_mark)
- sum(R_position) + pending_entry_risk + proposed_entry_risk ≤ 0.01 × equity

A proposal must separately satisfy 0.005 × equity and all cash, allocation,
exposure and position limits. C excludes booked expenses already reflected in
cash/equity. Costs and allowances are nonnegative and cannot default from unknown
to zero. Stops and allowances DO NOT guarantee maximum loss, including gaps,
illiquidity and stop-limit nonexecution.

PositionRiskContract validates required inputs and reports issues. It requires both supplied risk measurements and their maximum, and validates their
arithmetic against the formulas. It does not size positions, aggregate a portfolio, calculate equity or enforce
cash constraints. Those algorithms remain future work. `unprotected_quantity` and
`marked_capital_exposure` are separate diagnostics, never stop-risk substitutes.
Missing marks return null exposure; a reported stale mark must remain labelled
stale using issues(as_of), not treated as validated exposure.

Block new entries whenever the current mark is equal to or below the protective
trigger, even with claimed active protection and confirmed reconciliation. Preserve
actual position facts and risk measurements; do not infer a fill, liquidation or
change of protection state. Exit handling and reconciliation remain possible.

Block entries for unknown/planned/submitted/broker-held/triggered-unfilled/cancelled/
expired protection, missing activation evidence, inadequate protective quantity,
missing/stale marks, missing expense/allowance provenance or unresolved reconciliation.
Mark validity must have an explicit evidence basis; no arbitrary freshness age is
invented. The future runtime must supply authoritative reconciliation snapshots.

## Execution facts

ExecutionEvent is a tagged immutable record: DECISION, TRADE_APPROVAL,
MANUAL_SUBMISSION, ACKNOWLEDGEMENT, FILL or PROTECTION_ACTIVATION. Each fill is a
separate fact with its own identifier, quantity and execution price. Configuration
ApprovalReceipt is a separate type and cannot substitute for TRADE_APPROVAL.

Parent links: approval→decision, submission→approval, acknowledgement→submission,
fill→submission, activation→an actual preceding fill. Activation includes its own
protective order identifier, trigger and quantity. Fill links intentionally do not
require an acknowledgement notification to have arrived first. Occurrence time,
notification time and recording time are distinct timezone-aware fields. Receipt
order is not occurrence order. Late notification does not change earlier fills.

`event_issues` preserves parseable anomalous actual records and reports causal,
identity, timing, duplicate or missing-link issues. It never rewrites/discards
actual events. Invalid primitive types/nonfinite prices are rejected at ingestion;
a future durable raw-event quarantine is outside this package. Reconciliation
must retain such original source evidence. No event persistence or order processor
is implemented. Passing validation cannot prove a broker actually activated an order.

`entry_contract_issues` links the supplied position snapshot to activation facts,
configuration/profile hashes, profile purposes and evidence. Passing means only
that necessary contracts are internally consistent; it is NOT operational readiness.
Caller-supplied lists are not proof of complete account reconciliation.

## Verification profiles

Four distinct profiles: BROKER, FEES, SLIPPAGE, ADVERSE_EXECUTION. Each contains
version, purpose, explicit status, immutable specification content, hashed evidence,
verification time, historical applicability [effective_start,effective_end) interval
and evidence supporting applicability. Approval has a separate validity contract.
Approval binds the profile version/hash/purpose and includes reviewer/evidence data.
The content hash covers the whole ProfileBody, avoiding a self-referential hash.
Changing content requires a new hash and approval; changing config pins invalidates
the configuration signature. No real broker rules, rates or validity periods are supplied.

Missing validity requirements stay null and fail closed; arbitrary expiry periods
are not assigned. Unsupported/UNVERIFIED, missing/unapproved/altered/expired profiles
fail checks. SYNTHETIC and RESEARCH purposes cannot satisfy OPERATIONAL checks.
Profile evidence records still require external authenticity verification at deployment.

## One-session operator delay

Preserve the existing experimental value 1. If the strategy decides after session
D closes, D+1 is a complete intervening NSE exchange session; earliest simulated
opportunity is D+2. Holidays/special sessions require the future verified exchange
calendar. Human approval alone never implies an opening fill. Eligibility also
requires available data, a valid approval, revalidation, cutoff and supported order
capabilities; actual fills need broker evidence. `operator_delay_operational_approved`
remains false. A documented decision on real broker cutoff/capability and whether
this research delay represents the intended operational workflow is still required.

## Focused review corrections: temporal and binding semantics

The schema-3 profile adds typed ExecutionAssumptions and a knowledge_basis.
Approval additionally requires an explicit validity mode and supporting evidence:
UNVERIFIED blocks, EXPIRES requires valid_until, NO_SCHEDULED_EXPIRY requires an
explicit evidence basis rather than inventing an expiry. revoked_at blocks at and
after that timestamp. No production expiry or no-expiry decision is supplied.
All new JSON fields are required even when their value is null; schema-2 profile
JSON cannot silently acquire these semantics. New hashes and approvals are needed.

Historical applicability is the interval in which the rule/assumption applies.
Research authorization uses the requested historical [start,end) window, with
Asia/Kolkata midnight boundaries (not rounded dates that lose intraday precision).
That interval need not contain the dataset sealing or authorization time.

Evidence availability, verification and approval are checked at authorization_at.
If omitted, the explicitly documented cutoff is manifest.sealed_at, reproducing an
authorization decision at sealing; it is NOT a present-time approval. A subsequent
research run must supply its actual authorization cutoff and current revocation
records. Cutoffs before sealing or before the end of the requested history fail.
Approval expiry/revocation is evaluated at the cutoff, never at the historical
trade date. No contract can discover a revocation omitted by its caller.

POINT_IN_TIME requires source and applicability evidence available by the start of
the requested historical window. Later verification/approval is permitted; this is
not proof of historically available data features. RETROSPECTIVE_RESEARCH explicitly
labels execution/cost assumptions reconstructed later, using evidence available by
the cutoff. It is research-only, never historical signal information or operational
authority. UNVERIFIED knowledge basis blocks. Data point-in-time and availability
requirements, snapshot hashes, development-only boundaries and sealed holdout remain
unchanged. No retrospective market features or outcome-based tuning are authorized.

Duplicated execution fields are checked explicitly in authorize_development_window:

| Profile | Required configuration bindings |
| --- | --- |
| BROKER | version, order_cutoff_rule, protective_order_type |
| FEES | version, fee_source_reference, exact fee_effective_start/end boundaries |
| SLIPPAGE | slippage_bps |
| ADVERSE_EXECUTION | fixed_execution_allowance_inr |

All four profile hashes must match configuration pins; verification flags alone are
insufficient. Free-text specification is evidence context only, not machine-validated
agreement on numeric values. Fields in ExecutionAssumptions belonging to other
profile kinds are not authoritative for that profile. The broker cutoff string is
bound exactly, not interpreted as an executable calendar or broker rule. Fee rates,
charging units and execution models still require later engines; no adapter,
fee engine or simulator is implemented. Position-specific G must still come from an
approved allowance methodology; the config scalar is not a computed per-position G.
