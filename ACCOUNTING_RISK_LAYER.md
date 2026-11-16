# Prompt 7 — synthetic fees, accounting and risk (approved Prompt 7 release)

Baseline primary main ffb38ef4c11987fe508113443e58747c1db6ea5e; secondary main
941212a5e36632e52ddbb53f2b3bdccb75f08350. Both verified at tree
3deb71e7ed29305f443d3a44ef99046612c0b7c0. Python standard library only.
No real tariff, broker, market data, research or operational approval is supplied.

The user approved closure after independent GO review. All six reviewed source/test
hashes are preserved. Earlier review-gate wording below describes historical work;
Prompt 8 and production integration remain unauthorized. Final publication SHAs
are reported separately after remote verification.

## Ownership and integration

`ledger.Journal` owns durable accounting facts. `reconstruct` produces cash,
receivables, payables, reservations, holdings, charges, external flows and realized
P&L from those facts. `portfolio.value` uses explicit raw timestamped marks;
`update_nav` and `journal_nav` compute unitized NAV without mutable cached peaks.
`risk_manager.assess_quantity` checks a supplied whole quantity; `size` searches
for a valid whole quantity. `fee_model.quote` returns itemized scoped fee deltas.
`AccountingDependencies.assess` implements Prompt 6's pure dependency interface.

Prompt 6 alone decides fills, activation and exits. `project` translates only
APPLIED audit events into stable-ID accounting records. Rejected/quarantined
commands remain in the simulator audit and cannot acquire ledger fill effects.
Funding, buy reservations, fills, estimated fees and buy-fee payments project once.
Export the same records with Journal.append; exact duplicates are no-ops.
Projection and durable reconstruction use the same accounting reducer, not two
independent balance implementations. Before new entries the adapter compares ledger
cash, net unsettled assets and holdings with the simulator. Any discrepancy blocks.
No published Prompt 6 code or unsupported-feature guard was changed.

A material integration boundary remains explicit: Prompt 6 cannot ingest settlement
credits, external flows, fee refunds, reservation cancellation or documented resume.
These have standalone journal/NAV contracts where supported, but are NOT injected
into its immutable account. The adapter supports the original fixed-funding replay;
it does not clear simulator entry blocks. Integrating a durable live account and
resumption needs a separately reviewed execution interface. No production claim.

## Fees

All seven components must be specified: brokerage, STT, stamp duty, exchange,
regulatory, GST and DP. An explicit zero needs source text. Schedules carry version,
effective interval, source/evidence, evidence availability, approval availability/
expiry, status and SYNTHETIC purpose. The deterministic content hash accompanies
quotes; user approval and authentic external evidence are not established by Python
records. No real broker was selected and no real rates were researched or invented.
Operational profile and trust gates remain unchanged and blocked.

Rules support turnover rates, fixed/minimum/maximum charges, side applicability,
explicit rounding quantum (UP/HALF_UP/DOWN), and bases referencing earlier itemized
components (for example GST on brokerage). Exact Fractions are rounded with integer
arithmetic, independent of ambient Decimal precision. Non-fill scopes require
explicit cumulative scope turnover: ORDER, INSTRUMENT_DAY or ACCOUNT_EVENT.
The caller supplies ScopeTotals(scope_id, buy, sell), with a stable identity for
each scope and separate side turnovers. A subsequent quote supplies the previous
bound FeeQuote, whose profile, scope identities and accrued totals are validated.
Accrued totals are recomputed for every component using only its applicable side(s),
including previously accrued opposite-side amounts. Quotes return differences,
avoiding repeated fixed/minimum charges. A non-applicable side cannot erase accruals.
GST-like bases use same-scope cumulative rounded component totals. A side-specific
dependent component cannot reference a differently scoped or broader/opposite-side
base: that ambiguous schedule is rejected.
Normal updates cannot decrease either side's turnover or change the opposite side.
Explicit correction_evidence with a previous bound quote permits revised turnover
and negative deltas, including dependent-tax/rounding changes; they are not clamped.
Corrections are quotes, not automatically booked refunds. Repeating a corrected
snapshot yields zero increment. Old unbound charged tuples are rejected. Scalar
scope totals remain one-shot estimates only and cannot seed incremental quotes.
This is an incompatible local FeeQuote contract extension; regenerate old quotes.
Unknown scope totals fail. Arbitrary nonlinear cost bounds are supported by sizing.

The execution adapter deliberately supports ORDER/FILL schedules only, matching
Prompt 6's all-or-none orders. Cross-order scope accumulation must not be invented;
the adapter rejects such schedules. It estimates buy fees at the frozen ceiling.
A changed fee at later submission/fill remains rejected by Prompt 6. CHARGE records
book estimates; a linked ACTUAL_CHARGE applies the actual-minus-estimate once.
Payments carry the CHARGE ID as parent. For older unlinked PAY records, attribution
is allowed only when exactly one positive charge liability exists; otherwise the
original record is retained as an anomaly without account effects. The execution
projector now emits explicit fee-payment parents. ACTUAL_CHARGE adjusts only its
own estimate: due=max(actual-paid,0), refund=max(paid-actual,0). Other liabilities
are untouched. One actual correction per estimate is supported; conflicting/new-ID
second corrections are quarantined. Further invoice revisions need future contracts.
Any excess payment creates a nonspendable refund receivable keyed by the actual
correction ID. REFUND must reference that ID and match its outstanding amount;
it transfers the receivable to cash exactly once without changing P&L a second time.
Partial refund receipts are unsupported. SETTLE cannot consume fee refunds.
ADJUST cannot reference charges, actual charges, payments or refunds: fee correction
must use this attributed workflow. General cash adjustments still require a unique
existing parent and cannot silently edit old facts. Existing durable payload fields
are unchanged; REFUND is a new local record kind. Ambiguous old payments fail closed.
No automatic fee reconciliation into Prompt 6 is implemented. Slippage and remaining
exit costs/adverse allowances are separate evidence fields, not embedded twice.

## Ledger and settlement

Records preserve occurrence/notification/recording times and evidence/source IDs.
All records are SYNTHETIC; ACTUAL cannot mix into the same account. SQLite uses
BEGIN IMMEDIATE transactions and FULL synchronous mode. A whole append batch either
commits or rolls back. Canonical payloads form a hash chain checked on restart.
There is no update/delete API; external database tamper resistance, access control,
backup recovery and production concurrency/load are not certified.

Conflicting event IDs survive as separate records and produce blocking anomalies;
exact duplicates have no additional effects. Rejected semantic transitions preserve
their original facts and do not mutate balances. Historical receipt insertion is
rejected at append; late-occurring accounting mutations with current receipt times
are retained but quarantined in reconstruction. Old as-of results exclude future
receipts. This store is not an upstream raw malformed-message archive.

Reservations reduce buying power, never equity. RELEASE must match a live
reservation and carry explicit evidence. BUY requires positive consideration and its own sufficient reservation, and cannot
pyramid. Immediately before applying it, purchase amount must be no greater than
settled cash minus all payables minus every other live reservation. Only its own
reservation is excluded from this cash check. New charges can make a previously
reserved purchase underfunded; such a BUY is quarantined with no cash, holding or
reservation changes. The charge and other commitments remain recorded. Zero-cost
share acquisition/corporate-action conversion is unsupported and must not enter as
a BUY. Representable rejected facts remain in the journal; valuation reports unknown
equity while anomalies exist, rather than presenting the account as ready.
SELL requires the entire remaining quantity and matching price series.
Partial execution remains unsupported. Sale proceeds are receivables, not cash.
CHARGE creates a payable; PAY consumes settled cash explicitly. Equity is settled
cash + gross holdings + receivables - payables. Realized P&L is sale proceeds minus
raw purchase basis minus booked charges; unrealized P&L is marks minus raw basis.
Purchase charges are not also capitalized in basis. Reservations never count twice.

Settlement requires an explicitly versioned rule bound to a supplied calendar,
applicability, availability and confirmation evidence. `confirmed_settlement` checks
an open session and creates an exact receivable-linked SETTLE record. No elapsed-day
T+1/T+0 inference exists. Callers must provide authentic confirmation in a future
production integration; a synthetic evidence string cannot prove real settlement.

## Valuation and NAV

Missing, stale, future, conflicting or incompatible marks produce incomplete
valuation (`equity=None`), never a safe zero. Current marks require a documented
validity interval; no arbitrary age is invented. Mark records can persist in the
same Journal and replay through journal_nav. They are RAW, with stable instrument
and provider/version series binding. No adjusted view or corporate action conversion.

Initialization requires positive cash-only funding and NAV=1; units equal capital.
Subsequent cash flows issue/redeem units at a complete same-cutoff pre-flow NAV.
Full withdrawal, zero units or depleted equity block confident continuation; they do
not reset the peak. Fraction arithmetic retains exact ratios for threshold checks.
At drawdown >=5% latch pause; >=8% escalate hard suspension. Recovery never clears a
latch. A clearance binds account, exact current recovered-state hash, time, reason
and evidence. The conservative implementation convention requires recovery strictly
below 5% for either latch. Peak never resets. A journal CLEARANCE parent references
the candidate computed from the preceding journal at the clearance cutoff (excluding
the clearance itself, avoiding a circular hash). Authentication remains external.

The adapter replays known mark observations and accepted fill cutoffs rather than
accepting a caller's risk-approved or drawdown-clear flag. Missing historical marks
block entry. Earlier accounting receipts must be available at the execution cutoff;
late ambiguous revalidation requires reconciliation. It does not promise continuous
unobserved NAV coverage or complete external mark feeds. External mark evidence and
valuation history must be retained by the caller; durable journal MARK records are
the supported standalone storage path. Adapter resumption/flow injection is unsupported.

## Risk

Existing position contracts are constructed from simulator entry, stop, quantity,
activation and trigger state, plus timestamped marks and explicit cost evidence.
Both entry-to-stop and mark-to-stop risk include remaining unbooked costs/allowance;
the larger contributes to aggregate risk. Marks at/below stops, inactive/inadequate
protection, missing inputs and unresolved reconciliation block new entries.

Fixed limits are consumed from config: 0.5% per trade, 1% aggregate, 40% stock,
80% gross and two held/committed slots. No leverage, pyramiding or fractional shares.
Commitments contribute exposure/risk; reservations reduce settled buying power.
Fill revalidation removes only its own pending commitment/reservation before adding
that same proposed quantity. Other commitments remain. Submitted quantities are
never silently reduced. Worst admissible price and explicit total cost bounds are
used. `size` exhaustively checks a finite cash/equity upper bound so nonmonotone
quantity costs do not invalidate a binary-search assumption. Very large share-count
resource use is unbenchmarked; target synthetic capitals are INR 5,000/10,000.
Costs callback must bound the full admissible price interval; a generic callback
cannot prove external cost completeness. No optimized correlation policy is added;
sector/correlation concentration remains a limitation despite fixed exposure caps.
Stops and adverse allowances do not guarantee maximum loss.

## Verification and next step

Run:
```
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p test_accounting_risk.py -q
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -q
git diff --check
```
See TEST_RESULTS.md for actual outcomes and REVIEW_MANIFEST.json for exact candidate
source/test hashes. Separate independent review is required; Prompt 7 is not closed.
Real manifest stays UNSEALED. No commit/push, broker connection or Prompt 8.
