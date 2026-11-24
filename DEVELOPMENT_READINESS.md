# Development-data readiness · local review candidate

**Release assessed:** Prompt 11, primary commit `5467b53d7a021c517ead15dbc9e96173ea508824`.
**Real development research: BLOCKED.** Run
`PYTHONDONTWRITEBYTECODE=1 python development_readiness.py` from this checkout to reproduce
the inventory. It opens only config.example.json and research_manifest.json.
The inventory lists missing fields and outstanding external evidence. It cannot authorize a study.

## What the release actually supports

ResearchManifest validates [start, end) intervals and an exact final 12-calendar-month partition.
authorize_development_window checks the independently supplied manifest hash, seal, config and
snapshot pins, requested interval, applicable profile versions, values, evidence and approval status.
data_fetcher.authorize_actual_research requires a caller-supplied aware authorization timestamp.
fetch_daily calls a provider's whole-snapshot fetch before inspecting its rows and verifying pins.
It is suitable for engineering fixtures and has no range-confined historical interface.
research_pipeline.execute gates its fixture supplier on a synthetic engineering specification.
walk_forward.prepare/run accept named synthetic fixtures and preserve the declared study and trial audit.

The preparation entry point preview_development_window calls the explicit-time wrapper, verifies
the synthetic loader's independent snapshot ID and hash, and passes the exact immutable window to
its metadata preview method. It has no row-read method. No production provider is attached.
The guard assumes trusted, current inputs. This probe cannot establish the freshness of an external
revocation feed, verify snapshot contents from metadata, or enforce a real provider's storage permissions.

## Current release inventory and required evidence

The manifest has 17 unset or empty fields, including its optional software commit. The configuration
prerequisite checker identifies 20 missing or unverified settings. There are zero pinned profiles.
These are missing inputs. The tested boundary cases showed no defect in the existing guard.

| Area | Evidence or decision required |
|---|---|
| Dataset and seal | Data custodian supplies provider identity/version, permitted use, immutable snapshot ID, content digest, creation time and stable instrument list. Independently pin the sealed manifest digest. Record the exact research config hash and software revision. Obtain separate authorization for sealing. |
| Chronology | Supply snapshot and development start/end and final holdout start/end. Require snapshot start = development start, development end = holdout start and holdout end = snapshot end, with the final 12 calendar months reserved. All six real dates remain unknown. |
| Universe and actions | Supply versioned dated constituent inclusions/exclusions, listing and symbol history, NIFTY 50 identity and coverage, suspensions/delistings, corporate-action terms, effective dates and publication/revision times. Document gaps, raw tradable basis and point-in-time signal adjustments. Block unsupported conversions. |
| Calendar and revisions | Supply sourced NSE calendar versions, session closes including exceptional sessions, original bar availability and subsequent revision receipts. Verify completed weekly/monthly aggregation against those vintages. |
| Account and costs | Owner selects explicit study account and starting cash. Supply historical settlement assumptions, broker cutoff/order capabilities and protective order type, itemized fee source/version/effective dates, slippage and adverse-execution allowance. Unknown costs remain unresolved. |
| Verification and approval | Supply BROKER, FEES, SLIPPAGE and ADVERSE_EXECUTION research-purpose profiles with typed assumptions, evidence, content hashes, historical applicability, documented reviewers and validity/expiry. At the actual authorization instant obtain current revocations from the authoritative custodian. Label retrospective assumptions. |
| Access and study | Separately review a development-only reader with a storage boundary excluding holdout rows, including during warmup. Pin provider metadata independently of the manifest. A real-data runner and storage isolation remain unverified. |

## Synthetic loader observation

The successful test recorded one call for snapshot SYNTHETIC_ONLY (fixture hash of 64 lowercase
'a' characters), [2019-01-01, 2023-01-01), authorization 2024-02-09T00:00:00Z, and the exact
manifest and config digests. The end equals the first excluded holdout date. Every denied case
recorded zero calls. All paths read zero market rows. Those fixture dates and hashes carry no
meaning for the real manifest.

## Operator handoff

Next, assemble the evidence above for metadata review and obtain separate approval for the seal
and restricted integration. Before any real outcomes, freeze the development-only study with
A (weekly baseline) and B (same baseline with the completed month-end snapshot of the daily NIFTY 50
EMA200), identical universe, costs, folds, warmup, account, execution and fixed risk rules.
Bind each candidate configuration to its approved manifest/config pins. Preserve all planned,
failed, blocked and completed trials in the research audit. Obtain separate authorization for
that exact development comparison, and recheck current profile approvals at execution time.
The final holdout requires a distinct one-time owner authorization. Submission remains blocked.
