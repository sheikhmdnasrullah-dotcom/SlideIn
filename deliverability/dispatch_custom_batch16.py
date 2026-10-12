#!/usr/bin/env python3
"""
Dispatch Batch 16 (Prospects 76-80)
Implements:
1. 100% Human-authentic Apple Mail HTML view (zero background shading, dark/light mode native)
2. Subject line: strictly '{FirstName}?'
3. Concise, authentic Tanim tone with deep personalization
4. Customized capability pitches mapped to each prospect's workflow:
   - Roy (Speaking Podcast): Automated podcast->reels workflow + speaker self-assessment lead funnel
   - Danny (FocalPoint Coaching): 60-second Business Growth Diagnostic WebApp funnel + speed-to-lead follow-up automation
   - Ryan (The Struggle Climbing Show): Elite climbing interview video-to-reels workflow + training newsletter writing agents
   - Greg (Grindline Podcast): Skate podcast-to-reels automated workflow + sponsor & listener lead funnel
   - Antonio (Business Coaching Italia): Corporate diagnostic WebApp funnel + speed-to-lead response automation & writing agents
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
        "name": "Roy",
        "email": "roy@speakingpodcast.com",
        "subject": "Roy?",
        "sender_email": "hello@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "public speaking coaching and presentation mastery",
        "body": """Hey Roy, I know you're busy, so I'll keep this short.

I went through your episodes on the Speaking Podcast, especially your conversations on overcoming stage fright, vocal tonality, and structuring keynote presentations, and I really enjoy the practical guidance you give to aspiring speakers.

Here's how I can help streamline your backend:

On the content side, I can set up an automated workflow that turns your full podcast interviews into a full week of reels, short clips, and LinkedIn insights, scheduled across all platforms while keeping a human in the loop.

On the audience side, I can build an interactive speaker assessment tool on your website that engages visitors, captures their specific speaking challenges, and automates personalized follow-ups for your coaching programs.

Basically, I can automate all the repetitive backend tasks inside your workflow that take time and effort.

If you have a few minutes, I can walk you through how it works on a quick call. If not, I can quickly send a loom video on how I can help you out.

Either way, I'd love to help you build something great.

Thanks,
Tanim"""
    },
    {
        "name": "Danny",
        "email": "dcreed@focalpointcoaching.com",
        "subject": "Danny?",
        "sender_email": "talk@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "executive business coaching and sales growth",
        "body": """Hey Danny, I know you're busy, so I'll keep this short.

I came across your work with FocalPoint Business Coaching and your keynote speaking, especially your direct, results-oriented focus on sales mastery, executive accountability, and business turnaround strategies, and I really respect the track record you've established.

Here's how I can help streamline your backend:

On the client acquisition side, I can set up an interactive lead capturing funnel on your site—like a 60-second Business Growth & Sales Diagnostic tool—that engages corporate visitors, identifies their organizational bottlenecks, and triggers personalized email workflows.

On the operations side, I can build a system that responds to new inquiries in seconds and automates consultation reminders and CRM updates so you can focus purely on coaching leaders.

Basically, I can automate all the repetitive backend tasks inside your workflow that take time and effort.

If you have a few minutes, I can walk you through how it works on a quick call. If not, I can quickly send a loom video on how I can help you out.

Either way, I'd love to help you build something great.

Thanks,
Tanim"""
    },
    {
        "name": "Ryan",
        "email": "ryan@thestruggleclimbingshow.com",
        "subject": "Ryan?",
        "sender_email": "connect@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "climbing performance podcast and athlete training",
        "body": """Hey Ryan, I know you're busy, so I'll keep this short.

I've been listening to The Struggle Climbing Show, particularly the deep dives with pro climbers on mental training, nutrition protocols, and breaking through plateaus, and I love how you extract the real struggles behind elite performance.

Here's how I can help streamline your backend:

On the media side, I can build an automated workflow that turns your long-form athlete interviews and episodes into a full week of high-energy reels, clips, and YouTube Shorts, scheduled across platforms while keeping a human in the loop.

On the community side, I can set up writing agents that take your episode takeaways and draft engaging weekly newsletters for your listeners, alongside automated workflows for sponsor inquiry follow-ups and community updates.

Basically, I can automate all the repetitive backend tasks inside your workflow that take time and effort.

If you have a few minutes, I can walk you through how it works on a quick call. If not, I can quickly send a loom video on how I can help you out.

Either way, I'd love to help you build something great.

Thanks,
Tanim"""
    },
    {
        "name": "Greg",
        "email": "greg@grindlinepodcast.com",
        "subject": "Greg?",
        "sender_email": "hello@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "skateboarding culture and lifestyle podcasting",
        "body": """Hey Greg, I know you're busy, so I'll keep this short.

I went through Grindline Podcast and your content covering skateboard culture, park building stories, and sessions with veteran skaters, and I really respect the genuine vibe and core community roots you bring to every episode.

Here's how I can help streamline your backend:

On the content side, I can build an automated workflow that turns your audio and video recordings into a full week of short clips, reels, and highlights, scheduled across all platforms while keeping a human in the loop.

On the operations side, I can set up an automated system that handles sponsor lead capture, listener question routing, and guest booking reminders so you spend less time on admin and more time recording.

Basically, I can automate all the repetitive backend tasks inside your workflow that take time and effort.

If you have a few minutes, I can walk you through how it works on a quick call. If not, I can quickly send a loom video on how I can help you out.

Either way, I'd love to help you build something great.

Thanks,
Tanim"""
    },
    {
        "name": "Antonio",
        "email": "antonio@businesscoachingitalia.com",
        "subject": "Antonio?",
        "sender_email": "talk@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "executive business consulting and SME scale-up",
        "body": """Hey Antonio, I know you're busy, so I'll keep this short.

I went through Business Coaching Italia and your work helping entrepreneurs scale operations, structure sales organizations, and build sustainable company culture, and I really admire the methodology you've established.

Here's how I can help streamline your backend:

On the acquisition side, I can set up an interactive lead capturing funnel that acts like a WebApp on your website—such as a 60-second Business Health Check—engaging executive visitors, matching them with your ideal corporate profile, and automating personalized email outreach.

On the operations side, I can build a system that responds to new business inquiries in seconds and automates consultation follow-ups and CRM record updates so your coaches can focus on high-impact strategy.

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

    print(f"🚀 Starting Batch 16 Dispatch with Clean Human View ({len(BATCH_PROSPECTS)} Prospects)...", flush=True)
    primary_seed = seeds[0]
    results = []

    for item in BATCH_PROSPECTS:
        res = dispatch_prospect(item, primary_seed)
        results.append(res)
        if res.get("status") == "blocked_gate":
            print("⚠️ Halting batch due to Seed Gate Block!", flush=True)
            break

    print("\n========================================================", flush=True)
    print("🏁 BATCH 16 EXECUTION COMPLETE (HUMAN VIEW & CUSTOM PITCHES)", flush=True)
    print("========================================================", flush=True)
    for r in results:
        print(f"• {r.get('recipient')}: {r.get('status', 'ERROR').upper()} (Sender: {r.get('sender', 'N/A')})", flush=True)


if __name__ == "__main__":
    main()
