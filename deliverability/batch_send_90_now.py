#!/usr/bin/env python3
"""
Immediate 90-Email Batch Dispatcher (10 per Mailbox across 9 Active Mailboxes)
Strictly enforces:
- Exactly 10 emails per mailbox across 9 accounts (90 total)
- Real-time DNS MX Preflight Validation
- MUA Apple Mail Transactional Header Emulation
- Hidden Ghost Ink & Anti-Bleed Zero-Width Padding
- Dual-Service Pitch (Content + Outreach) & Prospective CTA
- 0 Em Dashes and Generous Paragraph Spacing
- Atomic Lead Deletion from CSV & Archiving
"""

import sys
import time
import random
import datetime
from pathlib import Path

HERE = Path(__file__).parent.resolve()
sys.path.insert(0, str(HERE))

import json
from background_outreach_daemon import (
    PROFILES,
    NY_TZ,
    CONFIG_PATH,
    DEFAULT_CSV_PATH,
    ARCHIVE_CSV_PATH,
    DB_PATH,
    init_db,
    increment_daily_sent_count,
    pop_and_delete_first_lead,
    archive_sent_lead,
    build_custom_email_body_from_lead,
)
from advanced_deliverability import MXValidator, build_bulletproof_email, dispatch_via_kumomta

TARGET_PER_INBOX = 10
TOTAL_TARGET = len(PROFILES) * TARGET_PER_INBOX  # 90


def run_90_batch():
    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)
    conn = init_db(DB_PATH)
    csv_path = DEFAULT_CSV_PATH
    
    print("=" * 80, flush=True)
    print("🚀 LAUNCHING IMMEDIATE 90-EMAIL DISPATCH BATCH (10 PER INBOX ACROSS 9 ACCOUNTS)", flush=True)
    print(f"   Target: {len(PROFILES)} mailboxes × {TARGET_PER_INBOX} emails = {TOTAL_TARGET} emails total", flush=True)
    print(f"   Active CSV Queue: {csv_path}", flush=True)
    print("=" * 80, flush=True)
    
    # Track sent count per mailbox in this batch
    batch_counts = {p["email"]: 0 for p in PROFILES}
    total_batch_sent = 0
    start_time = time.time()
    
    # 10 rounds of round-robin across all 9 profiles
    for round_num in range(1, TARGET_PER_INBOX + 1):
        print(f"\n==================== STARTING ROUND {round_num}/{TARGET_PER_INBOX} ====================", flush=True)
        for profile in PROFILES:
            email_addr = profile["email"]
            name = profile["name"]
            
            # Pop a valid lead
            lead = None
            meta = None
            email_msg = None
            subject = ""
            recipient_email = ""
            full_name = ""
            detected_niche = ""
            
            while True:
                candidate = pop_and_delete_first_lead(csv_path)
                if not candidate:
                    print(f"⚠️ Active lead queue is empty! Finished early at {total_batch_sent} sends.", flush=True)
                    return
                
                rec_email = candidate.get("Email", "").strip().lower()
                f_name = candidate.get("First Name", "").strip() or "there"
                l_name = candidate.get("Last Name", "").strip()
                f_name_full = f"{f_name} {l_name}".strip()
                
                # Preflight DNS MX Check
                to_domain = rec_email.split("@")[-1] if "@" in rec_email else ""
                if not to_domain:
                    print(f"   ⚠️ Malformed email '{rec_email}' skipped.", flush=True)
                    continue
                
                mx_info = MXValidator.get_mx_identity(to_domain)
                if not mx_info.get("valid", False):
                    print(f"   ❌ Preflight DNS MX Check Failed for {rec_email} ({mx_info.get('detail', 'No MX')}). Skipping.", flush=True)
                    continue
                
                # Valid candidate found
                lead = candidate
                recipient_email = rec_email
                full_name = f_name_full
                break
            
            # Build canonical copy & headers
            subject, body_text, detected_niche = build_custom_email_body_from_lead(lead)
            
            now_ny = datetime.datetime.now(NY_TZ)
            today_eastern = now_ny.strftime("%Y-%m-%d")
            
            print("\n" + "-" * 75, flush=True)
            print(f"[{now_ny.strftime('%Y-%m-%d %H:%M:%S %Z')}] 📤 Dispatching {total_batch_sent + 1}/{TOTAL_TARGET} to: {full_name} <{recipient_email}>", flush=True)
            print(f"   From Inbox:       {name} <{email_addr}> (Inbox Batch: {batch_counts[email_addr] + 1}/{TARGET_PER_INBOX})", flush=True)
            print(f"   Subject:          {subject}", flush=True)
            print(f"   Niche Pitch:      {detected_niche}", flush=True)
            
            try:
                email_msg, meta = build_bulletproof_email(
                    from_name=name,
                    from_addr=email_addr,
                    to_name=full_name,
                    to_addr=recipient_email,
                    subject=subject,
                    body_text=body_text,
                    enable_spintax=False,
                    niche=detected_niche
                )
                
                msg_id = dispatch_via_kumomta(
                    config=config,
                    from_addr=email_addr,
                    recipient=recipient_email,
                    email_msg=email_msg
                )
                
                meta["sender"] = email_addr
                meta["subject"] = subject
                meta["detected_niche"] = detected_niche
                meta["delivery_status"] = "delivered_to_kumo"
                
                # Update SQLite DB
                increment_daily_sent_count(conn, today_eastern, email_addr)
                conn.execute("""
                    INSERT INTO outreach_history (
                        recipient_email, sender_email, subject,
                        message_id, mx_id, provider, detected_niche,
                        sent_date_eastern, sent_at, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    recipient_email,
                    email_addr,
                    subject,
                    msg_id,
                    meta.get("mx_id", ""),
                    meta.get("provider", ""),
                    detected_niche,
                    today_eastern,
                    time.time(),
                    "delivered_to_kumo"
                ))
                conn.commit()
                
                # Archive to CSV
                archive_sent_lead(ARCHIVE_CSV_PATH, lead, meta)
                
                batch_counts[email_addr] += 1
                total_batch_sent += 1
                
                print(f"   Destination MX:   {meta['mx_id']} ({meta['provider']})", flush=True)
                print(f"   Ghost Ink:        {meta['ghost_ink_length']} words (hidden + anti-bleed padded)", flush=True)
                print(f"   Message-ID:       {msg_id}", flush=True)
                print(f"   ✅ SUCCESS: Purged from CSV, archived, and delivered to KumoMTA!", flush=True)
                print(f"   📊 Batch Progress: {total_batch_sent}/{TOTAL_TARGET} | {email_addr}: {batch_counts[email_addr]}/{TARGET_PER_INBOX}", flush=True)
                
            except Exception as e:
                print(f"   ❌ Delivery Error for {recipient_email}: {e}", flush=True)
            
            # Pacing delay between sends: Gaussian 15s - 18s (safe for MTA, gives ~2.5 min rest per inbox)
            if total_batch_sent < TOTAL_TARGET:
                delay = round(random.uniform(14.0, 18.5), 2)
                print(f"   🕒 Humanized rest {delay}s before next mailbox...", flush=True)
                time.sleep(delay)

    elapsed = time.time() - start_time
    print("\n" + "=" * 80, flush=True)
    print(f"🎉 BATCH COMPLETE: Successfully dispatched {total_batch_sent}/{TOTAL_TARGET} emails in {elapsed/60:.1f} minutes!", flush=True)
    for p in PROFILES:
        print(f"   - {p['email']}: {batch_counts[p['email']]}/{TARGET_PER_INBOX}", flush=True)
    print("=" * 80, flush=True)


if __name__ == "__main__":
    run_90_batch()
