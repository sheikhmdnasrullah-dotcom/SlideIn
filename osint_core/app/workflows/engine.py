"""Agentic campaign workflow — autonomous multi-step execution with an
approval checkpoint.

State machine per lead (Redis-backed, survives worker restarts — Celery
`acks_late` re-queues anything that dies mid-step, so the workflow completes
even while the client is offline):

    ENRICHING  --(enrich_lead_task completes)-->  PENDING_APPROVAL
    PENDING_APPROVAL --(founder/client decision)-->  APPROVED | REJECTED

Everything up to PENDING_APPROVAL runs unattended: recon matrix -> entity
graph -> agent cluster -> draft. The draft then waits in the approval queue
(`approval:pending` sorted set) until a human decides. Approved drafts are
ready for the sender/export layer; rejected leads are suppressed.

Keys:
  campaign:{job_id}              hash {name, created_at, total}
  wf:{job_id}:lead:{email}       lead state string
  approval:{email}               hash {state, subject, decided_at, note, job_id}
  approval:pending               sorted set (score=ts) of emails awaiting decision
"""
from __future__ import annotations

import time

import redis

from ..config import settings

STATES = ("ENRICHING", "PENDING_APPROVAL", "APPROVED", "REJECTED")
TTL = 30 * 86400

_client: redis.Redis | None = None


def _conn() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _client


def create_campaign(name: str, job_id: str, total: int) -> None:
    r = _conn()
    r.hset(f"campaign:{job_id}", mapping={
        "name": name, "created_at": str(time.time()), "total": total,
    })
    r.expire(f"campaign:{job_id}", TTL)
    for key in r.hkeys(f"job:{job_id}"):
        if ":" in key and key not in ("status", "total", "done", "failed", "created_at"):
            pass  # per-lead keys created by workers; state init below on enqueue


def init_lead(job_id: str, email: str) -> None:
    r = _conn()
    r.setex(f"wf:{job_id}:lead:{email}", TTL, "ENRICHING")


def mark_pending_approval(email: str, job_id: str | None, draft_subject: str | None) -> None:
    r = _conn()
    pipe = r.pipeline()
    if job_id:
        pipe.setex(f"wf:{job_id}:lead:{email}", TTL, "PENDING_APPROVAL")
    pipe.hset(f"approval:{email}", mapping={
        "state": "PENDING_APPROVAL",
        "subject": draft_subject or "",
        "job_id": job_id or "",
        "decided_at": "",
        "note": "",
    })
    pipe.expire(f"approval:{email}", TTL)
    pipe.zadd("approval:pending", {email: time.time()})
    pipe.execute()


def decide(email: str, action: str, note: str = "") -> dict:
    """action: approve | reject. Idempotent; returns the record."""
    if action not in ("approve", "reject"):
        raise ValueError("action must be 'approve' or 'reject'")
    r = _conn()
    state = "APPROVED" if action == "approve" else "REJECTED"
    pipe = r.pipeline()
    pipe.hset(f"approval:{email}", mapping={
        "state": state, "decided_at": str(time.time()), "note": note,
    })
    pipe.zrem("approval:pending", email)
    job_id = (r.hget(f"approval:{email}", "job_id") or "")
    if job_id:
        pipe.setex(f"wf:{job_id}:lead:{email}", TTL, state)
    pipe.execute()
    return get_record(email)


def get_record(email: str) -> dict:
    r = _conn()
    rec = r.hgetall(f"approval:{email}")
    if not rec:
        raise KeyError(email)
    rec["email"] = email
    rec["pending"] = r.zscore("approval:pending", email) is not None
    return rec


def pending_queue(limit: int = 100) -> list[dict]:
    r = _conn()
    emails = r.zrange("approval:pending", 0, limit - 1)
    out = []
    for e in emails:
        rec = r.hgetall(f"approval:{e}")
        rec["email"] = e
        out.append(rec)
    return out


def campaign_status(job_id: str) -> dict:
    r = _conn()
    meta = r.hgetall(f"campaign:{job_id}") or {}
    job = r.hgetall(f"job:{job_id}") or {}
    lead_states: dict[str, str] = {}
    for key in r.scan_iter(f"wf:{job_id}:lead:*", count=200):
        email = key.split(":lead:", 1)[1]
        lead_states[email] = r.get(key) or "UNKNOWN"
    return {
        "job_id": job_id,
        "name": meta.get("name", ""),
        "job": job,
        "lead_states": lead_states,
        "pending_approval": sum(1 for s in lead_states.values()
                                if s == "PENDING_APPROVAL"),
    }
