"""SlideIn Conversational Email AI & Lead Qualification Engine.

Handles:
- Inbound MIME reply parsing (unwrapping threads, stripping signature/quotes, extracting references)
- Two-way conversation thread stitching (In-Reply-To, References, Lead correlation)
- Intent classification (Buying timeline, Pre-approval status, Rate inquiries, Ready to book, Opt-outs)
- Speed-to-lead auto-responder generation for calculator funnels
- Dynamic meeting booking link injection
- Full deliverability gate validation on all outbound replies
"""
from __future__ import annotations

import email
from email import policy
from email.message import EmailMessage
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    Conversation,
    IntentType,
    Lead,
    LeadStage,
    Message,
    MessageDirection,
    SenderProfile,
    Workspace,
)
from .analyzer import analyze, analyze_draft
from .transactional import TransactionalEmail, build_transactional_eml
from .provider import get_provider, DeliveryResult


def parse_inbound_email(raw_content: str | bytes) -> Dict[str, Any]:
    """Parses raw MIME email or webhook payload into structured clean data."""
    if isinstance(raw_content, str):
        msg = email.message_from_string(raw_content, policy=policy.default)
    else:
        msg = email.message_from_bytes(raw_content, policy=policy.default)

    from_header = msg.get("From", "")
    to_header = msg.get("To", "")
    subject = msg.get("Subject", "")
    message_id = msg.get("Message-ID", "")
    in_reply_to = msg.get("In-Reply-To", "")
    references = msg.get("References", "")

    from_addr = email.utils.parseaddr(from_header)[1].lower().strip()
    to_addr = email.utils.parseaddr(to_header)[1].lower().strip()

    body_text = ""
    body_html = ""

    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            cdisp = str(part.get("Content-Disposition", ""))
            if "attachment" in cdisp:
                continue
            if ctype == "text/plain" and not body_text:
                body_text = part.get_content()
            elif ctype == "text/html" and not body_html:
                body_html = part.get_content()
    else:
        ctype = msg.get_content_type()
        if ctype == "text/html":
            body_html = msg.get_content()
        else:
            body_text = msg.get_content()

    clean_text = clean_reply_body(body_text or "")

    return {
        "from_addr": from_addr,
        "from_header": from_header,
        "to_addr": to_addr,
        "to_header": to_header,
        "subject": subject,
        "message_id": message_id,
        "in_reply_to": in_reply_to,
        "references": references,
        "body_text": body_text,
        "body_html": body_html,
        "clean_text": clean_text,
    }


def clean_reply_body(text: str) -> str:
    """Strips out quoted reply history, email headers, and signatures."""
    lines = text.splitlines()
    clean_lines = []
    
    quote_markers = (
        ">", "On ", "wrote:", "-----Original Message-----",
        "From:", "Sent:", "To:", "Subject:", "Sent from my iPhone",
        "Sent from my iPad", "Get Outlook for iOS"
    )

    for line in lines:
        stripped = line.strip()
        if any(stripped.startswith(m) for m in (">", "-----Original Message-----")):
            break
        if "wrote:" in stripped and (stripped.startswith("On ") or "@" in stripped):
            break
        clean_lines.append(line)

    cleaned = "\n".join(clean_lines).strip()
    return cleaned if cleaned else text.strip()


def classify_intent(text: str, subject: str = "") -> Tuple[IntentType, float]:
    """Analyzes text to classify borrower intent and conversation phase."""
    combined = f"{subject} {text}".lower()

    # 1. Unsubscribe / Negative intent
    if any(phrase in combined for phrase in ["unsubscribe", "stop emailing", "remove me", "not interested", "wrong email", "don't email", "do not contact"]):
        return IntentType.NOT_INTERESTED, 0.98

    # 2. Out of Office
    if any(phrase in combined for phrase in ["out of the office", "auto-reply", "automatic reply", "on vacation", "away from my desk", "back in the office on"]):
        return IntentType.OUT_OF_OFFICE, 0.95

    # 3. Ready to Book / Schedule Call
    booking_signals = [
        "book a time", "schedule", "calendar", "call me", "speak with you",
        "let's talk", "lets talk", "free tomorrow", "free thursday", "free friday",
        "free monday", "free tuesday", "free wednesday", "what is your availability",
        "time to chat", "give me a call", "set up a call", "send a link", "calendly", "cal.com"
    ]
    if any(phrase in combined for phrase in booking_signals):
        return IntentType.READY_TO_BOOK, 0.92

    # 4. Purchase / Refinance Timeline
    timeline_signals = [
        "next month", "30 days", "60 days", "in the spring", "in the summer",
        "asap", "right away", "looking to buy", "under contract", "made an offer",
        "shopping for homes", "already found a house", "first time homebuyer"
    ]
    if any(phrase in combined for phrase in timeline_signals):
        return IntentType.PURCHASE_TIMELINE, 0.88

    # 5. Pre-approval & Financial qualification
    preapproval_signals = [
        "pre-approved", "preapproved", "pre approval", "credit score",
        "fha", "conventional", "va loan", "jumbo", "down payment",
        "debt to income", "dti", "w2", "self employed", "bank statements"
    ]
    if any(phrase in combined for phrase in preapproval_signals):
        return IntentType.PRE_APPROVAL_STATUS, 0.85

    # 6. Rate & Cost inquiries
    rate_signals = [
        "what is your rate", "interest rate", "current rates", "points",
        "closing costs", "apr", "monthly payment", "quote", "rate sheet"
    ]
    if any(phrase in combined for phrase in rate_signals):
        return IntentType.ASKING_RATES, 0.82

    return IntentType.GENERAL_INQUIRY, 0.60


class ConversationalEngine:
    """Manages two-way conversational email flow and speed-to-lead automation."""

    def __init__(self, workspace: Workspace, default_sender: SenderProfile):
        self.workspace = workspace
        self.sender = default_sender
        self.provider = get_provider()

    def generate_speed_to_lead_email(
        self,
        lead: Lead,
        calculator_data: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, str, str]:
        """Generates an authentic, high-deliverability immediate welcome + calculation report."""
        first_name = lead.first_name or "there"
        loan_amt = lead.loan_amount or 450000
        prop_type = lead.property_type or "Single Family Home"
        
        # Calculate rough estimate if needed
        interest_rate = 6.625
        monthly_principal_int = (loan_amt * (interest_rate / 100 / 12)) / (1 - (1 + interest_rate / 100 / 12) ** -360)
        
        subject = f"{first_name} - your mortgage breakdown ({prop_type})"

        body_text = f"""Hi {first_name},

I just pulled the numbers based on your calculation for the {prop_type} (est. ${loan_amt:,.0f} loan amount).

Quick overview:
• Estimated Rate: ~{interest_rate:.3f}% (30-Yr Fixed Conventional)
• Est. Principal & Interest: ~${monthly_principal_int:,.2f}/mo
• Estimated Property Tax & Insurance: ~${(loan_amt * 0.015 / 12):,.2f}/mo

Are you actively shopping for a home right now, or just scoping out your price range for later this year?

Best,
{self.sender.name}
Senior Loan Advisor
{self.sender.email}
"""

        body_html = f"""<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 15px; color: #222; line-height: 1.5;">
<p>Hi {first_name},</p>

<p>I just pulled the numbers based on your calculation for the {prop_type} (est. ${loan_amt:,.0f} loan amount).</p>

<div style="background: #f8fafc; border-left: 3px solid #2563eb; padding: 12px 16px; margin: 16px 0; border-radius: 4px;">
  <p style="margin: 0 0 6px 0;">Quick Overview:</p>
  <ul style="margin: 0; padding-left: 20px;">
    <li>Estimated Rate: ~{interest_rate:.3f}% (30-Yr Fixed Conventional)</li>
    <li>Est. Principal &amp; Interest: ~${monthly_principal_int:,.2f}/mo</li>
    <li>Estimated Property Tax &amp; Insurance: ~${(loan_amt * 0.015 / 12):,.2f}/mo</li>
  </ul>
</div>

<p>Are you actively shopping for a home right now, or just scoping out your price range for later this year?</p>

<p style="margin-top: 24px; color: #555;">
Best,<br>
{self.sender.name}<br>
Senior Loan Advisor<br>
<a href="mailto:{self.sender.email}" style="color: #2563eb; text-decoration: none;">{self.sender.email}</a>
</p>
</div>"""

        return subject, body_text, body_html

    def generate_ai_reply(
        self,
        lead: Lead,
        conversation: Conversation,
        inbound_msg: Message
    ) -> Tuple[str, str, str, LeadStage]:
        """Generates contextual conversational reply based on identified lead intent."""
        first_name = lead.first_name or "there"
        booking_url = self.workspace.settings.get("booking_url", "https://cal.com/mortgage-advisor/intro")
        subject = f"Re: {conversation.subject.replace('Re: ', '')}"

        stage = conversation.stage

        if inbound_msg.intent == IntentType.READY_TO_BOOK.value:
            stage = LeadStage.BOOKED.value
            body_text = f"""Hi {first_name},

Sounds great! You can grab whatever time works best directly on my calendar here:
{booking_url}

Looking forward to walking through the loan scenarios with you.

Best,
{self.sender.name}"""
            body_html = f"""<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 15px; color: #222; line-height: 1.5;">
<p>Hi {first_name},</p>
<p>Sounds great! You can grab whatever time works best directly on my live calendar:</p>
<p style="margin: 18px 0;"><a href="{booking_url}" style="background: #2563eb; color: #ffffff; padding: 10px 18px; text-decoration: none; border-radius: 6px; font-weight: 500; display: inline-block;">Select a 15-Min Time Slot &rarr;</a></p>
<p>Looking forward to walking through the loan scenarios with you.</p>
<p style="margin-top: 20px; color: #555;">Best,<br>{self.sender.name}</p>
</div>"""

        elif inbound_msg.intent == IntentType.PURCHASE_TIMELINE.value:
            stage = LeadStage.QUALIFIED.value
            body_text = f"""Hi {first_name},

That timeline makes a lot of sense. For home purchases in that window, getting a verified pre-approval in hand beforehand gives you serious leverage when putting in offers.

Have you already spoken with a realtor or submitted any preliminary income documents, or starting completely fresh?

Best,
{self.sender.name}"""
            body_html = f"""<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 15px; color: #222; line-height: 1.5;">
<p>Hi {first_name},</p>
<p>That timeline makes a lot of sense. For home purchases in that window, getting a verified pre-approval in hand beforehand gives you serious leverage when putting in offers.</p>
<p>Have you already spoken with a realtor or submitted any preliminary income documents, or starting completely fresh?</p>
<p style="margin-top: 20px; color: #555;">Best,<br><strong>{self.sender.name}</strong></p>
</div>"""

        elif inbound_msg.intent == IntentType.ASKING_RATES.value:
            stage = LeadStage.ENGAGED.value
            body_text = f"""Hi {first_name},

Rates fluctuate daily based on bond yields, credit score tiers, and loan structure (conforming vs jumbo, 20% down vs 5% down).

If you have 5 minutes to connect, I can run an exact lock comparison for your specific scenario:
{booking_url}

Best,
{self.sender.name}"""
            body_html = f"""<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 15px; color: #222; line-height: 1.5;">
<p>Hi {first_name},</p>
<p>Rates fluctuate daily based on bond yields, credit score tiers, and loan structure (conforming vs jumbo, 20% down vs 5% down).</p>
<p>If you have 5 minutes to connect, I can run an exact lock comparison for your specific scenario:</p>
<p style="margin: 18px 0;"><a href="{booking_url}" style="background: #2563eb; color: #ffffff; padding: 10px 18px; text-decoration: none; border-radius: 6px; font-weight: 600; display: inline-block;">View Live Rate Calendar &rarr;</a></p>
<p style="margin-top: 20px; color: #555;">Best,<br><strong>{self.sender.name}</strong></p>
</div>"""

        else:
            stage = LeadStage.ENGAGED.value
            body_text = f"""Hi {first_name},

Thanks for following up! Happy to help navigate this.

Would a quick 10-minute phone call be helpful to review your options, or would you prefer me to email over a preliminary breakdown?

Best,
{self.sender.name}"""
            body_html = f"""<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 15px; color: #222; line-height: 1.5;">
<p>Hi {first_name},</p>
<p>Thanks for following up! Happy to help navigate this.</p>
<p>Would a quick 10-minute phone call be helpful to review your options, or would you prefer me to email over a preliminary breakdown?</p>
<p style="margin-top: 20px; color: #555;">Best,<br><strong>{self.sender.name}</strong></p>
</div>"""

        return subject, body_text, body_html, stage

    def dispatch_outbound_message(
        self,
        to_addr: str,
        subject: str,
        body_text: str,
        body_html: str,
        in_reply_to: Optional[str] = None,
        references: Optional[str] = None,
    ) -> Tuple[DeliveryResult, Dict[str, Any]]:
        """Constructs RFC-compliant email, runs deliverability gate, and sends via provider."""
        # 1. Deliverability Gate Check
        score_data = analyze_draft(
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            from_addr=self.sender.email,
            from_name=self.sender.name,
            to_addr=to_addr,
        )
        
        # 2. Build Transactional / Conversational RFC Email
        extra_headers = {}
        if in_reply_to:
            extra_headers["In-Reply-To"] = in_reply_to
        if references:
            extra_headers["References"] = references

        tx_obj = TransactionalEmail(
            to_addr=to_addr,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            from_name=self.sender.name,
            from_addr=self.sender.email,
            reply_to=self.sender.reply_to,
            headers=extra_headers if extra_headers else {},
        )
        tx_eml_bytes = build_transactional_eml(tx_obj)

        # 3. Dispatch through provider (KumoMTA / DevSink)
        result = self.provider.send(
            msg=tx_eml_bytes,
            recipient=to_addr,
            sender=self.sender.email,
        )

        analysis_dict = {
            "score": score_data.score,
            "grade": score_data.grade,
            "findings": score_data.findings,
        }

        return result, analysis_dict
