#!/usr/bin/env python3
import json
import imaplib
from pathlib import Path

HERE = Path(__file__).parent
with open(HERE / "config.json") as f:
    cfg = json.load(f)

seeds = cfg.get("seed_accounts", [])
print(f"Auditing prior history across seeds...", flush=True)

clean_seeds = []
history_seeds = []

for s in seeds:
    email_addr = s["email"]
    pwd = s["password"]
    if pwd.startswith("FILL_IN") or "slideinventure1" in email_addr:
        continue
    try:
        M = imaplib.IMAP4_SSL(s.get("host", "imap.gmail.com"), s.get("port", 993), timeout=10)
        M.login(email_addr, pwd)
        
        # Check INBOX for nasrullahtanim.me
        M.select("INBOX", readonly=True)
        typ, data = M.search(None, 'FROM "nasrullahtanim.me"')
        inbox_count = len(data[0].split()) if data and data[0] else 0
        
        # Check SPAM for nasrullahtanim.me
        spam_folder = s.get("spam_folder", "[Gmail]/Spam")
        spam_count = 0
        try:
            M.select(spam_folder, readonly=True)
            typ, sdata = M.search(None, 'FROM "nasrullahtanim.me"')
            spam_count = len(sdata[0].split()) if sdata and sdata[0] else 0
        except Exception:
            pass
        
        M.logout()
        total_from_domain = inbox_count + spam_count
        print(f"• {email_addr:34} | prior from nasrullahtanim.me: {total_from_domain} (Inbox: {inbox_count}, Spam: {spam_count})", flush=True)
        
        if total_from_domain == 0:
            clean_seeds.append(s)
        else:
            history_seeds.append(s)
    except Exception as e:
        print(f"❌ {email_addr}: {e}", flush=True)

print(f"\nFresh seeds with ZERO prior connection: {len(clean_seeds)}", flush=True)
for cs in clean_seeds:
    print(f"  ⭐ {cs['email']}")
