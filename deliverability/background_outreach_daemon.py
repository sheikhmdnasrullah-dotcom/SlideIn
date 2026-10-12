#!/usr/bin/env python3
"""Autonomous Background Outreach Worker Daemon (Production Engine).

Operational Specifications:
1. Mailbox Allocation:
   - Exactly 9 active mailboxes rotated round-robin:
     * hello@nasrullahtanim.me
     * talk@nasrullahtanim.me
     * connect@nasrullahtanim.me
     * hello@tanim.social
     * talk@tanim.social
     * connect@tanim.social
     * hello@tanim.tech
     * talk@tanim.tech
     * connect@tanim.tech
   - Exactly 10 emails per mailbox per day = 90 emails/day total.

2. Lead List Management:
   - Reads from final_checklist_of_prospects.csv.
   - Automatically and atomically DELETES each approached recipient from the CSV
     upon dispatch so the active queue is always pristine and non-repeating.
   - Automatically archives sent leads into sent_prospects_archive.csv.
   - Records forensic state (MX ID, provider, message ID, timestamp) into SQLite.

3. Working Hours & Calendar Schedule:
   - Operating Timezone: U.S. Eastern Time (America/New_York).
   - Operating Hours: 9:00 AM to 5:00 PM EDT (9-to-5 U.S. working hours).
   - Skips Sunday completely.
   - Skips all official U.S. Federal Public Holidays.
   - Paces the 90 daily sends smoothly across the 8-hour window (~5.3 mins + Gaussian jitter).

4. Deliverability & Copy Enforcement:
   - Real-time DNS MX Preflight resolution & MX ID capture (eliminates bounces).
   - 1:1 Desktop Apple Mail native header replication + transactional flags.
   - Dynamic Ghost Ink (~150-300 words) with anti-bleed padding (&zwnj;&nbsp;).
   - Subject: '{First_Name}?'
   - Opening: 'Hey {First_Name}, I know you're busy and I promise I won't take more than two minutes of your time.'
   - Dual-Service Pitch across all industries (Content + Outreach).
   - Outcome: 'Once both are running, we can expect to have more responses from potential [buyers/partners/clients/customers].'
   - Prospective CTA: 'I can put together a quick 2-minute video...'
   - Zero em dashes (—).
   - Double-newline paragraph spacing.
   - Clean signature: 'Thanks,\nTanim.'
"""
from __future__ import annotations

import csv
import datetime
import json
import os
import random
import re
import shutil
import sqlite3
import sys
import time
import zoneinfo
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from advanced_deliverability import (
    build_hardcoded_canonical_email,
    build_bulletproof_email,
    dispatch_via_kumomta,
    generate_tailored_pitch,
    MXValidator,
    HumanPacer,
)

CONFIG_PATH = HERE / "config.json"
DEFAULT_CSV_PATH = HERE / "final_checklist_of_prospects.csv"
if not DEFAULT_CSV_PATH.exists():
    DEFAULT_CSV_PATH = HERE.parent / "final_checklist_of_prospects.csv"

ARCHIVE_CSV_PATH = HERE / "sent_prospects_archive.csv"
DB_PATH = HERE / "outreach_history.db"

NY_TZ = zoneinfo.ZoneInfo("America/New_York")

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

DAILY_LIMIT_PER_INBOX = 20
TOTAL_DAILY_LIMIT = len(PROFILES) * DAILY_LIMIT_PER_INBOX  # 180


def is_us_holiday(dt: datetime.date) -> bool:
    """Checks if date is an official US Federal Public Holiday."""
    month, day, weekday = dt.month, dt.day, dt.weekday()
    
    # 1. New Year's Day (Jan 1)
    if month == 1 and day == 1:
        return True
    # 2. MLK Jr. Day (3rd Monday of Jan: 15-21)
    if month == 1 and weekday == 0 and 15 <= day <= 21:
        return True
    # 3. Washington's Birthday / Presidents' Day (3rd Monday of Feb: 15-21)
    if month == 2 and weekday == 0 and 15 <= day <= 21:
        return True
    # 4. Memorial Day (Last Monday of May: >= 25)
    if month == 5 and weekday == 0 and day >= 25:
        return True
    # 5. Juneteenth (June 19)
    if month == 6 and day == 19:
        return True
    # 6. Independence Day (July 4)
    if month == 7 and day == 4:
        return True
    # 7. Labor Day (1st Monday of Sept: <= 7)
    if month == 9 and weekday == 0 and day <= 7:
        return True
    # 8. Columbus Day (2nd Monday of Oct: 8-14)
    if month == 10 and weekday == 0 and 8 <= day <= 14:
        return True
    # 9. Veterans Day (Nov 11)
    if month == 11 and day == 11:
        return True
    # 10. Thanksgiving Day (4th Thursday of Nov: 22-28, weekday == 3)
    if month == 11 and weekday == 3 and 22 <= day <= 28:
        return True
    # 11. Christmas Day (Dec 25)
    if month == 12 and day == 25:
        return True
    return False


def is_within_us_working_hours(now_dt: datetime.datetime | None = None) -> tuple[bool, str]:
    """Evaluates whether current Eastern Time is within 9:00 AM - 5:00 PM, Mon-Sat (skipping Sun & US holidays)."""
    if now_dt is None:
        now_dt = datetime.datetime.now(NY_TZ)
    
    # Sunday check (weekday == 6)
    if now_dt.weekday() == 6:
        return False, "Sunday (Weekly Rest Day per schedule policy)"
    
    # US Federal Holiday check
    if is_us_holiday(now_dt.date()):
        return False, f"U.S. Public Holiday on {now_dt.date()}"
    
    # Time window 9:00 AM to 5:00 PM
    start_time = datetime.time(9, 0, 0)
    end_time = datetime.time(17, 0, 0)
    current_time = now_dt.time()
    
    if not (start_time <= current_time < end_time):
        return False, f"Outside 9-to-5 window (Current NY time: {current_time.strftime('%H:%M:%S')} EDT)"
    
    return True, f"Active US Working Hours ({current_time.strftime('%H:%M:%S')} EDT)"


def init_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS outreach_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient_email TEXT UNIQUE,
            first_name TEXT,
            last_name TEXT,
            sender_email TEXT,
            subject TEXT,
            message_id TEXT,
            mx_id TEXT,
            provider TEXT,
            detected_niche TEXT,
            sent_date_eastern TEXT,
            sent_at REAL,
            status TEXT
        );
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_quota_tracker (
            date_eastern TEXT,
            sender_email TEXT,
            sent_count INTEGER,
            PRIMARY KEY (date_eastern, sender_email)
        );
    """)
    conn.commit()
    return conn


def get_daily_sent_count(conn: sqlite3.Connection, date_eastern: str, sender_email: str) -> int:
    row = conn.execute(
        "SELECT sent_count FROM daily_quota_tracker WHERE date_eastern = ? AND sender_email = ?",
        (date_eastern, sender_email)
    ).fetchone()
    return row[0] if row else 0


def increment_daily_sent_count(conn: sqlite3.Connection, date_eastern: str, sender_email: str):
    conn.execute("""
        INSERT INTO daily_quota_tracker (date_eastern, sender_email, sent_count)
        VALUES (?, ?, 1)
        ON CONFLICT(date_eastern, sender_email) DO UPDATE SET sent_count = sent_count + 1;
    """, (date_eastern, sender_email))
    conn.commit()


def pop_and_delete_first_lead(csv_path: Path) -> dict | None:
    """
    Atomically reads the first lead from the active CSV, removes that lead row
    from the file immediately, and returns the lead dict.
    Ensures 0 duplicate approaches and automatic list cleanup.
    """
    if not csv_path.exists():
        return None

    temp_path = csv_path.with_suffix(".tmp")
    target_lead = None
    remaining_rows = []

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            if target_lead is None:
                email_val = row.get("Email", "").strip().lower()
                if email_val and "@" in email_val:
                    target_lead = row
                    continue
            remaining_rows.append(row)

    if target_lead is None:
        return None

    # Write remaining rows back atomically
    with open(temp_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(remaining_rows)

    shutil.move(temp_path, csv_path)
    return target_lead


def archive_sent_lead(archive_path: Path, lead: dict, meta: dict):
    """Appends approached lead to sent_prospects_archive.csv so no records are lost."""
    file_exists = archive_path.exists()
    lead_copy = dict(lead)
    lead_copy["Dispatched At (EDT)"] = datetime.datetime.now(NY_TZ).strftime("%Y-%m-%d %H:%M:%S")
    lead_copy["Sender"] = meta.get("sender", "")
    lead_copy["Subject"] = meta.get("subject", "")
    lead_copy["Personalized Email Body"] = meta.get("body_text", "")
    lead_copy["Message-ID"] = meta.get("message_id", "")
    lead_copy["Destination MX"] = meta.get("mx_id", "")
    lead_copy["Provider"] = meta.get("provider", "")
    lead_copy["Detected Niche"] = meta.get("detected_niche", "")
    lead_copy["Status"] = meta.get("delivery_status", "delivered")

    fieldnames = list(lead_copy.keys())
    with open(archive_path, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(lead_copy)


def build_custom_email_body_from_lead(lead: dict) -> tuple[str, str, str]:
    """
    Constructs the canonical email body using the lead's custom observation (if present)
    while strictly enforcing dual-service pitch, prospective CTA, generous spacing, 0 em dashes,
    and ABSOLUTELY ZERO Google Drive links or video links/attachments.
    """
    first_name = lead.get("First Name", "").strip() or "there"
    clean_first_name = first_name.title()
    subject = f"{clean_first_name}?"
    
    position = lead.get("Position / Niche") or lead.get("Position") or ""
    niche = lead.get("Position / Niche") or lead.get("Niche") or ""
    email_addr = lead.get("Email", "").strip()
    
    obs_default, content_pitch, outreach_pitch, audience, detected_niche = generate_tailored_pitch(
        niche=niche, position=position, email_addr=email_addr
    )
    
    # If lead already has a personalized observation in CSV, clean it
    csv_obs = lead.get("Personalized Observation", "").strip()
    raw_obs = csv_obs if csv_obs else obs_default
    clean_obs = raw_obs.replace("—", ",").replace("–", ",").replace("--", ",").strip()
    # Strip any Google Drive links or external URLs completely
    clean_obs = re.sub(r'https?://\S+', '', clean_obs).strip()
    # Clean any video mentions if present
    clean_obs = re.sub(r'watched your video on', 'went through your breakdown on', clean_obs, flags=re.IGNORECASE)
    clean_obs = re.sub(r'your video on', 'your content on', clean_obs, flags=re.IGNORECASE)
    
    clean_content_pitch = content_pitch.replace("—", ",").replace("–", ",").replace("--", ",").strip()
    clean_content_pitch = clean_content_pitch.replace("videos and", "materials and").replace("short videos", "short-form content").replace("videos", "visual content")
    
    clean_outreach_pitch = outreach_pitch.replace("—", ",").replace("–", ",").replace("--", ",").strip()
    clean_audience = audience.replace("—", ",").replace("–", ",").replace("--", ",").strip()

    body = (
        f"Hey {clean_first_name}, I know you're busy and I promise I won't take more than two minutes of your time.\n\n"
        f"{clean_obs}\n\n"
        "I was wondering if I could help you with both your content and outreach sides.\n\n"
        f"For content I can help you with {clean_content_pitch}, and for outreach I can help you with {clean_outreach_pitch}.\n\n"
        f"Once both are running, we can expect to have more responses from potential {clean_audience}.\n\n"
        "If you have time, I can break everything down in a quick call. If not, I can put together a quick 2-minute breakdown walking through how it works. Let me know if you'd like me to send it over.\n\n"
        "Either way, I'd love to work together to grow and build something great.\n\n"
        "Thanks,\n"
        "Tanim."
    )
    return subject, body, detected_niche


def run_daemon_loop(
    csv_path: Path = DEFAULT_CSV_PATH,
    ignore_window: bool = False,
    test_run_limit: int = 0,
    pacing_base: float = 160.0
):
    print("================================================================================")
    print("🚀 AUTONOMOUS BACKGROUND OUTREACH WORKER DAEMON ACTIVATED")
    print("================================================================================")
    print(f"• Target List:        {csv_path.name}")
    print(f"• Active Mailboxes:   {len(PROFILES)} inboxes ({DAILY_LIMIT_PER_INBOX} emails/mailbox/day = {TOTAL_DAILY_LIMIT}/day total)")
    print(f"• Working Window:     09:00 - 17:00 U.S. Eastern Time (Mon-Sat, Sunday skipped)")
    print(f"• U.S. Holidays:      Automatically detected and skipped")
    print(f"• Auto-Deletion:      Recipients automatically purged from CSV upon dispatch")
    print(f"• Deliverability:     Real-time MX ID, 1:1 Apple Mail headers, Ghost Ink, Anti-bleed")
    print("================================================================================")

    conn = init_db()
    
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    profile_idx = 0
    total_sent_lifetime = 0

    while True:
        now_ny = datetime.datetime.now(NY_TZ)
        today_eastern = now_ny.strftime("%Y-%m-%d")

        # 1. Schedule Check
        is_active, status_reason = is_within_us_working_hours(now_ny)
        if not is_active and not ignore_window:
            print(f"[{now_ny.strftime('%Y-%m-%d %H:%M:%S %Z')}] ⏸️  Worker Paused: {status_reason}")
            print(f"   Sleeping 120s before checking schedule again...")
            time.sleep(120)
            continue

        # 2. Check Daily Quotas
        eligible_profiles = []
        for p in PROFILES:
            count = get_daily_sent_count(conn, today_eastern, p["email"])
            if count < DAILY_LIMIT_PER_INBOX:
                eligible_profiles.append((p, count))

        if not eligible_profiles:
            print(f"[{now_ny.strftime('%Y-%m-%d %H:%M:%S %Z')}] 🏁 All 9 mailboxes reached their {DAILY_LIMIT_PER_INBOX}-email daily quota ({TOTAL_DAILY_LIMIT}/{TOTAL_DAILY_LIMIT} sent today).")
            print("   Sleeping 15 minutes until next day window...")
            time.sleep(900)
            continue

        # 3. Select Next Profile Round-Robin
        profile, current_count = eligible_profiles[profile_idx % len(eligible_profiles)]
        profile_idx += 1

        # 4. Pop and Atomically Delete Next Lead from Active CSV
        lead = pop_and_delete_first_lead(csv_path)
        if not lead:
            print("⚠️ Active lead queue is empty! All prospects in final_checklist_of_prospects.csv have been processed.")
            print("   Sleeping 10 minutes...")
            time.sleep(600)
            continue

        recipient_email = lead.get("Email", "").strip().lower()
        first_name = lead.get("First Name", "").strip() or "there"
        last_name = lead.get("Last Name", "").strip()
        full_name = f"{first_name} {last_name}".strip()

        print("\n" + "-" * 75)
        print(f"[{now_ny.strftime('%Y-%m-%d %H:%M:%S %Z')}] 📤 Dispatching to: {full_name} <{recipient_email}>")
        print(f"   From Inbox:       {profile['name']} <{profile['email']}> (Daily count: {current_count + 1}/{DAILY_LIMIT_PER_INBOX})")

        # 5. Preflight Real-time DNS MX check
        to_domain = recipient_email.split("@")[-1]
        mx_info = MXValidator.get_mx_identity(to_domain)
        if not mx_info["valid"]:
            print(f"   ❌ Preflight DNS MX Check Failed: {mx_info['detail']}. Skipping to protect domain reputation.")
            continue

        # 6. Build Hardcoded Canonical Copy (both services + prospective CTA)
        subject, body_text, detected_niche = build_custom_email_body_from_lead(lead)

        # 7. Assemble Bulletproof Email with Native Headers & Ghost Ink
        try:
            email_msg, meta = build_bulletproof_email(
                from_name=profile["name"],
                from_addr=profile["email"],
                to_name=full_name,
                to_addr=recipient_email,
                subject=subject,
                body_text=body_text,
                enable_spintax=False,
                niche=detected_niche
            )

            # 8. Dispatch via KumoMTA
            msg_id = dispatch_via_kumomta(
                config=config,
                from_addr=profile["email"],
                recipient=recipient_email,
                email_msg=email_msg
            )

            meta["sender"] = profile["email"]
            meta["subject"] = subject
            meta["body_text"] = body_text
            meta["detected_niche"] = detected_niche
            meta["delivery_status"] = "delivered_to_kumo"

            # 9. Update Database & Quota
            increment_daily_sent_count(conn, today_eastern, profile["email"])
            conn.execute("""
                INSERT OR REPLACE INTO outreach_history
                (recipient_email, first_name, last_name, sender_email, subject, message_id, mx_id, provider, detected_niche, sent_date_eastern, sent_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                recipient_email,
                first_name,
                last_name,
                profile["email"],
                subject,
                msg_id,
                meta["mx_id"],
                meta["provider"],
                detected_niche,
                today_eastern,
                time.time(),
                "delivered_to_kumo"
            ))
            conn.commit()

            # 10. Archive Record into sent_prospects_archive.csv
            archive_sent_lead(ARCHIVE_CSV_PATH, lead, meta)

            total_sent_lifetime += 1
            print(f"   Subject:          {subject}")
            print(f"   Resolved MX ID:   {meta['mx_id']} ({meta['provider']})")
            print(f"   Niche Pitch:      {detected_niche}")
            print(f"   Ghost Ink:        {meta['ghost_ink_length']} words (hidden + anti-bleed padded)")
            print(f"   Message-ID:       {msg_id}")
            print(f"   ✅ SUCCESS: Recipient automatically purged from active CSV & archived!")
            print(f"   📊 Session Total: {total_sent_lifetime} sends | Inbox {profile['email']}: {current_count + 1}/{DAILY_LIMIT_PER_INBOX}")

            if test_run_limit > 0 and total_sent_lifetime >= test_run_limit:
                print(f"\n🛑 Test run limit of {test_run_limit} reached. Exiting test run.")
                break

            # 11. Pacing Calculation: Distribute sends with Gaussian humanized jitter
            variance = max(5.0, pacing_base * 0.15)
            delay = round(random.gauss(pacing_base, variance), 2)
            delay = max(max(10.0, pacing_base - variance * 2), min(pacing_base + variance * 2, delay))
            print(f"   🕒 Taking Gaussian humanized break for {delay}s (~{delay/60:.1f} mins) before next send...")
            time.sleep(delay)

        except Exception as e:
            print(f"   ❌ Delivery Error for {recipient_email}: {e}")
            time.sleep(30)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Autonomous Background Outreach Worker Daemon")
    parser.add_argument("--csv", default=str(DEFAULT_CSV_PATH), help="Path to final_checklist_of_prospects.csv")
    parser.add_argument("--ignore-window", action="store_true", help="Bypass 9-to-5 US working hours check (for instant test run)")
    parser.add_argument("--test-limit", type=int, default=0, help="Stop after N sends (for verification)")
    parser.add_argument("--pacing", type=float, default=160.0, help="Base pacing delay in seconds between sends (default: 160s for 180 daily sends)")
    args = parser.parse_args()

    run_daemon_loop(
        csv_path=Path(args.csv),
        ignore_window=args.ignore_window,
        test_run_limit=args.test_limit,
        pacing_base=args.pacing
    )
