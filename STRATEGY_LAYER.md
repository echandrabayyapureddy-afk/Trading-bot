# Prompt 5 approved closure and publication — 2026-11-12

The user reports an independent re-review GO and explicitly approves Prompt 5
closure and publication to both main branches. The exact tick-floor correction
is included. Preserve separate repository histories with identical release trees;
no force-push. Prompt 6 requires separate authorization and has not begun.
Real integration remains UNVERIFIED, operational readiness blocked and the manifest
UNSEALED. The release report records resulting remote SHAs after verification.
Earlier review-status sections below are historical and superseded by this approval.

# Prompt 5 — synthetic EMA crossover strategy, contract 1.0

Local review candidate on published primary `416f87ab74283302e2c27cc9f9c5ea1fa194ad89`.
No additional dependencies; Python 3.12+ standard library. No legacy code reused.
All parameters retain their configuration provenance, not performance validation.

## Interfaces

`strategy.Strategy` describes `EMACrossoverStrategy.replay`. Supply the typed config,
stock Snapshot, stable stock ID, explicit initialization date, chronological decision
tuple, synthetic NIFTY50 Snapshot/BenchmarkBinding/start, matching Prompt 4 results,
and optional TickEvidence. Optional ExitResolution records explicitly resolve intents.
Replay owns all state locally; do not resume it from an externally fabricated label.
It verifies supplied regime results against a full Prompt 4 replay of that exact
benchmark, configuration and decision schedule. This deliberately favors auditability
over throughput. A mismatch raises ConfigError, including changed flags, stale/future
cutoffs or diagnostic labels substituted for eligibility. Earlier regime confirmation
requires earlier decisions in the input schedule. No hidden initialization decisions.

Immutable StrategyResult contains EMA/ATR, monthly evidence, opportunity, exit intent,
regime hash, source/identity/calendar/configuration/initialization lineage and cutoff.
`signal_eligible` means only this strategy's necessary signal checks passed. It is
NOT order authorization or even D+2 execution eligibility. `operational_authorized`
is always false, with explicit unresolved downstream checks. No account or position
is created. Consumers must keep resolved and unresolved exit intents for audit.

## Numerical conventions

DAILY EMA N uses the arithmetic mean of first N valid closes at zero-based index
N-1, then alpha=2/(N+1). EMA9 first appears at index 8, EMA21 at 20; the first
possible crossover comparison is index 21. No partial warmup. Flat histories have
equal EMAs and cannot qualify. ATR14 starts at index 14: mean of TR at indices
1..14, followed by (13*previous ATR+TR)/14. TR=max(H-L,abs(H-prev C),abs(L-prev C)).
The first bar has no TR. Decimal arithmetic uses Prompt 4's fixed 50-digit context.
These numerical conventions retain deterministic initialization; no tuning is done.

## Selection, monitoring and lifecycle

Select the latest full calendar week whose final scheduled session is complete;
Friday is not assumed to be final if the calendar lists a special weekend session.
Calendar coverage must include the entire period. Missing bars in that week block;
never fall back to an older conveniently complete week. Require complete history
from the explicit initialization start. Crossover is previous fast<=slow AND current
fast>slow, within that week, with fast>slow on its final session. If there are several
crossovers in the week, retain the last qualifying event. A persistent above-state
without a new event is insufficient. The selection timestamp is the actual replay
cutoff, separate from crossover date. Selection IDs bind instrument, candidate,
week, config and initialization. Repeated selection does not make duplicates.

An ACTIVE opportunity has no invented time expiry. A later qualifying week replaces
it; an unqualified week does not. Daily fast<=slow retires it, permanently for that
selection. Monitor intervening sessions too, so a missed evaluation cannot hide a
reversal followed by recovery. Retired opportunities need a later qualifying weekly
selection. UNKNOWN/rejected evidence blocks entry but preserves the opportunity
for diagnostics. Recovery queries all missing history before permitting reuse.
Consumed source or identity revision retires the active selection and consumes the
current selection week, preventing same-week revival. A later week can qualify.
Earlier outputs remain immutable; replay each historical cutoff with its own vintage.
Calendar/config/init changes require fresh replay, never carrying an old opportunity.

Proposal inputs are frozen at first selection, even if another gate currently blocks
entry. Missing proposal evidence leaves levels unavailable for that selection; there
is no silent later reprice. A later qualifying week can form a new proposal. This is
a conservative implementation convention, not an arbitrary expiry policy.

## Candidate B and price basis

B additionally requires the latest completed monthly NIFTY50 close strictly above
DAILY EMA200 evaluated through that same month's final session, using the data
vintage visible at the evaluation cutoff. It never uses today's EMA200 or a 200-month
EMA. Full month coverage and all seed history are required. Equality/missing evidence
blocks B without falling back to A. Monthly evidence preserves its final session,
close, daily EMA, availability and lineage. Future unavailable revisions cannot
change earlier outputs. Known later revisions can change a later evaluation.

Only RAW/RAW_SHARES/UNADJUSTED synthetic records are consumed. Prompt 3 REJECTED
results block calculations even when diagnostic bars exist. Mixed providers/versions
are rejected. AdjustedView is unsupported, so no NONTRADABLE/raw arithmetic is mixed.
Known effective corporate actions across consumed history block pending a separately
specified conversion. There is no claim of complete real action-feed coverage.
Real stock and index ingestion, ticks, calendars and universe coverage are UNVERIFIED.
No historical universe selection or ranking is implemented; caller chooses a single
synthetic instrument. No suitability for unbiased performance validation is claimed.

## Frozen prices, delay and exits

Stop = proposal close - config.strategy.stop_atr_multiple * prior available ATR14.
Ceiling = floor(close/tick)*tick, computed exactly by `exact_tick_floor`.
Both Decimal inputs are converted to exact integer ratios; integer cross-products
and // determine the floor. Reconstruction multiplies the integer tick coefficient
by the integer count, then constructs a Decimal tuple with the original tick exponent.
No Decimal division or multiplication rounds either step. This is independent of
ambient precision/rounding; no epsilon, input rounding or fixed precision increase.
The independent review's 109.(60 nines) / 0.05 case now produces 109.95, not 110.
The stop calculation retains its existing 50-digit convention. TickEvidence binds instrument, dates, basis and
availability. Stop must be positive and strictly below ceiling. PlannedLevels retain
source/tick hashes and proposal time and are explicitly NOT active protection.
The versioned calendar determines D+1 and D+2 from the proposal's completed session D.
D+1 is a full intervening session; `earliest_session` is D+2. Future calendar coverage
must be available already; missing coverage blocks levels. No approval or fill is
inferred. `entry_price_issues` reports prices above ceiling, at/below stop and dates
before D+2. Passing these necessary checks is not execution simulation; actual order
cutoffs, intraday times, fill ordering and gap/OHLC ambiguity remain Prompt 6 work.

Ordinary fast<=slow creates an ExitIntent, independent of regime/monthly entry gates.
It persists on recovery and UNKNOWN until an available, matching explicit resolution.
A later invalid session after resolution can create a new intent. Initial evaluation
observes the current condition; it does not invent pre-initialization holdings or exits.
This is a signal intent only; the future portfolio consumer determines whether a
position exists. Protective exits are a separate runtime obligation. Neither regime
nor monthly disagreement liquidates positions or suppresses reconciliation.

## Review and limitations

Full replay is intentionally conservative and unbenchmarked for production. No
approval persistence, simulator, fees, sizing, ranking, portfolio accounting, orders,
research, holdout access, or automatic promotion. Real manifest remains UNSEALED.
Python immutable records do not authenticate external evidence or enforce deployment
permissions. A full-snapshot config pin must match each supplied snapshot; deployments
needing distinct pinned stock/benchmark datasets need a separately specified binding.

Run `PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p test_strategy.py -q`,
then `PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -q` and
`git diff --check`. Independent review is required before closure or Prompt 6.
