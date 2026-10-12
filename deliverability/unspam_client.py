#!/usr/bin/env python3
"""
unspam_client.py - Integration client for Unspam.email deliverability APIs.

Used as the external "content + placement" engine inside the inbox pipeline.
Two capabilities (per Unspam API docs):
  * Spam Checker  POST /ext/v2/spam-check -> inbox_address; send email there;
                   GET /ext/v2/spam-check/{id} -> score (0-100) + results[]
  * Inbox Placement POST /ext/v2/inbox-placement -> addresses; send email to each;
                   GET /ext/v2/inbox-placement/{id} -> per-mailbox tab

Auth: single Bearer token (UNSPAM_API_KEY). Put it in deliverability/config.json
under "unspam": {"api_key": "...", "base_url": "..."} (secrets stay in config.json
per PROJECT_POLICY).

Note: Unspam API access is on their White Label plan (custom limits). The free
web tool has no self-serve API trial. The engine returns content/auth SIGNAL, not
a guarantee of inbox placement (their own docs say so) -- same honest ceiling we
engineer to.

Requires: requests  (pip install requests)
"""
import os, sys, time, json, argparse, re
from urllib.parse import urlparse
try:
    import requests
except Exception:
    requests = None

DEFAULT_BASE = "https://unspam.email/ext/v2"  # VERIFY with Unspam; may be https://api.unspam.email/ext/v2

# Only genuine Unspam API hosts, over TLS. The base URL comes from local
# config, but a typo (or a copied config) must never turn this client
# into a request-forger against internal hosts (audit S6).
ALLOWED_HOSTS = {"unspam.email", "api.unspam.email"}
CHECK_ID_RE = re.compile(r"[A-Za-z0-9_-]+")


def _cfg():
    here = os.path.dirname(__file__)
    try:
        c = json.load(open(os.path.join(here, "config.json")))
    except Exception:
        c = {}
    u = c.get("unspam", {})
    return u.get("api_key"), u.get("base_url", DEFAULT_BASE)


def _headers():
    if requests is None:
        raise RuntimeError("requests not installed (pip install requests)")
    key, _ = _cfg()
    if not key:
        raise RuntimeError("unspam.api_key is missing in config.json; refusing unauthenticated request")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _base():
    _, b = _cfg()
    return _validated_base(b)


def _validated_base(base_url: str) -> str:
    """Return the base URL iff it is a genuine Unspam https endpoint."""
    if not base_url or not isinstance(base_url, str):
        raise ValueError("unspam.base_url is missing")
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").lower()
    if (parsed.scheme.lower() != "https"
            or host not in ALLOWED_HOSTS
            or parsed.username or parsed.password):
        raise ValueError(f"unspam.base_url is not an allowed Unspam endpoint: {base_url!r}")
    return base_url.rstrip("/")


def _checked_id(check_id: str) -> str:
    """Validate an API-issued ID before interpolating it into a URL path."""
    if not check_id or not CHECK_ID_RE.fullmatch(check_id):
        raise ValueError(f"invalid Unspam check/placement id: {check_id!r}")
    return check_id


def create_spam_check():
    r = requests.post(f"{_base()}/spam-check", headers=_headers(), json={}, timeout=30)
    r.raise_for_status()
    return r.json()  # {id, inbox_address, ...}


def get_spam_result(check_id, timeout=60, poll=3):
    url = f"{_base()}/spam-check/{_checked_id(check_id)}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(url, headers=_headers(), timeout=30)
        r.raise_for_status()
        d = r.json()
        if d.get("status") == "completed":
            return d
        time.sleep(poll)
    raise TimeoutError("spam-check did not complete in time")


def list_mailboxes():
    r = requests.get(f"{_base()}/inbox-placement/mailboxes", headers=_headers(), timeout=30)
    r.raise_for_status()
    return r.json()


def create_placement_test(mailboxes=None):
    body = {"mailboxes": mailboxes} if mailboxes else {}
    r = requests.post(f"{_base()}/inbox-placement", headers=_headers(), json=body, timeout=30)
    r.raise_for_status()
    return r.json()  # {id, addresses:[...]}


def get_placement_result(test_id, timeout=120, poll=5):
    url = f"{_base()}/inbox-placement/{_checked_id(test_id)}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(url, headers=_headers(), timeout=30)
        r.raise_for_status()
        d = r.json()
        if d.get("status") == "completed":
            return d
        time.sleep(poll)
    raise TimeoutError("placement test did not complete in time")


def spam_check_report(check_id):
    """Pretty summary of a completed spam-check."""
    d = get_spam_result(check_id)
    print(f"  score        : {d.get('score')}  (80+ healthy, 50-70 risky, <50 spam)")
    print(f"  report_url   : {d.get('report_url')}")
    for res in d.get("results", []):
        flag = res.get("status", "?")
        print(f"    [{flag}] {res.get('id')}: {res.get('detail', '')}")


def placement_report(test_id):
    d = get_placement_result(test_id)
    for r in d.get("results", []):
        print(f"  {r.get('name','?'):20} tab={r.get('tab'):12} status={r.get('status')} blacklists={r.get('blacklists')}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--spam-check", metavar="ID", help="fetch + print a spam-check result")
    ap.add_argument("--placement", metavar="ID", help="fetch + print a placement result")
    a = ap.parse_args()
    if a.spam_check:
        spam_check_report(a.spam_check)
    elif a.placement:
        placement_report(a.placement)
    else:
        print("Pass --spam-check ID or --placement ID (needs unspam.api_key in config.json)")
