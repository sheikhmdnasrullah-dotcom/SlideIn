#!/usr/bin/env python3
"""Autonomous Outreach Campaign Worker (Production Engine).

Hardcodes 100% adherence to all deliverability and copy rules:
- Transactional email imitation & 1:1 Desktop Apple Mail native header replication
- Real-time DNS MX Preflight validation & Destination MX ID capture
- Subject strictly: '{First_Name}?'
- Opening line strictly: "Hey {First_Name}, I know you're busy and I promise I won't take more than two minutes of your time."
- Generous paragraph spacing with double newlines
- Tailored service pitch matching recipient's exact domain/niche
- Absolute zero em dashes (—)
- Ghost Ink dynamic conversational reflection (~150-300 words)
- Anti-bleed zero-width preview padding (&zwnj;&nbsp;)
- 9 sender profiles rotated round-robin across all 3 domains
- Gaussian humanized jitter delay
- 10-send milestone checkpoint
- SQLite persistence recording MX ID, provider, and forensic delivery state
"""
from __future__ import annotations

import csv
import json
import os
import random
import sqlite3
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from advanced_deliverability import (
    build_hardcoded_canonical_email,
    build_bulletproof_email,
    send_canonical_bulletproof_outreach,
    MXValidator,
    HumanPacer,
)
from core import state as st
from core.circuit_breaker import BreakerConfig, CircuitBreaker

CONFIG_PATH = HERE / "config.json"
DB_PATH = HERE / "campaign_outreach.db"
STATE_PATH = HERE / "deliverability_state.db"

PROFILES = [
    {"name": "Nasrullah Tanim", "email": "hello@nasrullahtanim.me"},
    {"name": "Nasrullah Tanim", "email": "talk@nasrullahtanim.me"},
    {"name": "Nasrullah Tanim", "email": "connect@nasrullahtanim.me"},
    {"name": "Nasrullah Tanim", "email": "hello@tanim.social"},
    {"name": "Nasrullah Tanim", "email": "talk@tanim.social"},
    {"name": "Nasrullah Tanim", "email": "connect@tanim.social"},
    {"name": "Nasrullah Tanim", "email": "hello@tanim.tech"},
    {"name": "Nasrullah Tanim", "email": "talk@tanim.tech"},
    {"name": "Nasrullah Tanim", "email": "connect@tanim.tech"},
]


def init_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS outreach_sent (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            first_name TEXT,
            last_name TEXT,
            position TEXT,
            csv_source TEXT,
            sender_email TEXT,
            subject TEXT,
            message_id TEXT,
            mx_id TEXT,
            provider TEXT,
            detected_niche TEXT,
            ghost_ink_words INTEGER,
            sent_at REAL,
            status TEXT
        );
    """)
    # Add columns if migrating from old schema
    cursor = conn.execute("PRAGMA table_info(outreach_sent);")
    cols = [r[1] for r in cursor.fetchall()]
    for col, col_type in [("mx_id", "TEXT"), ("provider", "TEXT"), ("detected_niche", "TEXT"), ("ghost_ink_words", "INTEGER")]:
        if col not in cols:
            conn.execute(f"ALTER TABLE outreach_sent ADD COLUMN {col} {col_type};")
    conn.commit()
    return conn


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def is_already_sent(conn: sqlite3.Connection, recipient_email: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM outreach_sent WHERE email = ? AND status = 'delivered_to_kumo'",
        (recipient_email.strip().lower(),)
    ).fetchone()
    return bool(row)


def record_outreach(
    conn: sqlite3.Connection,
    lead: dict,
    sender_email: str,
    subject: str,
    message_id: str,
    mx_id: str = "",
    provider: str = "",
    detected_niche: str = "",
    ghost_ink_words: int = 0,
    status: str = "delivered_to_kumo"
):
    conn.execute("""
        INSERT OR REPLACE INTO outreach_sent 
        (email, first_name, last_name, position, csv_source, sender_email, subject, message_id, mx_id, provider, detected_niche, ghost_ink_words, sent_at, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        lead.get("Email", "").strip().lower(),
        lead.get("First Name", ""),
        lead.get("Last Name", ""),
        lead.get("Position", ""),
        lead.get("csv_source", ""),
        sender_email,
        subject,
        message_id,
        mx_id,
        provider,
        detected_niche,
        ghost_ink_words,
        time.time(),
        status
    ))
    conn.commit()


def load_all_leads(leads_dir: Path) -> list[dict]:
    all_leads = []
    csv_files = ["safe1.csv", "safe2.csv", "safe3.csv"]

    for filename in csv_files:
        filepath = leads_dir / filename
        if not filepath.exists():
            continue
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                email_val = row.get("Email") or row.get("email") or ""
                email_val = email_val.strip()
                if email_val and "@" in email_val:
                    row["Email"] = email_val
                    row["csv_source"] = filename
                    all_leads.append(row)

    print(f"📊 Loaded {len(all_leads)} total leads from safe1.csv, safe2.csv, safe3.csv.")
    return all_leads


def process_lead(
    conn: sqlite3.Connection,
    store: st.Store,
    breaker: CircuitBreaker,
    config: dict,
    lead: dict,
    profile: dict,
) -> dict:
    """Eligibility gate + dispatch for one lead.

    Consults the shared safety core before any send: duplicate check,
    circuit breaker (fail-closed halt), and per-recipient suppression —
    the same checks the approved pipeline path enforces. Returns a status
    dict; only ``sent`` means a dispatch happened.
    """
    recipient = (lead.get("Email") or "").strip().lower()
    first_name = (lead.get("First Name") or "").strip() or "there"
    last_name = (lead.get("Last Name") or "").strip()
    full_name = f"{first_name} {last_name}".strip()

    if not recipient or "@" not in recipient:
        return {"status": "error_invalid_email", "recipient": recipient}

    if is_already_sent(conn, recipient):
        return {"status": "already_sent", "recipient": recipient}

    if breaker.is_open():
        reason = store.get_circuit().get("reason", "circuit open")
        print(f"   🛑 CIRCUIT OPEN ({reason}). Halting campaign.")
        store.record_send_event(
            recipient=recipient, provider="kumomta",
            result="blocked_breaker", detail=f"Circuit open: {reason}",
        )
        return {"status": "blocked_breaker", "recipient": recipient}

    if store.is_suppressed(recipient):
        print(f"   ⚠️ Recipient {recipient} is suppressed. Skipping.")
        store.record_send_event(
            recipient=recipient, provider="kumomta",
            result="skipped_suppressed", detail="Recipient on suppression list",
        )
        return {"status": "skipped_suppressed", "recipient": recipient}

    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] 📤 Preparing Lead: {full_name} <{recipient}> ({lead.get('csv_source')})")
    print(f"   Sender:  {profile['name']} <{profile['email']}>")

    try:
        meta = send_canonical_bulletproof_outreach(
            config=config,
            from_profile=profile,
            lead=lead,
            enable_spintax=False
        )

        record_outreach(
            conn=conn,
            lead=lead,
            sender_email=profile["email"],
            subject=meta["subject"],
            message_id=meta["message_id"],
            mx_id=meta["mx_id"],
            provider=meta["provider"],
            detected_niche=meta["detected_niche"],
            ghost_ink_words=meta["ghost_ink_length"],
            status="delivered_to_kumo"
        )
        store.record_send_event(
            recipient=recipient, provider="kumomta", result="sent",
            detail=f"MsgId: {meta['message_id']} MX: {meta['mx_id']}",
        )

        print(f"   Subject:      {meta['subject']}")
        print(f"   Dest MX ID:   {meta['mx_id']} ({meta['provider']})")
        print(f"   Niche Pitch:  {meta['detected_niche']}")
        print(f"   Ghost Ink:    {meta['ghost_ink_length']} words (multi-client hidden + anti-bleed padded)")
        print(f"   Message-ID:   {meta['message_id']}")
        return {"status": "sent", "recipient": recipient, "meta": meta}

    except Exception as e:
        print(f"   ❌ Delivery halted for {recipient}: {e}")
        record_outreach(
            conn=conn,
            lead=lead,
            sender_email=profile["email"],
            subject=f"{first_name}?",
            message_id="",
            status=f"error: {e}"
        )
        time.sleep(15)
        return {"status": "error", "recipient": recipient, "detail": str(e)}


def run_campaign(batch_limit: int = 10, interactive: bool = False):
    print("================================================================================")
    print("🚀 BULLETPROOF 100% INBOX PLACEMENT OUTREACH ENGINE STARTING")
    print("================================================================================")
    print("• Transactional & 1:1 Desktop Apple Mail native headers enforced")
    print("• Real-time DNS MX Preflight & Destination MX ID resolution active")
    print("• Subject strictly '{First_Name}?' | Opening strictly 'I know you're busy...'")
    print("• Generous double-newline spacing | Niche-custom service pitch | 0 em dashes")
    print("• Dynamic Ghost Ink (~150-300 words) with anti-bleed &zwnj;&nbsp; spacer")
    print("• 9 sender mailboxes rotating round-robin across nasrullahtanim.me, tanim.social, tanim.tech")
    print("================================================================================")

    conn = init_db()
    config = load_config()
    store = st.Store(str(STATE_PATH))
    breaker = CircuitBreaker(store, BreakerConfig())

    leads_dir = HERE / "Leads to Mail"
    if not leads_dir.exists():
        leads_dir = HERE.parent / "Leads to Mail"
    if not leads_dir.exists():
        leads_dir = HERE / "leads"

    leads = load_all_leads(leads_dir)
    profile_idx = 0
    sent_in_batch = 0
    total_sent_session = 0

    for lead in leads:
        # Checkpoint rule: prompt or pause after each batch_limit (10) sends
        if sent_in_batch >= batch_limit:
            print("\n" + "=" * 60)
            print(f"🛑 BATCH CHECKPOINT: Reached {batch_limit} sends.")
            print(f"Total sent this session: {total_sent_session}")
            print("============================================================")
            if interactive:
                resp = input("Proceed with next 10 sends? (Y/n): ").strip().lower()
                if resp not in ["y", "yes", ""]:
                    print("Campaign worker paused at user request.")
                    break
            else:
                print("Automated 10-send safety cycle complete. Pausing for human verification.")
                break
            sent_in_batch = 0

        profile = PROFILES[profile_idx % len(PROFILES)]
        profile_idx += 1

        result = process_lead(conn, store, breaker, config, lead, profile)

        if result["status"] == "blocked_breaker":
            print("Campaign halted: circuit breaker is open.")
            break
        if result["status"] != "sent":
            continue

        sent_in_batch += 1
        total_sent_session += 1
        print(f"   ✅ Successfully Dispatched to KumoMTA! (Batch Count: {sent_in_batch}/{batch_limit}, Session: {total_sent_session})")

        # Humanized Gaussian Jitter Delay (60s to 110s)
        delay = HumanPacer.get_jitter_delay(base_seconds=80, variance=20)
        print(f"   🕒 Humanized Gaussian pacing delay: {delay}s ({delay/60:.1f}m)...")
        time.sleep(delay)

    print("\n================================================================================")
    print(f"🏁 RUN SUMMARY: {total_sent_session} total emails dispatched with 100% bulletproof headers.")
    print("================================================================================")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Autonomous Outreach Campaign Worker")
    parser.add_argument("--batch-limit", type=int, default=10, help="Number of sends before checkpoint pause (default: 10)")
    parser.add_argument("--interactive", action="store_true", help="Prompt user interactively after each batch of 10 sends")
    args = parser.parse_args()

    run_campaign(batch_limit=args.batch_limit, interactive=args.interactive)
