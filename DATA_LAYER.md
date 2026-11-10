# Prompt 3 data layer v1 — approved Prompt 3 release

Baseline: chinmaymr37/Trading-bot main at
8af831aa8e0da840671fa9e1dbb9975953a1cec7. Python 3.12+, standard library only.
No dependencies to install. This is offline data engineering, not research or
operational approval. Real providers and production NSE calendar coverage remain
UNVERIFIED. All accepted Snapshot/DailyBar/ExchangeCalendar origins are SYNTHETIC.
A caller labelling actual data synthetic would violate this boundary; Python
contracts cannot establish the authenticity of upstream claims or filesystem ACLs.

## Interfaces and validation

- `data_records.py`: immutable daily, identity, action, universe and calendar
  records; `Snapshot`, deterministic `digest`, `calendar_as_of`.
- `data_validator.py`: `validate_daily` preserves invalid finite OHLC facts and
  reports rejection reasons; structural/type/nonfinite failures raise ConfigError.
  `batch_issues` checks stream ordering, duplicates and conflicting revisions.
  `daily_as_of` returns `(valid_visible_bars, QualityResult)`; a REJECTED result is
  not a complete dataset. Callers must inspect status/reasons, not just the bars.
  `universe_as_of` requires dated available membership; no current roster fallback.
- `data_fetcher.py`: `DailyProvider` protocol, `FixtureProvider`, explicitly blocked
  `UnverifiedProvider`, `fetch_daily`, `ingest_ordered_fixture`, `completed_candle`,
  `split_adjusted_view`, `snapshot_metadata`, `authorize_actual_research`.
  Fetching returns raw immutable records; validated queries are authoritative.
  `fetch_daily` consumes an existing validated BotConfig and enforces any supplied
  provider/version/calendar/snapshot/universe pins without changing configuration.
- `data_cache.py`: `LocalCache.put/get` stores canonical immutable JSON by SHA-256;
  CacheRead keeps retrieval time outside the snapshot content hash.

Prices are positive raw tradable prices; volumes are nonnegative RAW_SHARES.
Adjusted views are separately typed, NONTRADABLE and never enter raw candle
aggregation. No forward fill, fabricated bars or missing-to-holiday conversion.
Daily session completion is the final close of every segment on one trading date.
Segment bars are not accepted as separate daily observations. Providers must supply
one consolidated daily record; intraday consolidation is outside this phase.

Input records must include every declared field when decoded with config.from_dict.
Frozen records reuse Prompt 2 strict type checks and timezone-awareness validation.
Semantically invalid finite bars can be cached for diagnostics; caching is NOT a
validation certificate. Invalid latest revisions never fall back to older prices.
Identical duplicate records also block a query rather than being silently removed.
Snapshot storage canonicalizes set ordering; `ingest_ordered_fixture` additionally
rejects a disordered incoming stream. Cached revisions are never overwritten.

## Time, revisions and completed candles

All windows are [start,end). Session dates use Asia/Kolkata. Instants serialize in
UTC. Daily queries require complete sessions, matching stable identity/symbol,
LISTED status, valid OHLCV and availability <= the decision timestamp. Revisions
are nonnegative provider-assigned integers; visible revisions must have strictly
increasing availability times. Reusing a revision identity blocks affected queries.
Unknown identity, suspension and unavailable history block affected records.
`require_current=True` requires a window ending the day after the decision's exchange
date and the latest completed scheduled session. No arbitrary wall-clock stale-age
threshold is invented. Historical queries do not claim to be current-price quotes.

Calendars explicitly enumerate EVERY date in their coverage, including closures
with reasons. They contain a version, publication availability, evidence label,
and exchange-local session segments. There is no weekday-only production fallback.
Exceptional Saturday sessions and multiple segments are supported. Production
calendar sourcing/approval is deliberately absent, not inferred from test fixtures.
Calendar vintages must be retained. `calendar_as_of` selects only published vintages;
queries pin the selected calendar hash in outputs. Passing a newer, unavailable
calendar to an earlier query fails, rather than silently revising history.

Weekly membership is Monday–Sunday; monthly membership is the calendar month.
The calendar must cover the ENTIRE period even if the data ends earlier. Every
scheduled session must have completed and have a valid, available daily record.
Open/close come from first/last contributing sessions, high/low are extrema,
volume is the exact sum of raw shares. A period can complete at its final scheduled
close if the rest of that period is explicitly closed by the known calendar.
Missing or delayed records block the period. No partial candle query is provided.
Candle availability is the maximum of contributing bar, calendar and identity
availability. Output lineage contains daily hashes, calendar hash and identity hashes.
Daily lineage includes provider/version/revision, basis and evidence.
Raw volumes across splits remain raw reported shares, not split-adjusted units.

## Corporate actions and historical universes

Only split back-adjustment is implemented: for applicable split ratios r,
historical prices divide by product(r), volume multiplies by product(r).
The raw record and its hash are retained. Computation uses 50 significant decimal
digits with ROUND_HALF_EVEN, explicitly independent of caller decimal context.
The date-only action contract uses 00:00 Asia/Kolkata on effective_date, inclusive,
as its precise synthetic effective-time convention. This is NOT an asserted exchange
or broker event time. An action applies only at/after that instant and announcement
(`known_at`).
Evidence availability (`available_at`) is separate: an announced, effective action
without available evidence blocks the affected adjusted view. Late announcements
are not inserted into earlier knowledge. Future effective actions do not adjust
prior as-of views. Conflicting action IDs and unsupported known action types block.
Dividends, mergers, rights issues, total returns, corrections to action histories
and provider-adjusted historical data imports are not implemented.

The synthetic action list does not prove completeness of a real corporate-action
feed. No adjusted output or metadata is certified for unbiased historical validation.
Real point-in-time action coverage/evidence and provider semantics need a separately
approved integration. An empty list is not a claim that a real instrument had no
corporate actions. Historical Universe records have dated intervals and availability;
missing/conflicting membership raises a survivorship-bias limitation. Real universe
coverage remains unavailable. Current constituents are never projected backward.

## Cache and research boundaries

Snapshot hashes include schema, provenance, all revisions, calendar, identities,
actions and universes. Canonical serialization sorts object keys and record sets,
normalizes equivalent decimal strings and UTC instants, and retains session order.
Duplicate records are retained, not erased by hashing. Retrieval timestamps do not
change data hashes. Exclusive cache writes never replace an existing object.
Partial writes, corruption, mismatched keys and noncanonical content fail on read.
Cache miss/offline failure is explicit; no stale or network fallback exists.
Filesystem durability, access control and concurrent-writer coordination beyond
exclusive creation remain deployment concerns. Cache files contain no approval.

Offline synthetic engineering works with the real UNSEALED manifest. No function
here reads holdout files, seals a dataset or authorizes holdout evaluation.
`authorize_actual_research` requires an explicit actual `authorization_at` and
verification-profile records; it forwards them through Prompt 2 authorization.
Future callers must obtain CURRENT approval/revocation records at that cutoff.
The wrapper cannot prove a revocation feed is fresh. Do not use the older helper's
default sealing-time cutoff as present-time permission. Neither signatures nor
Python immutability replace independently enforced deployment isolation.

## Reproduction and review

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p test_data_layer.py -v
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v
git diff --check
```

`tests/test_data_layer.py:fixture` creates every synthetic observation. It covers
2024-01-29 through 2024-03-03 with an invented Feb 2 holiday and a segmented Feb 3
Saturday session. These are NOT assertions about the actual NSE calendar.
Independent weekly expected OHLCV is 100/110/95/107/61. February expected OHLCV is
103/136/98/133/576 (21 synthetic sessions). The volume offsets are independently
3+5+45+80+115+118=366, plus 210 base volume. SYNTHETIC_DATA_REPORT.json records the
fixture hash and query quality. No real dataset snapshot/date was invented.
Self-checks do not replace the required independent review. No indicators, signals,
regime logic, ranking, sizing, portfolio, order simulation or submission was added.

## Focused independent-review corrections

AdjustedView output schema is now 2.0 (incompatible derived-output shape); Snapshot
input/cache schema remains 1.0 because inputs and serialization are unchanged.
Adjusted availability is the maximum of source, calendar, identity, action evidence
and every applied action's effective instant. The view records `as_of`,
`applied_effective_at` and `effective_time_convention`, in addition to action lineage.
A consumer must call `require_as_of(decision)` before using a stored view: it rejects
any different cutoff, including earlier ones. Recompute for a different decision;
availability alone does not describe the adjustment basis of a later view. This is
a supported contract check, not isolation from arbitrary code ignoring the contract.
Raw bars remain unchanged.

Daily queries now reject mixed provider, provider_version, price_basis, volume_basis
or corporate_action_treatment among selected valid, completed, visible records.
Reasons are `incompatible_series_<field>`. Records/lineage remain in the result for
diagnostics; REJECTED results must not enter calculations. No source is preferred,
merged or normalized. Unavailable future revisions do not affect earlier queries.
Higher-timeframe queries consume this same quality gate. The current input schema
also rejects unsupported price/volume/action bases at construction.

Focused regression command:
`PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p test_prompt3_corrections.py -v`
