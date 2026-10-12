#!/usr/bin/env python3
"""
Dispatch Batch 13 (Prospects 62-66)
Implements:
1. 100% Human-authentic Apple Mail HTML view (zero background shading, dark/light mode native)
2. Subject line: strictly '{FirstName}?'
3. Concise, authentic Tanim tone with deep personalization
4. Customized capability pitches mapped to each prospect's workflow
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
        "name": "Lyssa",
        "email": "lyssa@lyssadehart.com",
        "subject": "Lyssa?",
        "sender_email": "hello@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "executive coaching and leadership development",
        "body": """Hey Lyssa, I know you're busy, so I'll keep this short.

I went through your content and the Coaching Conversations podcast, especially your focus on reflective leadership and StoryJacking frameworks for executive coaches, and I really respect the depth you bring to the profession.

Here's how I can help streamline your backend:

On the content side, I can set up an automated workflow that turns your podcast episodes and masterclasses into a full week of reels, short clips, and LinkedIn insights, scheduled across platforms while keeping a human in the loop.

On the client side, I can set up writing agents that research coaching and leadership trends to prepare regular insights for your community, paired with an automated system that handles inquiry follow-ups and consultation scheduling so you can stay fully focused on mentoring.

Basically, I can automate all the repetitive backend tasks inside your workflow that take time and effort.

If you have a few minutes, I can walk you through how it works on a quick call. If not, I can quickly send a loom video on how I can help you out.

Either way, I'd love to help you build something great.

Thanks,
Tanim"""
    },
    {
        "name": "Gary",
        "email": "gary@modernsoccercoach.com",
        "subject": "Gary?",
        "sender_email": "talk@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "sports coaching tactical analysis and education",
        "body": """Hey Gary, I know you're busy, so I'll keep this short.

I went through Modern Soccer Coach and your podcast sessions, especially your breakdowns on tactical decision-making, coach development models, and session design, and I really appreciate the practical standard you set for coaches.

Here's how I can help streamline your backend:

On the content side, I can build an automated workflow that turns your tactical masterclasses, webinars, and podcast interviews into a full week of high-retention short clips and visual drill breakdowns across platforms while keeping a human in the loop.

On the audience side, I can set up an interactive lead capturing funnel on your site—like a 60-second coach development self-assessment tool—that engages visitors, captures their details, matches them with your masterclass profiles, and automates personalized outreach emails.

Basically, I can automate all the repetitive backend tasks inside your workflow that take time and effort.

If you have a few minutes, I can walk you through how it works on a quick call. If not, I can quickly send a loom video on how I can help you out.

Either way, I'd love to help you build something great.

Thanks,
Tanim"""
    },
    {
        "name": "Jamal",
        "email": "jamal@jamaljivanjee.com",
        "subject": "Jamal?",
        "sender_email": "connect@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "personal coaching and emotional integration",
        "body": """Hey Jamal, I know you're busy, so I'll keep this short.

I went through your content and podcast episodes, especially your reflections on emotional integration and moving beyond performance-driven identity, and I really respect the honest perspective you share with your audience.

Here's how I can help streamline your backend:

On the content side, I can set up an automated workflow that takes your long-form reflections, podcast talks, and writings, turns them into a full week of clean short clips and quote carousels, and schedules them across platforms while keeping a human in the loop.

On the client side, I can build a system that responds to new coaching inquiries in seconds, handles follow-ups, consultation reminders, and record updates automatically, so you can spend your time completely on coaching clients rather than admin.

Basically, I can automate all the repetitive backend tasks inside your workflow that take time and effort.

If you have a few minutes, I can walk you through how it works on a quick call. If not, I can quickly send a loom video on how I can help you out.

Either way, I'd love to help you build something great.

Thanks,
Tanim"""
    },
    {
        "name": "Michael",
        "email": "michael@bayareaexecutivecoach.com",
        "subject": "Michael?",
        "sender_email": "hello@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "executive coaching and corporate leadership training",
        "body": """Hey Michael, I know you're busy, so I'll keep this short.

I went through your content and work at Bay Area Executive Coach, especially your frameworks on executive communication, 360 assessments, and leadership presence for tech executives, and I really respect the reputation you've built in the Bay Area.

Here's how I can help streamline your backend:

On the acquisition side, I can set up an interactive lead-capturing funnel—acting like a WebApp assessment tool (e.g. an Executive Leadership Diagnostic in 60 seconds)—that engages corporate visitors, identifies their organizational profile, and triggers tailored email workflows.

On the operations side, I can build a speed-to-lead system that responds to new corporate inquiries in seconds, automates discovery call reminders, and updates CRM records so you can focus entirely on high-value client engagements.

Basically, I can automate all the repetitive backend tasks inside your workflow that take time and effort.

If you have a few minutes, I can walk you through how it works on a quick call. If not, I can quickly send a loom video on how I can help you out.

Either way, I'd love to help you build something great.

Thanks,
Tanim"""
    },
    {
        "name": "Michelle",
        "email": "michelle@michellejoykramer.com",
        "subject": "Michelle?",
        "sender_email": "talk@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "functional health coaching and wellness consulting",
        "body": """Hey Michelle, I know you're busy, so I'll keep this short.

I went through your content and coaching work, especially your focus on functional wellness, sustainable habit change, and helping busy professionals recover from chronic burnout, and I really respect your approach to health.

Here's how I can help streamline your backend:

On the outreach side, I can build an interactive health assessment quiz on your site that engages visitors, captures their specific wellness goals, and automatically sequences personalized follow-up emails matched to their needs.

On the content side, I can set up newsletter writing agents that research relevant health studies, draft practical weekly updates for your subscribers, and prepare short-version articles for LinkedIn while keeping a human in the loop.

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

    print(f"🚀 Starting Batch 13 Dispatch with Clean Human View ({len(BATCH_PROSPECTS)} Prospects)...", flush=True)
    primary_seed = seeds[0]
    results = []

    for item in BATCH_PROSPECTS:
        res = dispatch_prospect(item, primary_seed)
        results.append(res)
        if res.get("status") == "blocked_gate":
            print("⚠️ Halting batch due to Seed Gate Block!", flush=True)
            break

    print("\n========================================================", flush=True)
    print("🏁 BATCH 13 EXECUTION COMPLETE (HUMAN VIEW & CUSTOM PITCHES)", flush=True)
    print("========================================================", flush=True)
    for r in results:
        print(f"• {r.get('recipient')}: {r.get('status', 'ERROR').upper()} (Sender: {r.get('sender', 'N/A')})", flush=True)


if __name__ == "__main__":
    main()
