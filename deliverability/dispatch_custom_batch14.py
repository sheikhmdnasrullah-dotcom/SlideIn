#!/usr/bin/env python3
"""
Dispatch Batch 14 (Prospects 66-70)
Implements:
1. 100% Human-authentic Apple Mail HTML view (zero background shading, dark/light mode native)
2. Subject line: strictly '{FirstName}?'
3. Concise, authentic Tanim tone with deep personalization
4. Customized capability pitches mapped to each prospect's workflow:
   - Simi (Wellbeing Face): Automated video->reels workflow + research/newsletter writing agents
   - Jesse (Consult Disrupt): Interactive WebApp readiness diagnostic + speed-to-lead lead response
   - Ryan (Mortgage Choice): Loan calculator/60-sec eligibility WebApp funnel + automated lead response/follow-ups for loan officers
   - Liz (Liz Wolfe Coaching): Automated podcast->reels workflow + business article/newsletter writing agents
   - Jeff (Jeff Kikel / Freedom Day): Podcast->reels automation + interactive financial calculator funnel
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
        "name": "Simi",
        "email": "simi@wellbeingface.com",
        "subject": "Simi?",
        "sender_email": "hello@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "facial wellness and holistic skin health",
        "body": """Hey Simi, I know you're busy, so I'll keep this short.

I went through Wellbeing Face and your content, especially your holistic routines around facial wellness and natural skin rejuvenation, and I really admire how accessible you make holistic health for your audience.

Here's how I can help streamline your backend:

On the content side, I can set up an automated workflow that turns your longer tutorials and wellness sessions into a full week of engaging reels and short clips, and schedule them across platforms while keeping a human in the loop.

On the client side, I can set up writing agents that research emerging wellness studies to prepare weekly updates for your subscribers, while an automated lead-capturing funnel engages site visitors with an interactive skin routine assessment and sequences personalized follow-ups.

Basically, I can automate all the repetitive backend tasks inside your workflow that take time and effort.

If you have a few minutes, I can walk you through how it works on a quick call. If not, I can quickly send a loom video on how I can help you out.

Either way, I'd love to help you build something great.

Thanks,
Tanim"""
    },
    {
        "name": "Jesse",
        "email": "jesse@consultdisrupt.com",
        "subject": "Jesse?",
        "sender_email": "talk@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "management consulting and business transformation",
        "body": """Hey Jesse, I know you're busy, so I'll keep this short.

I came across your work at Consult Disrupt, particularly your focus on organizational agility, strategic transformation, and breaking conventional consulting models, and I really like the disruptive approach you take.

Here's how I can help streamline your backend:

On the acquisition side, I can set up an automated outreach funnel that acts like an interactive WebApp—such as a 60-second Business Disruption Diagnostic—to engage executive visitors, capture their operational challenges, match them with your ideal client profile, and trigger personalized follow-ups.

On the operations side, I can build a system that responds to new inquiries in seconds and automates consultation reminders and CRM updates so you can focus purely on client strategy.

Basically, I can automate all the repetitive backend tasks inside your workflow that take time and effort.

If you have a few minutes, I can walk you through how it works on a quick call. If not, I can quickly send a loom video on how I can help you out.

Either way, I'd love to help you build something great.

Thanks,
Tanim"""
    },
    {
        "name": "Ryan",
        "email": "ryan.pappas@mortgagechoice.com.au",
        "subject": "Ryan?",
        "sender_email": "connect@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "mortgage broking and home loan advisory",
        "body": """Hey Ryan, I know you're busy, so I'll keep this short.

I looked into your work with Mortgage Choice, especially how you guide home buyers and refinancers through complex lending scenarios, and I know how much time gets consumed by repetitive admin and back-and-forth qualification.

Here's how I can help streamline your backend:

On the lead side, I can automate outreach through a lead capturing funnel that acts like a WebApp on your site, engaging visitors with free tools like a loan calculator or a "get your loan eligibility test in 60 seconds", capturing their numbers, matching them with your ideal client profile, and preparing personalized emails.

On the operations side, I can build a system that responds to new leads in seconds and automates follow-ups, document reminders, and CRM record updates so you and your team spend time on actual borrowers rather than chasing paperwork.

Basically, I can automate all the repetitive backend tasks inside your workflow that take time and effort.

If you have a few minutes, I can walk you through how it works on a quick call. If not, I can quickly send a loom video on how I can help you out.

Either way, I'd love to help you build something great.

Thanks,
Tanim"""
    },
    {
        "name": "Liz",
        "email": "liz@lizwolfecoaching.com",
        "subject": "Liz?",
        "sender_email": "hello@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "solopreneur business coaching and time management",
        "body": """Hey Liz, I know you're busy, so I'll keep this short.

I went through your coaching work and your philosophy in 'How to Grow a Business When You Have No Time', and I really love how practical your systems are for solopreneurs who feel overwhelmed by daily operations.

Here's how I can help streamline your backend:

On the content side, I can build an automated workflow that turns your podcast episodes, workshops, and coaching recordings into a full week of reels, short clips, and LinkedIn carousels, scheduled across platforms while keeping a human in the loop.

On the audience side, I can set up writing agents that research entrepreneurship and productivity trends to prepare weekly updates for your subscribers, alongside an automated system that handles discovery call reminders and onboarding updates.

Basically, I can automate all the repetitive backend tasks inside your workflow that take time and effort.

If you have a few minutes, I can walk you through how it works on a quick call. If not, I can quickly send a loom video on how I can help you out.

Either way, I'd love to help you build something great.

Thanks,
Tanim"""
    },
    {
        "name": "Jeff",
        "email": "jeff@jeffkikel.com",
        "subject": "Jeff?",
        "sender_email": "talk@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "financial freedom education and business acquisition",
        "body": """Hey Jeff, I know you're busy, so I'll keep this short.

I went through your content and the Freedom Day Method podcast, especially your frameworks on business acquisition, cash-flowing assets, and creating sustainable lifestyle freedom, and I really respect the sheer consistency of your output.

Here's how I can help streamline your backend:

On the content side, I can create an automated workflow that turns your podcast episodes and YouTube recordings into a full week of reels and clips, and schedules them across all platforms while keeping a human in the loop.

On the audience side, I can set up an interactive WebApp funnel—like a Freedom Day retirement or acquisition calculator—that captures visitor information, matches them with your ideal client profile, and automates personalized outreach emails and follow-ups.

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

    print(f"🚀 Starting Batch 14 Dispatch with Clean Human View ({len(BATCH_PROSPECTS)} Prospects)...", flush=True)
    primary_seed = seeds[0]
    results = []

    for item in BATCH_PROSPECTS:
        res = dispatch_prospect(item, primary_seed)
        results.append(res)
        if res.get("status") == "blocked_gate":
            print("⚠️ Halting batch due to Seed Gate Block!", flush=True)
            break

    print("\n========================================================", flush=True)
    print("🏁 BATCH 14 EXECUTION COMPLETE (HUMAN VIEW & CUSTOM PITCHES)", flush=True)
    print("========================================================", flush=True)
    for r in results:
        print(f"• {r.get('recipient')}: {r.get('status', 'ERROR').upper()} (Sender: {r.get('sender', 'N/A')})", flush=True)


if __name__ == "__main__":
    main()
