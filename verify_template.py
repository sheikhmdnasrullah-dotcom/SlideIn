#!/usr/bin/env python3
"""Render approved_template.eml with sample vars (MIMEText = proper line wrapping),
send via KumoMTA, check seed Inbox vs Spam placement."""
import json, time, uuid, smtplib, ssl, imaplib
from email import message_from_string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

c = json.load(open("deliverability/config.json"))
K = c["kumo"]
seeds = c["seed_accounts"]

raw = open("deliverability/sample/approved_template.eml", encoding="utf-8").read()
src = message_from_string(raw)
SUBJECT = src["Subject"]
FROM = src["From"]
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE

def parts():
    plain = html = None
    for part in src.walk():
        if part.is_multipart():
            continue
        ct = part.get_content_type()
        p = part.get_payload(decode=True)
        if p is None:
            continue
        try:
            t = p.decode("utf-8")
        except Exception:
            continue
        if ct == "text/plain":
            plain = t
        elif ct == "text/html":
            html = t
    return plain, html

def render(to_addr):
    plain, html = parts()
    plain = (plain or "").replace("{{recipient}}", to_addr).replace("{{first_name}}","Tanim") \
        .replace("{{personalization_line}}","I came across your recent video on content workflow and thought the breakdown was genuinely useful.")
    html = (html or "").replace("{{recipient}}", to_addr).replace("{{first_name}}","Tanim") \
        .replace("{{personalization_line}}","I came across your recent video on content workflow and thought the breakdown was genuinely useful.")
    msg = MIMEMultipart("alternative")
    msg["From"] = FROM
    msg["To"] = to_addr
    msg["Subject"] = SUBJECT
    msg["Message-ID"] = f"<{uuid.uuid4().hex}@nasrullahtanim.me>"
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    if html:
        msg.attach(MIMEText(html, "html", "utf-8"))
    return msg

sent = []
for seed in seeds[:2]:
    to = seed["email"]
    m = render(to)
    mid = m["Message-ID"]
    s = smtplib.SMTP(K["host"], K["port"], timeout=30)
    s.ehlo(); s.starttls(context=ctx); s.ehlo()
    s.login(K["user"], K["password"])
    s.sendmail("hello@nasrullahtanim.me", [to], m.as_string())
    s.quit()
    sent.append((to, mid))
    print(f"[sent] -> {to}  id={mid}")

print("[wait 30s] Gmail filtering...")
time.sleep(30)

print("[check] placement:")
for to, mid in sent:
    seed = next(s for s in seeds if s["email"] == to)
    im = imaplib.IMAP4_SSL(seed["host"], seed["port"], ssl_context=ctx)
    im.login(seed["email"], seed["password"])
    res = {}
    for box in (seed.get("inbox_folder","INBOX"), seed.get("spam_folder","[Gmail]/Spam")):
        im.select(box)
        _, d = im.search(None, f'HEADER Message-ID "{mid}"')
        res[box] = d[0].decode().split() or "none"
    im.logout()
    print(f"  {to}: {res}")
