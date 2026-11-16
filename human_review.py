"""Durable SYNTHETIC review journal. No execution/account mutations or submission API."""
import json
import sqlite3
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal
from config import Validated, canonical_json, from_dict
from data_records import digest
from execution_engine import require

@dataclass(frozen=True, slots=True)
class ReviewFact(Validated):
    event_id: str
    proposal_id: str
    proposal_json: str
    state: Literal['PROPOSED','REVIEWED','APPROVED','REJECTED','EXPIRED']
    occurred_at: datetime
    notified_at: datetime
    recorded_at: datetime
    actor: str
    evidence: str
    version: Literal['REVIEW-1'] = 'REVIEW-1'
    origin: Literal['SYNTHETIC'] = 'SYNTHETIC'

@dataclass(frozen=True, slots=True)
class ReviewState:
    state: str | None
    issues: tuple[str, ...]
    facts: tuple[ReviewFact, ...]
    operational_authorized: bool = False

class ReviewJournal:
    def __init__(self,path):
        self.db=sqlite3.connect(path,isolation_level=None)
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS reviews(seq INTEGER PRIMARY KEY,payload TEXT NOT NULL,chain TEXT NOT NULL)')
    def close(self): self.db.close()
    def facts(self):
        chain=''; result=[]
        for payload,stored in self.db.execute('SELECT payload,chain FROM reviews ORDER BY seq'):
            chain=digest((chain,payload));require(chain==stored,'review journal corruption')
            result.append(from_dict(ReviewFact,json.loads(payload)))
        return tuple(result)
    def append(self,fact):
        require(type(fact) is ReviewFact,'typed review fact required')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            facts=self.facts()
            if fact not in facts:
                last=self.db.execute('SELECT chain FROM reviews ORDER BY seq DESC LIMIT 1').fetchone()
                payload=canonical_json(fact);chain=digest((last[0] if last else '',payload))
                self.db.execute('INSERT INTO reviews(payload,chain) VALUES (?,?)',(payload,chain))
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK');raise
    def state(self,proposal,at):
        from suitability import Row
        require(type(proposal) is Row,'typed proposal required')
        require(proposal.proposal_id==digest(replace(proposal,proposal_id='UNBOUND')),'proposal hash mismatch')
        expected=canonical_json(proposal); state=None;issues=[];seen={};last=None;visible=[]
        # Global event IDs cannot be reused across proposals. Receipt order is durable order.
        receipt=None
        all_facts=self.facts()
        eligible=[]
        for f in all_facts:
            receipt=max(receipt,f.recorded_at) if receipt else f.recorded_at
            if receipt<=at: eligible.append(f)
        conflicts={f.event_id for f in eligible if len({digest(x) for x in eligible if x.event_id==f.event_id})>1}
        receipt=None
        for f in eligible:
            backdated=receipt is not None and f.recorded_at<receipt
            receipt=max(receipt,f.recorded_at) if receipt else f.recorded_at
            conflict=f.event_id in seen and seen[f.event_id]!=f
            seen[f.event_id]=f
            if f.proposal_id!=proposal.proposal_id: continue
            visible.append(f)
            bad=(conflict or f.event_id in conflicts or backdated or not f.event_id or not f.actor.strip() or not f.evidence.strip() or
                 f.proposal_json!=expected or proposal.status!='BUY-CANDIDATE' or
                 not proposal.at<=f.occurred_at<=f.notified_at<=f.recorded_at or
                 (last is not None and (f.occurred_at<last.occurred_at or f.recorded_at<last.recorded_at)))
            allowed={None:('PROPOSED',),'PROPOSED':('REVIEWED','REJECTED','EXPIRED'),
                     'REVIEWED':('APPROVED','REJECTED','EXPIRED'),'APPROVED':('EXPIRED',),
                     'REJECTED':(),'EXPIRED':()}
            bad=bad or f.state not in allowed[state] or (f.state!='EXPIRED' and f.recorded_at>=proposal.expires_at)
            if bad: issues.append('invalid/conflicting/stale review fact:'+f.event_id);continue
            state=f.state;last=f
        if at>=proposal.expires_at: state='EXPIRED'
        if issues and state=='APPROVED': state='REVIEWED'
        return ReviewState(state,tuple(issues),tuple(visible))


def approval_issues(journal, proposal, current, at):
    """Only review eligibility. Manual submission bridge intentionally unsupported."""
    from suitability import revalidation_issues
    state=journal.state(proposal,at)
    reasons=list(state.issues)+list(revalidation_issues(proposal,current))
    if state.state!='APPROVED': reasons.append('human approval missing or expired')
    if current.at!=at: reasons.append('fresh evaluation required at actual cutoff')
    return tuple(reasons)


def submission_issues(journal,proposal,current,at):
    return approval_issues(journal,proposal,current,at)+('review-to-execution bridge unsupported; no order authorized',)
