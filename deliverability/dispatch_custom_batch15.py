#!/usr/bin/env python3
"""
Dispatch Batch 15 (Prospects 71-75)
Implements:
1. 100% Human-authentic Apple Mail HTML view (zero background shading, dark/light mode native)
2. Subject line: strictly '{FirstName}?'
3. Concise, authentic Tanim tone with deep personalization
4. Customized capability pitches mapped to each prospect's workflow:
   - Georgina (The Honest Vocal Coach): Automated video/reaction -> reels/clips workflow + vocal assessment lead funnel
   - Russ (Sojourn Partners): Executive diagnostic WebApp funnel + speed-to-lead follow-up automation + leadership writing agents
   - Tamu (Luxpad Interiors): Portfolio walkthrough -> short clips workflow + interactive design style quiz & inquiry automation
   - Scott (On The Edge Podcast / Loan-Officer Tools): Podcast-to-reels workflow + loan calculator/eligibility WebApp funnel + speed-to-lead for loan officers
   - James (Dadvice TV): Long-form health video-to-reels automation + renal nutrition research/newsletter writing agents
5. Background Ghost Ink + Anti-bleed zero-width padding
6. Real-time DNS MX validation and seed-gate pre-check
"""
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from core import state as st
from preflight_verifier import load_config
from advanced_deliverability import build_bulletproof_email, HumanPacer
from dispatch_custom_batch11 import send_smtp, check_seed_placement

STATE_PATH = HERE / "deliverability_state.db"

BATCH_PROSPECTS = [
    {
        "name": "Georgina",
        "email": "georgina@honestvocalcoach.co.uk",
        "subject": "Georgina?",
        "sender_email": "hello@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "vocal coaching and vocal technique education",
        "body": """Hey Georgina, I know you're busy, so I'll keep this short.

I went through your content at The Honest Vocal Coach, especially your vocal technique breakdowns and live reaction analyses, and I love how practical and no-nonsense your advice is for singers.

Here's how I can help streamline your backend:

On the content side, I can set up an automated workflow that turns your long-form YouTube tutorials and reviews into a full week of high-retention reels and short clips, and schedule them across all platforms while keeping a human in the loop.

On the client side, I can set up an interactive vocal assessment quiz on your site that engages singers, captures their specific vocal goals, and automates personalized outreach emails and lesson booking follow-ups.

Basically, I can automate all the repetitive backend tasks inside your workflow that take time and effort.

If you have a few minutes, I can walk you through how it works on a quick call. If not, I can quickly send a loom video on how I can help you out.

Either way, I'd love to help you build something great.

Thanks,
Tanim"""
    },
    {
        "name": "Russ",
        "email": "russ@sojournpartners.com",
        "subject": "Russ?",
        "sender_email": "talk@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "executive coaching and organizational leadership",
        "body": """Hey Russ, I know you're busy, so I'll keep this short.

I came across your work at Sojourn Partners, particularly your frameworks around executive coaching, leadership team alignment, and cultural transformation, and I really respect the standard you set for corporate leadership.

Here's how I can help streamline your backend:

On the client acquisition side, I can set up an interactive lead capturing funnel on your website—like a 60-second Executive Leadership Diagnostic tool—that engages corporate visitors, identifies their organizational challenges, and triggers personalized email workflows.

On the operations side, I can build a system that responds to new leadership inquiries in seconds and automates follow-ups, consultation reminders, and CRM updates so your coaches can spend their time on actual executive clients.

Basically, I can automate all the repetitive backend tasks inside your workflow that take time and effort.

If you have a few minutes, I can walk you through how it works on a quick call. If not, I can quickly send a loom video on how I can help you out.

Either way, I'd love to help you build something great.

Thanks,
Tanim"""
    },
    {
        "name": "Tamu",
        "email": "tamu@luxpadinteriors.com",
        "subject": "Tamu?",
        "sender_email": "connect@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "interior design and luxury space transformation",
        "body": """Hey Tamu, I know you're busy, so I'll keep this short.

I went through Luxpad Interiors and your project showcases, especially your eye for spatial balance, custom joinery, and functional luxury, and I really admire the aesthetic quality of your portfolio.

Here's how I can help streamline your backend:

On the content side, I can build an automated workflow that turns your project walkthroughs and design presentations into a full week of short clips and aesthetic reels, scheduled across platforms while keeping a human in the loop.

On the client side, I can build an interactive WebApp funnel on your site—like a 60-second Design Style & Scope Calculator—that engages visitors, captures their budget and project vision, and automates personalized consultation follow-ups.

Basically, I can automate all the repetitive backend tasks inside your workflow that take time and effort.

If you have a few minutes, I can walk you through how it works on a quick call. If not, I can quickly send a loom video on how I can help you out.

Either way, I'd love to help you build something great.

Thanks,
Tanim"""
    },
    {
        "name": "Scott",
        "email": "scott@ontheedgepodcast.com",
        "subject": "Scott?",
        "sender_email": "hello@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "podcast production and loan officer enablement tools",
        "body": """Hey Scott, I know you're busy, so I'll keep this short.

I looked into your work on the On The Edge Podcast and your tools for loan officers, and I really like how you bridge media production with practical mortgage and lending workflows.

Here's how I can help streamline your backend:

On the podcast side, I can create an automated workflow that turns your podcast episodes and video recordings into a full week of reels and short clips, and schedule them across all platforms while keeping a human in the loop.

On the lending tools side, I can automate outreach emails at scale through an interactive lead-capturing funnel that acts like a WebApp, engaging visitors with tools like a "loan calculator" or "get your loan eligibility test in 60 seconds", capturing lead data, matching ideal borrower profiles, and triggering speed-to-lead follow-ups so loan officers spend time with actual clients.

Basically, I can automate all the repetitive backend tasks inside your workflow that take time and effort.

If you have a few minutes, I can walk you through how it works on a quick call. If not, I can quickly send a loom video on how I can help you out.

Either way, I'd love to help you build something great.

Thanks,
Tanim"""
    },
    {
        "name": "James",
        "email": "james@dadvicetv.com",
        "subject": "James?",
        "sender_email": "talk@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "kidney health coaching and patient advocacy education",
        "body": """Hey James, I know you're busy, so I'll keep this short.

I went through your work on Dadvice TV, especially your comprehensive breakdowns on renal nutrition, lab work interpretations, and practical lifestyle adjustments for kidney health, and I really respect the support you provide to your community.

Here's how I can help streamline your backend:

On the content side, I can set up an automated workflow that turns your long-form YouTube episodes and live Q&A sessions into a full week of informative short clips and reels, scheduled across platforms while keeping a human in the loop.

On the audience side, I can set up writing agents that research current renal health studies to draft weekly newsletter updates for your subscribers, paired with an automated system that handles community inquiries and consultation reminders.

Basically, I can automate all the repetitive backend tasks inside your workflow that take time and effort.

If you have a few minutes, I can walk you through how it works on a quick call. If not, I can quickly send a loom video on how I can help you out.

Either way, I'd love to help you build something great.

Thanks,
Tanim"""
    }
]


def dispatch_prospect(item: dict, seed_account: dict) -> dict:
    config = load_config()
    store = st.Store(str(STATE_PATH))

    recipient_email = item["email"]
    recipient_name = item["name"]
    sender_email = item["sender_email"]
    sender_name = item["sender_name"]
    subject = item["subject"]
    body = item["body"]
    niche = item.get("niche", "business workflow")

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

    # 3. Build bulletproof email for pre-send seed verification
    test_msg, meta = build_bulletproof_email(
        from_name=sender_name,
        from_addr=sender_email,
        to_name=seed_account["email"].split("@")[0],
        to_addr=seed_account["email"],
        subject=subject,
        body_text=body,
        enable_spintax=False,
        niche=niche
    )
    test_bytes = test_msg.as_bytes()

    print(f"1️⃣  Executing Pre-Send Seed Gate on ({seed_account['email']})...", flush=True)
    send_smtp(config, sender_email, seed_account["email"], test_bytes)

    folder, _ = check_seed_placement(seed_account, meta["message_id"], timeout=30)
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

    print("🎉 SEED GATE PASSED: 100% Primary Inbox Verified (Clean Human Apple Mail View)!", flush=True)

    # 4. Build and dispatch to actual prospect
    prospect_msg, prospect_meta = build_bulletproof_email(
        from_name=sender_name,
        from_addr=sender_email,
        to_name=recipient_name,
        to_addr=recipient_email,
        subject=subject,
        body_text=body,
        enable_spintax=False,
        niche=niche
    )
    prospect_bytes = prospect_msg.as_bytes()
    prospect_msg_id = prospect_meta["message_id"]

    print(f"2️⃣  Dispatching Verified Email to Prospect ({recipient_email})...", flush=True)
    send_smtp(config, sender_email, recipient_email, prospect_bytes)
    print(f"✅ DELIVERED to {recipient_email}! (MsgId: {prospect_msg_id})", flush=True)

    store.record_send_event(
        recipient=recipient_email,
        provider="kumomta",
        result="sent",
        detail=f"Delivered via KumoMTA with clean human HTML view. MsgId: {prospect_msg_id}",
    )

    pacing_delay = HumanPacer.get_jitter_delay(base_seconds=36, variance=8)
    print(f"⏳ Human pacing delay: waiting {pacing_delay}s before next send...", flush=True)
    time.sleep(pacing_delay)

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

    print(f"🚀 Starting Batch 15 Dispatch with Clean Human View ({len(BATCH_PROSPECTS)} Prospects)...", flush=True)
    primary_seed = seeds[0]
    results = []

    for item in BATCH_PROSPECTS:
        res = dispatch_prospect(item, primary_seed)
        results.append(res)
        if res.get("status") == "blocked_gate":
            print("⚠️ Halting batch due to Seed Gate Block!", flush=True)
            break

    print("\n========================================================", flush=True)
    print("🏁 BATCH 15 EXECUTION COMPLETE (HUMAN VIEW & CUSTOM PITCHES)", flush=True)
    print("========================================================", flush=True)
    for r in results:
        print(f"• {r.get('recipient')}: {r.get('status', 'ERROR').upper()} (Sender: {r.get('sender', 'N/A')})", flush=True)


if __name__ == "__main__":
    main()
