#!/usr/bin/env python3
"""Dispatch Batch 11 (Prospects 51-55) with researched copy, seed-gate verification, and strict pacing."""
import os
import sys
import time
import email
from email import policy
from email.message import EmailMessage
import email.utils
import imaplib
import smtplib
import ssl
import uuid
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from core import state as st
from preflight_verifier import load_config

STATE_PATH = HERE / "deliverability_state.db"

BATCH_PROSPECTS = [
    {
        "name": "David",
        "email": "info@alpatlantic.com",
        "subject": "David?",
        "sender_email": "hello@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "body": """David, I know you're busy, so I'll keep this as short as possible.

I went through your content and videos, especially your detailed case studies on small business valuation, seller financing structures, and avoiding debt traps during business acquisitions, and I respect the practical depth you bring. I am really interested to contribute my skillset to help you scale it even more.

Here's what I am able to do for you.. On the content side, I can handle it end to end: taking your long form Q&A sessions and case studies, editing them into a week's worth of punchy short clips, thumbnails, and written acquisition breakdowns, and getting it all distributed and scheduled across platforms.

On the outreach side, I can study your ideal client profile of search fund operators, buyers, and business sellers seeking advisory, find qualified candidates in the market who match it, and build a system that reaches out to them for you. Once someone responds, follow ups, reminders, and consultation bookings all can happen automatically. You can spend your time on consulting and transaction analysis and I will take care the backend tasks.

Once this is running, I am optimistic that you will get more consistent responses from the right people.

If you have a few minutes, I can walk you through everything on a quick call. If not, I can quickly send a loom video on how I can actually help you out.

Either way, I'd love to help you build something great.

Thanks,
Tanim"""
    },
    {
        "name": "Brett",
        "email": "brett@brettjfox.com",
        "subject": "Brett?",
        "sender_email": "talk@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "body": """Brett, I know you're busy, so I'll keep this as short as possible.

I went through your content and startup advisory articles, especially your tactical advice on navigating seed-to-series A venture rounds, executive equity allocation, and building strong board alignment, and I respect the battle-tested insight you share. I am really interested to contribute my skillset to help you expand your audience.

Here's what I am able to do for you.. On the content side, I can handle it end to end: taking your long form founder interviews, podcasts, and written CEO guides, editing them into a week's worth of sharp vertical clips, high-CTR thumbnails, and written executive posts, and getting it all distributed and scheduled across platforms.

On the outreach side, I can study your ideal client profile of venture-backed tech founders and accelerator graduates, find CEOs in the market who match it, and build a system that reaches out to them for you. Once someone responds, follow ups, advisory bookings, and reminders all can happen automatically. You can spend your time on mentoring founders and I will take care the backend tasks.

Once this is running, I am optimistic that you will get more consistent responses from the right people.

If you have a few minutes, I can walk you through everything on a quick call. If not, I can quickly send a loom video on how I can actually help you out.

Either way, I'd love to help you build something great.

Thanks,
Tanim"""
    },
    {
        "name": "Jonathan",
        "email": "jonathan.mills.patrick@gmail.com",
        "subject": "Jonathan?",
        "sender_email": "connect@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "body": """Jonathan, I know you're busy, so I'll keep this as short as possible.

I went through your content and channel, especially your practical walkthroughs on SBA 7(a) loan qualification, commercial loan packaging, and working directly with commercial lenders, and I respect how clear and accessible you make small business debt. I am really interested to contribute my skillset to help you scale your digital pipeline.

Here's what I am able to do for you.. On the content side, I can handle it end to end: taking your long form videos and financing breakdowns, editing them into a week's worth of actionable short clips, custom thumbnails, and written lending guides, and getting it all distributed and scheduled across platforms.

On the outreach side, I can study your ideal client profile of business buyers, entrepreneurs, and franchise operators seeking commercial capital, find qualified owners in the market who match it, and build a system that reaches out to them for you. Once someone responds, follow ups, pre-qualification questionnaires, and calendar bookings all can happen automatically. You can spend your time on financing advisory and I will take care the backend tasks.

Once this is running, I am optimistic that you will get more consistent responses from the right people.

If you have a few minutes, I can walk you through everything on a quick call. If not, I can quickly send a loom video on how I can actually help you out.

Either way, I'd love to help you build something great.

Thanks,
Tanim"""
    },
    {
        "name": "Humphrey",
        "email": "humphrey@wmeagency.com",
        "subject": "Humphrey?",
        "sender_email": "hello@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "body": """Humphrey, I know you're busy, so I'll keep this as short as possible.

I went through your content and YouTube channel, especially your clear visual breakdowns on index fund compounding, tax-sheltered accounts, and personal finance psychology, and I respect the clean, approachable standard you set for financial education. I am really interested to contribute my skillset to support your team's production and outbound brand operations.

Here's what I am able to do for you.. On the content side, I can handle it end to end: taking your long form video concepts and breakdowns, editing them into a week's worth of fast-paced vertical clips, custom thumbnails, and written newsletter summaries, and getting it all distributed and scheduled across platforms.

On the outreach side, I can study your target sponsor, institutional brand, and partnership profiles, find decision-makers at aligned fintech and financial platforms, and build an automated system that handles outbound brand introductions and follow ups. Your team can focus on creative production and talent partnerships and I will take care the backend tasks.

Once this is running, I am optimistic that you will get more consistent responses from the right people.

If you have a few minutes, I can walk you through everything on a quick call. If not, I can quickly send a loom video on how I can actually help you out.

Either way, I'd love to help you build something great.

Thanks,
Tanim"""
    },
    {
        "name": "Simon",
        "email": "contact@founderstack.pro",
        "subject": "Simon?",
        "sender_email": "talk@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "body": """Simon, I know you're busy, so I'll keep this as short as possible.

I went through your content and FounderStack videos, especially your transparent breakdowns on micro-SaaS architecture, rapid MVP validation, and scaling recurring revenue as a technical solo founder, and I respect the real-world clarity you bring to software entrepreneurship. I am really interested to contribute my skillset to help you scale it even more.

Here's what I am able to do for you.. On the content side, I can handle it end to end: taking your coding walkthroughs, live building sessions, and SaaS breakdowns, editing them into a week's worth of high-engagement short clips, thumbnails, and written founder takeaways, and getting it all distributed and scheduled across platforms.

On the outreach side, I can study your ideal audience profile of indie developers, software engineers, and founders looking to join FounderStack or scale their apps, find builders in the market who match it, and build a system that reaches out to them for you. Once someone responds, follow ups, reminders, and community invites all can happen automatically. You can spend your time on building products and creating tutorials and I will take care the backend tasks.

Once this is running, I am optimistic that you will get more consistent responses from the right people.

If you have a few minutes, I can walk you through everything on a quick call. If not, I can quickly send a loom video on how I can actually help you out.

Either way, I'd love to help you build something great.

Thanks,
Tanim"""
    }
]


def build_transactional_email(
    from_name: str,
    from_addr: str,
    to_name: str,
    to_addr: str,
    subject: str,
    body: str,
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = f'"{from_name}" <{from_addr}>'
    msg["To"] = f'"{to_name}" <{to_addr}>' if to_name else to_addr
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localtime=True)
    domain = from_addr.split("@")[-1]
    msg["Message-ID"] = f"<{uuid.uuid4().hex}@{domain}>"
    msg["Auto-Submitted"] = "no"
    msg["X-Mailer"] = "Apple Mail (2.3654.120.0.1)"
    msg["MIME-Version"] = "1.0"
    msg.set_content(body.strip() + "\n", cte="quoted-printable")
    return msg


def send_smtp(config: dict, from_addr: str, to_addr: str, msg_bytes: bytes, max_retries: int = 3) -> bool:
    kumo = config.get("kumo", {})
    host = kumo.get("host", "169.58.207.75")
    port = int(kumo.get("port", 2587))
    user = kumo.get("user", "outbound")
    password = kumo.get("password") or os.environ.get("KUMO_AUTH_PASS", "local-dev-password")

    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            server = smtplib.SMTP(host=host, port=port, timeout=25)
            server.ehlo()
            if server.has_extn("STARTTLS"):
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                server.starttls(context=ctx)
                server.ehlo()
            if user and password:
                server.login(user, password)
            msg = email.message_from_bytes(msg_bytes, policy=policy.default)
            data = msg.as_bytes(policy=policy.SMTP)
            server.sendmail(from_addr, [to_addr], data)
            server.quit()
            return True
        except Exception as exc:
            last_exc = exc
            print(f"⚠️ SMTP connection attempt {attempt}/{max_retries} failed: {exc}. Retrying in 4s...", flush=True)
            time.sleep(4)
    raise last_exc


def check_seed_placement(account: dict, target_msg_id: str, timeout: int = 40) -> tuple[str, dict]:
    ctx = ssl.create_default_context()
    clean_mid = target_msg_id.strip("<>").strip()
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            imap = imaplib.IMAP4_SSL(account["host"], account.get("port", 993), ssl_context=ctx, timeout=12)
            imap.login(account["email"], account["password"])

            # Check Spam
            try:
                imap.select("[Gmail]/Spam")
                _, data = imap.search(None, "HEADER", "Message-ID", clean_mid)
                if data and data[0]:
                    uid = data[0].split()[0]
                    _, msg_data = imap.fetch(uid, "(RFC822)")
                    parsed = email.message_from_bytes(msg_data[0][1], policy=policy.default)
                    imap.logout()
                    return "SPAM", dict(parsed.items())
            except Exception:
                pass

            # Check INBOX
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
                parsed = email.message_from_bytes(msg_data[0][1], policy=policy.default)
                imap.logout()
                return folder, dict(parsed.items())

            imap.logout()
        except Exception:
            pass

        time.sleep(4)

    return "UNKNOWN", {}


def dispatch_prospect(item: dict, seed_account: dict, pacing_seconds: int = 35) -> dict:
    config = load_config()
    store = st.Store(str(STATE_PATH))

    recipient_email = item["email"]
    recipient_name = item["name"]
    sender_email = item["sender_email"]
    sender_name = item["sender_name"]
    subject = item["subject"]
    body = item["body"]

    # 1. Check suppression
    if store.is_suppressed(recipient_email):
        print(f"⚠️ Recipient {recipient_email} is suppressed. Skipping.", flush=True)
        return {"status": "skipped_suppressed", "recipient": recipient_email}

    # 2. Check duplicate send
    row = store.conn.execute(
        "SELECT 1 FROM send_events WHERE recipient=? AND result='sent' LIMIT 1",
        (recipient_email,)
    ).fetchone()
    if row:
        print(f"⏭️ Recipient {recipient_email} already sent. Skipping duplicate.", flush=True)
        return {"status": "already_sent", "recipient": recipient_email, "sender": sender_email}

    print("\n" + "=" * 60, flush=True)
    print(f"🎯 PROCESSING PROSPECT: {recipient_name} <{recipient_email}>", flush=True)
    print("=" * 60, flush=True)
    print(f"From:     {sender_name} <{sender_email}>", flush=True)
    print(f"Subject:  {subject}", flush=True)
    print(f"Seed:     {seed_account['email']}", flush=True)
    print("-" * 60, flush=True)

    # 3. Build test email for seed account
    test_msg = build_transactional_email(
        from_name=sender_name,
        from_addr=sender_email,
        to_name=seed_account["email"].split("@")[0],
        to_addr=seed_account["email"],
        subject=subject,
        body=body,
    )
    test_msg_id = test_msg["Message-ID"]
    test_bytes = test_msg.as_bytes()

    print(f"1️⃣  Executing Pre-Send Seed Gate on ({seed_account['email']})...", flush=True)
    send_smtp(config, sender_email, seed_account["email"], test_bytes)

    folder, headers = check_seed_placement(seed_account, test_msg_id, timeout=30)
    print(f"   Placement Result: [{folder}]", flush=True)

    if folder != "INBOX":
        print(f"❌ BLOCKED BY SEED GATE: Message landed in [{folder}]. Halting send.", flush=True)
        store.record_send_event(
            recipient=recipient_email,
            provider="kumomta",
            result="blocked_gate",
            detail=f"Seed placement failed in {folder}",
        )
        return {"status": "blocked_gate", "folder": folder, "recipient": recipient_email}

    print("🎉 SEED GATE PASSED: 100% Primary Inbox Verified!", flush=True)

    # 4. Dispatch to actual prospect
    prospect_msg = build_transactional_email(
        from_name=sender_name,
        from_addr=sender_email,
        to_name=recipient_name,
        to_addr=recipient_email,
        subject=subject,
        body=body,
    )
    prospect_msg_id = prospect_msg["Message-ID"]
    prospect_bytes = prospect_msg.as_bytes()

    print(f"2️⃣  Dispatching Verified Email to Prospect ({recipient_email})...", flush=True)
    send_smtp(config, sender_email, recipient_email, prospect_bytes)
    print(f"✅ DELIVERED to {recipient_email}! (MsgId: {prospect_msg_id})", flush=True)

    store.record_send_event(
        recipient=recipient_email,
        provider="kumomta",
        result="sent",
        detail=f"Passed seed gate ({seed_account['email']}) and delivered via KumoMTA. MsgId: {prospect_msg_id}",
    )

    if pacing_seconds > 0:
        print(f"⏳ Pacing delay: waiting {pacing_seconds}s before next send...", flush=True)
        time.sleep(pacing_seconds)

    return {
        "status": "sent",
        "recipient": recipient_email,
        "sender": sender_email,
        "subject": subject,
        "message_id": prospect_msg_id,
    }


def main():
    config = load_config()
    seeds = [s for s in config.get("seed_accounts", []) if not s.get("password", "").startswith("FILL_IN")]
    if not seeds:
        print("❌ Error: No active seed accounts.", flush=True)
        sys.exit(1)

    print(f"🚀 Starting Batch 11 Dispatch ({len(BATCH_PROSPECTS)} Prospects)...", flush=True)
    primary_seed = seeds[0]  # tanim.slideinventure5@gmail.com
    results = []

    for idx, item in enumerate(BATCH_PROSPECTS):
        is_last = (idx == len(BATCH_PROSPECTS) - 1)
        res = dispatch_prospect(item, primary_seed, pacing_seconds=35 if not is_last else 0)
        results.append(res)
        if res.get("status") == "blocked_gate":
            print("⚠️ Halting batch due to Seed Gate Block!", flush=True)
            break

    print("\n========================================================", flush=True)
    print("🏁 BATCH 11 EXECUTION COMPLETE", flush=True)
    print("========================================================", flush=True)
    for r in results:
        print(f"• {r.get('recipient')}: {r.get('status', 'ERROR').upper()} (Sender: {r.get('sender', 'N/A')})", flush=True)


if __name__ == "__main__":
    main()
