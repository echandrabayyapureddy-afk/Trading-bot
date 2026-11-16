"""Append-only synthetic journal, atomic SQLite storage and exact reconstruction."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal as D
from fractions import Fraction as F
from typing import Literal
import sqlite3
import json
from config import Validated, ConfigError, canonical_json, from_dict
from data_records import digest
from execution_engine import exact, require

@dataclass(frozen=True, slots=True)
class Record(Validated):
    event_id: str
    account_id: str
    kind: Literal['DEPOSIT','WITHDRAW','RESERVE','RELEASE','BUY','SELL','SETTLE','CHARGE','ACTUAL_CHARGE','PAY','REFUND','ADJUST','MARK','CLEARANCE']
    occurred_at: datetime
    notified_at: datetime
    recorded_at: datetime
    source: str
    evidence: str
    amount: D
    instrument: str | None = None
    quantity: int = 0
    parent: str | None = None
    series: str | None = None
    valid_until: datetime | None = None
    origin: Literal['SYNTHETIC'] = 'SYNTHETIC'

    def validate(self):
        require(bool(self.event_id and self.account_id and self.source and self.evidence),'journal provenance missing')
        require(self.occurred_at<=self.notified_at<=self.recorded_at,'invalid journal times')
        require(self.quantity>=0 and (self.amount>=0 or self.kind=='ADJUST'),'invalid journal amount')
        if self.kind=='MARK':
            require(self.instrument is not None and self.series is not None and self.amount>0 and
                    self.valid_until is not None and self.recorded_at<self.valid_until,'mark terms missing')
        if self.kind=='CLEARANCE': require(self.parent is not None and self.amount==0,'clearance binding missing')

@dataclass(frozen=True, slots=True)
class Holding:
    instrument: str
    quantity: int
    basis: D
    series: str

@dataclass(frozen=True, slots=True)
class Balance:
    account_id: str
    cash: D
    receivables: tuple[tuple[str,D], ...]
    payables: D
    reservations: tuple[tuple[str,D], ...]
    holdings: tuple[Holding, ...]
    charges: D
    realized: D
    flows: D
    anomalies: tuple[str, ...]
    journal_sha256: str
    @property
    def buying_power(self):
        return exact(F(self.cash)-F(self.payables)-sum((F(v) for _,v in self.reservations),F(0)))


def reconstruct(records, account_id, as_of):
    cash=F(0); payable=F(0); charges=F(0); realized=F(0); flows=F(0)
    held={}; reserves={}; receivables={}; seen={}; accepted={}; adjustments=set(); actual=set(); issues=[]; visible=[]
    charge_due={}; charge_paid={}; refund_keys=set()
    last=None
    for r in records:
        if r.recorded_at>as_of: continue
        visible.append(r)
        if r.event_id in seen:
            if seen[r.event_id]!=r: issues.append(r.event_id+': conflicting identifier')
            continue
        seen[r.event_id]=r
        try:
            require(r.account_id==account_id,'account mismatch')
            require(last is None or r.recorded_at>=last,'out-of-order receipt')
            require(not accepted or r.occurred_at>=max(x.occurred_at for x in accepted.values()),'late accounting mutation requires reconciliation')
            a=F(r.amount); buying=cash-payable-sum(reserves.values(),F(0))
            if r.kind=='DEPOSIT': cash+=a; flows+=a
            elif r.kind=='WITHDRAW':
                require(a<=buying,'withdrawal exceeds buying power'); cash-=a; flows-=a
            elif r.kind=='RESERVE':
                require(a<=buying,'reservation exceeds buying power'); reserves[r.event_id]=a
            elif r.kind=='RELEASE':
                require(r.parent in reserves and a==reserves[r.parent],'release must match live reservation')
                del reserves[r.parent]
            elif r.kind=='BUY':
                require(r.instrument and r.series and r.quantity>0 and r.instrument not in held,'invalid/pyramiding purchase')
                require(a>0,'zero-consideration purchase unsupported')
                require(r.parent in reserves and a<=reserves[r.parent],'purchase reservation missing/insufficient')
                other_reservations=sum((v for key,v in reserves.items() if key!=r.parent),F(0))
                require(a<=cash-payable-other_reservations,'purchase cash insufficient after other commitments')
                held[r.instrument]=Holding(r.instrument,r.quantity,r.amount,r.series)
                cash-=a; del reserves[r.parent]
            elif r.kind=='SELL':
                h=held.get(r.instrument)
                require(h is not None and h.quantity==r.quantity and h.series==r.series,'partial/oversell/series mismatch')
                realized+=a-F(h.basis); del held[r.instrument]; receivables[r.event_id]=a
            elif r.kind=='SETTLE':
                require(r.parent in receivables and a==receivables[r.parent],'settlement receivable mismatch')
                require(r.parent not in refund_keys,'fee refund requires explicit REFUND receipt')
                # Evidence must be constructed by confirmed_settlement, not inferred elapsed days.
                require(r.source.startswith('settlement:'),'settlement rule/confirmation missing')
                cash+=a; del receivables[r.parent]
            elif r.kind=='CHARGE':
                payable+=a; charges+=a
                charge_due[r.event_id]=a; charge_paid[r.event_id]=F(0)
            elif r.kind=='ACTUAL_CHARGE':
                old=accepted.get(r.parent)
                require(old is not None and old.kind=='CHARGE' and r.parent not in actual,'charge adjustment already applied/missing estimate')
                delta=a-F(old.amount)
                due=max(a-charge_paid[r.parent],F(0))
                refund=max(charge_paid[r.parent]-a,F(0))
                payable+=due-charge_due[r.parent]; charge_due[r.parent]=due
                if refund:
                    receivables[r.event_id]=refund; refund_keys.add(r.event_id)
                charges+=delta; actual.add(r.parent)
            elif r.kind=='PAY':
                parent=r.parent
                if parent is None:
                    candidates=[key for key,due in charge_due.items() if due>0]
                    require(len(candidates)==1,'payment attribution missing/ambiguous')
                    parent=candidates[0]
                require(parent in charge_due and a<=charge_due[parent] and
                        a<=cash-sum(reserves.values(),F(0)),'invalid attributed payment')
                cash-=a; payable-=a; charge_due[parent]-=a; charge_paid[parent]+=a
            elif r.kind=='REFUND':
                require(r.parent in refund_keys and r.parent in receivables and
                        a==receivables[r.parent],'refund receipt missing/mismatched/already received')
                cash+=a; del receivables[r.parent]
            elif r.kind=='ADJUST':
                require(r.parent in accepted and r.parent not in adjustments,'adjustment link missing/reused')
                require(accepted[r.parent].kind not in ('CHARGE','ACTUAL_CHARGE','PAY','REFUND','SETTLE'),
                        'fee/payment corrections require attributed workflow')
                require(cash+a>=payable+sum(reserves.values(),F(0)),'adjustment makes cash insolvent')
                cash+=a; realized+=a; adjustments.add(r.parent)
            accepted[r.event_id]=r; last=r.recorded_at
        except ConfigError as e: issues.append(r.event_id+': '+str(e))
    return Balance(account_id,exact(cash),tuple((k,exact(v)) for k,v in sorted(receivables.items())),exact(payable),
        tuple((k,exact(v)) for k,v in sorted(reserves.items())),tuple(held[k] for k in sorted(held)),
        exact(charges),exact(realized-charges),exact(flows),tuple(issues),digest(tuple(visible)))

@dataclass(frozen=True, slots=True)
class SettlementRule(Validated):
    version: str
    available_at: datetime
    effective_start: datetime
    effective_end: datetime
    calendar_sha256: str
    evidence: str
    origin: Literal['SYNTHETIC'] = 'SYNTHETIC'


def confirmed_settlement(sale, rule, calendar, at, recorded_at, evidence):
    require(bool(rule.version and rule.evidence and evidence),'settlement evidence missing')
    require(rule.available_at<=at and rule.effective_start<=sale.occurred_at<rule.effective_end,'settlement rule unavailable/inapplicable')
    require(digest(calendar)==rule.calendar_sha256 and calendar.available_at<=at,'settlement calendar mismatch')
    from data_records import IST
    from datetime import timedelta
    day=at.astimezone(IST).date()
    require(bool(calendar.sessions(day,day+timedelta(days=1),at)) and sale.occurred_at<=at,'settlement confirmation outside calendar')
    return Record('settle:'+sale.event_id,sale.account_id,'SETTLE',at,recorded_at,recorded_at,
                  'settlement:'+digest(rule),evidence,sale.amount,parent=sale.event_id)

class Journal:
    """SQLite transaction log; no update/delete API. Not tamper-proof deployment storage."""
    def __init__(self,path,account_id):
        self.account_id=account_id
        self.db=sqlite3.connect(path,isolation_level=None)
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS metadata (account TEXT NOT NULL)')
        rows=self.db.execute('SELECT account FROM metadata').fetchall()
        if not rows: self.db.execute('INSERT INTO metadata VALUES (?)',(account_id,))
        else: require(rows==[(account_id,)],'journal account mismatch')
        self.db.execute('CREATE TABLE IF NOT EXISTS journal (seq INTEGER PRIMARY KEY, payload TEXT NOT NULL, chain TEXT NOT NULL)')
    def close(self): self.db.close()
    def records(self):
        result=[]; chain=''
        for payload,stored in self.db.execute('SELECT payload,chain FROM journal ORDER BY seq'):
            chain=digest((chain,payload)); require(chain==stored,'journal corruption')
            result.append(from_dict(Record,json.loads(payload)))
        return tuple(result)
    def append(self,records):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            existing=list(self.records()); chain=self.db.execute('SELECT chain FROM journal ORDER BY seq DESC LIMIT 1').fetchone()
            chain=chain[0] if chain else ''
            for r in records:
                require(type(r) is Record and r.account_id==self.account_id,'invalid journal record/account')
                if r in existing: continue
                require(not existing or r.recorded_at>=existing[-1].recorded_at,'cannot insert historical receipt')
                payload=canonical_json(r); chain=digest((chain,payload))
                self.db.execute('INSERT INTO journal(payload,chain) VALUES (?,?)',(payload,chain)); existing.append(r)
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK'); raise
    def balance(self,at): return reconstruct(self.records(),self.account_id,at)
