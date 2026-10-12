#!/usr/bin/env python3
"""Verification: send from each of the 3 KumoMTA profiles to an owned seed Gmail,
then check Inbox vs Spam placement via IMAP. Local-only, uses existing config."""
import json, time, email.utils, imaplib, smtplib, ssl

c = json.load(open("deliverability/config.json"))
K = c["kumo"]
profiles = c["profiles"]
seed = c["seed_accounts"][0]  # owned seed mailbox we can read

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def send(from_addr):
    msg = (
        f"From: {from_addr}\r\n"
        f"To: {seed['email']}\r\n"
        f"Subject: deliverability verification - {from_addr}\r\n"
        f"Message-ID: <{int(time.time())}.{from_addr.replace('@','_')}@nasrullahtanim.me>\r\n"
        f"Date: {email.utils.formatdate(localtime=True)}\r\n"
        f"MIME-Version: 1.0\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n\r\n"
        f"This is a deliverability placement test from {from_addr} via KumoMTA.\r\n"
    )
    s = smtplib.SMTP(K["host"], K["port"], timeout=30)
    s.ehlo(); s.starttls(context=ctx); s.ehlo()
    s.login(K["user"], K["password"])
    s.sendmail(from_addr, [seed["email"]], msg)
    s.quit()
    print(f"[sent] {from_addr} -> {seed['email']}")

def check_placement():
    im = imaplib.IMAP4_SSL(seed["host"], seed["port"], ssl_context=ctx)
    im.login(seed["email"], seed["password"])
    res = {}
    for box in (seed.get("inbox_folder","INBOX"), seed.get("spam_folder","[Gmail]/Spam")):
        try:
            im.select(box)
            _, data = im.search(None, "FROM", "nasrullahtanim.me")
            res[box] = data[0].split()[-3:]  # last few msg ids
        except Exception as e:
            res[box] = f"err {e}"
    im.logout()
    return res

for p in profiles:
    send(p)
    time.sleep(2)

print("[wait] letting Gmail filter (25s)...")
time.sleep(25)
print("[check] IMAP placement:")
for box, ids in check_placement().items():
    print(f"  {box}: {ids}")
