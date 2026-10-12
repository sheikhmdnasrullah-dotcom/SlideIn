#!/usr/bin/env python3
"""
inbox_pipeline.py  -  Unified KumoMTA + GoPhish inbox-placement pipeline.

Brings together the pieces already wired on the VPS:
  * KumoMTA  -> transport (GoPhish's SMTP profiles 9/10/11 point here)
  * GoPhish  -> campaign engine (uses KumoMTA)
  * assurance.py -> pre-flight content + auth check + compliance headers
  * warmup-engine -> reputation (running on VPS)
  * seed IMAP -> placement verification

Flow:  preflight(template) -> send via KumoMTA -> verify seed Inbox/Spam -> report

Legitimate deliverability only. No header forgery / filter evasion.
Usage:
  python3 inbox_pipeline.py --template deliverability/sample/approved_template.eml \
      --profile hello@nasrullahtanim.me --to tanim.slideinventure5@gmail.com
"""
import sys, os, re, json, time, uuid, smtplib, ssl, imaplib, argparse, email
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
import assurance
import unspam_client as unspam
import rspamd_scan as rspamd
import rules_engine

KUMO = {
    "host": os.environ.get("KUMO_HOST", "127.0.0.1"),
    "port": int(os.environ.get("KUMO_SMTP_PORT", "2587")),
    "user": os.environ.get("KUMO_AUTH_USER", "outbound"),
    "password": os.environ.get("KUMO_AUTH_PASS", "local-dev-password"),
}
VPS = os.environ.get("VPS_SSH", "root@127.0.0.1")

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def render_template(eml_path, to_addr, unsub_mailto):
    """Pull plain+html from an .eml template, substitute vars, return (subject, plain, html)."""
    msg = email.message_from_file(open(eml_path, encoding="utf-8"))
    subject = msg.get("Subject", "No subject")
    plain = html = ""
    for part in msg.walk():
        if part.is_multipart():
            continue
        ct = part.get_content_type()
        p = part.get_payload(decode=True)
        if p is None:
            continue
        t = p.decode("utf-8", "ignore")
        t = t.replace("{{recipient}}", to_addr).replace("{{first_name}}", "Tanim") \
             .replace("{{personalization_line}}", "I came across your recent work and thought it was genuinely useful.")
        if ct == "text/plain":
            plain = t
        elif ct == "text/html":
            html = t
    return subject, plain, html


def send_via_kumo(from_addr, to_addr, msg_string):
    s = smtplib.SMTP(KUMO["host"], KUMO["port"], timeout=30)
    s.ehlo(); s.starttls(context=ctx); s.ehlo()
    s.login(KUMO["user"], KUMO["password"])
    s.sendmail(from_addr, [to_addr], msg_string)
    s.quit()
    msg = email.message_from_string(msg_string)
    return msg["Message-ID"], msg_string


def send_via_sendgrid(from_addr, to_addr, msg_string, api_key):
    """Send via SendGrid SMTP relay (apikey auth). Requires a verified domain + DNS CNAMEs."""
    if not api_key:
        raise RuntimeError("SendGrid api_key missing in config.json [sendgrid].api_key")
    s = smtplib.SMTP("smtp.sendgrid.net", 587, timeout=30)
    s.ehlo(); s.starttls(context=ctx); s.ehlo()
    s.login("apikey", api_key)
    s.sendmail(from_addr, [to_addr], msg_string)
    s.quit()
    msg = email.message_from_string(msg_string)
    return msg["Message-ID"], msg_string


def send_via_resend(from_addr, to_addr, msg_string, api_key):
    """Send via Resend SMTP relay. Free tier = 100/day on a SHARED IP. Requires verified domain + DNS."""
    if not api_key:
        raise RuntimeError("Resend api_key missing in config.json [resend].api_key")
    s = smtplib.SMTP("smtp.resend.com", 587, timeout=30)
    s.ehlo(); s.starttls(context=ctx); s.ehlo()
    s.login("resend", api_key)
    s.sendmail(from_addr, [to_addr], msg_string)
    s.quit()
    msg = email.message_from_string(msg_string)
    return msg["Message-ID"], msg_string


def verify_seed(seed, mid, wait=30):
    time.sleep(wait)
    im = imaplib.IMAP4_SSL(seed["host"], seed["port"], ssl_context=ctx)
    im.login(seed["email"], seed["password"])
    res = {}
    for box in (seed.get("inbox_folder", "INBOX"), seed.get("spam_folder", "[Gmail]/Spam")):
        im.select(box)
        _, d = im.search(None, f'HEADER Message-ID "{mid}"')
        res[box] = d[0].decode().split() or []
    im.logout()
    return "INBOX" if res.get("INBOX") else ("SPAM" if res.get("[Gmail]/Spam") else "UNKNOWN")


def warmup_status():
    import subprocess, tempfile, os
    try:
        script = os.path.join(tempfile.gettempdir(), "warmup_status.py")
        open(script, "w").write(
            "import sqlite3\n"
            "try:\n"
            "    c=sqlite3.connect('/opt/warmup-engine/warmup.db')\n"
            "    tabs=[r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")]\n"
            "    print('tables:', ', '.join(tabs[:12]))\n"
            "    for t in ('reputation','sent','stats','accounts'):\n"
            "        if t in tabs:\n"
            "            print(t+'_rows:', c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0])\n"
            "except Exception as e:\n"
            "    print('err', e)\n")
        host, pw = rspamd._ssh()
        scp = ["sshpass", "-p", pw, "scp", "-o", "StrictHostKeyChecking=no",
               "-o", "UserKnownHostsFile=/dev/null", script, f"root@{host}:/tmp/warmup_status.py"]
        ssh = ["sshpass", "-p", pw, "ssh", "-o", "StrictHostKeyChecking=no",
               "-o", "UserKnownHostsFile=/dev/null", f"root@{host}", "python3 /tmp/warmup_status.py"]
        out = subprocess.check_output(scp, stderr=subprocess.DEVNULL, timeout=20)
        out = subprocess.check_output(ssh, stderr=subprocess.DEVNULL, timeout=20).decode().strip()
        return out or "warmup-engine: running"
    except Exception as e:
        return f"warmup-engine: running (status check skipped: {e})"


def run_unspam_spamcheck(msg_string, from_addr):
    """Create a spam-check, send the built email to Unspam's address, poll the verdict."""
    try:
        chk = unspam.create_spam_check()
    except Exception as e:
        print(f"  [unspam] skipped (no api_key / network): {e}")
        return
    addr = chk.get("inbox_address")
    if not addr:
        print("  [unspam] no inbox_address returned")
        return
    s = smtplib.SMTP(KUMO["host"], KUMO["port"], timeout=30)
    s.ehlo(); s.starttls(context=ctx); s.ehlo()
    s.login(KUMO["user"], KUMO["password"])
    s.sendmail(from_addr, [addr], msg_string)
    s.quit()
    print(f"  [unspam] sent to {addr}, waiting for verdict...")
    try:
        unspam.spam_check_report(chk["id"])
    except Exception as e:
        print(f"  [unspam] verdict fetch failed: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", required=True)
    ap.add_argument("--profile", required=True, help="from address, e.g. hello@nasrullahtanim.me")
    ap.add_argument("--to", required=True, help="recipient (use a seed for safe testing)")
    ap.add_argument("--unsub-mailto", default="unsubscribe@nasrullahtanim.me")
    ap.add_argument("--wait", type=int, default=30)
    ap.add_argument("--unspam", action="store_true", help="also run content analysis via Unspam.email API (paid; opt-in)")
    ap.add_argument("--no-rspamd", action="store_true", help="skip the default local rspamd analysis (free, on VPS)")
    ap.add_argument("--force", action="store_true", help="send even if a rule FAILs (override the gate)")
    ap.add_argument("--transport", choices=["kumo", "sendgrid", "resend"], default="kumo",
                    help="transport to send through (kumo=dedicated IP, sendgrid/resend=free shared-IP tiers)")
    args = ap.parse_args()

    cfg = json.load(open(os.path.join(os.path.dirname(__file__), "config.json")))
    seed = next((s for s in cfg["seed_accounts"] if s["email"] == args.to), None)
    if not seed:
        # fallback: treat --to as a literal seed spec isn't safe; require a known seed
        print("ERROR: --to must be one of the configured seed_accounts for verification.")
        sys.exit(2)

    print("=== 1. Pre-flight (assurance) ===")
    subject, plain, html = render_template(args.template, args.to, args.unsub_mailto)
    cf = assurance.content_preflight(plain, html)
    for sev, d in cf:
        print(f"  [{sev}] {d}")
    if not cf:
        print("  (clean)")

    print("=== 2. Warmup / reputation ===")
    print("  " + warmup_status())

    domain = args.profile.split("@", 1)[1]
    msg = assurance.build_message(args.profile, args.to, subject, plain, html, None, args.unsub_mailto)
    msg_str = msg.as_string()

    print("=== 2b. Rules Gate (MailReach 12 tips) ===")
    results = rules_engine.run_all(msg, plain, html, args.profile, domain, eml_text=msg_str)
    fails = rules_engine.print_report(results)
    if fails and not args.force:
        print("  ABORT: one or more rules FAILED. Fix them, or re-run with --force to override.")
        sys.exit(3)
    if fails:
        print("  [--force] override: sending despite FAIL.")

    label = "KumoMTA" if args.transport == "kumo" else "SendGrid"
    print(f"=== 3. Send via {label} ({args.profile} -> {args.to}) ===")
    rules_engine.check_volume(args.profile, domain, n=1, commit=True)
    if args.transport == "sendgrid":
        sg_key = cfg.get("sendgrid", {}).get("api_key")
        mid, msg_str = send_via_sendgrid(args.profile, args.to, msg_str, sg_key)
    elif args.transport == "resend":
        rs_key = cfg.get("resend", {}).get("api_key")
        mid, msg_str = send_via_resend(args.profile, args.to, msg_str, rs_key)
    else:
        mid, msg_str = send_via_kumo(args.profile, args.to, msg_str)
    print(f"  sent Message-ID {mid}")

    if args.unspam:
        print("=== 3b. Content analysis via Unspam.email ===")
        run_unspam_spamcheck(msg_str, args.profile)

    if not args.no_rspamd:
        print("=== 3c. Local spam analysis via rspamd (VPS, free, default) ===")
        rspamd.report(msg_str)

    print(f"=== 4. Verify placement (wait {args.wait}s) ===")
    placement = verify_seed(seed, mid, wait=args.wait)
    print(f"  RESULT: {placement}")

    print("\n=== Summary ===")
    print(f"  Template     : {args.template}")
    print(f"  From profile : {args.profile}")
    print(f"  Pre-flight   : {'clean' if not cf else f'{len(cf)} finding(s)'}")
    print(f"  Placement    : {placement}")


if __name__ == "__main__":
    main()
