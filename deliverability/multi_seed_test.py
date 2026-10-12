#!/usr/bin/env python3
"""
Multi-Seed Test Across Diverse Seed Accounts
Tests true inbox vs spam placement across accounts with different historical interactions:
1. tanim.slideinventure5@gmail.com (Positive history)
2. contacttanim24@gmail.com (Negative history: previously 51 in spam)
3. tanimsyt@gmail.com (Negative history: previously 82 in spam)
4. tanim.slideinventure3@gmail.com (Mixed history)
5. contacttanim21@gmail.com (Positive history)
"""
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from preflight_verifier import load_config
from advanced_deliverability import build_bulletproof_email
from dispatch_custom_batch11 import send_smtp, check_seed_placement

config = load_config()

TEST_SEEDS = [
    "tanim.slideinventure5@gmail.com",
    "contacttanim24@gmail.com",
    "tanimsyt@gmail.com",
    "tanim.slideinventure3@gmail.com",
    "contacttanim21@gmail.com"
]

seeds_map = {s["email"]: s for s in config.get("seed_accounts", [])}

# Tanim's exact human tone (zero AI formatting)
SUBJECT = "Test?"
BODY = """Hey, I know you're very busy, and I promise not to take more than two minutes of your time.

I've been following your recent work and really enjoyed the clarity and structure you bring to your content.

I've been going through your content and everything you're doing on social media, and really appreciate the work and effort you put into it. I'm wondering if I could help you on both the content and client side.

Basically, I can automate all the repetitive backend task inside a business workflow that takes time and effort. For example, I can create an automated workflow that will turn podcast and video recordings into a full week of reels and clips, and schedule them across all platforms while keeping a human in the loop.

Once everything is running, I'm confident you'll see a lot more conversations and traction.

If you have time, I can break everything down in a quick Zoom call. If not, I can quickly send a loom video on how I can help you out.

Either way, I'd love to work together to grow and build something great.

Thanks,
Tanim."""

print("============================================================", flush=True)
print("🔬 MULTI-SEED INBOX PLACEMENT TEST (5 DIVERSE SEEDS)", flush=True)
print("============================================================", flush=True)

results = {}

for email_addr in TEST_SEEDS:
    seed_cfg = seeds_map.get(email_addr)
    if not seed_cfg:
        continue
    
    print(f"\n📡 Testing Seed: {email_addr}...", flush=True)
    msg, meta = build_bulletproof_email(
        from_name="Nasrullah Tanim",
        from_addr="hello@nasrullahtanim.me",
        to_name="Test",
        to_addr=email_addr,
        subject=SUBJECT,
        body_text=BODY,
        enable_spintax=False,
        niche="podcast content and business automation"
    )
    msg_bytes = msg.as_bytes()
    msg_id = meta["message_id"]
    
    send_smtp(config, "hello@nasrullahtanim.me", email_addr, msg_bytes)
    print(f"   Sent MsgId: {msg_id}. Waiting for Gmail IMAP sync...", flush=True)
    
    folder, detail = check_seed_placement(seed_cfg, msg_id, timeout=30)
    print(f"   🏁 Result for {email_addr}: [{folder}] (Detail: {detail})", flush=True)
    results[email_addr] = folder
    time.sleep(5)

print("\n" + "=" * 60, flush=True)
print("📊 FINAL MULTI-SEED PLACEMENT AUDIT SUMMARY", flush=True)
print("=" * 60, flush=True)
for s, res in results.items():
    emoji = "✅" if res == "INBOX" else "❌"
    print(f" {emoji} {s:34} => [{res}]", flush=True)
