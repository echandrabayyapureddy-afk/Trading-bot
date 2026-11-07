# NEW NSE bot — configuration phase only

Python 3.12+, standard library only. No installation, downloads, legacy imports,
indicator calculations, strategy execution, broker integration or backtesting.

## Run tests

From this directory:

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v
```

`config.example.json` is a **draft template**, not approved live settings. Actual
capital/account, broker profile, fees, data versions and open-position risk basis
are intentionally unresolved. Loading a draft validates its shape and present
values; `require_ready()` rejects unresolved prerequisites. Missing JSON fields
and unknown fields are always errors, even when Python constructors have defaults.
Dates, hashes and identifiers have not been fabricated. A configured capital
above 10000 is allowed for later growth; positive actual capital is mandatory
before executable recommendations. Unit tests cover 5000 and 10000 explicitly.

`parameter_catalog.json` documents all 104 configuration leaves with POLICY,
BASELINE HYPOTHESIS or EXPERIMENTAL provenance and the reason for each default.
Decimal values in JSON are strings. All nested Python configuration records are
frozen and slotted, and collections are tuples. Serialization creates independent
copies. Changed drafts/candidates have different hashes; they are not live updates.
The structural JSON Schemas assist editing. The Python loader is authoritative
for strict types, fixed policy, cross-field relationships and readiness.

## Fixed policy and experimental defaults

Risk limits are locked to POLICY-1.0.0: 0.5% trade risk, 40% stock allocation,
80% gross exposure, 2 positions, 1% aggregate stop risk, 5%/8% drawdown thresholds,
zero leverage and whole shares. Changing these requires an explicitly reviewed
policy/schema revision, not a research override. Drawdown recovery alone cannot
resume entries, and drawdown does not liquidate holdings. Configuration declares
these contracts; actual NAV, cash, stop and drawdown engines belong to later phases.

The EMA9/21 periods, ADX14, EMA200, ten-session EMA slope, ATR14, 20/63 return
windows, 25/20 ADX levels and 2.0 spikes are baseline hypotheses. Two-session
confirmation is fixed policy. Stop multiplier 2, prior-close ceiling, liquidity
ranking and one-session operator delay are predeclared experimental assumptions,
not optimized or approved for live use by this deliverable.

`risk.open_risk_basis` stays null: ENTRY_TO_STOP versus MARK_TO_STOP still needs
your decision. Fee profiles, supported protective-order type, broker cutoffs,
slippage and execution allowance are required external inputs. Zero is accepted
for an explicitly configured nonnegative allowance, but never substituted for
missing input. Phase 7 will implement dated fee amounts, charging units, rounding
and all statutory/broker/depository components; this phase stores references and
coverage only. No profitability or exact execution result can follow from config.

## Research manifest

`research_manifest.json` is UNSEALED. Every snapshot identifier, date, hash and
instrument list is empty. `software_commit` is null because no data seal exists;
populate it with the actual research release commit if available when sealing.
No actual dataset was loaded and no holdout dates were guessed.

All intervals are [start, end). A seal must exactly partition the snapshot into
development then the final twelve calendar months, with no overlap or gaps.
The holdout ends at the exclusive snapshot end. Subtract one calendar year for
its start, clamping Feb 29 to Feb 28 in a non-leap year. This is a date interval,
not a count of trading sessions; the data/calendar phase must verify its coverage.

`authorize_development_window()` checks readiness, explicit external manifest
hash pin, sealed status, config/dataset/provider/calendar/universe/fee identity,
fee coverage and development-only boundaries. It never reads the dataset and
never authorizes holdout access. The final one-time holdout state machine is NOT
implemented here (Prompt 12). A SEALED JSON label or hash alone does not prove
data truth: future data verification must supply the matching immutable snapshot.

## Approval and research isolation

There is **no save, sign, promote, environment override or automatic fallback API**.
The live loader accepts only a complete configuration plus an externally signed
approval receipt, external expected version/hash and a >=32-byte approval key.
The caller supplies a timezone-aware decision timestamp; future approvals and
fee profiles not effective on that Asia/Kolkata decision date are rejected.
The HMAC-SHA256 signature covers the configuration hash, version, purpose,
timezone-aware approval timestamp and two reviewer identifiers. Recomputing a
changed JSON file's hash does not forge its approval. External version/hash pins
prevent silently accepting another signed version. No real approval receipt or
secret is supplied. Tests use obviously synthetic credentials and receipts.

Operator-controlled tooling must create receipts outside research. Research must
not possess the key, write access to approved configuration/trust pins, or code
deployment permission. Use separate OS identities/read-only mounts or another
enforced boundary when integrated. Python immutability/HMAC verification cannot
protect against code with the same privileges that steals the key, alters the
verifier, forges the external trust inputs or bypasses the API. This package
prevents silent changes through its supported APIs; it does not claim a sandbox.
The future runtime must exclusively use the approved loader and reverify before
starting each decision run. No filesystem permissions were changed in this phase.

## Remaining order

Prompt 2 configuration/tests -> Prompt 3 data/timeframe validation/tests ->
Prompt 4 regime/tests -> Prompt 5 strategy -> Prompt 6 simulator interfaces/tests
-> Prompt 7 fees/risk/portfolio/ledger -> Prompt 8 recommendations/manual states.
No later-phase implementation is included. The optional Prompt 9 does not revive
rejected legacy research engines. Each phase stops for review and approval.
