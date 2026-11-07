# Configuration phase validation

Final command, from `nse_bot_config/`:

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v
```

Actual final suite result: **50 tests, 1.314 seconds, OK**. The earlier suite
contained 46 tests and passed in 1.018 seconds. Four further tests were added for
precision-independent hashing, future-dated approvals and fee-profile effectivity.
The final command exited with code 0. Tests use Python 3.12.14 and only the
standard library; no dependencies were installed.

Coverage includes:

- Fixed risk and market-scope invariants; 5000/10000 capital; invalid amounts.
- All missing JSON keys, unknown fields, duplicate keys, strict numeric/boolean
  types, nonfinite values, versions and nested immutable records.
- 104 parameter provenance entries; canonical hashing and independent candidate
  copies; hash sensitivity without decimal-context rounding.
- Unsealed manifest denial; exact final twelve-calendar-month intervals including
  leap-day convention; overlap/gap/partial-boundary rejection; snapshot/config/
  provider/calendar/universe/fee version mismatches; development-only access.
- Signed approval verification, tampering with both config and adjacent hash,
  wrong/short keys, external version/hash pins, reviewer metadata, future approval,
  missing prerequisites and fee dates in Asia/Kolkata.
- Import without output or files in a clean temporary working directory.

An initial smoke command ran from the parent directory and could not find
`config`; it was rerun from the documented project directory and succeeded.
This was a command working-directory error, not a failed configuration test.

No market data, historical strategy results, live credentials or final holdout
were used. All sealed manifests and approval receipts in tests are synthetic.
Tests do not prove broker behavior, indicator correctness, portfolio accounting,
profitability, dataset truth or a deployed OS permission boundary; those are not
implemented in this phase.
