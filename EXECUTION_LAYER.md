# Prompt 6 — synthetic execution simulator, contract 1.0

Closure approved 2026-11-14 after the user-reported separate read-only review GO.
Publication to both repositories is authorized. Earlier local review status below
is historical; implementation limitations remain unchanged. See PROJECT_HANDOFF.md
and TEST_RESULTS.md for release verification. Prompt 7 is not authorized.

## Causal correction — 2026-11-14

Positions now retain trigger_at, trigger_command_id and trigger_evidence_sha256.
Activation <= trigger <= protective fill occurrence is mandatory. Equal timestamps
are allowed only when the prerequisite transition has already been accepted under
the declared receipt/priority ordering; no future trigger is inferred. Ordinary
fills still require occurrence strictly after intent observation. A protective fill
may resolve an already-observed intent at the same instant, but never before it.

The late-fill guard additionally checks accepted TRIGGER and EXIT_INTENT commands,
and unresolved BAR diagnostics (at their recording cutoff). A fill predating those
transitions is quarantined with original occurrence/notification/recording fields,
without position, cash, proceeds or intent-resolution effects. New entries block;
no reconciliation-clearance API is added. The sell transition also checks trigger
and intent ordering directly as defense in depth. Acknowledgements are not account
mutations and legitimate late acknowledgement notifications remain supported.
The additional optional Position fields extend this unpublished local contract;
no published configuration schema or approval is migrated.

Local implementation on primary main `f4146432e662c37028e411e33d4496e3021cd51f`.
Secondary main was verified at `907c8f06bb6d3b3f1d1dce82214c26cfa1a33567` with identical
tree `fc3521fab33b4ed38892f024c4f12ffe1e911438`. Python 3.12+, standard library only.
This is offline engineering. No actual account, broker, market dataset or outcomes
are accessed. Snapshot, funding, commands, dependencies, capabilities and price
points are explicitly SYNTHETIC. Embedded Prompt 2 events use its existing
`SIMULATED` enum; ACTUAL events are rejected and retained in the audit quarantine.

## Interfaces and ownership

`execution_engine.replay(snapshot, config, funding, capabilities, commands,
dependencies, as_of)` returns one immutable Account with orders, positions, accepted
events, original command audit records and entry-block reasons. No prior mutable
account state is accepted. `execution_records.py` defines the frozen typed contracts
and Dependencies protocol. The sole state transition implementation lives in
execution_engine: `_exit_transition` owns intent/activation/trigger transitions and
`_sell` owns the only position-decrement path. There is no parallel strategy exit
executor. `_event` routes all ordinary/protective fills through this shared path.

Prompt 7 owns sizing, fee schedules, equity/drawdown calculations, settlement and
the durable ledger. `Dependencies.assess` receives the complete current immutable
account, command and config fingerprint. It returns DependencyEvidence bound to
that state hash and exact event occurrence cutoff. Fees and adverse slippage are
explicit per-order INR and per-share INR respectively, including explicit zero.
Missing values are never zero. Synthetic tests supply deterministic adapters; no
production risk decision or fee engine is implemented here. Their fixture approvals
test execution plumbing and do not certify an account as satisfying actual risk.
Accepted submission/fill audit lineage includes the dependency record hash; the
adapter/caller must retain those referenced records. No durable evidence store is
implemented here, and fingerprints do not authenticate an external adapter.

Entry approval must cover each named fixed policy, spendable settled cash and
reconciliation. Every existing position additionally needs its Prompt 2 dual-risk
contract, checked against remaining quantity, average entry, frozen trigger,
activation ID and coverage. Unknown/stale marks, costs, protection or reconciliation
block entries. Risk calculations and aggregate 0.5%/1%/40%/80% limits are the external
dependency's responsibility, not inferred from flags by a new risk engine. The
simulator itself also enforces two held/pending instruments, whole supplied quantities,
no pyramiding, no duplicate trade IDs and shared cash conservation.

Drawdown suspension decisions latch an entry block. There is no automatic recovery,
peak reset or resumption interface. Existing exits continue despite entry blocks.
Current synthetic capability records are not broker VerificationProfiles and cannot
authorize operational entry paths. Production integration remains UNVERIFIED.

## Event order and receipts

Visible commands are ordered by (recorded_at, caller priority, command_id). Distinct
simultaneous buy submissions require unique caller priorities: no ranking heuristic
is invented. Command IDs break ties for other actions; callers must explicitly order
simultaneous trigger/fill actions. Commands with identical IDs and contents are
idempotent. Identical event facts under receipt aliases are applied once. The audit
retains whichever alias sorts first, while cash, accepted events and quantities are
unchanged. Conflicting IDs retain the conflicting original command and block entry.

Prompt 2 event_issues enforces DECISION -> TRADE_APPROVAL -> MANUAL_SUBMISSION,
ACKNOWLEDGEMENT -> submission, FILL -> submission, and PROTECTION_ACTIVATION -> entry
fill. Occurrence, notification and recording times remain distinct and untouched.
Acknowledgement is not a prerequisite for processing an otherwise valid fill; late
acknowledgement notifications do not rewrite fill occurrence. Late state mutations
that predate accepted fills/activations are quarantined for reconciliation. There is
no insertion into an earlier account history or silent disposal of parseable facts.
Structurally invalid primitives fail typed construction; upstream raw-message storage
is outside this package. Each failed transition is atomic and leaves cash/quantities
unchanged, with its original command and rejection reasons retained.

## Entry, prices and availability

Consume Prompt 5 StrategyResult at decision, buy submission and fill. Require ACTIVE
opportunity, signal eligibility, matching config/calendar/instrument, available cutoff,
latest completed session and identical daily/identity lineage at the execution cutoff.
Frozen proposal source is checked at its original cutoff; revisions do not rewrite it.
The proposal is bound back to the decision through approval/submission ancestry.
Passing a diagnostic label, rejected result, stale signal or changed levels blocks.
These checks consume the approved strategy interface; they do not independently rerun
all strategy/regime mathematics or authenticate a caller who fabricates records.

D+1 is the full intervening exchange session; D+2 is independently checked against
the versioned calendar and stored earliest_session. Opening evidence at/below the
stop or above the exact ceiling blocks. Adverse slippage may never be clipped into
a buy fill. `exact_tick_floor` remains unchanged, with its previous regressions.
Cash arithmetic uses exact rational operations and exact Decimal reconstruction.

PricePoint is a separate timestamped RAW synthetic execution observation, not the
unavailable final daily OHLC at an opening time. Its provider/version must match the
signal or held position, identity must be listed at occurrence and session segments
must contain the timestamp. No adjusted NONTRADABLE input type is accepted.

Supported fill assumptions are explicitly declared in versioned Capabilities with
availability and expiry supplied by the fixture (no invented production validity):
- OPENING_ASSUMPTION: all-or-none fill at the first segment's open, only when enabled
  and submission occurred strictly before that open. This is a declared hypothetical
  execution assumption, not a claim that daily open/volume proves liquidity.
- EXPLICIT_TRADE: timestamped synthetic execution fact, when explicitly enabled.
  Submission must precede execution strictly; an opening opportunity missed earlier
  may only execute later using this distinct evidence. No backdated open.
  A buy also needs separate timestamped opening-price evidence from the same series;
  an opening at/below the frozen stop blocks that session even after a rebound.
  An above-ceiling open can only be followed by an independently evidenced later
  admissible trade, never a claimed opening fill.
- OBSERVATION: can establish a post-activation protective trigger; never a fill.

Actual fill price must equal point price plus buy slippage or minus sell slippage.
It must remain positive and satisfy applicable buy ceiling/stop or sell stop-limit.
No real order type, broker cutoff, queue model, partial liquidity or slippage bound
is inferred. Costs/slippage changes after reservation reject the affected fill.

## Cash and position conservation

Buy submission reserves ceiling*whole_quantity + explicit order fee atomically.
Availability is the lesser of remaining synthetic settled cash and dependency
spendable cash, minus other pending reservations. Capacity includes pending buys.
Fills recheck dependency evidence and cash, debit the supplied full quantity once,
release that order's reservation and create one unprotected position. Quantities are
never silently reduced to fit cash. Partial entry or exit execution is unsupported
and explicitly rejected; consequently position quantity is full or zero here.

Sell proceeds net of explicit fees accumulate as unsettled_proceeds and are never
spendable. There are no settlement credits, deposits, reservation cancellations or
durable ledger APIs yet. Exit fees exceeding proceeds require external settlement
and remain blocked. This minimal account is conservation state for simulation only.

## Protection and ordinary exits

Position states: UNPROTECTED -> ACTIVE -> TRIGGERED_UNFILLED -> CLOSED; an ordinary
exit may close any remaining position. Entry_at and activation_at delimit the explicit
unprotected interval, and quantity minus protected_quantity exposes incomplete
coverage. Activation requires its own event, a preceding protective submission,
the exact entry-fill parent and frozen trigger, and cannot exceed remaining quantity.
Protection order types must be explicit, with configured type pins respected.

An OBSERVATION at/below trigger establishes TRIGGERED_UNFILLED only at/after activation.
STOP_MARKET requires a separate execution fact/assumption at an actual hypothetical
price; gaps need not fill at trigger. STOP_LIMIT retains its trigger latch while a
price below its separately supplied limit remains unfilled. Order types are never
substituted. No stop/allowance guarantees a maximum loss.

EXIT_INTENT commands ingest Prompt 5's persistent ordinary intent only after its
completed session close. Intent ingestion is independent of entry eligibility,
regime and monthly filters. Ordinary submission needs that unresolved intent. A
fill must occur strictly after intent observation, so it cannot use an earlier price
in the same daily bar. Merely proposing, approving or acknowledging never resolves it.
A full ordinary or protective sell resolves the intent with the synthetic fill ID,
zeros remaining/protected quantity and cancels other pending orders for that trade.
A second competing fill cannot sell again. Resolution objects remain simulation-only.

## Daily ambiguity and unsupported processing

BAR commands consume Prompt 3 validated daily bars and retain lineage. They ALWAYS
return UNRESOLVED: this deliberately conservative diagnostic path never infers entry,
activation, trigger ordering or fills from daily low/high, even for benign bars.
New entries latch blocked; existing exits/reconciliation remain possible. No favorable
branch, target, trailing stop or conservative bound is booked as an account fact.

Missing/invalid daily evidence and known effective corporate actions reject processing
without fabricating prices or altering positions. No corporate-action conversion,
merger/dividend/rights treatment or real suspended/delisted liquidation is implemented.
Price facts already accepted remain immutable if later data revisions are appended.
Future commands/data cannot change earlier cutoff outputs (unless a deliberately
changed full-snapshot configuration pin rejects the new snapshot).

There is no in-place reconciliation-clearance or drawdown-resumption API. Unresolved
runs remain blocked and must be retained for review; a separately authorized corrected
replay can produce a new, distinguishable history. Cancelling/replacing orders,
partial fills, production adapters, settlement, durable persistence, ACLs and upstream
evidence authentication are unimplemented/untested. Python types do not establish
external evidence authenticity. Production throughput and extreme input sizes are
untested. The manifest remains UNSEALED; no research authorization is granted.

## Verification and next gate

`PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p test_execution.py -q`

`PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -q`

`git diff --check`

All fixtures are synthetic. See TEST_RESULTS.md for actual counts. Independent review
must challenge event timing, dependency fingerprints, shared resources, ambiguity
latches, price basis and competing exits before closure. Prompt 7 is not authorized.
