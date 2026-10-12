#!/usr/bin/env python3
"""
Next 10 Sends (Rows 82-91 in final_checklist_of_prospects.csv)
Key Rules:
1. ZERO em dashes (—) or en dashes (–) anywhere.
2. Exact opener: "Hey {Name}, I know you're busy and I promise I won't take more than two minutes of your time."
3. 100% Industry-Specific Tools & Workflows (no generic or mismatched suggestions):
   - Trading Education: Position sizing & risk calculator / 60-sec trader readiness test
   - Tech Interview Podcast: Video-to-reels workflow + weekly tech takeaway briefs
   - English Language Podcast: Audio-to-vocabulary reels + 60-sec English level placement test
   - Wealth & Philosophy Podcast: Podcast-to-reels workflow + guest coordination & listener routing
   - Workplace Safety Coaching: 60-sec workplace safety culture & risk diagnostic for site managers
   - Mindset / Personal Coach: Workshops-to-reels workflow + life alignment quiz & booking system
   - Asia Tech Podcast: Founder interview-to-reels workflow + weekly regional startup briefs
   - Cruise Travel Platform: Cruise vlog-to-reels workflow + cruise budget & itinerary planner tool
   - Leadership Consultant: 60-sec team culture & executive leadership diagnostic
   - Sustainable Packaging: Packaging sustainability & carbon footprint estimator for brand managers
4. Dual-Seed Verification: Checks BOTH 'tanimsyt@gmail.com' AND 'tanim.slideinventure5@gmail.com'.
5. Generous paragraph gaps (20px vertical gap, 1.6 line-height) in clean Apple Mail HTML.
6. Concise, punchy copy (~100 words), zero duplicate boilerplate.
7. Strictly pauses after these 10 sends to request user approval.
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

BATCH_TEN_PROSPECTS = [
    {
        "index": 82,
        "name": "Bernd",
        "email": "bernd@onlinetradingcampus.com",
        "subject": "Bernd?",
        "sender_email": "hello@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "trading education business",
        "body": """Hey Bernd, I know you're busy and I promise I won't take more than two minutes of your time.

I came across Online Trading Campus and really respect the disciplined approach you take to market education. I'm wondering if I could help you on both the outreach and student acquisition side.

Basically, I automate the repetitive backend tasks that take up your time. For example, I can build an interactive WebApp tool on your site (like a position sizing calculator or a 60-second trader readiness test) that captures leads, matches your ideal student profile, and automates personalized follow-ups.

Once running, I'm confident you'll see a lot more conversations and traction.

If you have time, I can break it down in a quick call. If not, I can send over a quick video showing how it works.

Either way, I'd love to help you build something great.

Thanks,
Tanim."""
    },
    {
        "index": 83,
        "name": "Tom",
        "email": "tom@tomorrow-podcast.com",
        "subject": "Tom?",
        "sender_email": "talk@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "technology journalism podcast",
        "body": """Hey Tom, I know you're busy and I promise I won't take more than two minutes of your time.

I've been following Tomorrow Podcast and really appreciate the depth you bring to conversations on emerging tech. I'm wondering if I could help you on both the content and client side.

Basically, I automate the repetitive backend tasks that take up your time. For example, I can turn your podcast recordings into a full week of short clips and reels scheduled across platforms, while keeping a human in the loop.

Once running, I'm confident you'll see a lot more conversations and traction.

If you have time, I can break it down in a quick call. If not, I can send over a quick video showing how it works.

Either way, I'd love to help you build something great.

Thanks,
Tanim."""
    },
    {
        "index": 84,
        "name": "Danny",
        "email": "danny@englishpluspodcast.com",
        "subject": "Danny?",
        "sender_email": "connect@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "English-teaching educational podcast",
        "body": """Hey Danny, I know you're busy and I promise I won't take more than two minutes of your time.

I've been following English Plus Podcast and really love how accessible you make language learning for your listeners. I'm wondering if I could help you on both the content and student side.

Basically, I automate the repetitive backend tasks that take up your time. For example, I can turn your audio lessons into daily bite-sized vocabulary reels across platforms, while an interactive 60-second English level test on your site captures prospective students and sends personalized study guides.

Once running, I'm confident you'll see a lot more conversations and traction.

If you have time, I can break it down in a quick call. If not, I can send over a quick video showing how it works.

Either way, I'd love to help you build something great.

Thanks,
Tanim."""
    },
    {
        "index": 85,
        "name": "Paul",
        "email": "paul@crazymoneypodcast.com",
        "subject": "Paul?",
        "sender_email": "hello@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "financial philosophy and lifestyle podcast",
        "body": """Hey Paul, I know you're busy and I promise I won't take more than two minutes of your time.

I've been listening to Crazy Money and really love the honest conversations you have around wealth and work. I'm wondering if I could help you on both the content and audience side.

Basically, I automate the repetitive backend tasks that take up your time. For example, I can turn full podcast interviews into a full week of punchy reels, YouTube Shorts, and LinkedIn takeaways, scheduled across platforms while keeping a human in the loop.

Once running, I'm confident you'll see a lot more conversations and traction.

If you have time, I can break it down in a quick call. If not, I can send over a quick video showing how it works.

Either way, I'd love to help you build something great.

Thanks,
Tanim."""
    },
    {
        "index": 86,
        "name": "David",
        "email": "david@newviewsafetycoach.com.au",
        "subject": "David?",
        "sender_email": "talk@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "safety coaching and workplace culture",
        "body": """Hey David, I know you're busy and I promise I won't take more than two minutes of your time.

I came across New View Safety Coach and really liked your practical focus on modern safety leadership. I'm wondering if I could help you on both the outreach and client side.

Basically, I automate the repetitive backend tasks that take up your time. For example, I can set up an interactive WebApp tool on your site (like a 60-second workplace safety culture diagnostic) that engages safety managers, matches your ideal client profile, and automates personalized follow-ups.

Once running, I'm confident you'll see a lot more conversations and traction.

If you have time, I can break it down in a quick call. If not, I can send over a quick video showing how it works.

Either way, I'd love to help you build something great.

Thanks,
Tanim."""
    },
    {
        "index": 87,
        "name": "Kelly",
        "email": "kelly@coachkellyj.com",
        "subject": "Kelly?",
        "sender_email": "connect@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "personal coaching and leadership development",
        "body": """Hey Kelly, I know you're busy and I promise I won't take more than two minutes of your time.

I went through your coaching work and really appreciated how clearly you structure mindset growth for your clients. I'm wondering if I could help you on both the content and client side.

Basically, I automate the repetitive backend tasks that take up your time. For example, I can turn your workshops and client talks into a full week of clean reels and carousels, while an automated lead system responds to new inquiries in seconds and handles consultation reminders.

Once running, I'm confident you'll see a lot more conversations and traction.

If you have time, I can break it down in a quick call. If not, I can send over a quick video showing how it works.

Either way, I'd love to help you build something great.

Thanks,
Tanim."""
    },
    {
        "index": 88,
        "name": "Michael",
        "email": "michael@asiatechpodcast.com",
        "subject": "Michael?",
        "sender_email": "hello@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "Asian tech innovation podcast",
        "body": """Hey Michael, I know you're busy and I promise I won't take more than two minutes of your time.

I've been following Asia Tech Podcast and really enjoyed your conversations with founders across the Asian tech ecosystem. I'm wondering if I could help you on both the content and client side.

Basically, I automate the repetitive backend tasks that take up your time. For example, I can turn your podcast recordings into a full week of reels and short clips across platforms with a human in the loop, while writing agents prepare weekly industry briefs for your listeners.

Once running, I'm confident you'll see a lot more conversations and traction.

If you have time, I can break it down in a quick call. If not, I can send over a quick video showing how it works.

Either way, I'd love to help you build something great.

Thanks,
Tanim."""
    },
    {
        "index": 89,
        "name": "Andrew",
        "email": "andrew@thechillcruiser.blog",
        "subject": "Andrew?",
        "sender_email": "talk@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "travel and cruise content platform",
        "body": """Hey Andrew, I know you're busy and I promise I won't take more than two minutes of your time.

I saw what you have been putting out at The Chill Cruiser and found your cruise reviews and itinerary breakdowns genuinely valuable. I'm wondering if I could help you on both the content and audience side.

Basically, I automate the repetitive backend tasks that take up your time. For example, I can turn your video walkthroughs into a full week of reels and TikTok clips, alongside an interactive cruise budget planner on your site that captures travelers' emails and sends personalized deal alerts.

Once running, I'm confident you'll see a lot more conversations and traction.

If you have time, I can break it down in a quick call. If not, I can send over a quick video showing how it works.

Either way, I'd love to help you build something great.

Thanks,
Tanim."""
    },
    {
        "index": 90,
        "name": "Todd",
        "email": "todd@toddturner.com",
        "subject": "Todd?",
        "sender_email": "connect@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "executive consulting and keynote leadership",
        "body": """Hey Todd, I know you're busy and I promise I won't take more than two minutes of your time.

I've been following your recent work and really enjoyed the clarity you bring to executive leadership and team performance. I'm wondering if I could help you on both the outreach and client side.

Basically, I automate the repetitive backend tasks that take up your time. For example, I can build an interactive WebApp tool on your site (like a 60-second team culture diagnostic) that engages corporate leaders, identifies their organization profile, and automates personalized outreach and meeting bookings.

Once running, I'm confident you'll see a lot more conversations and traction.

If you have time, I can break it down in a quick call. If not, I can send over a quick video showing how it works.

Either way, I'd love to help you build something great.

Thanks,
Tanim."""
    },
    {
        "index": 91,
        "name": "Estal",
        "email": "estal@estal.com",
        "subject": "Estal?",
        "sender_email": "hello@nasrullahtanim.me",
        "sender_name": "Nasrullah Tanim",
        "niche": "sustainable packaging design and manufacturing",
        "body": """Hey Estal, I know you're busy and I promise I won't take more than two minutes of your time.

I came across Estal recently and really enjoyed your focus on sustainable glass design and packaging for premium brands. I'm wondering if I could help streamline things on both the outreach and client side.

Basically, I automate the repetitive backend tasks that take up your time. For example, I can set up an interactive WebApp tool on your site that allows brand managers to estimate packaging specs and carbon savings, while automatically routing qualified project details to your sales team.

Once running, I'm confident you'll see a lot more conversations and traction.

If you have time, I can break it down in a quick call. If not, I can send over a quick video showing how it works.

Either way, I'd love to help you build something great.

Thanks,
Tanim."""
    }
]


def verify_dual_seeds(config, sender_email, subject, body, niche):
    """
    Dual-seed gate: Requires 100% Primary [INBOX] placement on BOTH:
    1. tanimsyt@gmail.com
    2. tanim.slideinventure5@gmail.com
    """
    seeds_map = {s["email"]: s for s in config.get("seed_accounts", [])}
    dual_targets = ["tanimsyt@gmail.com", "tanim.slideinventure5@gmail.com"]
    
    print("\n🔍 EXECUTING DUAL-SEED GATE PRE-CHECK (tanimsyt + slideinventure5)...", flush=True)
    all_passed = True
    
    for seed_email in dual_targets:
        seed_cfg = seeds_map.get(seed_email)
        if not seed_cfg:
            print(f"⚠️ Seed config for {seed_email} not found!", flush=True)
            return False
            
        test_msg, meta = build_bulletproof_email(
            from_name="Nasrullah Tanim",
            from_addr=sender_email,
            to_name="Test",
            to_addr=seed_email,
            subject=subject,
            body_text=body,
            enable_spintax=False,
            niche=niche
        )
        test_bytes = test_msg.as_bytes()
        send_smtp(config, sender_email, seed_email, test_bytes)
        
        folder, _ = check_seed_placement(seed_cfg, meta["message_id"], timeout=30)
        print(f"   📡 Seed [{seed_email}]: [{folder}]", flush=True)
        if folder != "INBOX":
            all_passed = False
            
    return all_passed


def dispatch_prospect(item: dict) -> dict:
    config = load_config()
    store = st.Store(str(STATE_PATH))

    recipient_email = item["email"]
    recipient_name = item["name"]
    sender_email = item["sender_email"]
    sender_name = item["sender_name"]
    subject = item["subject"]
    body = item["body"]
    niche = item.get("niche", "business workflow")

    # Safety checks
    assert "—" not in body and "–" not in body, f"Em dash detected in body for {recipient_email}!"
    assert "—" not in subject and "–" not in subject, f"Em dash detected in subject for {recipient_email}!"

    if store.is_suppressed(recipient_email):
        print(f"⚠️ Recipient {recipient_email} is suppressed. Skipping.", flush=True)
        return {"status": "skipped_suppressed", "recipient": recipient_email}

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
    print("-" * 60, flush=True)

    # Dual-seed gate check
    passed_dual = verify_dual_seeds(config, sender_email, subject, body, niche)
    if not passed_dual:
        print(f"❌ BLOCKED BY DUAL-SEED GATE: Placement failed. Halting send to {recipient_email}.", flush=True)
        store.record_send_event(
            recipient=recipient_email,
            provider="kumomta",
            result="blocked_gate",
            detail="Dual seed placement failed",
        )
        return {"status": "blocked_gate", "recipient": recipient_email}

    print("🎉 DUAL-SEED GATE PASSED: Both inboxes verified 100% Primary!", flush=True)

    # Build and send to actual prospect
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

    print(f"🚀 Dispatching Verified Email to Prospect ({recipient_email})...", flush=True)
    send_smtp(config, sender_email, recipient_email, prospect_bytes)
    print(f"✅ DELIVERED to {recipient_email}! (MsgId: {prospect_msg_id})", flush=True)

    store.record_send_event(
        recipient=recipient_email,
        provider="kumomta",
        result="sent",
        detail=f"Delivered via KumoMTA with dual-seed gate verified. MsgId: {prospect_msg_id}",
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
    print(f"🚀 Preparing dispatch for batch of exactly 10 prospects...", flush=True)
    results = []

    for item in BATCH_TEN_PROSPECTS:
        res = dispatch_prospect(item)
        results.append(res)
        if res.get("status") == "blocked_gate":
            print("⚠️ Halting batch due to Dual-Seed Gate Block!", flush=True)
            break

    print("\n========================================================", flush=True)
    print(f"🏁 BATCH OF 10 COMPLETED: {len([r for r in results if r.get('status') == 'sent'])} SENT", flush=True)
    print("🛑 PAUSING OUTREACH. WAITING FOR USER APPROVAL FOR NEXT BATCH.", flush=True)
    print("========================================================", flush=True)


if __name__ == "__main__":
    main()
