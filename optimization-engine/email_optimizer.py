#!/usr/bin/env python3
"""
email_optimizer.py - Inbox Placement Optimization Engine

Scores email content against Gmail/Yahoo/Olympics spam and promotions classifiers.
Run before every send to ensure maximum inbox placement.

Usage:
  python3 email_optimizer.py <message.eml>
  python3 email_optimizer.py --subject "..." --text "..." --html "..."
  python3 email_optimizer.py --json '{"subject":"...", "text":"..."}'
"""
from __future__ import annotations
import sys, json, re, email
from email import policy
from email.parser import BytesParser
from dataclasses import dataclass, field
from typing import List, Optional

# === SPAM WORD DICTIONARY ===
SPAM_WORDS = [
    r"\b100%\b", r"\bguarantee\b", r"\bfree\b", r"\bact now\b", r"\burgent\b",
    r"\blimited time\b", r"\bclick here\b", r"\bbuy now\b", r"\bcash\b",
    r"\bearn\b", r"\bincome\b", r"\bmillion\b", r"\boffer\b", r"\bprize\b",
    r"\bpromo\b", r"\bsale\b", r"\bsave big\b", r"\bwinner\b",
    r"\bcongratulations\b", r"\bno risk\b", r"\brisk[- ]free\b",
    r"\bbest price\b", r"\bcheap\b", r"\bdeal\b", r"\border now\b",
    r"\bspecial\b", r"\bweight loss\b", r"\bpharmaceuticals\b",
    r"\bviagra\b", r"\bcialis\b", r"\bdiscount pharmacy\b",
    r"\bmake money\b", r"\byou have won\b", r"\bno cost\b",
    r"\boffer expires\b", r"\bverify.{0,12}(account|password)\b",
    r"\bcongratulations\b", r"\bfree.{0,5}(trial|consultation|quote)\b",
]

# === PROMOTIONS TAB TRIGGERS (Gmail ML Classifier) ===
PROMOTION_TRIGGERS = [
    "lead funnel", "funnel that work", "work like a magnet", "wire the whole thing",
    "potential prospects", "lead generation side", "content production side",
    "discussion about working in your content and marketing side",
    "working together on your content and marketing",
    "working on your content and lead generation",
    "discussion on your content production and marketing",
    "helping you with content production and marketing",
    "partnership on your content and marketing side",
    "marketing side", "lead generation", "video editing",
    "video editor", "editing your",
]

# === AI SLOP OPENERS (Fake Personalization Filter) ===
AI_SLOP_OPENERS = [
    "loved your recent work on", "as a fellow", "i noticed that you are doing great things",
    "hope this email finds you well", "i'm reaching out because",
    "i came across your", "i was impressed by", "i stumbled upon",
]

# === BANNED SUBJECT TROPES ===
BANNED_SUBJECT_TROPES = [
    "quick thought", "quick idea", "quick note", "quick question", "thoughts on",
    "idea regarding", "regarding your", "partnership proposal", "synergy",
    "marketing side", "lead generation", "video editing", "video editor",
    "editing your",
]

# === GMAIL/YAHOO ACCEPTED PATTERNS ===
GOOD_PATTERNS = [
    r"^[A-Z][a-z]+ [A-Z][a-z]+",  # Proper name capitalization
    r"(recommend|suggest|connect|meet|discuss|explore|consider)",  # Action-oriented
    r"(you|your)",  # Personal
    r"([0-9]+ [a-z]+ ago|this week|recently|today)",  # Specific time reference
    r"(article|post|video|podcast|blog|newsletter)",  # Content reference
]

# === COMPLIANCE HEADERS ===
COMPLIANCE_HEADERS = {
    "Precedence": "bulk",
    "X-Mailer": "KumoMTA-GoPhish v1.0",
    "List-Unsubscribe": "<mailto:unsubscribe@nasrullahtanim.me?subject=unsubscribe>",
    "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    "List-Help": "<mailto:help@nasrullahtanim.me>",
    "List-Subscribe": "<mailto:subscribe@nasrullahtanim.me>",
    "Feedback-ID": "nasrullahtanim.me:2026",
}

@dataclass
class OptimizationResult:
    score: float  # 0-100, higher = better inbox placement
    grade: str    # A-F
    findings: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    passes: List[str] = field(default_factory=list)
    spam_score: float = 0.0
    promotion_risk: float = 0.0
    ai_sloop_risk: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "grade": self.grade,
            "findings": self.findings,
            "warnings": self.warnings,
            "passes": self.passes,
            "spam_score": self.spam_score,
            "promotion_risk": self.promotion_risk,
            "ai_sloop_risk": self.ai_sloop_risk,
        }

def score_subject(subject: str) -> tuple[float, list[str], list[str]]:
    """Score the email subject line."""
    score = 100.0
    findings = []
    warnings = []
    
    # Check length
    if len(subject) > 50:
        score -= 15
        warnings.append(f"[Subject] Too long ({len(subject)} chars, max 50)")
    elif len(subject) > 40:
        score -= 5
        warnings.append(f"[Subject] Getting long ({len(subject)} chars)")
    else:
        findings.append("[Subject] Length OK")
    
    # Check for banned tropes
    subject_lower = subject.lower()
    for trope in BANNED_SUBJECT_TROPES:
        if trope in subject_lower:
            score -= 20
            findings.append(f"[Subject] Banned trope: '{trope}'")
    
    # Check for spam words
    for pattern in SPAM_WORDS:
        if re.search(pattern, subject, re.I):
            score -= 15
            findings.append(f"[Subject] Spam word: '{pattern}'")
    
    # Check for good patterns
    for pattern in GOOD_PATTERNS:
        if re.search(pattern, subject, re.I):
            score += 5
            findings.append(f"[Subject] Good pattern: '{pattern}'")
            break
    
    # Check for proper capitalization
    if subject and subject[0].isupper():
        score += 3
        findings.append("[Subject] Proper capitalization")
    
    return score, findings, warnings

def score_content(plain_text: str, html_text: str = "") -> tuple[float, list[str], list[str]]:
    """Score the email body content."""
    score = 100.0
    findings = []
    warnings = []
    body_text = plain_text + " " + html_text
    
    # Check spam words
    spam_hits = []
    for pattern in SPAM_WORDS:
        for m in re.finditer(pattern, body_text, re.I):
            spam_hits.append(m.group(0))
    if spam_hits:
        score -= len(spam_hits) * 8
        findings.append(f"[Content] Spam words found: {', '.join(set(spam_hits[:5]))}")
    
    # Check promotion tab triggers
    promo_hits = []
    for trigger in PROMOTION_TRIGGERS:
        if trigger.lower() in body_text.lower():
            promo_hits.append(trigger)
    if promo_hits:
        score -= len(promo_hits) * 15
        findings.append(f"[Promotions] Triggers found: {', '.join(promo_hits[:3])}")
    
    # Check AI slop openers
    ai_hits = []
    for opener in AI_SLOP_OPENERS:
        if opener.lower() in body_text.lower():
            ai_hits.append(opener)
    if ai_hits:
        score -= len(ai_hits) * 12
        findings.append(f"[AI-Slop] Openers found: {', '.join(ai_hits[:3])}")
    
    # Check plain text
    if not plain_text.strip():
        score -= 20
        warnings.append("[Content] No plain text part")
    else:
        findings.append("[Content] Has plain text")
    
    # Check word count
    word_count = len(plain_text.split())
    if word_count < 20:
        score -= 10
        warnings.append(f"[Content] Too short ({word_count} words, min 20)")
    elif word_count > 150:
        score -= 10
        warnings.append(f"[Content] Too long ({word_count} words, max 150)")
    else:
        findings.append(f"[Content] Word count OK ({word_count} words)")
    
    # Check for personalized content
    if re.search(r"(you|your)", plain_text, re.I):
        score += 5
        findings.append("[Content] Personalized language")
    
    # Check for unsubscribe language
    if re.search(r"unsubscrib|opt[- ]out|remove from", plain_text + " " + html_text, re.I):
        score += 5
        findings.append("[Content] Has unsubscribe language")
    else:
        score -= 10
        warnings.append("[Content] Missing unsubscribe language")
    
    # Check for proper formatting
    if "\n\n" in plain_text:
        score += 3
        findings.append("[Content] Has proper paragraph breaks")
    
    # Check for excessive capitalization
    uppercase_ratio = sum(1 for c in plain_text if c.isupper()) / max(len(plain_text), 1)
    if uppercase_ratio > 0.3:
        score -= 10
        findings.append("[Content] Too much ALL CAPS")
    
    # Check for excessive punctuation
    if plain_text.count("!!!") > 0 or plain_text.count("???") > 0:
        score -= 5
        findings.append("[Content] Excessive punctuation")
    
    return score, findings, warnings

def score_headers(headers: dict) -> tuple[float, list[str], list[str]]:
    """Score email headers for compliance."""
    score = 100.0
    findings = []
    warnings = []
    
    # Check compliance headers
    if headers.get("Precedence") == "bulk":
        findings.append("[Headers] Precedence: bulk ✓")
    else:
        score -= 5
        warnings.append("[Headers] Missing Precedence: bulk")
    
    if headers.get("List-Unsubscribe"):
        findings.append("[Headers] List-Unsubscribe ✓")
    else:
        score -= 10
        warnings.append("[Headers] Missing List-Unsubscribe")
    
    if headers.get("Message-ID"):
        findings.append("[Headers] Message-ID present ✓")
    
    if headers.get("From") and headers.get("To"):
        findings.append("[Headers] From/To present ✓")
    
    # Check Message-ID format
    msg_id = headers.get("Message-ID", "")
    if "@nasrullahtanim.me" in msg_id or "@tanim.social" in msg_id:
        findings.append("[Headers] Proper Message-ID domain ✓")
    elif msg_id:
        score -= 5
        warnings.append("[Headers] Message-ID domain mismatch")
    
    return score, findings, warnings

def optimize_message(eml_bytes: bytes = None, subject: str = "", 
                     plain_text: str = "", html_text: str = "",
                     custom_headers: dict = None) -> OptimizationResult:
    """Main optimization function. Returns scored result."""
    
    result = OptimizationResult()
    all_findings = []
    all_warnings = []
    
    # Parse email if bytes provided
    if eml_bytes:
        try:
            msg = BytesParser(policy=policy.default).parsebytes(eml_bytes)
            subject = msg.get("Subject", "")
            plain_text = ""
            html_text = ""
            for part in msg.walk():
                if part.is_multipart():
                    continue
                if part.get_content_type() == "text/plain":
                    plain_text = part.get_payload(decode=True).decode("utf-8", "ignore")
                elif part.get_content_type() == "text/html":
                    html_text = part.get_payload(decode=True).decode("utf-8", "ignore")
        except Exception as e:
            result.warnings.append(f"[Parse] Error parsing email: {e}")
    
    # Score each component
    sub_score, sub_f, sub_w = score_subject(subject)
    all_findings.extend(sub_f)
    all_warnings.extend(sub_w)
    result.score += sub_score * 0.15  # Subject weight: 15%
    
    content_score, content_f, content_w = score_content(plain_text, html_text)
    all_findings.extend(content_f)
    all_warnings.extend(content_w)
    result.score += content_score * 0.45  # Content weight: 45%
    
    # Collect headers
    headers_dict = custom_headers or {}
    if subject:
        headers_dict["Subject"] = subject
    if not headers_dict.get("From"):
        headers_dict["From"] = "hello@nasrullahtanim.me"
    if not headers_dict.get("Message-ID"):
        import uuid
        headers_dict["Message-ID"] = f"<{uuid.uuid4().hex}@nasrullahtanim.me>"
    
    header_score, header_f, header_w = score_headers(headers_dict)
    all_findings.extend(header_f)
    all_warnings.extend(header_w)
    result.score += header_score * 0.20  # Headers weight: 20%
    
    # Domain reputation weight: 20%
    result.score += 80 * 0.20  # Assume good domain reputation
    
    # Clamp score
    result.score = max(0, min(100, result.score))
    
    # Determine grade
    if result.score >= 90:
        result.grade = "A"
    elif result.score >= 80:
        result.grade = "B"
    elif result.score >= 70:
        result.grade = "C"
    elif result.score >= 55:
        result.grade = "D"
    else:
        result.grade = "F"
    
    result.findings = all_findings
    result.warnings = all_warnings
    result.spam_score = 100 - result.score
    result.promotion_risk = sum(1 for w in all_warnings if "Promotions" in w) * 10 + sum(1 for f in all_findings if "Promotions" in f) * 15
    result.ai_sloop_risk = sum(1 for w in all_warnings if "AI-Slop" in w) * 10 + sum(1 for f in all_findings if "AI-Slop" in f) * 12
    
    # Filter passes
    result.passes = [f for f in all_findings if not f.startswith("[WARN]") and f.startswith("[")]
    
    return result

def main():
    """CLI entry point."""
    ap = ap = type(sys)('argparse')
    ap.add_argument("--subject", default="")
    ap.add_argument("--text", default="")
    ap.add_argument("--html", default="")
    ap.add_argument("--json", default="")
    ap.add_argument("file", nargs="?", default=None)
    ap.add_argument("--output", default="")
    
    # Parse args manually
    args = sys.argv[1:]
    
    subject = ""
    plain_text = ""
    html_text = ""
    eml_file = None
    output_json = False
    
    for i, arg in enumerate(args):
        if arg == "--subject" and i+1 < len(args):
            subject = args[i+1]
        elif arg == "--text" and i+1 < len(args):
            plain_text = args[i+1]
        elif arg == "--html" and i+1 < len(args):
            html_text = args[i+1]
        elif arg == "--json":
            output_json = True
        elif not arg.startswith("-"):
            eml_file = arg
    
    # Run optimization
    if eml_file:
        with open(eml_file, "rb") as f:
            result = optimize_message(eml_bytes=f.read())
    elif subject or plain_text:
        result = optimize_message(subject=subject, plain_text=plain_text, html_text=html_text)
    elif args and "--json" in args:
        try:
            data = json.loads(args[-1])
            result = optimize_message(subject=data.get("subject",""), plain_text=data.get("text",""), html_text=data.get("html",""))
        except:
            result = optimize_message()
    else:
        result = optimize_message()
    
    # Output
    if output_json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print("=" * 60)
        print("  INBOX PLACEMENT OPTIMIZATION REPORT")
        print("=" * 60)
        print(f"\n  Score: {result.score:.1f}/100  |  Grade: {result.grade}")
        print(f"  Spam Risk: {result.spam_score:.1f}  |  Promotions Risk: {result.promotion_risk:.1f}  |  AI-Slop Risk: {result.ai_sloop_risk:.1f}")
        
        if result.passes:
            print("\n  PASSES:")
            for p in result.passes:
                print(f"    ✓ {p}")
        
        if result.warnings:
            print("\n  WARNINGS:")
            for w in result.warnings:
                print(f"    ⚠ {w}")
        
        if result.findings:
            print("\n  FINDINGS:")
            for f in result.findings[:10]:
                print(f"    {f}")
        
        print(f"\n  RECOMMENDATION: {'Send' if result.grade in ('A','B') else 'Fix issues before sending'}")
        print("=" * 60)

if __name__ == "__main__":
    main()
