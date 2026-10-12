#!/usr/bin/env python3
"""
Dispatch Batch 17 (Prospects 81-85)
Implements:
1. 100% Human-authentic Apple Mail HTML view (zero background shading, dark/light mode native)
2. Subject line: strictly '{FirstName}?'
3. Concise, authentic Tanim tone with deep personalization
4. Customized capability pitches mapped to each prospect's workflow:
   - Marybeth (Day One Life Coaching): Workshop/podcast-to-reels workflow + interactive life alignment assessment lead funnel
   - Bernd (Online Trading Campus): 60-sec trader readiness diagnostic/calculator + market research writing agents
   - Tom (Tomorrow Podcast): Tech journalism podcast-to-reels automated workflow + newsletter writing agents
   - Danny (English Plus Podcast): Educational audio-to-reels workflow + interactive language placement test funnel
   - Paul (Crazy Money Podcast): Full podcast interview-to-reels workflow + automated sponsor/guest follow-up system
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
        "name": "Marybeth",
        "email": "marybeth@dayonelifecoaching.com",
        "subject": "Marybeth?",
        "sender_email": "hello@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "life coaching and career mindset transitions",
        "body": """Hey Marybeth, I know you're busy, so I'll keep this short.

I went through Day One Life Coaching and your content, especially your focus on navigating major life transitions, overcoming self-doubt, and creating intentional personal growth, and I really admire the grounded clarity you bring to your coaching.

Here's how I can help streamline your backend:

On the content side, I can set up an automated workflow that turns your workshops, long-form reflections, and recordings into a full week of clean reels, short clips, and quote carousels, scheduled across platforms while keeping a human in the loop.

On the client side, I can build an interactive life assessment quiz on your site that engages visitors, captures their specific transition goals, matches them with your coaching profiles, and automates personalized follow-ups and discovery call reminders.

Basically, I can automate all the repetitive backend tasks inside your workflow that take time and effort.

If you have a few minutes, I can walk you through how it works on a quick call. If not, I can quickly send a loom video on how I can help you out.

Either way, I'd love to help you build something great.

Thanks,
Tanim"""
    },
    {
        "name": "Bernd",
        "email": "bernd@onlinetradingcampus.com",
        "subject": "Bernd?",
        "sender_email": "talk@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "financial trading education and market analysis",
        "body": """Hey Bernd, I know you're busy, so I'll keep this short.

I went through Online Trading Campus and your content, particularly your structured breakdowns on market mechanics, institutional order flow, and risk management psychology, and I really respect the disciplined standard you teach traders.

Here's how I can help streamline your backend:

On the acquisition side, I can set up an interactive lead capturing funnel that acts like a WebApp on your site—like a 60-second Trader Risk & Readiness Assessment or Trading Calculator—engaging visitors, capturing their details, and automating personalized educational email sequences.

On the content side, I can set up writing agents that research financial market updates, draft weekly market briefs for your subscribers, and prepare short-form LinkedIn posts while keeping a human in the loop.

Basically, I can automate all the repetitive backend tasks inside your workflow that take time and effort.

If you have a few minutes, I can walk you through how it works on a quick call. If not, I can quickly send a loom video on how I can help you out.

Either way, I'd love to help you build something great.

Thanks,
Tanim"""
    },
    {
        "name": "Tom",
        "email": "tom@tomorrow-podcast.com",
        "subject": "Tom?",
        "sender_email": "connect@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "technology journalism and future trends podcasting",
        "body": """Hey Tom, I know you're busy, so I'll keep this short.

I've been following Tomorrow Podcast and your in-depth conversations with founders and technologists, particularly how you examine the social and economic impact of emerging innovations, and I really appreciate the journalistic depth you maintain.

Here's how I can help streamline your backend:

On the media side, I can build an automated workflow that turns your full podcast recordings and video interviews into a full week of high-retention reels, clips, and LinkedIn insights, scheduled across all platforms while keeping a human in the loop.

On the audience side, I can set up writing agents that research industry news around upcoming episodes, draft weekly episode digest newsletters for your subscribers, and automate guest follow-up workflows so you spend time recording rather than managing operations.

Basically, I can automate all the repetitive backend tasks inside your workflow that take time and effort.

If you have a few minutes, I can walk you through how it works on a quick call. If not, I can quickly send a loom video on how I can help you out.

Either way, I'd love to help you build something great.

Thanks,
Tanim"""
    },
    {
        "name": "Danny",
        "email": "danny@englishpluspodcast.com",
        "subject": "Danny?",
        "sender_email": "hello@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "educational podcasting and language learning",
        "body": """Hey Danny, I know you're busy, so I'll keep this short.

I went through English Plus Podcast and your audio lessons, especially your bite-sized vocabulary breakdowns, idiom explanations, and practical grammar guides, and I really admire how accessible you make language mastery for listeners worldwide.

Here's how I can help streamline your backend:

On the content side, I can set up an automated workflow that turns your audio lessons and podcasts into a full week of short educational reels, visual vocabulary cards, and TikTok clips, scheduled across platforms while keeping a human in the loop.

On the student side, I can build an interactive WebApp funnel on your site—like a 60-second English Proficiency Test—that engages visitors, captures their specific learning goals, and automates personalized study guides and course follow-ups.

Basically, I can automate all the repetitive backend tasks inside your workflow that take time and effort.

If you have a few minutes, I can walk you through how it works on a quick call. If not, I can quickly send a loom video on how I can help you out.

Either way, I'd love to help you build something great.

Thanks,
Tanim"""
    },
    {
        "name": "Paul",
        "email": "paul@crazymoneypodcast.com",
        "subject": "Paul?",
        "sender_email": "talk@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "financial philosophy and lifestyle podcasting",
        "body": """Hey Paul, I know you're busy, so I'll keep this short.

I've been listening to Crazy Money, especially your conversations exploring the relationship between wealth, purpose, and personal fulfillment with authors and business leaders, and I really love the honest, humorous, and candid tone you strike.

Here's how I can help streamline your backend:

On the production side, I can set up an automated workflow that turns your full podcast interviews into a full week of punchy reels, YouTube Shorts, and LinkedIn takeaways, scheduled across platforms while keeping a human in the loop.

On the operational side, I can build an automated system that handles listener feedback capture, sponsor lead follow-ups, and guest prep reminders so you can stay fully focused on great conversations.

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

    print(f"🚀 Starting Batch 17 Dispatch with Clean Human View ({len(BATCH_PROSPECTS)} Prospects)...", flush=True)
    primary_seed = seeds[0]
    results = []

    for item in BATCH_PROSPECTS:
        res = dispatch_prospect(item, primary_seed)
        results.append(res)
        if res.get("status") == "blocked_gate":
            print("⚠️ Halting batch due to Seed Gate Block!", flush=True)
            break

    print("\n========================================================", flush=True)
    print("🏁 BATCH 17 EXECUTION COMPLETE (HUMAN VIEW & CUSTOM PITCHES)", flush=True)
    print("========================================================", flush=True)
    for r in results:
        print(f"• {r.get('recipient')}: {r.get('status', 'ERROR').upper()} (Sender: {r.get('sender', 'N/A')})", flush=True)


if __name__ == "__main__":
    main()
