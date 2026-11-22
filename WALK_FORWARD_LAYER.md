# Prompt 10 · synthetic walk-forward validation

The operator can freeze a comparison, replay both hypotheses over successive unseen
session windows, and inspect every arm, including cash-only, losing and incomplete
trials. The only accepted inputs are named, generated fixtures. This method tests
chronology and accounting. It supplies no market performance evidence.

## Reproduce the paired fixture

From this checkout, using the project's standard-library Python environment:

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from data_records import encoded
from walk_forward import prepare, run, TrialAudit

study = prepare()
with TemporaryDirectory() as root:
    audit = TrialAudit.create(Path(root) / "research-walk-forward")
    report = run(study, audit, attempt="example")
    print(encoded(report).decode())
```

For durable review, explicitly create a new research directory outside the source
checkout and retain it. Reopen it with `TrialAudit(path)`. The checked-in
`SYNTHETIC_WALK_FORWARD_REPORT.json` contains the default declaration and its report.

## Design frozen before the first outcome

`prepare(Scope(...), folds)` pins a typed frozen study. Its digest binds the
synthetic fixture (all daily revisions, identities, dated membership, index,
calendar, fee rules, funding, costs, tick and scripted opening assumptions), both
configuration digests, Prompt 9 base commit, and a fingerprint of the executing
Python sources. The synthetic declaration clock is the fixture calendar's publication
instant. The report uses timestamps from this simulated clock. Each arm/fold ID
is derived from the whole declaration, its fold and its candidate. A new vintage
changes study IDs even if its newly appended facts are invisible to every decision.

The entire search space is A and B. A uses the weekly swing strategy. B adds
the last completed month's NIFTY 50 close versus the month-end **daily** EMA200.
The selection rule retains both arms. Training initializes the existing signal and
regime histories and checks evidence. Selection continues these histories at each
completed-session cutoff. Neither window fits parameters, scores a winner, or
records test-account outcomes. Fold selection is predetermined even if an arm
subsequently fails. The low-turnover benchmark and diagnostics are not candidates.

| Fold | Warmup | Training | Selection | Unseen test |
|---|---|---|---|---|
| 1 | Jan 1–Nov 10 | Nov 10–12 | Nov 12–13 | Nov 13–18 |
| 2 | Jan 1–Nov 10 | Nov 10–18 | Nov 18–19 | Nov 19–24 |

All dates refer to the generated 2020 exchange calendar in Asia/Kolkata. All
intervals include the start and exclude the end. Boundaries must be trading
sessions (or calendar end for the last exclusive boundary). Calendar closures
and the deliberately exceptional Saturday affect session membership. Warmup
feeds only indicator history from the explicit seed date. Each trading session
from training onwards has a 16:00 decision using the vintage then visible.
A later fold may include a prior test period in its expanding training history.
Each test has a newly funded account. There is no cross-fold compounding,
reuse of an earlier trial's outcome as a label, or forced liquidation at the end.

## Execution and measurement

Both arms use the same one-member dated universe, raw stock and index streams,
calendar, account of 10,000 synthetic currency units and seven-component cost
schedule. The independent opening tape scripts a single two-share manual scenario
on November 17. The planned Friday decision and one-second-later synthetic human
approval require the eligible Friday proposal. Monday provides revalidation.
Submission is ten minutes before Tuesday's open, acknowledgement nine minutes
before it. Prompt 8 evaluates affordability at the open. A separate synthetic
receipt and Prompt 6 acceptance are required for a fill. A blocked open leaves
any pending order and reservation visible. No fill comes from a daily high/low.
No other manual orders or protective activations are scheduled. A confirmed
purchase without activation is explicitly unprotected. An outstanding ordinary
exit for a holding requires independent execution evidence.

Prompt 6 owns account events. Prompt 7 assesses the two whole shares, applies the
declared synthetic fee, reconstructs balances and values raw marks. This layer
records the account digest, cash, charges, buying power, held/protected shares,
pending orders and equity at each measured close. It compares the completed
arms using **B net return minus A net return** for each fold. Metrics are:

- Trade count is the number of applied buy fills. The example ends with an
  open holding. There is no implied round trip or liquidation fee.
- Time in cash is all-cash test closes divided by scheduled test sessions.
  The numerator and denominator are both reported. Intraday time is unmeasured.
- Net return is ending marked unit NAV divided by initial NAV minus one.
  Drawdown is the greatest test-close unit NAV decline from its running peak,
  including initial funding. Exact fractions preserve small fees and losses.
- Cash benchmark return is zero under the declared zero-interest cash convention.
  A separate tradable low-turnover benchmark tape is unavailable. No interval is
  estimated from two short, dependent generated windows.
- Rejected or unresolved execution, a pending order, valuation gaps, or missing
  source evidence withhold metrics. Account observations at ambiguous cutoffs
  describe booked facts only. They cannot establish a terminal account outcome.

For the paired fixture each arm has one buy fill in the first fold. Two shares
at 110 plus the synthetic fee of 1 leave 9,779 cash and 220 of marked shares.
Both arms have two cash closes out of three, a net return of −1/10,000 and
maximum close drawdown of 1/10,000. In the second fold both have three cash
closes out of three. Both paired differences are zero. These numbers are
independently checkable consequences of the fixture.

The read-only 1- and 3-session diagnostics report whether a ready raw daily
regime candidate has persisted for the shadow length. Unknown resets the
streak. Thursday shadow and Friday reference observations expose the already
computed decision and eligibility at those cutoffs. Neither diagnostic trades,
moves an order to a different day, substitutes an incomplete week, or changes
the production two-session rule. These are sensitivity observations, with no
alternative-policy return calculation.

## Audit and failure interpretation

`run(study, audit, attempt)` validates the scope before opening a data adapter or
appending a trial. It verifies the declaration against the generated inputs
and current software, records the study and all planned trials, then appends
STARTED and RESULT for each attempt. COMPLETE, BLOCKED, INCONCLUSIVE and FAILED
are distinct. STARTED without RESULT identifies an interrupted attempt. Reusing
the same label and inputs is idempotent; a fresh label preserves an independent
attempt. A conflicting key fails explicitly and preserves the original bytes.
Reopening verifies receipt keys and payload checksums. A marker, fixed receipt
names, local hard-link support, atomic file installation and directory restrictions separate this journal
from account and human-review stores. Receipts give local reproducibility;
authentication, adversarial storage protection and operational audit retention
require deployment controls.

## Evidence required for actual research

There is no real provider, manifest, holdout, historical file path or broker
input in this API. A later development-data implementation needs separately
approved scope and a sealed, independently pinned snapshot with point-in-time
revisions, calendar history, dated constituents, corporate-action evidence,
and exact development and final 12-calendar-month holdout boundaries. It must
call the existing development-window authorization guard with the **actual**
authorization timestamp, matching configuration, four historically applicable
verification profiles and current approvals/revocations. Missing historical
constituents prevent an unbiased-validation claim. Sealing does not grant
development access to the holdout. Realistic settlement, fees, slippage,
execution evidence and benchmark coverage remain prerequisites for corresponding
claims. The review-to-submission bridge and operational readiness remain blocked.

## Legacy audit

The uploaded legacy `walk_forward.py` was inspected as text only. Its useful
concept is the sequence of chronological training, freezing, unseen evaluation
and per-window reporting. Its training grid chooses a Sharpe winner, its private
strategy and portfolio functions assume execution, and its forced terminal
close and filled-in returns can conceal open exposure or missing observations.
This implementation uses the approved A/B declaration and existing engine
owners. No legacy code was imported, executed or adapted.
