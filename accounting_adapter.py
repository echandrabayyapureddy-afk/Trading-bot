"""Pure accounting projection and computed synthetic Prompt 6 Dependencies adapter.
No second execution engine; only APPLIED execution audit records have effects.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal as D
from fractions import Fraction as F
from typing import Literal
from config import Validated, ConfigError, content_hash
from config_contracts import Evidence, PositionRiskContract
from data_records import digest
from execution_engine import exact, require
from execution_records import DependencyEvidence, REQUIRED_CHECKS
from fee_model import quote
from ledger import Record, reconstruct
from portfolio import value, select_mark, update_nav, nav_hash
from risk_manager import Commitment, assess_quantity

@dataclass(frozen=True, slots=True)
class CostEvidence(Validated):
    available_at: datetime
    valid_until: datetime
    remaining_exit_cost_per_share: D
    adverse_per_share: D
    slippage_per_share: D
    evidence: str
    origin: Literal['SYNTHETIC'] = 'SYNTHETIC'
    def validate(self):
        require(self.available_at<self.valid_until and bool(self.evidence),'cost evidence missing')
        require(min(self.remaining_exit_cost_per_share,self.adverse_per_share,self.slippage_per_share)>=0,'negative cost')


def project(account,funding,account_id):
    """Reconstruct accounting from accepted audit only; export records to Journal.append.
    Funding is one event; synthetic all-or-none fees are booked once per fill.
    """
    records=[Record('funding',account_id,'DEPOSIT',funding.available_at,funding.available_at,
        funding.available_at,'funding',funding.evidence,funding.settled_cash)]
    orders={o.order_id:o for o in account.orders}
    for a in account.audit:
        if a.outcome!='APPLIED' or a.command.event is None: continue
        c=a.command; e=c.event
        require(e.origin=='SIMULATED','actual fact in synthetic projection')
        def record(suffix,kind,amount,**kw):
            return Record(e.event_id+suffix,account_id,kind,e.occurred_at,e.notified_at or e.recorded_at,
                          e.recorded_at,e.event_id,digest(e),amount,**kw)
        if e.kind=='MANUAL_SUBMISSION' and c.role=='BUY':
            records.append(record(':reserve','RESERVE',orders[e.order_id].reservation))
        if e.kind!='FILL': continue
        o=orders[e.order_id]; gross=exact(F(e.price)*e.quantity)
        if c.role=='BUY':
            submission=next(x for x in account.events if x.event_id==e.parent_id)
            records.append(record(':fill','BUY',gross,instrument=c.instrument_id,quantity=e.quantity,
                                  parent=submission.event_id+':reserve',series=c.point.provider+'@'+c.point.provider_version))
        else:
            records.append(record(':fill','SELL',gross,instrument=c.instrument_id,quantity=e.quantity,
                                  series=c.point.provider+'@'+c.point.provider_version))
        records.append(record(':fee','CHARGE',o.fee))
        if c.role=='BUY': records.append(record(':pay','PAY',o.fee,parent=e.event_id+':fee'))
    return tuple(records)

class AccountingDependencies:
    """No caller approval boolean. Recompute valuation, NAV, fees and risk on every call.
    Marks must cover each consumed fill cutoff; missing historical coverage blocks buys.
    Settlement/cash-flow/resumption injection into Prompt 6 is intentionally unsupported.
    """
    def __init__(self,config,funding,account_id,schedule,marks,costs):
        self.config,self.funding,self.account_id=config,funding,account_id
        self.schedule,self.marks,self.costs=schedule,tuple(marks),costs
    def assess(self,account,command,config_sha256):
        at=command.event.occurred_at
        require(config_sha256==content_hash(self.config),'adapter configuration mismatch')
        require(self.costs.available_at<=at<self.costs.valid_until,'cost/allowance evidence unavailable')
        order=next((o for o in account.orders if o.order_id==command.event.order_id),None)
        buying=command.role=='BUY'
        qty=command.event.quantity or (order.quantity if order else 0)
        require(qty>0,'adapter quantity missing')
        if buying:
            levels=order.levels if order else command.signal.opportunity.levels
            price=levels.ceiling
        else:
            # Estimate exit fee on explicit execution price, or frozen stop for submission.
            p=next((p for p in account.positions if p.trade_id==command.trade_id),None)
            require(p is not None,'exit position missing')
            price=command.event.price or p.levels.stop
        turnover=exact(F(price)*qty)
        fees=quote(self.schedule,'BUY' if buying else 'SELL',turnover,at,at,
                   scopes={r.scope:turnover for r in self.schedule.rules})
        # Multi-order scoped fees require a scope accumulator unavailable in Prompt 6.
        require(all(r.scope in ('ORDER','FILL') for r in self.schedule.rules),'cross-order fee scope needs reconciliation adapter')
        if not buying:
            return DependencyEvidence(digest(account),config_sha256,at,digest((self.schedule,self.costs)),False,False,
                REQUIRED_CHECKS,None,fees.total,self.costs.slippage_per_share,())
        try:
            records=project(account,self.funding,self.account_id)
            require(all(r.recorded_at<=at for r in records),'historical accounting cutoff requires reconciliation')
            balance=reconstruct(records,self.account_id,command.recorded_at)
            require(not balance.anomalies and not account.entry_blocks,'reconciliation blocked')
            require(balance.cash==account.settled_cash and
                    exact(sum((F(v) for _,v in balance.receivables),F(0))-F(balance.payables))==account.unsettled_proceeds,
                    'simulation/ledger discrepancy')
            require({h.instrument:h.quantity for h in balance.holdings}=={p.instrument_id:p.quantity for p in account.positions if p.quantity},'holdings discrepancy')
            v=value(balance,self.marks,at); require(not v.issues,'valuation unavailable')
            # Replay NAV at each accepted fill, rather than accepting an external latch flag.
            nav=update_nav(None,value(reconstruct(records[:1],self.account_id,self.funding.available_at),(),self.funding.available_at))
            cutoffs=sorted({r.recorded_at for r in records[1:] if r.kind in ('BUY','SELL')}|{at})
            # Also include every available mark observation to capture intervening drawdowns.
            nav2=update_nav(None,value(reconstruct(records[:1],self.account_id,self.funding.available_at),(),self.funding.available_at))
            for cutoff in sorted(set(cutoffs)|{m.available_at for m in self.marks if self.funding.available_at<=m.available_at<=at}):
                nav2=update_nav(nav2,value(reconstruct(records,self.account_id,cutoff),self.marks,cutoff))
            nav=nav2
            positions=[]
            for p in account.positions:
                if not p.quantity: continue
                m=select_mark(self.marks,p.instrument_id,p.provider+'@'+p.provider_version,at)
                ev=Evidence(m.evidence,digest(m),m.available_at)
                cost=exact(F(self.costs.remaining_exit_cost_per_share)*p.quantity)
                allowance=exact(F(self.costs.adverse_per_share)*p.quantity)
                re=exact(p.quantity*max(F(p.entry_price)-F(p.levels.stop),F(0))+F(cost)+F(allowance))
                rm=exact(p.quantity*max(F(m.price)-F(p.levels.stop),F(0))+F(cost)+F(allowance))
                positions.append(PositionRiskContract(p.trade_id,p.quantity,p.entry_price,m.price,m.at,m.valid_until,ev,
                    p.levels.stop,p.protected_quantity,'EXCHANGE_ACTIVE' if p.exit_state=='ACTIVE' else 'UNKNOWN',
                    p.activation_id,cost,Evidence(self.costs.evidence,digest(self.costs),self.costs.available_at),True,
                    allowance,digest(self.costs),'CONFIRMED',re,rm,max(re,rm)))
            commitments=[]
            for o in account.orders:
                if o.role!='BUY' or o.state!='PENDING' or (order and o.order_id==order.order_id): continue
                risk=exact(o.quantity*(F(o.levels.ceiling)-F(o.levels.stop)+F(self.costs.remaining_exit_cost_per_share)+F(self.costs.adverse_per_share))+F(o.fee))
                commitments.append(Commitment(o.order_id,o.instrument_id,exact(F(o.levels.ceiling)*o.quantity),risk,o.reservation))
            own=order.reservation if order and order.state=='PENDING' else D(0)
            power=exact(F(balance.buying_power)+F(own))
            result=assess_quantity(qty,command.instrument_id,levels.ceiling,levels.ceiling,levels.stop,
                v.equity,power,v.gross,tuple(h.instrument for h in balance.holdings),tuple(positions),tuple(commitments),
                lambda q: exact(F(fees.total)+q*F(self.costs.remaining_exit_cost_per_share)),
                exact(qty*F(self.costs.adverse_per_share)),at,self.config.risk)
            return DependencyEvidence(digest(account),config_sha256,at,digest((balance.journal_sha256,digest(v),nav_hash(nav),fees.profile_sha256,digest(self.costs))),
                result.quantity==qty,nav.latch>0,REQUIRED_CHECKS,balance.cash,fees.total,self.costs.slippage_per_share,tuple(positions))
        except ConfigError:
            return DependencyEvidence(digest(account),config_sha256,at,'SYNTHETIC accounting inputs unresolved',False,True,
                REQUIRED_CHECKS,None,fees.total,self.costs.slippage_per_share,())
