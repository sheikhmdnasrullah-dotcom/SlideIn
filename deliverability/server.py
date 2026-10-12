"""SlideIn Enterprise Email Platform & Conversational AI API Server.

Provides:
- Complete REST API for multi-tenant workspaces, calculator funnels, leads, conversational AI threads, and deliverability scoring.
- Live Web Command Center UI with pipeline KPIs, real-time email thread inspector, deliverability scoring sandbox, and speed-to-lead test bench.
"""
from __future__ import annotations

import email
import hmac
import json
import os
import re
import socket
import sys
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from core.models import (
    Conversation,
    DomainRecord,
    IntentType,
    Lead,
    LeadStage,
    Message,
    MessageDirection,
    SenderProfile,
    Workspace,
)
from core.repository import SlideInRepository
from core.conversational import (
    ConversationalEngine,
    classify_intent,
    clean_reply_body,
    parse_inbound_email,
)
from core.analyzer import analyze, analyze_draft
from core.provider import get_provider
from core import state as st

PORT = int(os.environ.get("PORT", "8088"))
HOST = "0.0.0.0"

repo = SlideInRepository()


class SlideInAPIHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for SlideIn REST API & Command Center."""

    def log_message(self, format: str, *args: Any) -> None:
        # Clean logging
        sys_msg = format % args
        if not sys_msg.startswith('"GET /favicon.ico'):
            print(f"[SlideIn API] {self.address_string()} - {sys_msg}")

    def _send_json(self, data: Any, status: int = 200) -> None:
        payload = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Key")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.end_headers()
        self.wfile.write(payload)

    def _send_html(self, html_content: str, status: int = 200) -> None:
        payload = html_content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _read_body_json(self) -> Dict[str, Any]:
        try:
            content_len = int(self.headers.get("Content-Length", 0))
            if content_len == 0:
                return {}
            raw_body = self.rfile.read(content_len)
            return json.loads(raw_body.decode("utf-8"))
        except Exception as e:
            return {}

    def _read_body_raw(self) -> bytes:
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len == 0:
            return b""
        return self.rfile.read(content_len)

    def _extract_api_key(self, query: Optional[Dict[str, List[str]]] = None) -> str:
        """Extract the caller's API key from header (preferred) or query param.

        The query-param fallback exists only for browser access to the
        dashboard UI, which cannot set headers. API clients must use
        ``X-API-Key`` or ``Authorization: Bearer``.
        """
        key = self.headers.get("X-API-Key") or ""
        if not key:
            auth = self.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                key = auth[len("Bearer "):]
            elif auth:
                key = auth
        if not key and query:
            values = query.get("api_key", [])
            if values:
                key = values[0]
        return key

    def _get_workspace_id(self, query: Optional[Dict[str, List[str]]] = None) -> Optional[str]:
        """Return the workspace id for a valid API key, else None.

        Missing, empty, or unknown keys authenticate to nothing — there is
        intentionally no default-workspace fallback (audit S2). Comparison
        is constant-time.
        """
        api_key = self._extract_api_key(query)
        if not api_key:
            return None
        for ws in repo.list_workspaces():
            if ws.api_key and hmac.compare_digest(str(ws.api_key), api_key):
                return ws.id
        return None

    def _require_auth(self, query: Optional[Dict[str, List[str]]] = None) -> Optional[str]:
        """Authenticate the request; send 401 and return None on failure."""
        ws_id = self._get_workspace_id(query)
        if ws_id is None:
            self._send_json({"error": "Valid API key required (X-API-Key header)"}, status=401)
            return None
        return ws_id

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Key")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # 1. UI Root / Dashboard (key via header or ?api_key= for browsers)
        if path in ("/", "/dashboard", "/app"):
            self._handle_dashboard_ui(query)
            return

        # 2. Health Check
        if path == "/health":
            provider = get_provider()
            health = provider.health_check()
            is_healthy = bool(health.get("healthy"))
            self._send_json({
                "status": "healthy" if is_healthy else "degraded",
                "timestamp": time.time(),
                "service": "SlideIn Enterprise Platform",
                "transport": {
                    "provider": provider.name,
                    "healthy": is_healthy,
                    "details": health,
                },
            })
            return

        # 3. System Status & Pipeline KPIs
        if path == "/v1/status":
            ws_id = self._require_auth()
            if ws_id is None:
                return
            stats = repo.get_pipeline_stats(ws_id)
            self._send_json({
                "status": "operational",
                "workspace_id": ws_id,
                "stats": stats,
                "server_time": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            })
            return

        # 4. Workspaces (authenticated; key material redacted)
        if path == "/v1/workspaces":
            ws_id = self._require_auth()
            if ws_id is None:
                return
            workspaces = []
            for w in repo.list_workspaces():
                item = w.to_dict()
                item.pop("api_key", None)
                workspaces.append(item)
            self._send_json({"workspaces": workspaces})
            return

        # 5. Verified Domains
        if path == "/v1/domains":
            ws_id = self._require_auth()
            if ws_id is None:
                return
            domains = [d.to_dict() for d in repo.list_domains(ws_id)]
            self._send_json({"domains": domains})
            return

        # 6. Senders
        if path == "/v1/senders":
            ws_id = self._require_auth()
            if ws_id is None:
                return
            senders = [s.to_dict() for s in repo.list_senders(ws_id)]
            self._send_json({"senders": senders})
            return

        # 7. Leads List
        if path == "/v1/leads":
            ws_id = self._require_auth()
            if ws_id is None:
                return
            limit = int(query.get("limit", [50])[0])
            leads = [l.to_dict() for l in repo.list_leads(ws_id, limit=limit)]
            self._send_json({"leads": leads, "count": len(leads)})
            return

        # 8. Conversations List
        if path == "/v1/conversations":
            ws_id = self._require_auth()
            if ws_id is None:
                return
            limit = int(query.get("limit", [50])[0])
            convs = [c.to_dict() for c in repo.list_conversations(ws_id, limit=limit)]
            self._send_json({"conversations": convs, "count": len(convs)})
            return

        # 9. Single Conversation Thread View
        if path.startswith("/v1/conversations/"):
            ws_id = self._require_auth()
            if ws_id is None:
                return
            conv_id = path.split("/")[-1]
            conv = repo.get_conversation(conv_id)
            if not conv or conv.workspace_id != ws_id:
                self._send_json({"error": "Conversation not found"}, status=404)
                return
            messages = [m.to_dict() for m in repo.list_messages(conv_id)]
            self._send_json({
                "conversation": conv.to_dict(),
                "messages": messages,
                "message_count": len(messages),
            })
            return

        # 10. Send Events Log
        if path == "/v1/events/sends":
            if self._require_auth() is None:
                return
            store = st.Store()
            events = store.recent_send_events(limit=50)
            self._send_json({"events": events})
            return

        # 11. Warmup Pool Stats
        if path == "/v1/warmup/stats":
            if self._require_auth() is None:
                return
            self._send_json({
                "warmup_pool": "SlideIn Peer-to-Peer Warmup Mesh",
                "active_senders": 3,
                "current_ramp_day": 21,
                "daily_capacity": 150,
                "inbox_placement_rate": "100.0%",
                "status": "healthy",
            })
            return

        self._send_json({"error": "Endpoint not found"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        # 1. Funnel Lead Ingest (Speed-to-Lead Auto-Responder & Thread Starter)
        if path == "/v1/leads/submit":
            data = self._read_body_json()
            email_addr = data.get("email", "").strip().lower()
            if not email_addr or "@" not in email_addr:
                self._send_json({"error": "Valid 'email' is required"}, status=400)
                return

            ws_id = self._require_auth()
            if ws_id is None:
                return
            ws = repo.get_workspace(ws_id)
            if ws is None:
                self._send_json({"error": "Workspace unavailable"}, status=401)
                return

            # Eligibility: breaker halt + suppression, before any lead
            # record is created or mail dispatched (roadmap Stage 2).
            elig_store = st.Store()
            if elig_store.get_circuit()["status"] == "open":
                reason = elig_store.get_circuit().get("reason", "circuit open")
                elig_store.record_send_event(
                    recipient=email_addr, provider="kumomta",
                    result="blocked_breaker",
                    detail=f"Circuit open: {reason}",
                )
                self._send_json(
                    {"error": "Sending paused: circuit breaker is open"},
                    status=503,
                )
                return
            if elig_store.is_suppressed(email_addr):
                elig_store.record_send_event(
                    recipient=email_addr, provider="kumomta",
                    result="skipped_suppressed",
                    detail="Recipient on suppression list",
                )
                self._send_json(
                    {"error": "Recipient is suppressed"}, status=403
                )
                return
            sender = repo.get_default_sender(ws.id)

            # Create or update lead
            existing_lead = repo.get_lead_by_email(ws.id, email_addr)
            first_name = data.get("first_name", "") or (existing_lead.first_name if existing_lead else "")
            last_name = data.get("last_name", "") or (existing_lead.last_name if existing_lead else "")
            phone = data.get("phone", "") or (existing_lead.phone if existing_lead else "")
            loan_amount = float(data.get("loan_amount", 450000))
            property_type = data.get("property_type", "Single Family Home")
            timeline = data.get("purchase_timeline", "30-60 days")
            credit_tier = data.get("credit_tier", "Excellent (740+)")

            lead = Lead(
                id=existing_lead.id if existing_lead else f"lead_{int(time.time()*1000)}",
                workspace_id=ws.id,
                email=email_addr,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                source=data.get("source", "mortgage_calculator_funnel"),
                stage=LeadStage.ENGAGED.value,
                loan_amount=loan_amount,
                property_type=property_type,
                purchase_timeline=timeline,
                credit_tier=credit_tier,
                custom_fields=data.get("custom_fields", {}),
                updated_at=time.time(),
            )
            repo.save_lead(lead)

            # Generate Speed-to-lead Email
            engine = ConversationalEngine(ws, sender)
            subj, text_body, html_body = engine.generate_speed_to_lead_email(lead, calculator_data=data)

            # Send via Provider (KumoMTA / DevSink)
            delivery_res, analysis = engine.dispatch_outbound_message(
                to_addr=lead.email,
                subject=subj,
                body_text=text_body,
                body_html=html_body,
            )

            # Create Conversation Thread
            conv = repo.find_conversation_by_lead_email(ws.id, lead.email)
            if not conv:
                conv = Conversation(
                    id=f"conv_{int(time.time()*1000)}",
                    workspace_id=ws.id,
                    lead_id=lead.id,
                    lead_email=lead.email,
                    lead_name=f"{lead.first_name} {lead.last_name}".strip() or lead.email,
                    subject=subj,
                    thread_root_msg_id=delivery_res.message_id,
                    stage=LeadStage.ENGAGED.value,
                    latest_intent=IntentType.UNKNOWN.value,
                )
            else:
                conv.message_count += 1
                conv.latest_message_at = time.time()
            repo.save_conversation(conv)

            # Save Message Record
            msg_record = Message(
                id=f"msg_{int(time.time()*1000)}",
                conversation_id=conv.id,
                workspace_id=ws.id,
                direction=MessageDirection.OUTBOUND.value,
                from_addr=sender.email,
                to_addr=lead.email,
                subject=subj,
                body_text=text_body,
                body_html=html_body,
                message_id_header=delivery_res.message_id,
                deliverability_score=analysis["score"],
                deliverability_grade=analysis["grade"],
                status="sent" if delivery_res.is_success else "failed",
            )
            repo.save_message(msg_record)

            # Record event in deliverability state
            st.Store().record_send_event(
                recipient=lead.email,
                provider=delivery_res.provider,
                result="sent" if delivery_res.is_success else "failed",
                detail=f"Speed-to-lead calculation report sent via {delivery_res.provider}",
            )

            self._send_json({
                "success": True,
                "lead": lead.to_dict(),
                "conversation_id": conv.id,
                "delivery": {
                    "status": delivery_res.status,
                    "provider": delivery_res.provider,
                    "message_id": delivery_res.message_id,
                    "score": analysis["score"],
                    "grade": analysis["grade"],
                }
            }, status=201)
            return

        # 2. Inbound Email Reply Ingest Webhook
        if path == "/v1/inbound/webhook":
            raw_body = self._read_body_raw()
            content_type = self.headers.get("Content-Type", "")

            # Can accept raw MIME or JSON webhook payload
            if "application/json" in content_type:
                json_data = json.loads(raw_body.decode("utf-8"))
                from_addr = json_data.get("from_addr", "") or json_data.get("from", "")
                subject = json_data.get("subject", "")
                body_text = json_data.get("body_text", "") or json_data.get("text", "")
                body_html = json_data.get("body_html", "") or json_data.get("html", "")
                in_reply_to = json_data.get("in_reply_to", "")
                references = json_data.get("references", "")
                clean_text = clean_reply_body(body_text)
            else:
                parsed_mime = parse_inbound_email(raw_body)
                from_addr = parsed_mime["from_addr"]
                subject = parsed_mime["subject"]
                body_text = parsed_mime["body_text"]
                body_html = parsed_mime["body_html"]
                in_reply_to = parsed_mime["in_reply_to"]
                references = parsed_mime["references"]
                clean_text = parsed_mime["clean_text"]

            if not from_addr:
                self._send_json({"error": "Unable to extract sender 'from_addr'"}, status=400)
                return

            ws_id = self._require_auth()
            if ws_id is None:
                return
            ws = repo.get_workspace(ws_id)
            if ws is None:
                self._send_json({"error": "Workspace unavailable"}, status=401)
                return
            sender = repo.get_default_sender(ws.id)

            # Match conversation thread. The message-id lookup is global,
            # so a match belonging to another workspace must be discarded —
            # inbound mail never attaches to a foreign thread (audit S3).
            conv = repo.find_conversation_by_message_id(in_reply_to)
            if conv is not None and conv.workspace_id != ws.id:
                conv = None
            if not conv:
                conv = repo.find_conversation_by_lead_email(ws.id, from_addr)

            lead = repo.get_lead_by_email(ws.id, from_addr)
            if not lead:
                lead = Lead(
                    workspace_id=ws.id,
                    email=from_addr,
                    source="inbound_reply",
                    stage=LeadStage.ENGAGED.value,
                )
                repo.save_lead(lead)

            if not conv:
                conv = Conversation(
                    id=f"conv_{int(time.time()*1000)}",
                    workspace_id=ws.id,
                    lead_id=lead.id,
                    lead_email=lead.email,
                    lead_name=lead.email,
                    subject=subject,
                    stage=LeadStage.ENGAGED.value,
                )

            # Classify Intent
            intent, confidence = classify_intent(clean_text, subject=subject)
            conv.latest_intent = intent.value
            conv.latest_message_at = time.time()
            conv.message_count += 1

            # Save Inbound Message
            inbound_msg = Message(
                id=f"msg_in_{int(time.time()*1000)}",
                conversation_id=conv.id,
                workspace_id=ws.id,
                direction=MessageDirection.INBOUND.value,
                from_addr=from_addr,
                to_addr=sender.email,
                subject=subject,
                body_text=clean_text,
                body_html=body_html,
                in_reply_to=in_reply_to,
                references=references,
                intent=intent.value,
                intent_confidence=confidence,
                status="delivered",
            )
            repo.save_message(inbound_msg)

            # Generate and dispatch automated conversational reply if enabled
            engine = ConversationalEngine(ws, sender)
            auto_reply_sent = False
            auto_reply_details = None

            if ws.settings.get("auto_qualify_enabled", True) and intent != IntentType.NOT_INTERESTED:
                reply_subj, reply_text, reply_html, new_stage = engine.generate_ai_reply(lead, conv, inbound_msg)
                stage_val = new_stage.value if hasattr(new_stage, "value") else str(new_stage)
                conv.stage = stage_val
                lead.stage = stage_val
                repo.save_lead(lead)

                delivery_res, analysis = engine.dispatch_outbound_message(
                    to_addr=lead.email,
                    subject=reply_subj,
                    body_text=reply_text,
                    body_html=reply_html,
                    in_reply_to=inbound_msg.message_id_header or in_reply_to,
                    references=references or in_reply_to,
                )

                outbound_ai_msg = Message(
                    id=f"msg_ai_{int(time.time()*1000)}",
                    conversation_id=conv.id,
                    workspace_id=ws.id,
                    direction=MessageDirection.OUTBOUND.value,
                    from_addr=sender.email,
                    to_addr=lead.email,
                    subject=reply_subj,
                    body_text=reply_text,
                    body_html=reply_html,
                    message_id_header=delivery_res.message_id,
                    in_reply_to=inbound_msg.message_id_header or in_reply_to,
                    intent=intent.value,
                    deliverability_score=analysis["score"],
                    deliverability_grade=analysis["grade"],
                    status="sent" if delivery_res.is_success else "failed",
                )
                repo.save_message(outbound_ai_msg)
                conv.message_count += 1
                auto_reply_sent = True
                auto_reply_details = {
                    "subject": reply_subj,
                    "message_id": delivery_res.message_id,
                    "stage": stage_val,
                    "score": analysis["score"],
                }

            repo.save_conversation(conv)

            self._send_json({
                "success": True,
                "conversation_id": conv.id,
                "intent": intent.value,
                "confidence": confidence,
                "auto_reply_sent": auto_reply_sent,
                "auto_reply": auto_reply_details,
            })
            return

        # 3. Deliverability Score Sandbox Endpoint
        if path == "/v1/drafts/score":
            if self._require_auth() is None:
                return
            data = self._read_body_json()
            subj = data.get("subject", "")
            body = data.get("body_text", "")
            html = data.get("body_html", "")
            
            analysis = analyze_draft(subject=subj, body_text=body, body_html=html)
            self._send_json({
                "score": analysis.score,
                "grade": analysis.grade,
                "findings": analysis.findings,
                "clean_text_length": len(body),
                "is_approved": analysis.score >= 80,
                "recommendation": "Ready for delivery" if analysis.score >= 80 else "Fix flagged spam markers",
            })
            return

        # 4. Manual / Agent In-Thread Reply
        if re.match(r"^/v1/conversations/[^/]+/reply$", path):
            ws_id = self._require_auth()
            if ws_id is None:
                return
            conv_id = path.split("/")[3]
            conv = repo.get_conversation(conv_id)
            if not conv or conv.workspace_id != ws_id:
                self._send_json({"error": "Conversation not found"}, status=404)
                return

            data = self._read_body_json()
            body_text = data.get("body_text", "").strip()
            if not body_text:
                self._send_json({"error": "body_text is required"}, status=400)
                return

            ws = repo.get_workspace(conv.workspace_id)
            sender = repo.get_default_sender(ws.id)
            engine = ConversationalEngine(ws, sender)
            subject = f"Re: {conv.subject.replace('Re: ', '')}"
            html_body = f"<p>{body_text.replace(chr(10), '<br>')}</p>"

            delivery_res, analysis = engine.dispatch_outbound_message(
                to_addr=conv.lead_email,
                subject=subject,
                body_text=body_text,
                body_html=html_body,
                in_reply_to=conv.thread_root_msg_id,
            )

            msg_rec = Message(
                id=f"msg_agent_{int(time.time()*1000)}",
                conversation_id=conv.id,
                workspace_id=ws.id,
                direction=MessageDirection.OUTBOUND.value,
                from_addr=sender.email,
                to_addr=conv.lead_email,
                subject=subject,
                body_text=body_text,
                body_html=html_body,
                message_id_header=delivery_res.message_id,
                deliverability_score=analysis["score"],
                deliverability_grade=analysis["grade"],
                status="sent" if delivery_res.is_success else "failed",
            )
            repo.save_message(msg_rec)

            conv.latest_message_at = time.time()
            conv.message_count += 1
            repo.save_conversation(conv)

            self._send_json({
                "success": True,
                "message": msg_rec.to_dict(),
                "delivery": {
                    "status": delivery_res.status,
                    "message_id": delivery_res.message_id,
                }
            })
            return

        self._send_json({"error": "Endpoint not found"}, status=404)

    def _handle_dashboard_ui(self, query: Optional[Dict[str, List[str]]] = None) -> None:
        """Renders SlideIn Web Command Center & Lead Pipeline UI."""
        ws_id = self._require_auth(query)
        if ws_id is None:
            return
        stats = repo.get_pipeline_stats(ws_id)
        convs = repo.list_conversations(ws_id, limit=20)
        leads = repo.list_leads(ws_id, limit=20)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SlideIn — Enterprise Email & Conversational AI Command Center</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #090d16;
      --card: #111827;
      --card-border: #1f293d;
      --accent: #2563eb;
      --accent-glow: rgba(37, 99, 235, 0.25);
      --success: #10b981;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --font: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      --font-mono: 'JetBrains Mono', monospace;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: var(--bg); color: var(--text); font-family: var(--font); padding: 24px; }}
    .container {{ max-width: 1380px; margin: 0 auto; }}
    
    header {{ display: flex; justify-content: space-between; align-items: center; padding-bottom: 24px; border-bottom: 1px solid var(--card-border); margin-bottom: 24px; }}
    .brand {{ display: flex; align-items: center; gap: 12px; }}
    .brand-logo {{ width: 36px; height: 36px; background: linear-gradient(135deg, #2563eb, #38bdf8); border-radius: 10px; display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 18px; color: white; box-shadow: 0 0 16px var(--accent-glow); }}
    .brand h1 {{ font-size: 20px; font-weight: 700; letter-spacing: -0.02em; }}
    .brand p {{ font-size: 12px; color: var(--text-muted); }}

    .status-badge {{ display: inline-flex; align-items: center; gap: 6px; padding: 6px 14px; background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.25); border-radius: 999px; color: #34d399; font-size: 12px; font-weight: 600; }}
    .status-badge::before {{ content: ""; width: 8px; height: 8px; border-radius: 50%; background: #10b981; box-shadow: 0 0 8px #10b981; }}

    .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 28px; }}
    .stat-card {{ background: var(--card); border: 1px solid var(--card-border); border-radius: 12px; padding: 18px 20px; }}
    .stat-title {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted); margin-bottom: 6px; }}
    .stat-value {{ font-size: 26px; font-weight: 700; color: white; }}
    .stat-hint {{ font-size: 11px; color: #34d399; margin-top: 4px; font-weight: 500; }}

    .main-grid {{ display: grid; grid-template-columns: 1.2fr 0.8fr; gap: 24px; }}
    @media (max-width: 1024px) {{ .main-grid {{ grid-template-columns: 1fr; }} }}

    .card {{ background: var(--card); border: 1px solid var(--card-border); border-radius: 14px; padding: 22px; margin-bottom: 24px; }}
    .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; }}
    .card-header h2 {{ font-size: 16px; font-weight: 600; }}

    .thread-list {{ display: flex; flex-direction: column; gap: 12px; }}
    .thread-item {{ background: #0c1220; border: 1px solid var(--card-border); border-radius: 10px; padding: 16px; transition: border 0.15s; }}
    .thread-item:hover {{ border-color: var(--accent); }}
    .thread-top {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
    .thread-lead {{ font-weight: 600; font-size: 14px; color: #fff; }}
    .thread-badge {{ font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 6px; text-transform: uppercase; }}
    .badge-booked {{ background: rgba(16, 185, 129, 0.15); color: #34d399; }}
    .badge-qualified {{ background: rgba(59, 130, 246, 0.15); color: #60a5fa; }}
    .badge-engaged {{ background: rgba(245, 158, 11, 0.15); color: #fbbf24; }}
    .thread-subj {{ font-size: 13px; color: var(--text-muted); margin-bottom: 6px; }}
    .thread-footer {{ display: flex; justify-content: space-between; font-size: 11px; color: #64748b; margin-top: 8px; font-family: var(--font-mono); }}

    /* Form Controls */
    .form-group {{ margin-bottom: 14px; }}
    label {{ display: block; font-size: 12px; font-weight: 500; color: var(--text-muted); margin-bottom: 6px; }}
    input, select, textarea {{ width: 100%; background: #090d16; border: 1px solid var(--card-border); border-radius: 8px; padding: 10px 14px; color: white; font-family: var(--font); font-size: 13px; outline: none; }}
    input:focus, textarea:focus {{ border-color: var(--accent); }}
    .btn-submit {{ width: 100%; background: var(--accent); color: white; border: none; padding: 12px; border-radius: 8px; font-weight: 600; font-size: 13px; cursor: pointer; transition: background 0.15s; box-shadow: 0 0 12px var(--accent-glow); }}
    .btn-submit:hover {{ background: #1d4ed8; }}

    /* Deliverability Sandbox */
    .score-meter {{ display: flex; align-items: center; gap: 14px; margin-top: 14px; padding: 14px; background: #0c1220; border-radius: 8px; border: 1px solid var(--card-border); }}
    .score-circle {{ width: 48px; height: 48px; border-radius: 50%; background: rgba(16, 185, 129, 0.15); border: 2px solid #10b981; display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 18px; color: #10b981; }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="brand">
        <div class="brand-logo">S</div>
        <div>
          <h1>SlideIn Enterprise Platform</h1>
          <p>Conversational Email AI &amp; High-Deliverability MTA Mesh</p>
        </div>
      </div>
      <div>
        <span class="status-badge">KumoMTA &amp; Safety Gate Operational</span>
      </div>
    </header>

    <!-- Pipeline KPIs -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-title">Total Ingested Leads</div>
        <div class="stat-value">{stats["total_leads"]}</div>
        <div class="stat-hint">&uarr; Speed-to-lead active</div>
      </div>
      <div class="stat-card">
        <div class="stat-title">Conversations Engaged</div>
        <div class="stat-value">{stats["engaged_leads"]}</div>
        <div class="stat-hint">Two-way auto-qualification</div>
      </div>
      <div class="stat-card">
        <div class="stat-title">Qualified Borrowers</div>
        <div class="stat-value">{stats["qualified_leads"]}</div>
        <div class="stat-hint">Loan &amp; timeline verified</div>
      </div>
      <div class="stat-card">
        <div class="stat-title">Booked Appointments</div>
        <div class="stat-value" style="color: #34d399;">{stats["booked_appointments"]}</div>
        <div class="stat-hint">Live calendar confirmed</div>
      </div>
      <div class="stat-card">
        <div class="stat-title">Deliverability Score</div>
        <div class="stat-value">{stats["avg_deliverability_score"]} / 100</div>
        <div class="stat-hint">100% Primary Inbox</div>
      </div>
    </div>

    <!-- Main Workspace -->
    <div class="main-grid">
      <!-- Left Column: Live Email Conversations -->
      <div>
        <div class="card">
          <div class="card-header">
            <h2>Active Lead Conversations</h2>
            <span style="font-size: 12px; color: var(--text-muted);">{len(convs)} Threads</span>
          </div>
          <div class="thread-list">
            {"".join([f'''
            <div class="thread-item">
              <div class="thread-top">
                <span class="thread-lead">{c.lead_name} &lt;{c.lead_email}&gt;</span>
                <span class="thread-badge badge-{c.stage}">{c.stage}</span>
              </div>
              <div class="thread-subj">{c.subject}</div>
              <div class="thread-footer">
                <span>Latest Intent: {c.latest_intent}</span>
                <span>{c.message_count} messages in thread</span>
              </div>
            </div>
            ''' for c in convs]) if convs else '<p style="color: #64748b; font-size: 13px; text-align: center; padding: 20px;">No active conversations yet. Trigger a calculator submission below!</p>'}
          </div>
        </div>
      </div>

      <!-- Right Column: Funnel Tester & Deliverability Sandbox -->
      <div>
        <!-- Calculator Lead Ingest Test Bench -->
        <div class="card">
          <div class="card-header">
            <h2>⚡ Calculator Funnel Test Bench</h2>
          </div>
          <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 16px;">
            Simulate a warm lead calculating an amortization schedule on your branded domain. SlideIn triggers the speed-to-lead auto-responder in &lt;1 second.
          </p>
          <form id="leadForm" onsubmit="submitLead(event)">
            <div class="form-group">
              <label>Borrower Email</label>
              <input type="email" id="f_email" value="alex.borrower@gmail.com" required>
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
              <div class="form-group">
                <label>First Name</label>
                <input type="text" id="f_fname" value="Alex" required>
              </div>
              <div class="form-group">
                <label>Loan Amount ($)</label>
                <input type="number" id="f_loan" value="550000" required>
              </div>
            </div>
            <div class="form-group">
              <label>Property Type</label>
              <select id="f_prop">
                <option value="Single Family Home">Single Family Home</option>
                <option value="Townhouse / Condo">Townhouse / Condo</option>
                <option value="Multi-Family (2-4 Unit)">Multi-Family (2-4 Unit)</option>
              </select>
            </div>
            <button type="submit" class="btn-submit">Dispatch Speed-to-Lead Email &rarr;</button>
          </form>
          <div id="leadResult" style="margin-top: 14px; font-size: 12px; font-family: var(--font-mono); display: none;"></div>
        </div>

        <!-- Real-Time Deliverability Gate Sandbox -->
        <div class="card">
          <div class="card-header">
            <h2>🛡️ Pre-Send Deliverability Sandbox</h2>
          </div>
          <div class="form-group">
            <label>Draft Subject Line</label>
            <input type="text" id="d_subj" value="Alex - your mortgage breakdown" oninput="scoreDraft()">
          </div>
          <div class="form-group">
            <label>Draft Email Body</label>
            <textarea id="d_body" rows="3" oninput="scoreDraft()">Hi Alex, I pulled your amortization numbers for the single family home. What timeline are you targeting?</textarea>
          </div>
          <div class="score-meter">
            <div class="score-circle" id="scoreVal">100</div>
            <div>
              <div style="font-weight: 600; font-size: 13px;" id="scoreGrade">Grade A — Primary Inbox Approved</div>
              <div style="font-size: 11px; color: var(--text-muted);" id="scoreDetail">0 spam triggers, authentic MUA structure</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
    async function submitLead(e) {{
      e.preventDefault();
      const btn = e.target.querySelector('button');
      btn.innerText = 'Dispatching via KumoMTA...';
      btn.disabled = true;

      const payload = {{
        email: document.getElementById('f_email').value,
        first_name: document.getElementById('f_fname').value,
        loan_amount: parseFloat(document.getElementById('f_loan').value),
        property_type: document.getElementById('f_prop').value,
        purchase_timeline: "30-60 days",
        source: "calculator_funnel_test_bench"
      }};

      try {{
        const res = await fetch('/v1/leads/submit', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(payload)
        }});
        const data = await res.json();
        const resEl = document.getElementById('leadResult');
        resEl.style.display = 'block';
        resEl.style.color = '#34d399';
        resEl.innerText = '✔ Success: Email sent via ' + data.delivery.provider + ' (Msg-ID: ' + data.delivery.message_id.substring(0, 18) + '...)';
        setTimeout(() => {{ location.reload(); }}, 1500);
      }} catch (err) {{
        alert('Failed: ' + err);
      }} finally {{
        btn.innerText = 'Dispatch Speed-to-Lead Email &rarr;';
        btn.disabled = false;
      }}
    }}

    async function scoreDraft() {{
      const subj = document.getElementById('d_subj').value;
      const body = document.getElementById('d_body').value;
      try {{
        const res = await fetch('/v1/drafts/score', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ subject: subj, body_text: body }})
        }});
        const data = await res.json();
        const circle = document.getElementById('scoreVal');
        circle.innerText = data.score;
        circle.style.color = data.score >= 80 ? '#10b981' : '#f87171';
        circle.style.borderColor = data.score >= 80 ? '#10b981' : '#f87171';
        document.getElementById('scoreGrade').innerText = 'Grade ' + data.grade + ' — ' + (data.score >= 80 ? 'Approved' : 'Needs Optimization');
        document.getElementById('scoreDetail').innerText = data.issues.length ? data.issues.join(', ') : '0 spam triggers, authentic MUA structure';
      }} catch (err) {{}}
    }}
  </script>
</body>
</html>
"""
        self._send_html(html)


def run_server(port: int = PORT) -> None:
    server_address = (HOST, port)
    httpd = HTTPServer(server_address, SlideInAPIHandler)
    print(f" SlideIn Enterprise Platform listening on http://127.0.0.1:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping SlideIn server...")
        httpd.server_close()


if __name__ == "__main__":
    run_server()
