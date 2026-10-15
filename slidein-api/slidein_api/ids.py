"""Identifier helpers.

Every persisted record gets a typed, unique id so a reference from one
stage to another can never be ambiguous.
"""

from __future__ import annotations

import uuid

PREFIXES = {
    "tenant": "ten",
    "profile": "prof",
    "offer": "off",
    "icp": "icp",
    "prospect": "prosp",
    "evidence": "ev",
    "qualification": "qual",
    "offer_match": "match",
    "draft": "draft",
    "draft_version": "dv",
    "sent": "sent",
    "delivery_event": "dev",
    "conversation": "conv",
    "reply": "rep",
    "suppression": "sup",
    "stage_run": "run",
    "activity": "act",
    "config_version": "cfg",
}


def new_id(kind: str) -> str:
    prefix = PREFIXES.get(kind)
    if prefix is None:
        raise KeyError(f"unknown id kind {kind!r}")
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


def run_key(tenant_id: str, stage: str, subject_id: str) -> str:
    """Idempotency key for a stage run."""
    return f"{tenant_id}:{stage}:{subject_id}"
