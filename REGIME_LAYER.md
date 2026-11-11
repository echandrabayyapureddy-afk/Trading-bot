# Prompt 4 — approved synthetic daily market regime, output contract 1.0

Local approved Prompt 4 package based on primary main f53204c75dc2b6f1274eb9196a28d4f9211f95f2.
Only regime_detector.py and focused tests implement new behavior. Standard library,
Python 3.12+; no dependencies, downloads, legacy imports, indicators for trade signals,
strategies or performance research. No production readiness or trade authorization.

## Public interface and scope

`replay(snapshot, config, benchmark, initialization_start, decisions)` is a pure
function returning a tuple of immutable validated RegimeResult records. `decisions`
is a chronological tuple of aware datetimes. No external/mutable confirmation state
is accepted. Empty decisions produce an empty tuple; out-of-order/naive decisions
raise ConfigError. `BenchmarkBinding` explicitly binds a stable instrument ID,
provider/version, NIFTY_50 identity, synthetic index-level kind, evidence and its
availability. This is a caller-supplied synthetic identity contract, not proof of
real index authenticity. No stock, ETF or roster is automatically substituted.

Use config.load_config to obtain the existing BotConfig. All regime values come
from config.regime; replay rejects any deviation from the current RegimeConfig
baseline. It does not tune or modify settings, provenance labels, approval hashes
or operational readiness. Provider/version/calendar pins are checked against visible
inputs; a supplied full-snapshot hash must match. Appending to a pinned snapshot
requires a separately bound snapshot; it is intentionally rejected under an old pin.
The fixed preceding-ATR window (63) is the explicit Prompt 4 contract constant:
Prompt 2 does not have a distinct ATR reference-window field. It is not a new option.

`classify(Indicators, RegimeConfig)` is a deterministic classification helper, not
an operational loader. Numeric and state helpers prefixed `_` are internal kernels;
they do not establish data quality or readiness. The supported entry point is replay.

## Basis, chronology and lineage

Only raw, unadjusted SYNTHETIC index-level DailyBar records are supported. The
existing daily contract carries RAW_SHARES volume, unused by this regime layer.
Real index OHLC/volume semantics require a future approved adapter; this phase does
not assert that a real index has tradable shares. AdjustedView inputs are rejected,
so no adjusted-view reuse is supported. Known effective actions affecting this
benchmark history block it rather than silently adjusting prices.

At EACH decision, Prompt 3 daily_as_of selects completed valid daily records using
that cutoff, calendar and identity evidence. Any rejection (even with diagnostic
records), mixed source/version/basis, missing expected session, unavailable benchmark
evidence or bad pin blocks indicator consumption. Holidays and special sessions
follow the explicit calendar. The evaluated date is the latest completed scheduled
session, never the latest conveniently available bar. Missing data is not compressed.
Missing older initialization observations block the entire history; there is no
implicit reseed or tail-only substitution. A caller must explicitly choose and
record any new initialization history.

Select/pin the calendar vintage before replay. An unavailable later calendar is
rejected at earlier cutoffs, not retroactively substituted. Within one replay the
calendar/config/binding are fixed. Keep earlier replay outputs when changing any
of them. Each output includes initialization_start, a history hash over the selected
bar hashes/identity hashes/calendar/binding/config, explicit lineage, and the
previous result hash. The full returned tuple records the decision chain. Future
unavailable revisions do not affect prior selected history or prior results.

Output available_at is conservatively the decision timestamp for the evaluation,
including its confirmation history. All consumed evidence must already be available
then. UNKNOWN diagnostics about unavailable evidence are available at the decision;
they do not claim the missing evidence or any unavailable indicator was available.

## Numerical definitions (zero-based completed-session index t)

Arithmetic uses a fresh Decimal context with 50 significant digits, HALF_EVEN,
standard Decimal exponent bounds/traps. Caller precision/rounding cannot alter it.
Decimal ln and sqrt are used. Nonfinite primitives are rejected by the data contract;
Decimal arithmetic errors yield UNKNOWN, not a safe zero. No threshold tolerance
or rounded display value is used for classification. Expected test values are
independent arithmetic fixtures, not outputs from this implementation.

Let C,H,L be raw close/high/low. Indices count scheduled valid observations from the
explicit initialization start. Baseline N=200, slope lag K=10, ATR/ADX period n=14.

| Measurement | Definition | First valid index |
| --- | --- | --- |
| EMA | E[199]=mean(C[0:200]); E[t]=(2/201)C[t]+(199/201)E[t-1] | 199 (200 bars) |
| Signed slope | (E[t]-E[t-10])/10, index-level points per completed-session interval | 209 (210 bars) |
| True range | max(H[t]-L[t], abs(H[t]-C[t-1]), abs(L[t]-C[t-1])) | 1 |
| +DM / -DM | u=H[t]-H[t-1], d=L[t-1]-L[t]; +DM=u iff u>0 and u>d, otherwise 0; -DM=d iff d>0 and d>u, otherwise 0 | 1 |
| ATR | mean(TR[1:15]) at 14, then (13*ATR[t-1]+TR[t])/14 | 14 (15 bars) |
| Smoothed DM | same SMA initialization and Wilder-average recurrence as TR | 14 |
| DI | 100*smoothed DM / smoothed TR, separately for + and - | 14 |
| DX | 100*abs(+DI - -DI)/(+DI + -DI) | 14 |
| ADX | mean(DX[14:28]) at 27, then (13*ADX[t-1]+DX[t])/14 | 27 (28 bars) |
| ATR reference | mean(ATR[t-63:t]), exactly 63 prior values, excluding ATR[t] | 77 (78 bars) |
| ATR ratio | ATR[t] / ATR reference, only if reference > 0 | 77 if defined |
| Log return | r[t]=ln(C[t]/C[t-1]) | 1 |
| Recent volatility | sample SD of r[t-19] through r[t], 20 returns | 20 (21 bars) |
| Reference volatility | sample SD of r[t-82] through r[t-20], preceding 63 returns | 83 (84 bars) |
| Volatility ratio | recent / reference, only if reference > 0 | 83 if defined |

Sample SD is computed with the equivalent pairwise identity
sqrt(sum(i<j, (r[i]-r[j])^2)/(n*(n-1))); there is no annualization.
This avoids a rounded mean inventing variance in equal values. Before the
logarithmic SD calculation, exactly equal rational ratios of all represented
Decimal closes identify geometric prices and give zero volatility. This is
an exact comparison of recorded prices, not a tolerance that discards small
genuine variation. Decimal logarithms may otherwise round equal returns
differently. A zero reference leaves the ratio unavailable and blocks entries.
The implementation's returns array begins with r[1], so the recent slice for bar t
is returns[t-20:t], and reference is returns[t-83:t-20]. They never overlap.

Implementation conventions where the specification did not fix an edge:
- First bar has no preceding close/DM; TR[0] and DM[0] are unavailable, not H[0]-L[0].
- Equal positive up/down movement produces both DM=0.
- Smoothed TR=0 gives both DI=0 (valid flat zero-range history). DI sum=0 gives DX=0.
  Thus flat ADX=0 is a measurement, not missing warmup.
- Zero ATR or volatility reference makes the ratio unavailable, including 0/0 and
  positive/0. It never becomes zero or an invented infinite spike; entries block.
- EMA slope is signed points/session, not percent, angle or an unscaled difference.
- Insufficient warmup is None per field. No incomplete sample estimates are used.
These conventions are tested and need independent review; they are not new trading
parameters or evidence of profitability.

## Classification, veto and eligibility

An ATR ratio >= configured 2.0 OR volatility ratio >= configured 2.0 establishes
HIGH_RISK candidate and immediate_veto. Volatility equality is explicitly inclusive
in Prompt 2 parameter provenance. ATR equality is a conservative implementation
convention because its comparison was not specified. Independently available
spike evidence has priority even if another indicator has not warmed up.

Without a spike, all required indicator values must exist. Otherwise candidate is
None and status UNKNOWN, never SIDEWAYS. With complete inputs:
- ADX >25 AND C>EMA AND slope>0: TRENDING_UP.
- ADX >25 AND C<EMA AND slope<0: TRENDING_DOWN.
- All other combinations: SIDEWAYS, including equality and conflicting directions.
ADX <20 is sideways; 20..25 is transitional sideways within the same economic label.

Unknown inputs always block entry eligibility and reset current confirmation, even
when partial evidence independently establishes a HIGH_RISK veto. An earlier
confirmed label is stored separately as diagnostic_previous and cannot authorize
entries. Thus a veto need not wait for
confirmed HIGH_RISK, and UNKNOWN never implies permission.

entry_eligible means ONLY: all current inputs valid/defined, current candidate and
confirmed label both TRENDING_UP, no veto or blocking reason. It is a regime-layer
gate, NOT permission to trade. trade_authorized is always False. Portfolio, risk,
broker, individual approval, reconciliation and deployment gates remain separate.
No exits/reconciliation are disabled and no position is liquidated by this layer.

## Confirmation and replay rules

Initial confirmed=None, pending=None, count=0. A new candidate starts count=1; the
same candidate on the next completed exchange session confirms it and clears pending.
An already confirmed candidate clears any pending transition. A different candidate
starts a fresh count=1. Exactly two confirmations are supported. An unknown/rejected
input clears confirmed/pending/count; the old label is retained only in
diagnostic_previous. After ordinary UNKNOWN recovery, two fresh consecutive
completed sessions with the same valid candidate are required before entry
eligibility returns.

Evaluate every intended session explicitly. Skipping an evaluation breaks a pending
sequence; no intermediate candidate is invented. Closures do not count. Repeated
calls for the same session cannot advance confirmation. If a previously UNKNOWN
session later gains valid evidence, that same-session retry still does not count;
the next two sessions can establish a fresh sequence. This conservative convention
avoids retroactive confirmation using late observations.

If newly visible revisions change any already consumed bar or identity lineage,
the current evaluation is rejected with consumed_history_changed_reset_required.
Current confirmation and pending reset; the next chronological session can start
fresh on that history, and the following completed session can confirm it.
This also conservatively resets for identity changes. Do not carry externally
constructed state through a config/calendar/init-history change; replay starts
with fresh state, and fingerprints make different histories distinguishable.

## Tests, limits and review gate

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p test_regime_detector.py -q
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -q
git diff --check
```

Fixtures are synthetic benchmark levels only; their calendars do not claim actual
NSE coverage. No sealed data, outcomes, optimization or strategy code is involved.
The full-series recomputation favors auditability over streaming performance;
large real histories and production throughput are untested and not authorized.
Identity authenticity, real index/provider/calendar integration and deployment
isolation remain UNVERIFIED. No config, manifest or existing data-layer file changed.
Independent review passed 45 focused and 222 complete tests and recommended GO;
the user approved closure on 2026-11-11. Publication to both repositories was subsequently authorized. Prompt 5 still
requires separate authorization. Read the current handoff and test log before further work.
