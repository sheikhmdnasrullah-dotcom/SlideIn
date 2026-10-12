#!/usr/bin/env python3
"""
assurance.py - legitimate pre-send deliverability assurance for the
nasrullahtanim.me cold-outreach pipeline (KumoMTA transport).

What this does (all legitimate, receiver-friendly):
  - Pre-flight content scoring: flags spam-trigger phrasing, image-only /
    no-plaintext bodies, and missing unsubscribe language.
  - Auth/DNS alignment check: SPF / DKIM selector / DMARC on the sending domain.
  - Compliance header injection: List-Unsubscribe (+ one-click), Precedence: bulk.
  - Builds a multipart message ready for KumoMTA.

What this does NOT do: forge provider headers, cloak URLs, or evade filters.
Run:  python3 assurance.py --from hello@nasrullahtanim.me --to seed@gmail.com \
        --subject "..." --plain plain.txt [--html html.html] [--unsub-url URL]
"""
import argparse, csv, json, re, socket, sys
try:
    import dns.resolver
except Exception:
    dns = None

SPAM_TRIGGERS = [
    r"\b100%\b", r"\bguarantee\b", r"\bfree\b", r"\bact now\b", r"\burgent\b",
    r"\blimited time\b", r"\bclick here\b", r"\bverify.{0,12}(account|password)\b",
    r"\byou have won\b", r"\bmake money\b", r"\brisk[- ]free\b",
    r"\bno cost\b", r"\boffer expires\b",
]
TRIGGER_RE = [re.compile(p, re.I) for p in SPAM_TRIGGERS]


def auth_alignment(domain, dkim_selector="dkim"):
    if dns is None:
        return {"spf": "skip(dnspython missing)", "dkim": "skip(dnspython missing)", "dmarc": "skip(dnspython missing)"}
    out = {}
    try:
        spf = dns.resolver.resolve(domain, "TXT")
        out["spf"] = any("v=spf1" in r.to_text() for r in spf)
    except Exception as e:
        out["spf"] = f"err:{e}"
    try:
        dkim = dns.resolver.resolve(f"{dkim_selector}._domainkey.{domain}", "TXT")
        out["dkim"] = bool(list(dkim))
    except Exception as e:
        out["dkim"] = f"err:{e}"
    try:
        dmarc = dns.resolver.resolve(f"_dmarc.{domain}", "TXT")
        out["dmarc"] = any("v=DMARC1" in r.to_text() for r in dmarc)
    except Exception as e:
        out["dmarc"] = f"err:{e}"
    return out


def content_preflight(plain, html=""):
    findings = []
    hits = []
    for rx in TRIGGER_RE:
        m = rx.search(plain + " " + html)
        if m:
            hits.append(m.group(0))
    if hits:
        findings.append(("MED", f"Spam-trigger language: {', '.join(set(hits))}"))
    if not plain.strip():
        findings.append(("HIGH", "No plain-text part (HTML-only hurts deliverability)"))
    if html and not plain.strip():
        findings.append(("MED", "Image/HTML-only body increases spam scoring"))
    if not re.search(r"unsubscrib", plain + " " + html, re.I):
        findings.append(("HIGH", "No unsubscribe language (Gmail/Yahoo bulk requirement)"))
    return findings


def build_message(frm, to, subject, plain, html, unsub_url, unsub_mailto):
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    import uuid, email.utils
    msg = MIMEMultipart("alternative")
    msg["From"] = frm
    msg["To"] = to
    msg["Subject"] = subject
    msg["Message-ID"] = f"<{uuid.uuid4().hex}@nasrullahtanim.me>"
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Precedence"] = "bulk"
    lst = []
    if unsub_mailto:
        lst.append(f"<mailto:{unsub_mailto}?subject=unsubscribe>")
    if unsub_url:
        lst.append(f"<{unsub_url}>")
    if lst:
        msg["List-Unsubscribe"] = ", ".join(lst)
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    if html:
        msg.attach(MIMEText(html, "html", "utf-8"))
    return msg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", required=True)
    ap.add_argument("--to", required=True)
    ap.add_argument("--subject", required=True)
    ap.add_argument("--plain", required=True, help="plain-text body file")
    ap.add_argument("--html", help="html body file")
    ap.add_argument("--unsub-url", help="https unsubscribe URL")
    ap.add_argument("--unsub-mailto", help="unsubscribe mailbox, e.g. unsubscribe@nasrullahtanim.me")
    ap.add_argument("--check-auth", action="store_true")
    ap.add_argument("--out", help="write built .eml here instead of sending")
    args = ap.parse_args()

    plain = open(args.plain, encoding="utf-8").read()
    html = open(args.html, encoding="utf-8").read() if args.html else ""
    domain = args.frm.split("@")[-1]

    print("=== Pre-flight content check ===")
    cf = content_preflight(plain, html)
    for sev, d in cf:
        print(f"  [{sev}] {d}")
    if not cf:
        print("  (clean)")

    if args.check_auth:
        print("=== Auth/DNS alignment ===")
        for k, v in auth_alignment(domain).items():
            print(f"  {k}: {v}")

    msg = build_message(args.frm, args.to, args.subject, plain, html,
                        args.unsub_url, args.unsub_mailto)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(msg.as_string())
        print(f"\nWrote prepared message -> {args.out}")
    else:
        print("\nPrepared message (headers):")
        for h in ("From", "To", "Subject", "Precedence", "List-Unsubscribe", "List-Unsubscribe-Post"):
            if h in msg:
                print(f"  {h}: {msg[h]}")


if __name__ == "__main__":
    main()
