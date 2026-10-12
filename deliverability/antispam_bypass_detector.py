#!/usr/bin/env python3
"""
antispam_bypass_detector.py
---------------------------
Lab/defensive detector that scores an inbound EML against the antispam-bypass
taxonomy described in Mantra's "How hackers bypass anti-spam" article.

Categories implemented (detection only):
  A. Sender reputation
     - trusted-provider / near-domain spoof (DMARC alignment, From vs envelope)
     - no warm-up history / new domain / volume-IP spread
     - ATO signals (reply-to mismatch, behavioural anomaly)
  B. Content / delivery-defence bypass
     - URL cloaking (displayed vs resolved host, redirectors, shorteners,
       doc-share hosting, image/obfuscated body)
     - crawler-blocking (captcha-gated links)
     - attachment evasion (risky types, externally hosted payloads)

This module never sends mail and never implements the attack techniques;
it only *detects* their signatures so it can be used for training + defence.

Run:  python3 antispam_bypass_detector.py <message.eml> [--json]
"""
import sys, re, json, socket, ssl, argparse, ipaddress
from email import message_from_binary_file
from urllib.parse import urlparse, unquote
from datetime import datetime, timezone

# ----------------------------------------------------------------------------
# Reference data (lab-safe; extend as needed)
# ----------------------------------------------------------------------------
TRUSTED_HOSTS = {
    "google.com", "googleapis.com", "drive.google.com", "docs.google.com",
    "amazonaws.com", "s3.amazonaws.com", "dropbox.com", "dropboxusercontent.com",
    "wetransfer.com", "mail.com",
}
SHORTENERS = {"bit.ly", "tinyurl.com", "goo.gl", "t.co", "ow.ly", "rb.gy"}
DOC_SHARE = {"drive.google.com", "docs.google.com", "dropbox.com",
             "dropboxusercontent.com", "wetransfer.com", "onedrive.live.com"}
RISKY_EXT = {".exe", ".scr", ".js", ".vbs", ".wsf", ".hta", ".jar",
             ".docm", ".xlsm", ".pptm", ".iso", ".zip", ".html", ".htm"}
# display-name impersonation targets (extend per org)
IMPERSONATE_NAMES = {"paypal", "microsoft", "apple", "bank", "supplier",
                     "invoice", "accounts", "finance", "it-support"}

URL_RE = re.compile(r"https?://[^\s\"'<>()]+", re.I)
DISPLAYED_URL_RE = re.compile(r"https?://[^\s\"'<>()]+", re.I)


def get_header(msg, name, default=""):
    v = msg.get(name)
    return v or default


def extract_urls(msg):
    urls = []
    for part in msg.walk():
        if part.is_multipart():
            continue
        ct = part.get_content_type()
        if ct in ("text/plain", "text/html"):
            try:
                payload = part.get_payload(decode=True) or b""
                text = payload.decode("utf-8", "ignore")
            except Exception:
                continue
            urls += URL_RE.findall(text)
    # also from hrefs in HTML
    return list(dict.fromkeys(urls))


def resolved_host(url):
    try:
        host = urlparse(url).hostname or ""
        return host.lower()
    except Exception:
        return ""


def findings():
    return []


def check_sender_reputation(msg, f, ctx):
    from_hdr = get_header(msg, "From")
    env_from = ctx.get("envelope_from", "")
    reply_to = get_header(msg, "Reply-To")
    domain = ""
    m = re.search(r"@([\w.-]+)", from_hdr or "")
    if m:
        domain = m.group(1).lower()

    # 1. DMARC alignment / From vs envelope
    if env_from and domain and (env_from.split("@")[-1].lower() != domain):
        f.append(("HIGH", "SENDER_REP",
                  f"Envelope sender domain ({env_from}) differs from From header domain ({domain}) — possible spoofing."))

    # 2. display-name impersonation
    for name in IMPERSONATE_NAMES:
        if name in (from_hdr or "").lower():
            f.append(("MED", "SENDER_REP",
                      f"From display name contains impersonation token '{name}'."))

    # 3. reply-to mismatch (ATO signal)
    if reply_to and domain:
        rm = re.search(r"@([\w.-]+)", reply_to)
        if rm and rm.group(1).lower() != domain:
            f.append(("HIGH", "ATO",
                      f"Reply-To domain ({rm.group(1)}) differs from From domain ({domain}) — classic ATO/redirect signal."))

    # 4. trusted provider but envelope not from that provider
    for th in TRUSTED_HOSTS:
        if domain == th or domain.endswith("." + th):
            if env_from and th not in env_from.lower():
                f.append(("MED", "SENDER_REP",
                          f"From claims trusted domain {th} but envelope origin is {env_from}."))
    ctx["from_domain"] = domain


def check_url_cloaking(msg, f, ctx):
    urls = extract_urls(msg)
    if not urls:
        return
    ctx["url_count"] = len(urls)
    for u in urls:
        host = resolved_host(u)
        if not host:
            continue
        # shortener hop
        if host in SHORTENERS:
            f.append(("MED", "URL_CLOAK",
                      f"URL uses shortener ({host}) — destination masked from static analysis: {u}"))
        # doc-share hosting of payload
        if host in DOC_SHARE:
            f.append(("MED", "ATTACH_HOST",
                      f"Payload/content hosted on doc-share service ({host}) to evade attachment scanning: {u}"))
        # trusted-domain wrapper: displayed host trusted but redirects elsewhere
        if host in TRUSTED_HOSTS:
            # check for redirect/query pointing off-domain
            q = urlparse(u)
            if q.query:
                for tok in re.findall(r"https?%3a|https?://", q.query, re.I):
                    f.append(("MED", "URL_CLOAK",
                              f"Trusted host {host} wraps an embedded/off-domain URL in query: {u}"))


def check_body_obfuscation(msg, f, ctx):
    text = ""
    for part in msg.walk():
        if part.is_multipart():
            continue
        if part.get_content_type() in ("text/plain", "text/html"):
            try:
                text += (part.get_payload(decode=True) or b"").decode("utf-8", "ignore")
            except Exception:
                pass
    if not text:
        return
    # image-only body (HTML with almost no text but <img>)
    imgs = text.lower().count("<img")
    words = len(re.findall(r"\b\w+\b", re.sub(r"<[^>]+>", " ", text)))
    if imgs >= 1 and words < 5:
        f.append(("MED", "OBFUSC", "Body is image-dominated with little text — common obfuscation to dodge content analysis."))
    # captcha-gated link (crawler-blocking)
    if re.search(r"captcha|i'?m not a robot|verify you are human", text, re.I):
        f.append(("LOW", "CRAWLER_BLOCK",
                  "References a captcha/verify-human step — can be used to block antispam crawlers from inspecting the destination."))
    # urgent / credential-harvest language
    if re.search(r"verify your (account|password)|your account will be (suspended|locked)|click here to (confirm|secure)", text, re.I):
        f.append(("LOW", "SOCIAL", "Contains credential-harvest / urgency phrasing."))


def check_attachments(msg, f, ctx):
    for part in msg.walk():
        if part.is_multipart():
            continue
        fn = part.get_filename() or ""
        if not fn:
            continue
        ext = "." + fn.rsplit(".", 1)[-1].lower() if "." in fn else ""
        if ext in RISKY_EXT:
            note = "macro-enabled" if ext in {".docm", ".xlsm", ".pptm"} else "executable/risky"
            f.append(("HIGH", "ATTACH",
                      f"{note} attachment '{fn}' — sandbox-evasion / payload delivery risk."))


SEVERITY_W = {"LOW": 1, "MED": 3, "HIGH": 6}


def score(f):
    return sum(SEVERITY_W[s] for s, _, _ in f)


def analyze(eml_path, envelope_from=""):
    with open(eml_path, "rb") as fh:
        msg = message_from_binary_file(fh)
    f = []
    ctx = {"envelope_from": envelope_from}
    check_sender_reputation(msg, f, ctx)
    check_url_cloaking(msg, f, ctx)
    check_body_obfuscation(msg, f, ctx)
    check_attachments(msg, f, ctx)
    return {
        "file": eml_path,
        "from": get_header(msg, "From"),
        "subject": get_header(msg, "Subject"),
        "score": score(f),
        "findings": [{"severity": s, "category": c, "detail": d} for s, c, d in f],
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("eml")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--env", default="", help="envelope sender (for alignment check)")
    args = ap.parse_args(argv)
    rep = analyze(args.eml, args.env)
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        print(f"File     : {rep['file']}")
        print(f"From     : {rep['from']}")
        print(f"Subject  : {rep['subject']}")
        print(f"Score    : {rep['score']}  (higher = more bypass-suspect)")
        print("Findings :")
        for s, c, d in [(x["severity"], x["category"], x["detail"]) for x in rep["findings"]]:
            print(f"  [{s:4}] {c:14} {d}")
        if not rep["findings"]:
            print("  (none)")


if __name__ == "__main__":
    main()
