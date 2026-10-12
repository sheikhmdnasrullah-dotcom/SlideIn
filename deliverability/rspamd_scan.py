#!/usr/bin/env python3
"""
rspamd_scan.py - Local, cost-free spam analysis via the rspamd instance already
running inside mailcow on the VPS.

Uses `rspamc` inside the mailcow rspamd container over SSH. Returns a structured
report: score, action, spam flag, and the per-symbol breakdown that explains WHY
the message scored where it did (the "fix before sending" signal).

This is the open-source equivalent of a paid spam-score API, and it's already
deployed on your infrastructure. No per-email cost.

Requires: sshpass + ssh (local), and the mailcow rspamd container on the VPS.
"""
import os, sys, re, json, subprocess

RSPAMD_CONTAINER = "mailcowdockerized-rspamd-mailcow-1"


def _ssh():
    c = json.load(open(os.path.join(os.path.dirname(__file__), "config.json")))
    return c.get("ssh", {}).get("host"), c.get("ssh", {}).get("password")


def scan_eml(eml_text):
    """Pipe an .eml (str/bytes) to rspamc in the VPS rspamd container; return dict."""
    host, pw = _ssh()
    if not host or not pw:
        return {"error": "missing ssh host/password in config.json"}
    cmd = [
        "sshpass", "-p", pw, "ssh",
        "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
        f"root@{host}",
        f"docker exec -i {RSPAMD_CONTAINER} rspamc",
    ]
    try:
        p = subprocess.run(cmd, input=eml_text.encode() if isinstance(eml_text, str) else eml_text,
                           capture_output=True, timeout=60)
    except Exception as e:
        return {"error": str(e)}
    out = p.stdout.decode("utf-8", "ignore")
    return parse(out)


def parse(text):
    res = {"score": None, "required": None, "action": None, "spam": None, "symbols": []}
    score_m = re.search(r"Score:\s*([\d.]+)\s*/\s*([\d.]+)", text)
    if score_m:
        res["score"] = float(score_m.group(1))
        res["required"] = float(score_m.group(2))
    am = re.search(r"Action:\s*(\w+)", text)
    if am:
        res["action"] = am.group(1)
    sm = re.search(r"Spam:\s*(true|false)", text, re.I)
    if sm:
        res["spam"] = sm.group(1).lower() == "true"
    for line in text.splitlines():
        m = re.match(r"Symbol:\s*(\S+)\s*\(([-\d.]+)\)(\[(.*)\])?", line)
        if m:
            res["symbols"].append({
                "name": m.group(1),
                "weight": float(m.group(2)),
                "detail": (m.group(4) or "").strip(),
            })
    res["raw"] = text
    return res


def report(eml_text):
    r = scan_eml(eml_text)
    if "error" in r:
        print(f"  [rspamd] error: {r['error']}")
        return
    print(f"  score   : {r['score']} / {r['required']}   action={r['action']} spam={r['spam']}")
    # show only symbols that pushed the score up (weight > 0)
    contrib = sorted([s for s in r["symbols"] if s["weight"] > 0], key=lambda s: -s["weight"])
    if contrib:
        print("  top spam signals:")
        for s in contrib:
            d = f"  ({s['detail']})" if s["detail"] else ""
            print(f"    +{s['weight']:<6} {s['name']} {d}")
    else:
        print("  no positive spam signals")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: rspamd_scan.py file.eml")
        sys.exit(2)
    print(report(open(sys.argv[1], encoding="utf-8").read()))
