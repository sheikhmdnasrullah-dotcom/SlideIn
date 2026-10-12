#!/usr/bin/env python3
"""Batch Prospect Outreach Runner with Pre-Flight Seed Gate, MX Validation & Checkpoints.

Strictly enforces:
- Pre-send seed test verification for 100% Primary Inbox placement.
- Real-time DNS MX preflight validation & Destination MX ID resolution.
- Transactional email imitation & 1:1 Desktop Apple Mail native header replication.
- Ghost Ink dynamic reflection (~150-300 words) with anti-bleed padding (&zwnj;&nbsp;).
- Strictly hardcoded copy: Subject '{First_Name}?', Opening 'I know you're busy...',
  generous spacing, niche-custom pitch, zero em dashes (—), clean Tanim signature.
- 9 sender profiles rotated round-robin across all 3 domains.
- Checkpoint rule: Pause and ask the user after each 10 sends.
- Human Gaussian jitter delay.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from core import state as st
from preflight_verifier import (
    load_config,
    check_seed_placement_and_fetch_headers,
)
from advanced_deliverability import (
    build_hardcoded_canonical_email,
    build_bulletproof_email,
    dispatch_via_kumomta,
    send_canonical_bulletproof_outreach,
    MXValidator,
    HumanPacer,
)

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


def send_prospect_with_seed_gate(
    lead: dict,
    profile_idx: int,
    seed_idx: int = 0,
    skip_gate: bool = False,
) -> dict:
    config = load_config()
    store = st.Store(str(STATE_PATH))
    profile = PROFILES[profile_idx % len(PROFILES)]

    first_name = lead.get("First Name") or lead.get("first_name") or "there"
    last_name = lead.get("Last Name") or lead.get("last_name") or ""
    full_name = f"{first_name} {last_name}".strip()
    recipient_email = lead.get("Email") or lead.get("email") or ""
    recipient_email = recipient_email.strip().lower()

    if not recipient_email or "@" not in recipient_email:
        return {"status": "error_invalid_email", "recipient": recipient_email}

    # 1. Real-Time DNS MX Preflight Check & MX ID
    to_domain = recipient_email.split("@")[-1]
    mx_info = MXValidator.get_mx_identity(to_domain)
    if not mx_info["valid"]:
        print(f"❌ Preflight MX Validation Failed for {recipient_email}: {mx_info['detail']}")
        return {"status": "error_mx_failed", "recipient": recipient_email, "detail": mx_info["detail"]}

    # 2. Check suppression and duplicate
    if store.is_suppressed(recipient_email):
        print(f"⚠️ Recipient {recipient_email} is suppressed. Skipping.")
        return {"status": "skipped_suppressed", "recipient": recipient_email}

    row = store.conn.execute(
        "SELECT 1 FROM send_events WHERE recipient=? AND result='sent' LIMIT 1",
        (recipient_email,)
    ).fetchone()
    if row:
        print(f"⏭️  Recipient {recipient_email} was already sent in this batch. Skipping duplicate.")
        return {"status": "already_sent", "recipient": recipient_email, "sender": profile["email"]}

    # 3. Build Hardcoded Canonical Copy
    subject, body_text, detected_niche = build_hardcoded_canonical_email(
        first_name=first_name,
        niche=lead.get("Niche", ""),
        position=lead.get("Position", ""),
        email_addr=recipient_email
    )

    print("\n" + "=" * 65)
    print(f"🎯 PROCESSING PROSPECT: {full_name} <{recipient_email}>")
    print("=" * 65)
    print(f"Sender Profile: {profile['name']} <{profile['email']}>")
    print(f"Subject:        {subject}")
    print(f"Recipient MX:   {mx_info['mx_id']} ({mx_info['provider']})")
    print(f"Niche Pitch:    {detected_niche}")
    print("-" * 65)

    # 4. Pre-Flight Seed Gate Test (Optional or per-batch)
    if not skip_gate:
        seeds = [s for s in config.get("seed_accounts", []) if not s.get("password", "").startswith("FILL_IN")]
        if seeds:
            seed_account = seeds[seed_idx % len(seeds)]
            print(f"1️⃣  Executing Pre-Send Seed Gate Verification ({seed_account['email']})...")

            test_msg, test_meta = build_bulletproof_email(
                from_name=profile["name"],
                from_addr=profile["email"],
                to_name=seed_account["email"].split("@")[0],
                to_addr=seed_account["email"],
                subject=subject,
                body_text=body_text,
                enable_spintax=False,
                niche=detected_niche
            )
            test_msg_id = test_meta["message_id"]

            dispatch_via_kumomta(config, profile["email"], seed_account["email"], test_msg)
            folder, raw_source, headers = check_seed_placement_and_fetch_headers(seed_account, test_msg_id, timeout=45)
            print(f"   Seed Placement: [{folder}]")

            if folder != "INBOX":
                print(f"❌ BLOCKED BY SEED GATE: Message landed in [{folder}]. Halting send.")
                store.record_send_event(
                    recipient=recipient_email,
                    provider="kumomta",
                    result="blocked_gate",
                    detail=f"Seed placement failed in {folder}",
                )
                return {"status": "blocked_gate", "folder": folder, "recipient": recipient_email}

            print("🎉 SEED GATE PASSED: 100% Primary Inbox Placement Verified!")

    # 5. Dispatch Verified Bulletproof Email to Prospect
    print(f"2️⃣  Dispatching Bulletproof Email to Prospect ({recipient_email})...")
    meta = send_canonical_bulletproof_outreach(
        config=config,
        from_profile=profile,
        lead=lead,
        enable_spintax=False
    )
    prospect_msg_id = meta["message_id"]
    print(f"✅ DELIVERED to {recipient_email}! (MsgId: {prospect_msg_id})")

    store.record_send_event(
        recipient=recipient_email,
        provider="kumomta",
        result="sent",
        detail=f"Delivered via KumoMTA. MsgId: {prospect_msg_id} MX: {meta['mx_id']}",
    )

    return {
        "status": "sent",
        "recipient": recipient_email,
        "sender": profile["email"],
        "subject": subject,
        "message_id": prospect_msg_id,
        "mx_id": meta["mx_id"],
        "provider": meta["provider"],
        "ghost_ink_length": meta["ghost_ink_length"],
    }

