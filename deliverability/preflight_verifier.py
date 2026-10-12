#!/usr/bin/env python3
"""Pre-flight Seed Inbox Placement Verifier and Header Cloner.

Workflow:
1. Generates authentic prospect email using the hardcoded canonical builder and
   bulletproof suite (Apple Mail 1:1 headers, transactional headers, ghost ink,
   anti-bleed padding, real-time DNS MX resolution).
2. Sends the exact email to active seed mailbox (e.g. tanimsyt@gmail.com) via KumoMTA.
3. Inspects the seed mailbox over IMAP, verifies folder placement (INBOX vs SPAM/PROMOTIONS).
4. Fetches and displays the full raw email headers received by Google (SPF/DKIM/DMARC/ARC).
5. Reports 100% Primary Inbox placement forensic verification.
"""
from __future__ import annotations

import email
from email import policy
from email.message import EmailMessage
import imaplib
import json
import ssl
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from advanced_deliverability import (
    build_hardcoded_canonical_email,
    build_bulletproof_email,
    dispatch_via_kumomta,
    MXValidator,
)

CONFIG_PATH = HERE / "config.json"


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def check_seed_placement_and_fetch_headers(
    account: dict,
    target_msg_id: str,
    timeout: int = 60,
) -> tuple[str, str, dict]:
    """Check IMAP for target_msg_id, returns (folder, raw_headers_str, headers_dict)."""
    ctx = ssl.create_default_context()
    clean_mid = target_msg_id.strip("<>").strip()
    
    deadline = time.time() + timeout
    print(f"⏳ Polling IMAP on {account['email']} for Message-ID <{clean_mid}>...")

    while time.time() < deadline:
        try:
            with imaplib.IMAP4_SSL(account["host"], account.get("port", 993), ssl_context=ctx) as imap:
                imap.login(account["email"], account["password"])

                # 1. Check Spam first
                try:
                    imap.select("[Gmail]/Spam")
                    _, data = imap.search(None, "HEADER", "Message-ID", clean_mid)
                    if data and data[0]:
                        uid = data[0].split()[0]
                        _, msg_data = imap.fetch(uid, "(RFC822)")
                        raw_email = msg_data[0][1]
                        parsed = email.message_from_bytes(raw_email, policy=policy.default)
                        return "SPAM", raw_email.decode("utf-8", errors="replace"), dict(parsed.items())
                except imaplib.IMAP4.error:
                    pass

                # 2. Check INBOX
                imap.select("INBOX")
                _, data = imap.search(None, "HEADER", "Message-ID", clean_mid)
                if data and data[0]:
                    uid = data[0].split()[0]
                    folder = "INBOX"
                    try:
                        _, labels = imap.fetch(uid, "(X-GM-LABELS)")
                        lab = labels[0].decode(errors="ignore") if labels else ""
                        if "CATEGORY_PROMOTIONS" in lab:
                            folder = "PROMOTIONS"
                    except Exception:
                        pass

                    _, msg_data = imap.fetch(uid, "(RFC822)")
                    raw_email = msg_data[0][1]
                    parsed = email.message_from_bytes(raw_email, policy=policy.default)
                    return folder, raw_email.decode("utf-8", errors="replace"), dict(parsed.items())

        except Exception as e:
            print(f"   (IMAP check error: {e}, retrying...)")
        time.sleep(5)

    return "UNKNOWN", "", {}


def run_preflight_verification(
    prospect_name: str,
    prospect_email: str,
    position: str = "",
    niche: str = "",
    sender_profile: str = "hello@nasrullahtanim.me",
    sender_name: str = "Nasrullah Tanim",
    seed_email_override: str = ""
) -> bool:
    config = load_config()
    seeds = [s for s in config.get("seed_accounts", []) if not s.get("password", "").startswith("FILL_IN")]
    if not seeds:
        print("❌ Error: No configured seed accounts found.")
        return False

    if seed_email_override:
        seed_account = next((s for s in seeds if s["email"].lower() == seed_email_override.lower()), seeds[0])
    else:
        seed_account = seeds[0]

    # Preflight real-time DNS MX resolution
    seed_domain = seed_account["email"].split("@")[-1]
    mx_info = MXValidator.get_mx_identity(seed_domain)

    # Hardcoded canonical email generation
    first_name = prospect_name.split()[0] if prospect_name else "there"
    subject, body_text, detected_niche = build_hardcoded_canonical_email(
        first_name=first_name,
        niche=niche,
        position=position,
        email_addr=prospect_email
    )

    print("\n========================================================")
    print("🚀 PRE-FLIGHT SEED PLACEMENT & FORENSIC VERIFIER")
    print("========================================================")
    print(f"Sender:     {sender_name} <{sender_profile}>")
    print(f"Prospect:   {prospect_name} <{prospect_email}>")
    print(f"Seed Test:  {seed_account['email']} (MX: {mx_info['mx_id']})")
    print(f"Subject:    {subject}")
    print(f"Niche:      {detected_niche}")
    print("--------------------------------------------------------")

    # Build Bulletproof Email
    test_msg, meta = build_bulletproof_email(
        from_name=sender_name,
        from_addr=sender_profile,
        to_name=seed_account["email"].split("@")[0],
        to_addr=seed_account["email"],
        subject=subject,
        body_text=body_text,
        enable_spintax=False,
        niche=detected_niche
    )
    test_msg_id = meta["message_id"]

    print(f"📤 Dispatching bulletproof test email via KumoMTA to seed ({seed_account['email']})...")
    dispatch_via_kumomta(config, sender_profile, seed_account["email"], test_msg)
    print(f"✅ Dispatched! Message-ID: {test_msg_id}")

    # Check folder placement on Google's seed mailbox
    folder, raw_source, headers = check_seed_placement_and_fetch_headers(seed_account, test_msg_id, timeout=60)

    print("\n--------------------------------------------------------")
    print(f"📬 GOOGLE SEED INBOX PLACEMENT RESULT: [{folder}]")
    print("--------------------------------------------------------")

    if folder == "INBOX":
        print("🎉 SUCCESS! The email landed directly in the PRIMARY INBOX (0 Spam, 0 Promotions)!")
    elif folder == "PROMOTIONS":
        print("⚠️ NOTICE: The email landed in the Promotions tab.")
    elif folder == "SPAM":
        print("❌ FAILED: The email landed in SPAM.")
    else:
        print("⚠️ UNKNOWN: Message not yet indexed.")

    if raw_source:
        print("\n========================================================")
        print("📄 EXACT GOOGLE-AUTHENTICATED HEADERS & AUTHENTICATION RESULTS:")
        print("========================================================")
        auth_results = headers.get("Authentication-Results", "N/A")
        dkim_sig = headers.get("DKIM-Signature", "N/A")
        received_spf = headers.get("Received-SPF", "N/A")
        arc_results = headers.get("ARC-Authentication-Results", "N/A")

        print(f"• Authentication-Results: {auth_results}")
        print(f"• Received-SPF:           {received_spf}")
        print(f"• DKIM-Signature:         {dkim_sig[:80]}...")
        print(f"• ARC-Results:            {arc_results}")
        print("========================================================\n")

    return folder == "INBOX"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Pre-flight Seed Inbox Placement Verifier")
    parser.add_argument("--name", default="Brandon Mulrenin", help="Target prospect name")
    parser.add_argument("--email", default="brandon@brandonmulrenin.com", help="Target prospect email")
    parser.add_argument("--position", default="Real Estate Broker", help="Target position/title")
    parser.add_argument("--niche", default="real estate", help="Target niche")
    parser.add_argument("--sender", default="hello@nasrullahtanim.me", help="Sender profile email")
    parser.add_argument("--seed", default="", help="Specific seed account to test (e.g. tanimsyt@gmail.com)")
    args = parser.parse_args()

    run_preflight_verification(
        prospect_name=args.name,
        prospect_email=args.email,
        position=args.position,
        niche=args.niche,
        sender_profile=args.sender,
        seed_email_override=args.seed
    )


