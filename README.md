# Prompt 9 — approved synthetic research evidence release

Prompt 8 is closed and published. Prompt 9 adds a fixed synthetic evidence pipeline
and separate durable research-attempt store. Read RESEARCH_LAYER.md for boundaries,
legacy dispositions and the offline example. No historical backtest, optimization,
holdout access or automatic promotion is implemented. Submission/live readiness remain
blocked. The user approved Prompt 9 closure following independent re-review. Prompt 10 requires separate authorization.
Earlier phase-status text below is historical.

# Prompt 8 — approved suitability and human review release

Prompt 7 is closed and published. Prompt 8 adds synthetic weekly recommendation
alternatives and an auditable review journal. Read SUITABILITY_LAYER.md for the JSON
report format, operator workflow and blocked submission bridge. Operational readiness
remains blocked. The user approved Prompt 8 closure after independent GO review
and authorized publication to both main branches. Prompt 9 is not authorized.
Earlier phase-status entries below are historical.

# Prompt 7 — approved accounting/risk release

Fees, a durable synthetic journal, portfolio valuation, unitized NAV, whole-share
risk sizing and a computed Prompt 6 dependency adapter are implemented.
Read ACCOUNTING_RISK_LAYER.md and PROJECT_HANDOFF.md for integration limits.
Operational readiness remains blocked; no real tariff or broker is approved.
Prompt 7 closure is approved following independent GO review; publication to both
repositories is authorized. Prompt 8 is not authorized.
Earlier phase status below is historical.

# NEW NSE bot — Prompt 6 approved execution simulator

Prompt 5 is approved and published. Prompt 6 adds a synthetic shared-account
execution simulator with one exit state machine, explicit event timing and fill
assumptions, cash reservations, protection activation, persistent ordinary exits
and unresolved daily-OHLC outcomes. Read EXECUTION_LAYER.md and PROJECT_HANDOFF.md.
The user approved Prompt 6 closure after separate review and authorized publication
to both repositories. Prompt 7 is not authorized.
Operational readiness remains blocked and the actual manifest remains UNSEALED.
Earlier phase descriptions below are historical and do not override this status.

## Prompt 2 corrected configuration contracts

Python 3.12+, standard library only. No installation required.

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v
```

Schema 3.0 / default config 0.3.0 is incompatible with configuration schemas 1.0 and 2.0.
Old documents and approvals are rejected; there is no approval migration.
Configuration objects, contract objects and their nested collections are frozen.
JSON requires every declared field and rejects unknown/duplicate fields. The Python
validators enforce relationships beyond the structural JSON Schemas.

`config.example.json` is a draft, NOT approved operational settings. Account/data/
broker/fee assumptions remain unset. `contracts_schema.json` defines position,
event and verification-profile records; `CONTRACTS.md` describes their semantics.
`parameter_catalog.json` records POLICY / BASELINE HYPOTHESIS / EXPERIMENTAL labels.
`APPROVAL_PROVENANCE.md` records the authority and limits of retained assumptions.

## Operational trust and supported entry points

`readiness_issues`, `require_ready` and `load_approved_live` fail closed because
**operational trust has not been provisioned**. There is deliberately no flag or
caller-supplied key that enables operational mode. Synthetic and research records
cannot make the package live-ready. Provisioning an independently controlled trust
anchor is a future, separately reviewed deployment integration, not this phase.

`verify_signed_config_contract` checks HMAC signatures, two reviewer identifiers,
externally supplied version/hash pins, approval availability and fee effectivity.
It is explicitly NON-AUTHORIZING: its returned config is not a permission token.
Caller-selected keys can establish cryptographic consistency, never real authority.
Tests use this helper to exercise signature/tampering checks without granting live
readiness. Profile approval evidence is similarly a contract, not identity proof.

`research_prerequisite_issues` / `require_research_prerequisites` only check input
completeness. They do not authorize data access, research or operational use.
`authorize_development_window` additionally requires a pinned SEALED manifest,
matching config and data identities, all four RESEARCH-purpose profiles pinned in
config, separate applicability/evidence/approval checks and strictly development-only coverage.
Typed execution assumptions bind profile versions, broker cutoff/order type, fee
source and interval, slippage and adverse allowance to configuration. Narrative
specifications do not prove agreement on numerical assumptions or actual broker behavior.
No supported function authorizes holdout evaluation.

Deployment must deny research write access to live settings, trust pins, verifier
code and approval credentials. The runtime must use only supported operational
entry points. Python immutability and signatures cannot sandbox code with equal OS
privileges. No deployment permission boundary has been installed here.

## Scope and fixed safety policy

Numerical limits unchanged: 0.5% per-trade planned risk, 1% aggregate planned risk,
40% stock allocation, 80% gross exposure, two positions, 5%/8% drawdown gates,
zero leverage and whole shares. Manual approval AND manual placement remain
mandatory; there is no broker submission API. Candidate A/B, completed bars,
monthly close versus same-month-end DAILY EMA200, and two daily-session regime
confirmation remain unchanged. These declare future engine requirements, not a
completed portfolio, ledger, simulator, recommendation or data-processing engine.

## Research and release artifacts

The manifest remains UNSEALED with no invented data or dates. Before outcome-based
research, freeze the actual snapshot and exact final twelve calendar months.
Intervals are [start,end), with the existing Feb-29-to-Feb-28 clamping convention.
Sealing never grants holdout access; the final one-time evaluator remains absent.
No market dataset, performance research or parameter optimization was used.

Files under `artifacts/` are historical schema-1 release archives and are NOT the
corrected schema-3 deliverable. They are retained unchanged for provenance; use the
current source tree. Prompt 2 closure and publication to both named repositories
were authorized following independent review. No new archive was generated.
This paragraph records the Prompt 2 publication state. See PROJECT_HANDOFF.md
for current phase status.

## Prompt 3 — approved release

The offline synthetic data-layer implementation is documented in DATA_LAYER.md.
It adds validation, revision-aware daily queries, completed weekly/monthly candles,
split-only nontradable views and an immutable local cache. Real ingestion/calendar
coverage remain UNVERIFIED; the real manifest remains UNSEALED. See the current
PROJECT_HANDOFF.md section and SYNTHETIC_DATA_REPORT.json. Prompt 3 closure was
approved after independent review; publication to both repositories is authorized.
Prompt 4's approved regime layer and review corrections are documented in
REGIME_LAYER.md. Publication to both repositories is authorized following
independent review and user closure approval. Prompt 5 is not authorized.

## Prompt 4 — approved regime layer

REGIME_LAYER.md documents the new strategy-independent synthetic daily regime
layer. It consumes the existing typed config and validated data contracts, computes
causal regime measurements, separates an immediate severe-risk veto from two-session
confirmation, and emits immutable audit records. Real integration and trading remain
blocked. Independent review passed and Prompt 4 closure was approved. Publication to both
repositories is authorized; Prompt 5 is not authorized.


## Prompt 5 — local strategy review candidate

`strategy.py` implements the minimal daily EMA9/21 strategy with completed-week
crossover selection, daily revalidation, Candidate B monthly context, frozen price
proposals and persistent ordinary exit intents. See STRATEGY_LAYER.md for interfaces
and lifecycle conventions. It consumes validated synthetic data and verified replay
of Prompt 4 regime outputs; it never authorizes an order. The preceding phase-status
paragraphs are historical. Prompt 5 is local pending independent review; no publication
or Prompt 6 is authorized. Fixed settings and the UNSEALED manifest are unchanged.


## Prompt 5 — approved closure and publication

Following the reported independent re-review GO, the user approved Prompt 5 closure
and publication to both repositories on 2026-11-12. This supersedes earlier local-only
status text. The reviewed strategy and exact tick-floor correction are included;
operational readiness remains blocked. Prompt 6 is not authorized.
