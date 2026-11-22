"""Closed catalogue of generated, synthetic scenarios for the method demonstration."""
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal as D

from accounting_adapter import CostEvidence
from data_records import (DailyBar, ExchangeCalendar, Identity, IST, Segment,
                          Snapshot, TradingDay, Universe)
from execution_engine import require
from execution_records import Capabilities, Funding, PricePoint
from fee_model import COMPONENTS, FeeRule, FeeSchedule
from regime_detector import BenchmarkBinding
from strategy import TickEvidence

CASES = ('paired', 'gap', 'unresolved', 'missing-mark', 'missing-universe',
         'missing-fees', 'future-revision', 'intervening-revision', 'declining-index')
STOCK = 'SYN-STOCK'
INDEX = 'SYN-N50'
OPEN_DAY = date(2020, 11, 17)


def instant(day, hour):
    return datetime.combine(day, time(hour), IST)


@dataclass(frozen=True, slots=True)
class Fixture:
    case: str
    stock: Snapshot
    index: Snapshot
    binding: BenchmarkBinding
    tick: TickEvidence
    fees: FeeSchedule
    costs: CostEvidence
    cash: Funding
    capabilities: Capabilities
    opening: PricePoint
    quantity: int
    fill_receipt: bool


def build(case):
    require(case in CASES, 'unknown synthetic fixture')
    start, end = date(2020, 1, 1), date(2020, 12, 1)
    known, until = instant(start - timedelta(days=1), 16), instant(end, 16)
    days, stocks, indices = [], [], []
    for i in range((end - start).days):
        day = start + timedelta(days=i)
        opened = (day.weekday() < 5 and day != date(2020, 1, 6)) or day == date(2020, 1, 11)
        segments = (Segment(instant(day, 9), instant(day, 15)),) if opened else ()
        days.append(TradingDay(day, segments, 'synthetic schedule'))
        if opened:
            price = D(500 - len(indices) if case == 'declining-index' else 100 + len(indices))
            bar = DailyBar(INDEX, INDEX, day, instant(day, 15), instant(day, 16),
                           'SYN-provider', 'v1', 0, 'generated index level', price,
                           price + 1, price - 1, price, D(0))
            indices.append(bar)
            price = D(100 if day < date(2020, 11, 9) else 110)
            opening = D(112) if case == 'gap' and day == OPEN_DAY else price
            stocks.append(replace(bar, instrument_id=STOCK, symbol=STOCK, open=opening,
                                  high=max(price, opening) + 1, low=price - 1,
                                  close=price, volume=D(10), evidence='generated cash share'))
    # The base tape ends one session before coverage expires. The future-only
    # variant appends that genuinely new observation as well as a later correction.
    if case != 'future-revision':
        stocks.pop()
    if case in ('future-revision', 'intervening-revision'):
        published = end if case == 'future-revision' else date(2020, 11, 16)
        stocks.append(replace(stocks[0], revision=1, available_at=instant(published, 16),
                              high=stocks[0].high + 1))
    cal = ExchangeCalendar('SYN-calendar-1', known, start, end, tuple(days), 'synthetic only')
    identity = Identity(STOCK, STOCK, start, end, known, 'LISTED', 'generated identity')
    universe = Universe('SYN-members-1', start, end, known, (STOCK,), 'generated dated membership')
    stock = Snapshot(cal, tuple(stocks), (identity,), universes=() if case == 'missing-universe' else (universe,))
    index = Snapshot(cal, tuple(indices), (replace(identity, instrument_id=INDEX, symbol=INDEX),))
    rules = tuple(FeeRule(n, 'BOTH', 'ORDER', D(0), D(int(n == 'brokerage')), D(0),
                          None, D('.01'), 'HALF_UP', (), 'synthetic fixed per order') for n in COMPONENTS)
    fees = FeeSchedule('SYN-fees-1', known, until, known, known, until, 'generated fee assumptions',
                       rules, 'UNVERIFIED' if case == 'missing-fees' else 'VERIFIED')
    at = instant(OPEN_DAY, 9)
    return Fixture(case, stock, index, BenchmarkBinding(INDEX, 'SYN-provider', 'v1', 'synthetic NIFTY 50', known),
                   TickEvidence(STOCK, D('.05'), start, end, known, 'synthetic tick'), fees,
                   CostEvidence(known, until, D(1), D(0), D(0), 'synthetic allowances'),
                   Funding(D(10000), known, 'synthetic settled deposit'),
                   Capabilities('SYN-cap-1', known, until, 'synthetic receipt capabilities', True, True),
                   PricePoint(STOCK, at, at, D(112 if case == 'gap' else 110), 'SYN-provider', 'v1',
                              'independent synthetic opening tape', 'OPENING_ASSUMPTION'),
                   2, case != 'unresolved')
