"""Continuous monitoring + circuit-breaker tick.

Runs on a schedule (cron / systemd timer on the VPS). Each tick:
   1) re-run seed placement test
   2) re-run DNS/auth audit
   3) pull reputation (Gmail Postmaster / Outlook SNDS / external JSON)
   4) ingest send metrics (bounce/complaint/deferral)
   5) evaluate the circuit breaker and auto-pause if degraded
"""
from __future__ import annotations

import json
import os
from typing import Optional


def compute_seed_inbox_pct(seed_results: list) -> float:
    if not seed_results:
        return 0.0
    passed = sum(1 for r in seed_results if r.passed)
    return round(100.0 * passed / len(seed_results), 2)


def _classify_bounce_rate(events: list) -> tuple[float, float, float]:
    """Compute bounce, complaint, and deferral rates from structured send events."""
    total = max(1, len(events))
    hard_bounces = sum(1 for e in events if e.get("bounce_type") == "hard_bounce")
    soft_bounces = sum(1 for e in events if e.get("bounce_type") == "soft_bounce")
    complaints = sum(1 for e in events if e.get("bounce_type") == "complaint")
    deferrals = sum(1 for e in events if e.get("bounce_type") == "deferred")
    # Count any 'error' or 'bounce' legacy results as bounce if no structured type
    legacy_bounces = sum(1 for e in events if e.get("result") in ("bounce", "error") and not e.get("bounce_type"))
    total_bounce = hard_bounces + soft_bounces + legacy_bounces
    total_complaint = complaints
    total_deferral = deferrals
    return (
        round(100.0 * total_bounce / total, 3),
        round(100.0 * total_complaint / total, 3),
        round(100.0 * total_deferral / total, 3),
    )


def run_tick(config: dict, store, gate, breaker, seed_runner,
             analyzer, dns_audit_fn, reputation_fn) -> dict:
    # 1) seed placement
    eml = config.get("_current_eml")
    seed_results = seed_runner(eml) if eml else []
    seed_pct = compute_seed_inbox_pct(seed_results)

    # 2) DNS / auth audit
    dns_issues = dns_audit_fn(config) if dns_audit_fn else []

    # 3) reputation
    rep = {}
    if reputation_fn:
        rep = reputation_fn(config) or {}

    # 4) send metrics from recent events
    events = store.recent_send_events(limit=1000)
    bounce_rate, complaint_rate, deferral_rate = _classify_bounce_rate(events)

    # 5) latest analyzer grade
    latest_gate = store.latest_gate_decision()
    grade = latest_gate["analyzer_grade"] if latest_gate else "F"

    metrics = {
        "seed_inbox_pct": seed_pct,
        "bounce_rate": bounce_rate,
        "complaint_rate": complaint_rate,
        "deferral_rate": deferral_rate,
        "analyzer_grade": grade,
        "blacklisted": rep.get("blacklisted", False),
        "dns_issues": len(dns_issues),
    }
    store.add_metric(metrics)

    tripped, reason = breaker.evaluate(metrics)
    return {
        "seed_inbox_pct": seed_pct,
        "bounce_rate": bounce_rate,
        "complaint_rate": complaint_rate,
        "deferral_rate": deferral_rate,
        "analyzer_grade": grade,
        "circuit_open": breaker.is_open(),
        "circuit_half_open": breaker.is_half_open(),
        "trip_reason": reason if tripped else "",
        "dns_issues": dns_issues,
        "reputation": rep,
    }
