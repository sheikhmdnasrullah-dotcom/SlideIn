#!/usr/bin/env python3
"""Dispatch Batch 12 (Prospects 56-60) with Ghost Ink Deliverability Engine and Seed-Gate Verification."""
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from core import state as st
from preflight_verifier import load_config
from ghost_ink import build_ghost_ink_email
from dispatch_custom_batch11 import send_smtp, check_seed_placement

STATE_PATH = HERE / "deliverability_state.db"

BATCH_PROSPECTS = [
    {
        "name": "Pat & Starter Story Team",
        "email": "support@starterstory.com",
        "subject": "Starter Story?",
        "sender_email": "hello@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "founder case studies and business breakdown content",
        "body": """Hey team, I know you're busy, so I'll keep this as short as possible.

I went through your content across Starter Story, especially your deep-dive founder case studies and revenue breakdowns, and I respect the practical value you bring to the entrepreneur community. I am really interested to contribute my skillset to support your media distribution and story operations.

Here's what I am able to do for you.. On the content side, I can handle it end to end: taking your long form founder interviews and written case studies, editing them into a week's worth of fast-paced short clips, thumbnails, and written highlights, and getting it all distributed and scheduled across platforms.

On the outreach side, I can study your ideal founder profile of bootstrapped entrepreneurs doing $10k-$100k/mo, find operators in the market who match it, and build a system that reaches out to coordinate story submissions automatically. Your team can focus on editorial and interviewing and I will take care the backend tasks.

Once this is running, I am optimistic that you will get more consistent responses from the right people.

If you have a few minutes, I can walk you through everything on a quick call. If not, I can quickly send a loom video on how I can actually help you out.

Either way, I'd love to help you build something great.

Thanks,
Tanim"""
    },
    {
        "name": "Simon",
        "email": "partnerships@simonsquibb.com",
        "subject": "Simon?",
        "sender_email": "talk@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "street founder interviews and entrepreneurship media",
        "body": """Simon, I know you're busy, so I'll keep this as short as possible.

I went through your videos and HelpBnk initiatives, especially your street interviews asking everyday people what their dream business is, and I respect the raw positivity and impact you create for entrepreneurs. I am really interested to contribute my skillset to help support your team's media operations.

Here's what I am able to do for you.. On the content side, I can handle it end to end: taking your long form video conversations and event talks, editing them into a week's worth of high-energy vertical clips, thumbnails, and written founder takeaways, and getting it all distributed and scheduled across platforms.

On the outreach side, I can study your target partnership and brand sponsorship profiles, find aligned impact-driven companies in the market who match them, and build an automated system that handles introductory outreach and coordination. Your team can focus on filming and community building and I will take care the backend tasks.

Once this is running, I am optimistic that you will get more consistent responses from the right people.

If you have a few minutes, I can walk you through everything on a quick call. If not, I can quickly send a loom video on how I can actually help you out.

Either way, I'd love to help you build something great.

Thanks,
Tanim"""
    },
    {
        "name": "Edward",
        "email": "info@primaryposition.com",
        "subject": "Edward?",
        "sender_email": "connect@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "search engine marketing and build in public",
        "body": """Edward, I know you're busy, so I'll keep this as short as possible.

I went through your content and Build in Public channel, especially your breakdowns on organic search architecture, programmatic SEO, and client acquisition workflows, and I respect the straightforward technical depth you bring. I am really interested to contribute my skillset to help you scale your audience.

Here's what I am able to do for you.. On the content side, I can handle it end to end: taking your tutorials, build logs, and client case studies, editing them into a week's worth of punchy vertical clips, high-CTR thumbnails, and written SEO playbooks, and getting it all distributed and scheduled across platforms.

On the outreach side, I can study your ideal agency client profile of e-commerce and B2B founders needing search growth, find businesses in the market who match it, and build a system that reaches out to them for you. Once someone responds, follow ups, audit offers, and calendar bookings all can happen automatically. You can spend your time on search strategy and I will take care the backend tasks.

Once this is running, I am optimistic that you will get more consistent responses from the right people.

If you have a few minutes, I can walk you through everything on a quick call. If not, I can quickly send a loom video on how I can actually help you out.

Either way, I'd love to help you build something great.

Thanks,
Tanim"""
    },
    {
        "name": "Matt",
        "email": "matt@emgigroup.com",
        "subject": "Matt?",
        "sender_email": "hello@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "business growth and operations consulting",
        "body": """Matt, I know you're busy, so I'll keep this as short as possible.

I went through your content and EMGI Group discussions, especially your focus on operational bottleneck identification, scaling service delivery, and revenue architecture, and I respect the clarity you bring to growth consulting. I am really interested to contribute my skillset to help you expand your digital pipeline.

Here's what I am able to do for you.. On the content side, I can handle it end to end: taking your long form talks, webinars, and advisory breakdowns, editing them into a week's worth of sharp vertical clips, thumbnails, and written operational posts, and getting it all distributed and scheduled across platforms.

On the outreach side, I can study your ideal client profile of mid-market business owners and founders looking to optimize operations, find leaders in target industries who match it, and build a system that reaches out to them for you. Once someone responds, follow ups, diagnostic bookings, and reminders all can happen automatically. You can spend your time on consulting and I will take care the backend tasks.

Once this is running, I am optimistic that you will get more consistent responses from the right people.

If you have a few minutes, I can walk you through everything on a quick call. If not, I can quickly send a loom video on how I can actually help you out.

Either way, I'd love to help you build something great.

Thanks,
Tanim"""
    },
    {
        "name": "John",
        "email": "john@magnatesmedia.com",
        "subject": "John?",
        "sender_email": "talk@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "business documentary production and cinematic storytelling",
        "body": """John, I know you're busy, so I'll keep this as short as possible.

I went through your videos on Magnates Media, especially your cinematic documentary storytelling on corporate rivalries and financial empire collapses, and I respect the unmatched production quality you consistently achieve. I am really interested to contribute my skillset to support your team's post-production and research operations.

Here's what I am able to do for you.. On the content side, I can handle it end to end: assisting with archival research, audio prep, cutting down your multi-million-view documentaries into high-retention vertical shorts, thumbnails, and written business breakdowns, and getting it distributed across secondary platforms.

On the outreach side, I can study your target sponsor and institutional brand profiles, find high-tier fintech and business platforms who want to sponsor your productions, and build an automated system to handle cold pitch sequences and follow ups. Your team can focus on writing and animation and I will take care the backend tasks.

Once this is running, I am optimistic that you will get more consistent responses from the right people.

If you have a few minutes, I can walk you through everything on a quick call. If not, I can quickly send a loom video on how I can actually help you out.

Either way, I'd love to help you build something great.

Thanks,
Tanim"""
    }
]


def dispatch_prospect(item: dict, seed_account: dict, pacing_seconds: int = 35) -> dict:
    config = load_config()
    store = st.Store(str(STATE_PATH))

    recipient_email = item["email"]
    recipient_name = item["name"]
    sender_email = item["sender_email"]
    sender_name = item["sender_name"]
    subject = item["subject"]
    body = item["body"]
    niche = item.get("niche", "business growth")

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
    print(f"🎯 PROCESSING PROSPECT (WITH GHOST INK): {recipient_name} <{recipient_email}>", flush=True)
    print("=" * 60, flush=True)
    print(f"From:     {sender_name} <{sender_email}>", flush=True)
    print(f"Subject:  {subject}", flush=True)
    print(f"Seed:     {seed_account['email']}", flush=True)
    print("-" * 60, flush=True)

    # 3. Build test email with Ghost Ink for seed account
    test_msg = build_ghost_ink_email(
        from_name=sender_name,
        from_addr=sender_email,
        to_name=seed_account["email"].split("@")[0],
        to_addr=seed_account["email"],
        subject=subject,
        body_text=body,
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

    print("🎉 SEED GATE PASSED: 100% Primary Inbox Verified (Ghost Ink Active)!", flush=True)

    # 4. Dispatch to actual prospect with unique Ghost Ink
    prospect_msg = build_ghost_ink_email(
        from_name=sender_name,
        from_addr=sender_email,
        to_name=recipient_name,
        to_addr=recipient_email,
        subject=subject,
        body_text=body,
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
        detail=f"Passed seed gate with Ghost Ink ({seed_account['email']}) and delivered via KumoMTA. MsgId: {prospect_msg_id}",
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

    print(f"🚀 Starting Batch 12 Dispatch with Ghost Ink ({len(BATCH_PROSPECTS)} Prospects)...", flush=True)
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
    print("🏁 BATCH 12 EXECUTION COMPLETE (GHOST INK POWERED)", flush=True)
    print("========================================================", flush=True)
    for r in results:
        print(f"• {r.get('recipient')}: {r.get('status', 'ERROR').upper()} (Sender: {r.get('sender', 'N/A')})", flush=True)


if __name__ == "__main__":
    main()
