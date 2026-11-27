# Development evidence register · 24 November 2026

**Decision: insufficient evidence to request an A/B outcome run.** Collection was limited
to public documentation and project metadata. No subscription, agreement acceptance,
provider selection or entitlement was recorded. No licensed data or credentials belong in Git.

## Primary sources consulted

Retrieval date for every entry: 2026-11-24 (India). Use in this register: source
reference and factual summary only. Project rights to download, retain, process,
share or redistribute the underlying datasets are **unverified for every entry**.
Mutable webpages have no pinned edition or established historical coverage here.
PDF references below identify the publisher's version, circular or dated filename;
no claim is made about a cryptographic pin for a remotely indexed document.

| Source and edition | Period supported | Claim supported and limit |
|---|---|---|
| [NSE data sharing and usage policy](https://www.nseindia.com/static/market-data/nse-data-policy), web policy | Retrieved edition; prior regimes unresolved | Subscriber agreement defines the applicable use. Obtain the actual agreement and project entitlement from the owner. |
| [NSE research data categories](https://nsearchives.nseindia.com/web/sites/default/files/inline-files/Data%20list%20under%20NSE%20Data%20Sharing%20Policy%20for%20Research%20and%20Analysis_20250728.pdf), filename 20250728 | Catalogue only; delivered dates unknown | Lists EOD securities/trade data, corporate actions and historical security masters. Request an immutable equity extract's coverage metadata, stable identifiers and delisting/symbol-change history. |
| [NSE Data & Analytics historical order/trade layout](https://nsearchives.nseindia.com/web/sites/default/files/inline-files/Hist_Order_data_layout_1.13.pdf), file version 1.13 | Layout-specific; applicability to a delivered snapshot unknown | Provisional delivery timings can slip. Require original publication/receipt times, timezone, revision IDs and subsequent publication times. An EOD date or download today cannot supply these facts. |
| [NSE Indices constituent data offering](https://www.niftyindices.com/offerings/data-subscription) and [NIFTY FAQ](https://www.niftyindices.com/resources/index-concepts/faqs), web editions | Historical products described; our entitlement, OHLC field coverage and interval unknown | The provider offers historical index data and constituent identifiers. Request actual daily OHLC for the NIFTY 50 price index, series identity, and dated membership additions/removals with announcement and effective dates. No ETF or current roster substitution. |
| [NSE equity report catalogue](https://betanseapi.nseindia.com/all-reports), field description | Current catalogue only | The adjusted 52-week high/low fields include action adjustments. This does not certify raw daily OHLCV. Require the delivered dictionary, raw-price/share-volume basis and a complete action/vintage file (including splits, bonuses, rights, mergers, suspensions). Unsupported conversions must block affected processing. |
| [NSE/MSD/60677](https://nsearchives.nseindia.com/content/circulars/MSD60677.pdf), dated 2024-02-14 | Special session 2024-03-02 only | The circular schedules Saturday capital-market trading in segments. Obtain all dated NSE cash calendars, amendments, exceptional sessions, and actual closes across the study before marking calendar coverage verified. |
| [NSE Clearing cash-market settlement cycle](https://www.nseclearing.in/clearing-settlement/capital-market/settlement-cycle), web edition | Current description; monthly schedules separately issued | Describes rolling settlement, holidays and settlement types including T+0. Request applicable historical segment schedules, exceptions and broker cash-availability evidence. |
| [Zerodha stop-loss order documentation](https://support.zerodha.com/category/trading-and-markets/charts-and-orders/order/articles/what-are-stop-loss-orders-and-how-to-use-them), web edition | Illustrative broker only; historical availability unknown | Distinguishes stop-limit and stop-market. Trigger alone cannot evidence a fill. Obtain selected broker's dated delivery-order capabilities, cutoff and protective activation semantics. |
| [Zerodha charges](https://zerodha.com/charges/) and [bulletin 391488](https://zerodha.com/marketintel/bulletin/391488/revision-in-transactions-charges-from-1st-october-2024) | Current tariff example; bulletin identifies change effective 2024-10-01, supersession unresolved | Brokerage, transaction charges, STT, GST, SEBI, stamp and applicable depository charges need separate treatment. The dated change illustrates the need for complete tariff versions. Obtain side, basis, scope, rounding, taxes and effective dates for the chosen account. |

## Dataset verification and decisions

Owner/project metadata inspected: config.example.json and research_manifest.json at primary
e18e4e81bdddbaf59aaee5b317c31661b651b61e, plus the published readiness inventory and
handoff. The supplied project instructions, phase prompts and legacy code supply no
custodian delivery receipt. Manifest file SHA-256 is
4d7779877353c75a9a31f5a152e23cdf7386da132b3e97626770bd96dddb37b7; this identifies
the empty template. No real snapshot ID/hash, provider release, partition digest,
usable date range, signed entitlement or verified market-row evidence was supplied.

All four real profiles have unknown historical start/end, no approved version/content
pin and no supplied reviewer approval, expiry policy, current validity or revocation receipt.
Each remains UNVERIFIED. No verified profile was constructed from a webpage.

| Profile | Smallest next artifact or owner decision |
|---|---|
| BROKER | Owner names intended broker, account type and research cash. Obtain versioned NSE cash-delivery cutoff, protection, order and settlement documentation for the selected period. |
| FEES | Custodian supplies itemized dated tariff and tax schedules with effective boundaries, including depository charges and rounding. Bind the fee assumptions to those sources. |
| SLIPPAGE | Supply a documented, dated research assumption with applicable instruments, order conditions and point-in-time execution evidence or explicitly retrospective justification. No bps inferred. |
| ADVERSE_EXECUTION | Supply a separately justified adverse allowance, units, applicable window and treatment of remaining costs. Gap exposure remains open. |

For each profile obtain approving reviewers, purpose, version/hash, evidence availability
time, validity mode and evidence of current revocations at the actual authorization time.
Approval for software engineering grants none of these. Keep originals and licensed
artifacts outside Git; record authorized references/digests only.

## Coverage and operator sequence

Let S and E be the independently evidenced inclusive first date and exclusive last date
of the common equity/index, calendar, identity, actions and profile coverage. Both are
unresolved. The manifest contract requires development [S,H) and holdout [H,E), where
H is E minus 12 calendar months using the existing month-end rule. Reject insufficient
development coverage. No official product launch date or synthetic date supplies S or E.

Pin the initialization start within development, before any scored fold. EMA200 needs
200 completed benchmark sessions; its ten-interval slope needs 210, and initial regime
confirmation needs a second consecutive qualifying session (earliest 211). Cover Wilder
seeds, the preceding 63 ATR values and the nonoverlapping 63+20 returns, stock daily
EMA9/21 including the previous observation for a crossover, prior ATR for stops, complete
weekly periods and the prior completed month with a seeded daily benchmark EMA200.
Closures, missing observations, unknowns and delayed releases can extend warmup.
Warmup has no scored outcomes. Keep one initialization history for both candidates.

1. Owner identifies the proposed data supplier and licensed research use. Request a
   metadata-only coverage and vintage inventory for the aligned equity and benchmark histories.
2. Custodian independently partitions development and holdout. Supply the dataset pin,
   development-only object catalogue and pin, sourced calendar, action, identity and membership
   history. Demonstrate OS/storage isolation including retries and warmup. The development
   identity must have no ability to read the holdout. Never hash a mixed dataset in this reader.
3. Obtain the profile evidence above. Agree exact boundaries and separate sealing approval.
   A real decoder, benchmark volume convention, storage capability and authorization evidence
   still need independent review against the delivered format.
4. Freeze A and B, identical folds, costs, initial account, risk policy, and trial audit.
   Seek separate authorization for that exact development-only comparison after all gates pass.
   The final one-time holdout evaluation remains pending.
