"""Promotions / Spam risk classifier.

Scores an email on known Gmail/Outlook/Yahoo placement signals and returns
a structured risk assessment. This is a pre-send gate helper, not a guarantee:
it flags high-risk content/header patterns before the real seed test.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from email import policy
from email.utils import getaddresses
from typing import List


@dataclass
class PlacementRisk:
    promotions_risk: float = 0.0      # 0..100
    spam_risk: float = 0.0            # 0..100
    promotions_signals: List[str] = field(default_factory=list)
    spam_signals: List[str] = field(default_factory=list)
    overall_risk: str = "low"         # low | medium | high | critical

    def to_dict(self) -> dict:
        return {
            "promotions_risk": round(self.promotions_risk, 2),
            "spam_risk": round(self.spam_risk, 2),
            "promotions_signals": self.promotions_signals,
            "spam_signals": self.spam_signals,
            "overall_risk": self.overall_risk,
       }


def classify_placement_risk(eml_bytes: bytes) -> PlacementRisk:
    """Analyze email for Promotions/Spam folder triggers."""
    from email.message import EmailMessage
    from email.parser import BytesParser

    try:
        msg = BytesParser(policy=policy.default).parsebytes(eml_bytes)
    except Exception:
        return PlacementRisk(promotions_risk=100, spam_risk=100, overall_risk="critical",
                             promotions_signals=["parse_error"], spam_signals=["parse_error"])

    risk = PlacementRisk()

    text_parts = []
    html_parts = []
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

    body_text = " ".join(text_parts).lower()
    body_html = " ".join(html_parts).lower()
    subject = (msg.get("Subject") or "").lower()

    # ---- Promotions tab signals ----
    promo_triggers = [
        "free", "100%", "guarantee", "act now", "limited time", "urgent",
        "click here", "buy now", "offer", "promo", "sale", "save big",
        "special", "discount", "deal", "order now", "winner", "prize",
        "partnership", "synergy", "working together", "content production side",
        "lead generation", "marketing side", "funnel", "prospects",
        "discussion about working", "helping you with", "content and marketing",
    ]
    for trig in promo_triggers:
        if trig in subject or trig in body_text or trig in body_html:
            risk.promotions_signals.append(trig)
            risk.promotions_risk += 8

    # HTML-heavy with little text
    html_len = len(body_html)
    text_len = len(body_text)
    if html_len > 0 and text_len > 0:
        ratio = text_len / (text_len + html_len)
        if ratio < 0.15:
            risk.promotions_signals.append("image_heavy_template")
            risk.promotions_risk += 20

    # Too many links
    link_count = body_html.count("href=") + body_text.count("http")
    if link_count > 5:
        risk.promotions_signals.append(f"high_link_count_{link_count}")
        risk.promotions_risk += min(25, link_count * 3)

    # Multiple unique link domains
    domains = set()
    for url in re.findall(r'href=["\'](.*?)["\']', body_html):
        try:
            d = url.split("/")[2].lower()
            domains.add(d)
        except IndexError:
            pass
    if len(domains) > 3:
        risk.promotions_signals.append(f"multi_domain_links_{len(domains)}")
        risk.promotions_risk += 15

    # List-Unsubscribe = bulk mail signal
    if msg.get("List-Unsubscribe"):
        risk.promotions_signals.append("list_unsubscribe_present")
        risk.promotions_risk += 25

    # Preheader / tracking headers often used in bulk
    if msg.get("X-Mailer") or msg.get("X-Mailing-Software") or msg.get("X-Campaign"):
        risk.promotions_signals.append("bulk_mail_headers")
        risk.promotions_risk += 15

    # ---- Spam folder signals ----
    spam_triggers = [
        "free", "100%", "guarantee", "act now", "limited time", "urgent",
        "click here", "buy now", "cash", "earn", "income", "million",
        "offer", "prize", "promo", "sale", "save big", "winner",
        "congratulations", "no risk", "risk-free", "best price", "cheap",
        "discount", "deal", "order now", "special",
    ]
    for trig in spam_triggers:
        if trig in subject or trig in body_text or trig in body_html:
            risk.spam_signals.append(trig)
            risk.spam_risk += 6

    # ALL CAPS words
    caps = [w for w in re.findall(r'\b[A-Z]{4,}\b', body_html + " " + body_text) if w.isalpha()]
    if caps:
        risk.spam_signals.append(f"all_caps_{caps[0]}")
        risk.spam_risk += 12

    # Excessive punctuation
    if "!!!" in body_text or "!!!" in body_html or "???" in body_text:
        risk.spam_signals.append("excessive_punctuation")
        risk.spam_risk += 12

    # Missing Date / Message-ID
    if not msg.get("Date"):
        risk.spam_signals.append("missing_date")
        risk.spam_risk += 10
    if not msg.get("Message-ID"):
        risk.spam_signals.append("missing_message_id")
        risk.spam_risk += 10

    # Auth failures
    ar = msg.get("Authentication-Results", "")
    ar_lower = ar.lower()
    for mech in ("spf", "dkim", "dmarc"):
        if f"{mech}=fail" in ar_lower:
            risk.spam_signals.append(f"{mech}_fail")
            risk.spam_risk += 25
        elif f"{mech}=softfail" in ar_lower and mech == "spf":
            risk.spam_signals.append("spf_softfail")
            risk.spam_risk += 15

    # Reply-To mismatch
    reply_to = msg.get("Reply-To")
    from_raw = msg.get("From") or ""
    from_addr = getaddresses([from_raw])[0][1] if getaddresses([from_raw]) else ""
    if reply_to:
        rt_addr = getaddresses([reply_to])[0][1]
        if rt_addr and from_addr and rt_addr.lower() != from_addr.lower():
            risk.spam_signals.append("reply_to_mismatch")
            risk.spam_risk += 15

    # Image ALT text check (missing ALT text)
    imgs_without_alt = re.findall(r'<img[^>]*?(?:(?!(?:alt=)[^>]*).)*>[^>]*>', body_html)
    # Count img tags and check ALT coverage
    img_tags = re.findall(r'<img[^>]+>', body_html)
    if img_tags:
        if len(img_tags) > 0 and imgs_with_alt == 0:
            risk.promotions_signals.append("missing_alt_text")
            risk.promotions_risk += 10

    # Too many links
    link_count = body_html.count("href=") + body_text.count("http")
    if link_count > 5:
        risk.promotions_signals.append(f"high_link_count_{link_count}")
        risk.promotions_risk += min(25, link_count * 3)

    # Multiple unique link domains
    domains = set()
    for url in re.findall(r'href=["\'](.*?)["\']', body_html):
        try:
            d = url.split("/")[2].lower()
            domains.add(d)
        except IndexError:
            pass
    if len(domains) > 3:
        risk.promotions_signals.append(f"multi_domain_links_{len(domains)}")
        risk.promotions_risk += 15

    # List-Unsubscribe = bulk mail signal
    if msg.get("List-Unsubscribe"):
        risk.promotions_signals.append("list_unsubscribe_present")
        risk.promotions_risk += 25

    # Preheader / tracking headers often used in bulk
    if msg.get("X-Mailer") or msg.get("X-Mailing-Software") or msg.get("X-Campaign"):
        risk.promotions_signals.append("bulk_mail_headers")
        risk.promotions_risk += 15

    # Check for embedded forms (forbidden)
    if re.search(r'<(form|fieldset)>', body_html):
        risk.promotions_signals.append("embedded_form")
        risk.promotions_risk += 20

    # Check for CSS background images (Outlook doesn't recognize)
    if re.search(r'background-image|background:', body_html):
        risk.promotions_signals.append("css_background_image")
        risk.promotions_risk += 5

    # Check for JavaScript/vbscript in links
    js_links = re.findall(r'href=["\'](javascript|vbscript):', body_html)
    if js_links:
        risk.promotions_signals.append("js_links")
        risk.promotions_risk += 15

    # Check for video embeds (iframe, video tags)
    video_tags = re.findall(r'<(?:iframe|video|object)[^>]*>', body_html)
    if video_tags:
        risk.promotions_signals.append("video_embed")
        risk.promotions_risk += 15

    # Check for large images (width/height attributes suggesting large images)
    large_imgs = re.findall(r'<img[^>]*(?:width|height)="\d{3,}[^>]*>', body_html)
    if large_imgs:
        risk.promotions_signals.append("large_images")
        risk.promotions_risk += 10

    # Check for excessive text length (keyword stuffing)
    if len(body_text) > 500:
        risk.promotions_signals.append("excessive_text")
        risk.promotions_risk += 10

    # Clamp risks
    risk.promotions_risk = max(0.0, min(100.0, risk.promotions_risk))
    risk.spam_risk = max(0.0, min(100.0, risk.spam_risk))

    # Overall
    combined = max(risk.promotions_risk, risk.spam_risk)
    if combined >= 60:
        risk.overall_risk = "critical"
    elif combined >= 40:
        risk.overall_risk = "high"
    elif combined >= 20:
        risk.overall_risk = "medium"
    else:
        risk.overall_risk = "low"

    return risk
