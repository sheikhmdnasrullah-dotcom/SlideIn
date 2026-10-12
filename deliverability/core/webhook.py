"""Webhook receiver for transactional email delivery tracking.

Receives and processes:
  - Delivery confirmations (SMTP 250 OK)
  - Bounces (hard/soft via DSN)
  - Complaints (ARF feedback loops)
  - Opens (via tracking pixel, if enabled)
  - Clicks (via link rewriting, if enabled)

Stores events in SQLite for monitoring and circuit-breaker decisions.
"""
from __future__ import annotations

import email
import hashlib
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email import policy
from email.utils import parseaddr
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse


@dataclass
class DeliveryEvent:
    """A single delivery event."""
    event_id: str
    timestamp: float
    message_id: str
    recipient: str
    event_type: str  # delivered, bounce, complaint, open, click
    status: str  # success, failed, deferred
    detail: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "message_id": self.message_id,
            "recipient": self.recipient,
            "event_type": self.event_type,
            "status": self.status,
            "detail": self.detail,
            "metadata": self.metadata,
        }


class WebhookProcessor:
    """Process incoming webhook events from email providers."""
    
    def __init__(self, db_path: str = "deliverability_state.db"):
        import sqlite3
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._ensure_tables()
    
    def _ensure_tables(self):
        """Create tables if they don't exist."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS delivery_events (
                event_id TEXT PRIMARY KEY,
                timestamp REAL,
                message_id TEXT,
                recipient TEXT,
                event_type TEXT,
                status TEXT,
                detail TEXT,
                metadata TEXT,
                created_at REAL DEFAULT (strftime('%s', 'now'))
            );
            
            CREATE TABLE IF NOT EXISTS delivery_stats (
                domain TEXT,
                date TEXT,
                sent INTEGER DEFAULT 0,
                delivered INTEGER DEFAULT 0,
                bounces INTEGER DEFAULT 0,
                complaints INTEGER DEFAULT 0,
                opens INTEGER DEFAULT 0,
                clicks INTEGER DEFAULT 0,
                PRIMARY KEY (domain, date)
            );
            
            CREATE INDEX IF NOT EXISTS idx_delivery_events_message 
            ON delivery_events(message_id);
            
            CREATE INDEX IF NOT EXISTS idx_delivery_events_recipient 
            ON delivery_events(recipient);
            
            CREATE INDEX IF NOT EXISTS idx_delivery_events_type 
            ON delivery_events(event_type);
        """)
        self.conn.commit()
    
    def process_sns_notification(self, payload: dict) -> List[DeliveryEvent]:
        """Process AWS SNS notification (for SES)."""
        events = []
        
        # SNS can be a subscription confirmation or notification
        if payload.get("Type") == "SubscriptionConfirmation":
            # Auto-confirm subscription
            return events
        
        if payload.get("Type") == "Notification":
            message = json.loads(payload.get("Message", "{}"))
            events.extend(self._process_ses_event(message))
        
        return events
    
    def process_sendgrid_webhook(self, payload: List[dict]) -> List[DeliveryEvent]:
        """Process SendGrid webhook events."""
        events = []
        
        for item in payload:
            event_type = item.get("event", "").lower()
            message_id = item.get("sg_message_id", "")
            recipient = item.get("email", "")
            
            if event_type == "delivered":
                events.append(self._create_event(
                    message_id, recipient, "delivered", "success",
                    detail=item.get("response", ""),
                    metadata={"smtp_code": item.get("smtpcode")}
                ))
            elif event_type in ("bounce", "dropped"):
                events.append(self._create_event(
                    message_id, recipient, "bounce", "failed",
                    detail=item.get("reason", ""),
                    metadata={
                        "bounce_type": item.get("type", ""),
                        "smtp_code": item.get("smtpcode"),
                        "status": item.get("status"),
                    }
                ))
            elif event_type == "spamreport":
                events.append(self._create_event(
                    message_id, recipient, "complaint", "failed",
                    detail="spam report",
                ))
            elif event_type == "open":
                events.append(self._create_event(
                    message_id, recipient, "open", "success",
                    metadata={"user_agent": item.get("useragent")}
                ))
            elif event_type == "click":
                events.append(self._create_event(
                    message_id, recipient, "click", "success",
                    detail=item.get("url"),
                    metadata={"user_agent": item.get("useragent")}
                ))
        
        return events
    
    def process_postmark_webhook(self, payload: dict) -> List[DeliveryEvent]:
        """Process Postmark webhook events."""
        events = []
        
        record_type = payload.get("RecordType", "").lower()
        message_id = payload.get("MessageID", "")
        recipient = payload.get("Recipient", "")
        
        if record_type == "delivery":
            events.append(self._create_event(
                message_id, recipient, "delivered", "success",
                detail=payload.get("Description", ""),
            ))
        elif record_type == "bounce":
            events.append(self._create_event(
                message_id, recipient, "bounce", "failed",
                detail=payload.get("Description", ""),
                metadata={
                    "bounce_type": payload.get("Type"),
                    "bounce_name": payload.get("Name"),
                    "can_activate": payload.get("CanActivate"),
                }
            ))
        elif record_type == "complaint":
            events.append(self._create_event(
                message_id, recipient, "complaint", "failed",
                detail=payload.get("Description", ""),
            ))
        elif record_type == "open":
            events.append(self._create_event(
                message_id, recipient, "open", "success",
                metadata={"client": payload.get("Client"), "user_agent": payload.get("UserAgent")}
            ))
        elif record_type == "click":
            events.append(self._create_event(
                message_id, recipient, "click", "success",
                detail=payload.get("Link"),
                metadata={"user_agent": payload.get("UserAgent")}
            ))
        
        return events
    
    def process_mailgun_webhook(self, event_type: str, payload: dict) -> List[DeliveryEvent]:
        """Process Mailgun webhook events."""
        events = []
        
        message_id = payload.get("message-id", "")
        recipient = payload.get("recipient", "")
        
        if event_type == "delivered":
            events.append(self._create_event(
                message_id, recipient, "delivered", "success",
                metadata={"mx_host": payload.get("mx-host")}
            ))
        elif event_type in ("failed", "rejected"):
            events.append(self._create_event(
                message_id, recipient, "bounce", "failed",
                detail=payload.get("reject-reason", ""),
                metadata={"severity": payload.get("severity")}
            ))
        elif event_type == "complained":
            events.append(self._create_event(
                message_id, recipient, "complaint", "failed",
            ))
        elif event_type == "opened":
            events.append(self._create_event(
                message_id, recipient, "open", "success",
            ))
        elif event_type == "clicked":
            events.append(self._create_event(
                message_id, recipient, "click", "success",
                detail=payload.get("url"),
            ))
        
        return events
    
    def process_generic_bounce(self, eml_bytes: bytes) -> Optional[DeliveryEvent]:
        """Process a generic bounce message (DSN/ARF)."""
        try:
            from . import bounce_parser
            result = bounce_parser.parse_bounce(eml_bytes)
            
            return self._create_event(
                result.message_id or "",
                result.recipient,
                "bounce",
                "failed" if bounce_parser.should_suppress(result) else "deferred",
                detail=result.diagnostic,
                metadata={
                    "dsn_code": result.dsn_code,
                    "status": result.status,
                }
            )
        except Exception as e:
            return None
    
    def _process_ses_event(self, message: dict) -> List[DeliveryEvent]:
        """Process a single SES event."""
        events = []
        
        notification_type = message.get("notificationType", "").lower()
        mail = message.get("mail", {})
        message_id = mail.get("messageId", "")
        
        destinations = message.get("destination", [])
        
        if notification_type == "delivery":
            delivery = message.get("delivery", {})
            for recipient in destinations:
                events.append(self._create_event(
                    message_id, recipient, "delivered", "success",
                    metadata={
                        "processing_time": delivery.get("processingTimeMillis"),
                        "smtp_response": delivery.get("smtpResponse"),
                        "mx_host": delivery.get("remoteMtaIp"),
                    }
                ))
        elif notification_type == "bounce":
            bounce = message.get("bounce", {})
            bounce_type = bounce.get("bounceType", "").lower()
            for recipient in bounce.get("bouncedRecipients", []):
                events.append(self._create_event(
                    message_id, recipient.get("emailAddress", ""), "bounce",
                    "failed" if bounce_type == "permanent" else "deferred",
                    detail=recipient.get("diagnosticCode", ""),
                    metadata={
                        "bounce_type": bounce_type,
                        "smtp_code": recipient.get("status"),
                    }
                ))
        elif notification_type == "complaint":
            complaint = message.get("complaint", {})
            for recipient in complaint.get("complainedRecipients", []):
                events.append(self._create_event(
                    message_id, recipient.get("emailAddress", ""), "complaint", "failed",
                    detail=complaint.get("complaintFeedbackType", ""),
                ))
        
        return events
    
    def _create_event(
        self,
        message_id: str,
        recipient: str,
        event_type: str,
        status: str,
        detail: str = "",
        metadata: Optional[dict] = None,
    ) -> DeliveryEvent:
        """Create and store a delivery event."""
        event = DeliveryEvent(
            event_id=uuid.uuid4().hex,
            timestamp=time.time(),
            message_id=message_id,
            recipient=recipient,
            event_type=event_type,
            status=status,
            detail=detail,
            metadata=metadata or {},
        )
        
        # Store in database
        self.conn.execute(
            """INSERT OR REPLACE INTO delivery_events 
               (event_id, timestamp, message_id, recipient, event_type, status, detail, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (event.event_id, event.timestamp, event.message_id, event.recipient,
             event.event_type, event.status, event.detail, json.dumps(event.metadata))
        )
        
        # Update daily stats
        domain = recipient.split("@")[1] if "@" in recipient else ""
        date = datetime.fromtimestamp(event.timestamp, tz=timezone.utc).strftime("%Y-%m-%d")
        
        if event_type == "delivered":
            self.conn.execute(
                """INSERT INTO delivery_stats (domain, date, delivered) 
                   VALUES (?, ?, 1)
                   ON CONFLICT(domain, date) DO UPDATE SET delivered = delivered + 1""",
                (domain, date)
            )
        elif event_type == "bounce":
            self.conn.execute(
                """INSERT INTO delivery_stats (domain, date, bounces) 
                   VALUES (?, ?, 1)
                   ON CONFLICT(domain, date) DO UPDATE SET bounces = bounces + 1""",
                (domain, date)
            )
        elif event_type == "complaint":
            self.conn.execute(
                """INSERT INTO delivery_stats (domain, date, complaints) 
                   VALUES (?, ?, 1)
                   ON CONFLICT(domain, date) DO UPDATE SET complaints = complaints + 1""",
                (domain, date)
            )
        
        self.conn.commit()
        
        return event
    
    def get_stats(self, domain: str = "", days: int = 30) -> dict:
        """Get delivery statistics."""
        import sqlite3
        
        if domain:
            rows = self.conn.execute(
                """SELECT date, sent, delivered, bounces, complaints, opens, clicks
                   FROM delivery_stats WHERE domain = ? AND date >= date('now', ?)
                   ORDER BY date""",
                (domain, f"-{days} days")
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT date, SUM(sent) as sent, SUM(delivered) as delivered,
                          SUM(bounces) as bounces, SUM(complaints) as complaints,
                          SUM(opens) as opens, SUM(clicks) as clicks
                   FROM delivery_stats WHERE date >= date('now', ?)
                   GROUP BY date ORDER BY date""",
                (f"-{days} days",)
            ).fetchall()
        
        stats = {
            "total_sent": 0,
            "total_delivered": 0,
            "total_bounces": 0,
            "total_complaints": 0,
            "total_opens": 0,
            "total_clicks": 0,
            "daily": [],
        }
        
        for row in rows:
            stats["total_sent"] += row["sent"] or 0
            stats["total_delivered"] += row["delivered"] or 0
            stats["total_bounces"] += row["bounces"] or 0
            stats["total_complaints"] += row["complaints"] or 0
            stats["total_opens"] += row["opens"] or 0
            stats["total_clicks"] += row["clicks"] or 0
            stats["daily"].append(dict(row))
        
        # Calculate rates
        total = stats["total_sent"] or 1
        stats["delivery_rate"] = stats["total_delivered"] / total
        stats["bounce_rate"] = stats["total_bounces"] / total
        stats["complaint_rate"] = stats["total_complaints"] / total
        stats["open_rate"] = stats["total_opens"] / stats["total_delivered"] if stats["total_delivered"] else 0
        stats["click_rate"] = stats["total_clicks"] / stats["total_delivered"] if stats["total_delivered"] else 0
        
        return stats
    
    def get_recent_events(self, limit: int = 100) -> List[dict]:
        """Get recent delivery events."""
        rows = self.conn.execute(
            """SELECT event_id, timestamp, message_id, recipient, event_type, 
                      status, detail, metadata
               FROM delivery_events ORDER BY timestamp DESC LIMIT ?""",
            (limit,)
        ).fetchall()
        
        return [dict(row) for row in rows]
    
    def close(self):
        """Close database connection."""
        self.conn.close()
