"""Conservative whole-share sizing using fixed policies and explicit cost functions."""
from dataclasses import dataclass
from decimal import Decimal as D
from fractions import Fraction as F
from config import RiskConfig
from execution_engine import exact, require

@dataclass(frozen=True, slots=True)
class Commitment:
    order_id: str
    instrument: str
    exposure: D
    risk: D
    reservation: D

@dataclass(frozen=True, slots=True)
class RiskResult:
    quantity: int
    reasons: tuple[str, ...]
    planned_risk: D | None
    operational_authorized: bool = False


def assess_quantity(quantity, instrument, low, high, stop, equity, buying_power, gross,
                    held_instruments, positions, commitments, costs, allowance, at, policy=None):
    policy=policy or RiskConfig(); policy.validate(); reasons=[]
    require(type(quantity) is int and quantity>0,'positive whole shares required')
    require(0<stop<low<=high and equity>0 and min(buying_power,gross,allowance)>=0,'invalid risk inputs')
    for p in positions: reasons.extend(p.issues(at))
    if len(positions)!=len(held_instruments): reasons.append('missing held-position risk')
    if all(p.current_mark is not None for p in positions):
        if F(gross)!=sum((F(p.current_mark)*p.remaining_quantity for p in positions),F(0)):
            reasons.append('gross exposure mismatch')
    require(len({p.position_id for p in positions})==len(positions),'duplicate position risks')
    require(len({c.order_id for c in commitments})==len(commitments),'duplicate commitments')
    require(all(min(c.exposure,c.risk,c.reservation)>=0 for c in commitments),'negative commitment')
    occupied=set(held_instruments)|{c.instrument for c in commitments}
    if instrument in occupied: reasons.append('pyramiding')
    if len(occupied)>=policy.max_positions: reasons.append('position slots')
    # costs(q) is an exact conservative bound over the supplied admissible price range.
    fee=costs(quantity)
    require(fee is not None and fee>=0,'unknown cost bound')
    risk=quantity*(F(high)-F(stop))+F(fee)+F(allowance)
    pending=sum((F(c.risk) for c in commitments),F(0))
    existing=sum((F(p.r_position) for p in positions if p.r_position is not None),F(0))
    exposure=quantity*F(high)
    if risk>F(equity)*F(policy.trade_risk): reasons.append('trade risk')
    if existing+pending+risk>F(equity)*F(policy.total_stop_risk): reasons.append('aggregate risk')
    if exposure>F(equity)*F(policy.stock_allocation): reasons.append('stock allocation')
    if F(gross)+sum((F(c.exposure) for c in commitments),F(0))+exposure>F(equity)*F(policy.gross_exposure): reasons.append('gross exposure')
    if exposure+F(fee)>F(buying_power): reasons.append('settled buying power')
    return RiskResult(0 if reasons else quantity,tuple(sorted(set(reasons))),exact(risk))


def size(instrument,low,high,stop,equity,buying_power,gross,held_instruments,positions,
         commitments,costs,allowance,at,policy=None):
    """Exhaustive finite scan supports nonlinear/fixed/minimum cost bounds without monotonicity assumptions."""
    if equity<=0 or buying_power<=0 or high<=0: return RiskResult(0,('no affordable shares',),None)
    upper=int(min(F(buying_power)/F(high),F(equity)/F(high)))
    last=RiskResult(0,('no affordable shares',),None)
    for q in range(upper,0,-1):
        from config import ConfigError
        try:
            last=assess_quantity(q,instrument,low,high,stop,equity,buying_power,gross,held_instruments,
                                 positions,commitments,costs,allowance,at,policy)
        except ConfigError as e:
            return RiskResult(0,(str(e),),None)
        if last.quantity: return last
    return last
