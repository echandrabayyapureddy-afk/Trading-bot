# Prompt 8 — synthetic suitability and human review, contract REVIEW-1

Local implementation on Prompt 7 primary e93f63259e51cfc0589a219ee6ec933afee8c499.
Secondary 55f91a83ab0c885d53f40898550f3f3e9a50eb4a retains independent history.
Both main heads verified unchanged; release tree 0920b5a58d15dac08adef973a6af7af65b1546b9.
Prompt 8 closure is approved following the user-reported separate independent GO
review. Publication to both main branches is authorized, preserving separate histories.
Earlier local-only status is historical; Prompt 9 remains unauthorized. The review-to-
execution bridge and operational readiness remain blocked. P8_REVIEW_MANIFEST.json
preserves the pre-release reviewed hashes: source/tests are unchanged, while release
preparation updates documentation only. Final publication SHAs are verified in the
completion report after publishing.

## Report interfaces and interpretation

`suitability.evaluate(snapshot, config, account, adapter, capabilities, request, at)`
returns an immutable Row. `weekly_report` produces the last completed weekly cohort
at a current decision cutoff; it does not promise an executable Friday-close trade.
D+1 must intervene, so a newly selected Friday opportunity is WATCH until D+2 and
all current gates pass. `render_report` is canonical JSON, including nested source
records for complete offline human review; there is no web UI or notification sender.

Each row contains a stable content-derived proposal_id, status, reasons, report time,
expiry, full Request (StrategyResult, RegimeResult and explicit PricePoint), quantity,
cash use, seven fee items, planned and aggregate risk, median turnover, account hash,
dependency evidence hash, SYNTHETIC origin, null target and false operational authority.
The nested signal exposes instrument, strategy version, config hash, signal/session
and decision timestamps, data status/reasons, weekly opportunity, frozen levels,
initialization and identity/source/calendar lineage. MonthlyEvidence records month
boundaries, final observation session, availability, close, daily EMA200 and lineage.
RegimeResult exposes its measurements, confirmation, veto and availability. Entry
band is strictly above frozen stop and at/below frozen ceiling. No target is approved.

BUY-CANDIDATE means passing supported synthetic pre-review gates, NOT human approval,
manual placement, queue fill or live authorization. An ACTIVE opportunity blocked by
any gate is WATCH (quantity zero); absent/retired opportunities are SKIP. Every reason
is explicit, unknown estimates remain null, and no ranked rows produces NO TRADE.
Only passing rows rank: median of the configured 20 valid completed raw close × raw
volume observations, descending; stable instrument ID ascending breaks ties. Even
windows use the arithmetic mean of the middle two, with exact Fraction arithmetic.
This is liquidity ordering, not a probability, expected return or optimization score.
Future-unavailable requests are excluded. Duplicate visible instruments fail clearly.

Reports are alternatives evaluated individually against the SAME immutable shared
account, including existing pending commitments. Quantities are NOT additive and do
not reserve cash. A user choosing more than one must submit/revalidate sequentially
through the authoritative execution interface; this package has no basket submission.
This avoids introducing a competing reservation ledger. A ranking never authorizes
spending the same cash twice. Actual batch integration remains unsupported.

## Integration and conservative boundaries

Only the concrete Prompt 7 AccountingDependencies adapter is supported. Whole-share
quantity scans call its computed assessment and Prompt 6 dependency checks; fees,
positions, settled buying power, pending reservations, fixed risk caps and NAV latch
are inherited rather than replaced. Missing fee/cost evidence blocks. Fees are
itemized through the same fee_model.quote and must match the adapter. Existing
ORDER/FILL-only scope guard remains. Remaining exit costs and adverse allowance are
included in planned risk; stops and allowances do not guarantee maximum loss.

Prompt 6's existing `_signal`, `_identity`, `_point`, `_dependency` helpers are reused
without modifying them. They are internal interfaces: future changes require this
layer's regressions. StrategyResult/RegimeResult must originate from Prompt 5/4 replay;
Python hashes bind supplied records but do not authenticate a producer. This report
checks source/identity vintages and current history, exact regime binding, raw series,
last completed weekly/monthly evidence, current price, delay and frozen band. It does
not implement a second strategy/benchmark engine. Rebuilding trusted upstream replay
at the true cutoff remains the caller's responsibility. No real index/provider exists.

Expiry is the earliest of explicit request expiry, next scheduled session close
(which invalidates current completed-session evidence), capability expiry, cost
expiry, fee approval expiry and fee historical applicability end. Current gates must
still be recomputed: expiry is not a promise of validity until that time.
`revalidation_issues` rejects changed account, dependency, signal, quantity/cash or
price. This deliberately conservative implementation may require a fresh proposal
when evidence changes even if the resulting economic decision looks identical.

## Durable review workflow

ReviewJournal is a separate SQLite HUMAN REVIEW record store, not an execution or
accounting ledger. Its immutable ReviewFact includes stable event/proposal IDs,
canonical complete proposal content, REVIEW-1 version, actor/evidence, occurrence,
notification and recording timestamps, and SYNTHETIC origin. The proposal hash is
checked on replay. Exact duplicate facts do not append; conflicting IDs remain
visible and block approval. FULL synchronous transactions and a verified hash chain
support deterministic restart and detect accidental payload corruption.

Allowed sequence: PROPOSED → REVIEWED → APPROVED. PROPOSED/REVIEWED may instead
become REJECTED. Any active state may expire; rejection and expiry are terminal.
Equal timestamps are allowed only in persisted prerequisite order. Approval needs
receipt before expiry; occurrence before expiry with late receipt after expiry does
not authorize anything. Explicit early expiry is conservative revocation. Implicit
EXPIRED is computed at the cutoff even without an expiry receipt.

Out-of-order, stale, mismatched or conflicting parseable facts remain diagnostic.
They cannot produce an approved effective state. Backdated receipt facts are visible
no earlier than the previous durable receipt watermark; their original timestamps
remain unchanged, and they are quarantined. Earlier historical prefixes remain intact.
Invalid primitive types fail before append; a raw malformed-message archive, external
actor authentication, database ACLs and tamper-proof signatures are not implemented.
The journal stores reviewable proposal content; retain source evidence separately.

Operator workflow: generate/render report; inspect full proposal and evidence; append
PROPOSED then REVIEWED then APPROVED or REJECTED facts; obtain a fresh evaluate result
at the actual cutoff; call approval_issues. Any issue requires stopping/reviewing anew.
`submission_issues` ALWAYS adds an explicit unsupported-bridge block. There is no
approved safe mapping of this journal into Prompt 6 approval event chains yet. Manual
downstream submission, acknowledgement, fill, activation and exit facts belong only
to Prompt 6; this layer neither emits them nor processes them. No credentials, broker
API, transmission, synthetic-to-actual conversion or live approval is supported.
Reports cannot disable exits/reconciliation; no existing execution code is changed.

## Verification and limitations

Offline fixtures cover formulas/order ties, A/B monthly evidence, missing/revised/stale
inputs, fees and pending commitments, zero shares, gaps, expiry, conflicting approval,
rejection, late receipt, restart, future rows/revisions and incomplete week/month gates.
The complete prior suite retains risk, drawdown, execution and holdout regressions.
Production storage load/concurrency/security, authentic operator identity, actual
provider calendars/fees/capabilities, basket execution and review-to-execution bridging
remain unverified/unsupported. These are not permissions to bypass existing blocks.
No outcome research, policy changes or holdout access. Real manifest stays UNSEALED.
