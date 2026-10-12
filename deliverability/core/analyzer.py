"""Email analyzer: produces an A–F deliverability grade + findings.

Primary path: happyDeliver (self-hosted, on VPS) over HTTP. It runs Postfix +
auth_milter + SpamAssassin + rspamd and returns a structured A–F report.

Fallback path: a pure-stdlib heuristic analyzer so the gate is operational even
when happyDeliver is unreachable (e.g. local dev). The heuristic is intentionally
conservative and explains WHY a grade is low.
"""
from __future__ import annotations

import email
import io
import json
import re
import urllib.request
import urllib.error
from email import policy
from email.utils import getaddresses
from dataclasses import dataclass, field


# Spammy patterns and commercial Promotions-tab triggers (Strictly Hard-Banned)
_SPAM_WORDS = [
    "free", "100%", "guarantee", "act now", "limited time", "urgent", "click here",
    "buy now", "cash", "earn", "income", "million", "offer", "prize", "promo",
    "sale", "save big", "winner", "congratulations", "no risk", "risk-free",
    "best price", "cheap", "deal", "order now", "special",
    "weight loss", "pharmaceuticals", "viagra", "cialis", "discount pharmacy",
]

# Specific B2B commercial buzzwords that trigger Gmail's "Promotions Tab" ML classifier
_PROMOTION_TAB_TRIGGERS = [
    "lead funnel", "funnel that work", "work like a magnet", "wire the whole thing",
    "potential prospects", "lead generation side", "content production side",
    "discussion about working in your content and marketing side", "working together on your content and marketing",
    "working on your content and lead generation", "discussion on your content production and marketing",
    "helping you with content production and marketing", "partnership on your content and marketing side"
]

# AI Slop Openers & Banned Subject Line Tropes
_AI_SLOP_OPENERS = [
    "loved your recent work on", "as a fellow", "i noticed that you are doing great things",
    "hope this email finds you well", "i'm reaching out because"
]

_BANNED_SUBJECT_TROPES = [
    "quick thought", "quick idea", "quick note", "quick question", "thoughts on",
    "idea regarding", "regarding your", "partnership proposal", "synergy",
    "marketing side", "lead generation", "video editing", "video editor", "editing your"
]



@dataclass
class Analysis:
    grade: str                 # A-F
    score: float               # 0..100 (higher = better)
    source: str                # "happydeliver" | "heuristic"
    spam_score: float          # spamassassin/rspamd-style (higher = worse)
    auth: dict = field(default_factory=dict)
    findings: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "grade": self.grade, "score": self.score, "source": self.source,
            "spam_score": self.spam_score, "auth": self.auth,
            "findings": self.findings, "raw": self.raw,
        }


def _grade_from_score(score: float) -> str:
    # score is 0..100 good
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 55:
        return "D"
    return "F"


def analyze_via_happydeliver(eml_bytes: bytes, base_url: str, timeout: int = 3) -> Analysis:
    """Upload .eml to happyDeliver /api/test/upload, fetch /api/report/{id}, and parse the report."""

    base = base_url.rstrip("/")
    boundary = "----happydeliverboundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="message.eml"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + eml_bytes + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{base}/api/test/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        upload_resp = json.loads(resp.read().decode())
    
    test_id = upload_resp.get("id")
    if not test_id:
        raise ValueError(f"happyDeliver upload failed to return test ID: {upload_resp}")
    
    # Fetch comprehensive deliverability report
    report_req = urllib.request.Request(
        f"{base}/api/report/{test_id}",
        headers={"Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(report_req, timeout=timeout) as resp:
        report = json.loads(resp.read().decode())
    
    score = float(report.get("score") or 0)
    grade = report.get("grade") or _grade_from_score(score)
    findings: list[str] = []
    
    # Content & HTML Issues
    content_analysis = report.get("content_analysis") or {}
    for issue in content_analysis.get("html_issues") or []:
        findings.append(f"[Content] {issue.get('severity', 'WARN')}: {issue.get('message', '')} ({issue.get('advice', '')})")
    for link in content_analysis.get("links") or []:
        if link.get("status") == "broken":
            findings.append(f"[Link] Broken link detected ({link.get('url')}) - HTTP {link.get('http_code', 'error')}")
    
    # Header Issues
    header_analysis = report.get("header_analysis") or {}
    for h_name, h_info in (header_analysis.get("headers") or {}).items():
        if isinstance(h_info, dict) and not h_info.get("valid", True):
            for iss in h_info.get("issues") or []:
                findings.append(f"[Header] {h_name}: {iss}")
    
    # DNS Results
    dns_results = report.get("dns_results") or {}
    dmarc = dns_results.get("dmarc_record") or {}
    if not dmarc.get("valid", False):
        findings.append(f"[DNS] DMARC record invalid or missing on {dmarc.get('domain', 'domain')}")
    
    # Spam and Authentication
    spam_score = float(report.get("summary", {}).get("spam_score") or 0)
    
    return Analysis(
        grade=grade,
        score=score,
        source="happydeliver",
        spam_score=spam_score,
        auth={
            "spf": "pass" if any(s.get("valid") for s in dns_results.get("spf_records", [])) else "fail",
            "dkim": "pass" if dmarc.get("dkim_alignment") else "unknown",
            "dmarc": dmarc.get("policy", "unknown"),
        },
        findings=findings,
        raw=report,
    )


def test_domain_via_happydeliver(domain: str, base_url: str, timeout: int = 15) -> dict:
    """Test domain DNS configuration (SPF, DKIM, DMARC, MX, BIMI) via happyDeliver."""
    base = base_url.rstrip("/")
    payload = json.dumps({"domain": domain}).encode()
    req = urllib.request.Request(
        f"{base}/api/domain",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def check_blacklist_via_happydeliver(ip: str, base_url: str, timeout: int = 15) -> dict:
    """Check IP address against DNS blacklists (RBLs) via happyDeliver."""
    base = base_url.rstrip("/")
    payload = json.dumps({"ip": ip}).encode()
    req = urllib.request.Request(
        f"{base}/api/blacklist",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())



def _safe(d, *keys):
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def analyze_heuristic(eml_bytes: bytes) -> Analysis:
    """Conservative stdlib-only analyzer used when happyDeliver is unavailable."""
    msg = email.message_from_bytes(eml_bytes, policy=policy.default)
    findings: list[str] = []
    score = 100.0

    # Required headers
    for h in ("From", "To", "Subject", "Date", "Message-ID"):
        if not msg.get(h):
            findings.append(f"Missing header: {h}")
            score -= 10


    # Authentication-Results present? (added by relay; absence is a soft signal)
    ar = msg.get("Authentication-Results")
    auth = {"spf": "unknown", "dkim": "unknown", "dmarc": "unknown"}
    if ar:
        for mech in ("spf", "dkim", "dmarc"):
            if f"{mech}=pass" in ar.lower():
                auth[mech] = "pass"
            elif f"{mech}=fail" in ar.lower():
                auth[mech] = "fail"
                findings.append(f"{mech.upper()} failed per Authentication-Results")
                score -= 10

    # Content analysis
    text_parts, html_parts = [], []
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain":
                text_parts.append(part.get_content() or "")
            elif ct == "text/html":
                html_parts.append(part.get_content() or "")
    else:
        if msg.get_content_type() == "text/html":
            html_parts.append(msg.get_content() or "")
        else:
            text_parts.append(msg.get_content() or "")

    if not text_parts:
        findings.append("No plain-text part (multipart/alternative required)")
        score -= 10
    if not html_parts and not text_parts:
        findings.append("Empty body")
        score -= 20

    body_text = " ".join(text_parts).lower()
    body_html = " ".join(html_parts).lower()

    # Link ratio
    link_count = body_html.count("href=") + body_text.count("http")
    if link_count == 0:
        findings.append("No links in email (unusual for outreach — verify)")
    elif link_count > 5:
        findings.append(f"High link count ({link_count}) — spam signal")
        score -= min(15, link_count)

    # Image-only / image ratio
    img_count = body_html.count("<img")
    if img_count > 0 and not text_parts:
        findings.append("Image-only email (no text) — strong spam signal")
        score -= 15

    # Check for hard-banned Promotions-Tab triggers
    for trig in _PROMOTION_TAB_TRIGGERS:
        if trig in body_text or trig in body_html or trig in (msg.get("Subject") or "").lower():
            findings.append(f"[Promotions-Trigger] Found commercial B2B phrase '{trig}' (triggers Gmail Promotions tab)")
            score -= 25

    # Check for AI slop openers
    for ai_op in _AI_SLOP_OPENERS:
        if ai_op in body_text or ai_op in body_html:
            findings.append(f"[AI-Slop] Found generic AI opener '{ai_op}' (triggers fake personalization filter)")
            score -= 20

    # Check for banned AI/commercial subject line tropes
    subject_text = (msg.get("Subject") or "").lower()
    for trope in _BANNED_SUBJECT_TROPES:
        if trope in subject_text:
            findings.append(f"[Subject-Slop] Found banned/AI subject trope '{trope}' in Subject")
            score -= 25

    # Check for bold formatting in body (banned in peer 1-on-1 emails)
    if "<b>" in body_html or "<strong>" in body_html or "**" in body_text:
        findings.append("[Formatting] Bold formatting detected in email body (banned for peer outreach)")
        score -= 15

    # Check for em-dashes (AI signature)
    if "—" in body_text or "—" in body_html or "&mdash;" in body_html:
        findings.append("[Typography] Em-dash (—) detected (AI artifact; replace with standard comma/hyphen)")
        score -= 10

    # Word count check (genuine peer emails are concise, under 200 words)
    words = len(body_text.split())
    if words > 220:
        findings.append(f"[Length] Email body is {words} words (exceeds 220-word limit; triggers commercial classification)")
        score -= 15

    # Avoid clickbait subject lines
    clickbait_patterns = [
        "buy now", "act now", "limited time", "once in a lifetime", "don't miss out",
        "last chance", "final notice", "amazing", "shocking", "you won't believe",
    ]
    subject_lower = (msg.get("Subject") or "").lower()
    for pattern in clickbait_patterns:
        if pattern in subject_lower:
            findings.append(f"[Subject] Clickbait pattern detected in subject: '{pattern}'")
            score -= 10
            break

    # Check for excessive whitespace / empty lines (template spam signal)
    empty_lines = sum(1 for line in body_text.splitlines() if not line.strip())
    if empty_lines > 10:
        findings.append(f"[Formatting] {empty_lines} empty/whitespace lines in body (template spam signal)")
        score -= 10

    # Check for URL shorteners or tracking domains
    shortener_domains = {"bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "buff.ly", "rebrand.ly"}
    found_shorteners = set()
    for url in re.findall(r'https?://[^\s<>"\']+', body_html + " " + body_text):
        try:
            domain = url.split("/")[2].lower()
            if domain in shortener_domains:
                found_shorteners.add(domain)
        except IndexError:
            pass
    if found_shorteners:
        findings.append(f"[Links] URL shortener domains detected: {', '.join(sorted(found_shorteners))} (spam signal)")
        score -= 20

    # Check for ALL CAPS words (spam signal)
    caps_words = [w for w in re.findall(r'\b[A-Z]{4,}\b', body_html + " " + body_text) if w.isalpha()]
    if caps_words:
        findings.append(f"[Content] ALL CAPS words detected: {', '.join(caps_words[:5])} (spam signal)")
        score -= 10

    # Check for excessive punctuation
    if body_text.count("!!!") > 0 or body_text.count("???") > 0 or body_html.count("!!!") > 0:
        findings.append("[Content] Excessive exclamation/question marks (spam signal)")
        score -= 10

    # Check for common spam trigger words in subject
    subject_lower = (msg.get("Subject") or "").lower()
    for word in _SPAM_WORDS:
        if word in subject_lower:
            findings.append(f"[Subject] Spam trigger word in subject: '{word}'")
            score -= 15
            break

# Check for MIME structure issues
    if msg.is_multipart():
        parts = list(msg.walk())
        if len(parts) > 10:
            findings.append(f"[MIME] Excessive MIME parts ({len(parts)}; unusual for legitimate mail)")
            score -= 10

    # Don't mix different types of messaging in the same email
    promo_keywords = ["promo", "sale", "discount", "offer", "buy", "order"]
    promo_count = sum(1 for p in promo_keywords if p in body_text or p in body_html)
    if promo_count >= 3:
        findings.append(f"[Mixing] Email contains multiple promotional signals (promo/sale/discount/offer/buy/order); avoid mixing messaging types")
        score -= 15

    # Links should be visible and easy to understand
    raw_links = re.findall(r'href=["\'](.*?)["\']', body_html)
    suspicious_link_patterns = ["bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly"]
    for link in raw_links:
        link_lower = link.lower()
        if any(pattern in link_lower for pattern in suspicious_link_patterns):
            findings.append(f"[Link] Suspicious shortened/link masking detected: {link}")
            score -= 10
            break

    # Reply-To must align with From (policy requirement)
    reply_to = msg.get("Reply-To")
    from_raw = msg.get("From") or ""
    from_addr = getaddresses([from_raw])[0][1] if getaddresses([from_raw]) else ""
    if reply_to:
        rt_addr = getaddresses([reply_to])[0][1]
        if rt_addr and from_addr and rt_addr.lower() != from_addr.lower():
            findings.append(f"[Alignment] Reply-To {rt_addr} does not match From {from_addr} (DMARC alignment risk)")
            score -= 10

    # HTML:text ratio: too much HTML with little text is spammy
    html_len = len(body_html)
    text_len = len(body_text)
    if html_len > 0 and text_len > 0:
        ratio = text_len / (text_len + html_len)
        if ratio < 0.2:
            findings.append("[Content] Very low text:HTML ratio (image-heavy / template spam signal)")
            score -= 15

    # Unique link count (too many unique domains = link spam)
    unique_domains = set()
    for url in re.findall(r'href=["\'](.*?)["\']', body_html):
        domain = url.split("/")[0].split("?")[0]
        if domain:
            unique_domains.add(domain)
    if len(unique_domains) > 3:
        findings.append(f"[Links] {len(unique_domains)} unique link domains (commercial spam signal)")
        score -= 15

    # List-Unsubscribe must be absent for 1-on-1 personal outreach (policy §3)
    if msg.get("List-Unsubscribe"):
        findings.append("[Policy] List-Unsubscribe header present (forbidden for 1-on-1 personal outreach)")
        score -= 20

    # Avoid excessive copy / keyword stuffing
    # Heuristic: if the body HTML has > 300 words or the text:HTML ratio is very skewed
    if html_len > 0 and text_len > 0:
        ratio = text_len / (text_len + html_len)
        if ratio < 0.1:
            findings.append("[Content] Very low text:HTML ratio - possible keyword stuffing / image-heavy template")
            score -= 15

    # Check for links to questionable/spammy sites
    questionable_tlds = [".zip", ".top", ".club", ".xyz", ".ooo", ".gq", ".ml", ".tk", ".cf", ".cn"]
    for url in re.findall(r'https?://[^\s<>"\']+', body_html + " " + body_text):
        try:
            domain = url.lower()
            for tld in questionable_tlds:
                if domain.endswith(tld):
                    findings.append(f"[Link] Questionable link domain detected: {url}")
                    score -= 10
                    break
        except IndexError:
            pass

    # Message-ID domain should match From domain for DMARC alignment
    mid = msg.get("Message-ID", "")
    if mid and from_addr:
        from_domain = from_addr.split("@")[-1] if "@" in from_addr else ""
        mid_domain = mid.split("@")[-1].rstrip(">") if "@" in mid else ""
        if from_domain and mid_domain and mid_domain != from_domain:
            findings.append(f"[Alignment] Message-ID domain ({mid_domain}) does not match From domain ({from_domain})")
            score -= 5

    # Plain text quality: too many template artifacts
    if body_text.count("{{") > 0 or body_text.count("}}") > 0:
        findings.append("[Template] Unrendered template variables in plain-text part")
        score -= 20

    # Date header format sanity
    if not msg.get("Date"):
        findings.append("[Header] Missing Date header")
        score -= 10


    return Analysis(
        grade=_grade_from_score(score), score=max(0.0, score),
        source="heuristic", spam_score=max(0.0, (100 - score) / 5.0),
        auth=auth, findings=findings,
    )



def analyze(eml_bytes: bytes, happydeliver_url: str | None = None) -> Analysis:
    if happydeliver_url:
        try:
            return analyze_via_happydeliver(eml_bytes, happydeliver_url)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            heur = analyze_heuristic(eml_bytes)
            heur.findings.insert(0, f"happyDeliver unreachable ({e}); used heuristic")
            return heur
    return analyze_heuristic(eml_bytes)


def analyze_draft(
    subject: str,
    body_text: str,
    body_html: str = "",
    from_addr: str = "hello@nasrullahtanim.me",
    to_addr: str = "prospect@example.com",
    from_name: str = "Nasrullah Tanim"
) -> Analysis:
    """Convenience helper to analyze raw subject and body before constructing full EML."""
    from email.message import EmailMessage
    from email.utils import formataddr, formatdate, make_msgid

    msg = EmailMessage()
    msg["From"] = formataddr((from_name, from_addr)) if from_name else from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=False)
    domain = from_addr.split("@")[1] if "@" in from_addr else "localhost"
    msg["Message-ID"] = make_msgid(domain=domain)
    msg["MIME-Version"] = "1.0"
    msg["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko)"

    if body_html:
        msg.set_content(body_text)
        msg.add_alternative(body_html, subtype="html")
    else:
        msg.set_content(body_text)

    return analyze(msg.as_bytes())


if __name__ == "__main__":
    import sys
    data = open(sys.argv[1], "rb").read()
    url = sys.argv[2] if len(sys.argv) > 2 else None
    a = analyze(data, url)
    print(json.dumps(a.to_dict(), indent=2, default=str))
