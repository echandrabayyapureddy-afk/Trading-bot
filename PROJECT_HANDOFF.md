# Phase handoff — Prompt 2 configuration only

Status: implementation and 50 configuration tests complete; awaiting human review.
Do not begin Prompt 3 without authorization. No production settings have been
approved or activated by this deliverable.

## Completed

- Typed, frozen, versioned config records for account/data/timeframes/regime/
  strategy/risk/execution/backtesting/reporting.
- Strict JSON parsing, semantic validation, canonical hashes, provenance catalog,
  structural schemas and signed/pinned read-only approval verification.
- UNSEALED research manifest template; no actual dataset/dates/hash invented.
- Synthetic offline tests; README records commands and trust boundaries.

## Fixed constraints

New project only; no legacy implementation copied. NSE cash long-only delivery
intent; zero leverage; manual approval AND placement; no broker submission API.
0.5% planned risk/trade; 40% stock allocation; 80% gross exposure; 2 positions;
1% aggregate planned risk; 5% review pause and 8% documented hard suspension.
Exits/protection/reconciliation continue during entry pauses. Two completed
daily-session regime confirmation; closed weekly/monthly bars only. Research
cannot automatically change live settings. Hold final twelve historical months
sealed before outcome-guided research and evaluate once at the final gate.

## Open prerequisites

Actual account identity/capital; provider/calendar/universe versions and verified
point-in-time availability; actual snapshot coverage and seal; broker-supported
order types and cutoffs; dated fees/slippage assumptions; ENTRY_TO_STOP versus
MARK_TO_STOP decision. All remain null/false where not known and block readiness.
Live approval keys and trusted pins must reside outside research access; no real
secret or approval receipt is created. The final holdout one-time evaluator and
filesystem/process isolation are deliberately not implemented in configuration.

## Only next bounded task

After review and approval, Prompt 3: new data_fetcher.py, data_validator.py, cache
interfaces, validated daily data and exchange-aware completed weekly/monthly
aggregation with offline tests. Then Prompt 4: regime_detector.py and tests.
No trading/risk/accounting algorithms should be implemented ahead of their phases.

## Carry forward

The complete configuration-phase archive, README, TEST_RESULTS.md and this handoff.
The archive includes a Git bundle for the new project's initial source history.
Source hashes and commit identity are provided in the archive's release inventory.
