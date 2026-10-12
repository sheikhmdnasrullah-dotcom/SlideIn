#!/usr/bin/env python3
import json
import imaplib
from pathlib import Path

HERE = Path(__file__).parent
with open(HERE / "config.json") as f:
    cfg = json.load(f)

seeds = cfg.get("seed_accounts", [])
print(f"Testing {len(seeds)} configured seed accounts...", flush=True)

valid_seeds = []
for s in seeds:
    email_addr = s["email"]
    pwd = s["password"]
    if pwd.startswith("FILL_IN"):
        print(f"⚪ {email_addr}: No password provided", flush=True)
        continue
    try:
        M = imaplib.IMAP4_SSL(s.get("host", "imap.gmail.com"), s.get("port", 993), timeout=10)
        M.login(email_addr, pwd)
        M.select("INBOX", readonly=True)
        typ, data = M.search(None, "ALL")
        inbox_count = len(data[0].split()) if data and data[0] else 0
        
        # Check spam folder
        spam_folder = s.get("spam_folder", "[Gmail]/Spam")
        spam_count = 0
        try:
            M.select(spam_folder, readonly=True)
            typ, sdata = M.search(None, "ALL")
            spam_count = len(sdata[0].split()) if sdata and sdata[0] else 0
        except Exception:
            pass
        
        M.logout()
        print(f"✅ {email_addr} | INBOX: {inbox_count} | SPAM: {spam_count}", flush=True)
        valid_seeds.append({
            "email": email_addr,
            "inbox": inbox_count,
            "spam": spam_count,
            "config": s
        })
    except Exception as e:
        print(f"❌ {email_addr}: Login failed ({e})", flush=True)

print(f"\nTotal verified working seeds: {len(valid_seeds)} / {len(seeds)}", flush=True)
