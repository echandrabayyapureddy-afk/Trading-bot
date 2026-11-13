# NEW NSE bot — Prompt 2 corrected configuration contracts

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
