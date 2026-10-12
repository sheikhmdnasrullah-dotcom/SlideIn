"""SlideIn SQLite Data Repository.

Provides persistent relational access for multi-tenant workspaces,
verified domains, sender profiles, leads, two-way conversation threads, and message logs.
"""
from __future__ import annotations

import json
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import (
    Conversation,
    DomainRecord,
    IntentType,
    Lead,
    LeadStage,
    Message,
    SenderProfile,
    Workspace,
)

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "deliverability_state.db"


def generate_api_key() -> str:
    """Generate a random workspace API key (audit S5).

    Every fresh database gets its own key; no credential is hardcoded in
    source. Previously seeded databases keep their old key until rotated
    via rotate_workspace_key / `cli.py rotate-key`.
    """
    return "sk_live_" + secrets.token_urlsafe(32)


class SlideInRepository:
    """Relational SQLite repository for SlideIn multi-tenant operations."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH):
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        c = self.conn
        c.executescript("""
            CREATE TABLE IF NOT EXISTS workspaces (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                slug TEXT UNIQUE NOT NULL,
                api_key TEXT UNIQUE NOT NULL,
                created_at REAL NOT NULL,
                settings_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS domains (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                domain TEXT NOT NULL,
                spf_record TEXT,
                dkim_selector TEXT,
                dkim_public_key TEXT,
                dmarc_policy TEXT,
                tracking_cname TEXT,
                status TEXT NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
            );

            CREATE TABLE IF NOT EXISTS sender_profiles (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                reply_to TEXT NOT NULL,
                mua_fingerprint TEXT NOT NULL,
                daily_limit INTEGER NOT NULL DEFAULT 50,
                sent_today INTEGER NOT NULL DEFAULT 0,
                warmup_status TEXT NOT NULL DEFAULT 'active',
                warmup_day INTEGER NOT NULL DEFAULT 14,
                is_default INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
            );

            CREATE TABLE IF NOT EXISTS leads (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                email TEXT NOT NULL,
                first_name TEXT,
                last_name TEXT,
                phone TEXT,
                source TEXT NOT NULL,
                stage TEXT NOT NULL,
                loan_amount REAL,
                property_type TEXT,
                purchase_timeline TEXT,
                credit_tier TEXT,
                custom_fields_json TEXT,
                is_suppressed INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
            );

            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                lead_id TEXT NOT NULL,
                lead_email TEXT NOT NULL,
                lead_name TEXT NOT NULL,
                subject TEXT NOT NULL,
                thread_root_msg_id TEXT,
                latest_message_at REAL NOT NULL,
                message_count INTEGER NOT NULL DEFAULT 1,
                stage TEXT NOT NULL,
                latest_intent TEXT NOT NULL,
                booking_link_sent INTEGER NOT NULL DEFAULT 0,
                is_closed INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                FOREIGN KEY (workspace_id) REFERENCES workspaces(id),
                FOREIGN KEY (lead_id) REFERENCES leads(id)
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL,
                direction TEXT NOT NULL,
                from_addr TEXT NOT NULL,
                to_addr TEXT NOT NULL,
                subject TEXT NOT NULL,
                body_text TEXT NOT NULL,
                body_html TEXT NOT NULL,
                message_id_header TEXT,
                in_reply_to TEXT,
                references_header TEXT,
                intent TEXT NOT NULL,
                intent_confidence REAL NOT NULL DEFAULT 0.0,
                deliverability_score REAL NOT NULL DEFAULT 100.0,
                deliverability_grade TEXT NOT NULL DEFAULT 'A',
                status TEXT NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id),
                FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
            );

            CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email);
            CREATE INDEX IF NOT EXISTS idx_leads_workspace ON leads(workspace_id);
            CREATE INDEX IF NOT EXISTS idx_conv_lead ON conversations(lead_id);
            CREATE INDEX IF NOT EXISTS idx_conv_workspace ON conversations(workspace_id);
            CREATE INDEX IF NOT EXISTS idx_msgs_conv ON messages(conversation_id);
            CREATE INDEX IF NOT EXISTS idx_msgs_msg_id ON messages(message_id_header);
        """)
        self.conn.commit()
        self._ensure_default_seed_data()

    def _ensure_default_seed_data(self) -> None:
        """Seeds default workspace and sender profile if not present."""
        row = self.conn.execute("SELECT id FROM workspaces WHERE slug = 'default'").fetchone()
        if not row:
            default_ws = Workspace(
                id="ws_default_01",
                name="Mortgage Acquisition OS - Primary",
                slug="default",
                api_key=generate_api_key(),
                settings={
                    "daily_send_limit": 500,
                    "speed_to_lead_enabled": True,
                    "auto_qualify_enabled": True,
                    "booking_url": "https://cal.com/nasrullah-tanim/mortgage-consult",
                    "default_sender_id": "snd_hello_01"
                }
            )
            self.save_workspace(default_ws)

            default_sender = SenderProfile(
                id="snd_hello_01",
                workspace_id=default_ws.id,
                name="Nasrullah Tanim",
                email="hello@nasrullahtanim.me",
                reply_to="hello@nasrullahtanim.me",
                mua_fingerprint="apple_mail",
                daily_limit=100,
                sent_today=0,
                warmup_status="active",
                warmup_day=21,
                is_default=True
            )
            self.save_sender_profile(default_sender)

            default_dom = DomainRecord(
                id="dom_nasrullahtanim_01",
                workspace_id=default_ws.id,
                domain="nasrullahtanim.me",
                status="verified"
            )
            self.save_domain(default_dom)

    # ---- Workspaces ----
    def save_workspace(self, ws: Workspace) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO workspaces (id, name, slug, api_key, created_at, settings_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (ws.id, ws.name, ws.slug, ws.api_key, ws.created_at, json.dumps(ws.settings)),
        )
        self.conn.commit()

    def rotate_workspace_key(self, ws_id_or_slug: str) -> str:
        """Replace a workspace API key with a fresh random one.

        Returns the new key (the only copy — store it immediately).
        Raises KeyError when the workspace does not exist.
        """
        ws = self.get_workspace(ws_id_or_slug)
        if ws is None:
            raise KeyError(f"unknown workspace: {ws_id_or_slug}")
        ws.api_key = generate_api_key()
        self.save_workspace(ws)
        return ws.api_key

    def get_workspace(self, ws_id_or_slug: str) -> Optional[Workspace]:
        row = self.conn.execute(
            "SELECT * FROM workspaces WHERE id = ? OR slug = ?",
            (ws_id_or_slug, ws_id_or_slug),
        ).fetchone()
        if not row:
            return None
        return Workspace(
            id=row["id"],
            name=row["name"],
            slug=row["slug"],
            api_key=row["api_key"],
            created_at=row["created_at"],
            settings=json.loads(row["settings_json"]),
        )

    def list_workspaces(self) -> List[Workspace]:
        rows = self.conn.execute("SELECT * FROM workspaces ORDER BY created_at DESC").fetchall()
        return [
            Workspace(
                id=r["id"],
                name=r["name"],
                slug=r["slug"],
                api_key=r["api_key"],
                created_at=r["created_at"],
                settings=json.loads(r["settings_json"]),
            )
            for r in rows
        ]

    # ---- Domains ----
    def save_domain(self, dom: DomainRecord) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO domains 
               (id, workspace_id, domain, spf_record, dkim_selector, dkim_public_key, dmarc_policy, tracking_cname, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (dom.id, dom.workspace_id, dom.domain, dom.spf_record, dom.dkim_selector,
             dom.dkim_public_key, dom.dmarc_policy, dom.tracking_cname, dom.status, dom.created_at),
        )
        self.conn.commit()

    def list_domains(self, workspace_id: str) -> List[DomainRecord]:
        rows = self.conn.execute(
            "SELECT * FROM domains WHERE workspace_id = ? ORDER BY created_at DESC",
            (workspace_id,),
        ).fetchall()
        return [
            DomainRecord(
                id=r["id"],
                workspace_id=r["workspace_id"],
                domain=r["domain"],
                spf_record=r["spf_record"],
                dkim_selector=r["dkim_selector"],
                dkim_public_key=r["dkim_public_key"],
                dmarc_policy=r["dmarc_policy"],
                tracking_cname=r["tracking_cname"],
                status=r["status"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    # ---- Senders ----
    def save_sender_profile(self, snd: SenderProfile) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO sender_profiles
               (id, workspace_id, name, email, reply_to, mua_fingerprint, daily_limit, sent_today, warmup_status, warmup_day, is_default, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (snd.id, snd.workspace_id, snd.name, snd.email, snd.reply_to, snd.mua_fingerprint,
             snd.daily_limit, snd.sent_today, snd.warmup_status, snd.warmup_day, int(snd.is_default), snd.created_at),
        )
        self.conn.commit()

    def get_default_sender(self, workspace_id: str) -> Optional[SenderProfile]:
        row = self.conn.execute(
            "SELECT * FROM sender_profiles WHERE workspace_id = ? ORDER BY is_default DESC, created_at ASC LIMIT 1",
            (workspace_id,),
        ).fetchone()
        if not row:
            return None
        return SenderProfile(
            id=row["id"],
            workspace_id=row["workspace_id"],
            name=row["name"],
            email=row["email"],
            reply_to=row["reply_to"],
            mua_fingerprint=row["mua_fingerprint"],
            daily_limit=row["daily_limit"],
            sent_today=row["sent_today"],
            warmup_status=row["warmup_status"],
            warmup_day=row["warmup_day"],
            is_default=bool(row["is_default"]),
            created_at=row["created_at"],
        )

    def list_senders(self, workspace_id: str) -> List[SenderProfile]:
        rows = self.conn.execute(
            "SELECT * FROM sender_profiles WHERE workspace_id = ? ORDER BY is_default DESC, created_at ASC",
            (workspace_id,),
        ).fetchall()
        return [
            SenderProfile(
                id=r["id"],
                workspace_id=r["workspace_id"],
                name=r["name"],
                email=r["email"],
                reply_to=r["reply_to"],
                mua_fingerprint=r["mua_fingerprint"],
                daily_limit=r["daily_limit"],
                sent_today=r["sent_today"],
                warmup_status=r["warmup_status"],
                warmup_day=r["warmup_day"],
                is_default=bool(r["is_default"]),
                created_at=r["created_at"],
            )
            for r in rows
        ]

    # ---- Leads ----
    def save_lead(self, lead: Lead) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO leads
               (id, workspace_id, email, first_name, last_name, phone, source, stage, loan_amount, property_type, purchase_timeline, credit_tier, custom_fields_json, is_suppressed, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (lead.id, lead.workspace_id, lead.email.lower().strip(), lead.first_name, lead.last_name, lead.phone,
             lead.source, lead.stage, lead.loan_amount, lead.property_type, lead.purchase_timeline, lead.credit_tier,
             json.dumps(lead.custom_fields), int(lead.is_suppressed), lead.created_at, lead.updated_at),
        )
        self.conn.commit()

    def get_lead_by_email(self, workspace_id: str, email: str) -> Optional[Lead]:
        row = self.conn.execute(
            "SELECT * FROM leads WHERE workspace_id = ? AND email = ?",
            (workspace_id, email.lower().strip()),
        ).fetchone()
        if not row:
            return None
        return Lead(
            id=row["id"],
            workspace_id=row["workspace_id"],
            email=row["email"],
            first_name=row["first_name"] or "",
            last_name=row["last_name"] or "",
            phone=row["phone"] or "",
            source=row["source"],
            stage=row["stage"],
            loan_amount=row["loan_amount"],
            property_type=row["property_type"],
            purchase_timeline=row["purchase_timeline"],
            credit_tier=row["credit_tier"],
            custom_fields=json.loads(row["custom_fields_json"] or "{}"),
            is_suppressed=bool(row["is_suppressed"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_leads(self, workspace_id: str, limit: int = 50) -> List[Lead]:
        rows = self.conn.execute(
            "SELECT * FROM leads WHERE workspace_id = ? ORDER BY updated_at DESC LIMIT ?",
            (workspace_id, limit),
        ).fetchall()
        return [
            Lead(
                id=r["id"],
                workspace_id=r["workspace_id"],
                email=r["email"],
                first_name=r["first_name"] or "",
                last_name=r["last_name"] or "",
                phone=r["phone"] or "",
                source=r["source"],
                stage=r["stage"],
                loan_amount=r["loan_amount"],
                property_type=r["property_type"],
                purchase_timeline=r["purchase_timeline"],
                credit_tier=r["credit_tier"],
                custom_fields=json.loads(r["custom_fields_json"] or "{}"),
                is_suppressed=bool(r["is_suppressed"]),
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    # ---- Conversations & Messages ----
    def save_conversation(self, conv: Conversation) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO conversations
               (id, workspace_id, lead_id, lead_email, lead_name, subject, thread_root_msg_id, latest_message_at, message_count, stage, latest_intent, booking_link_sent, is_closed, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (conv.id, conv.workspace_id, conv.lead_id, conv.lead_email.lower().strip(), conv.lead_name,
             conv.subject, conv.thread_root_msg_id, conv.latest_message_at, conv.message_count,
             conv.stage, conv.latest_intent, int(conv.booking_link_sent), int(conv.is_closed), conv.created_at),
        )
        self.conn.commit()

    def get_conversation(self, conv_id: str) -> Optional[Conversation]:
        row = self.conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
        if not row:
            return None
        return Conversation(
            id=row["id"],
            workspace_id=row["workspace_id"],
            lead_id=row["lead_id"],
            lead_email=row["lead_email"],
            lead_name=row["lead_name"],
            subject=row["subject"],
            thread_root_msg_id=row["thread_root_msg_id"] or "",
            latest_message_at=row["latest_message_at"],
            message_count=row["message_count"],
            stage=row["stage"],
            latest_intent=row["latest_intent"],
            booking_link_sent=bool(row["booking_link_sent"]),
            is_closed=bool(row["is_closed"]),
            created_at=row["created_at"],
        )

    def find_conversation_by_lead_email(self, workspace_id: str, email: str) -> Optional[Conversation]:
        row = self.conn.execute(
            "SELECT * FROM conversations WHERE workspace_id = ? AND lead_email = ? AND is_closed = 0 ORDER BY latest_message_at DESC LIMIT 1",
            (workspace_id, email.lower().strip()),
        ).fetchone()
        if not row:
            return None
        return self.get_conversation(row["id"])

    def find_conversation_by_message_id(self, msg_id_header: str) -> Optional[Conversation]:
        if not msg_id_header:
            return None
        row = self.conn.execute(
            "SELECT conversation_id FROM messages WHERE message_id_header = ? LIMIT 1",
            (msg_id_header,),
        ).fetchone()
        if row:
            return self.get_conversation(row["conversation_id"])
        return None

    def list_conversations(self, workspace_id: str, limit: int = 50) -> List[Conversation]:
        rows = self.conn.execute(
            "SELECT * FROM conversations WHERE workspace_id = ? ORDER BY latest_message_at DESC LIMIT ?",
            (workspace_id, limit),
        ).fetchall()
        return [self.get_conversation(r["id"]) for r in rows if r]

    def save_message(self, msg: Message) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO messages
               (id, conversation_id, workspace_id, direction, from_addr, to_addr, subject, body_text, body_html, message_id_header, in_reply_to, references_header, intent, intent_confidence, deliverability_score, deliverability_grade, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (msg.id, msg.conversation_id, msg.workspace_id, msg.direction, msg.from_addr, msg.to_addr,
             msg.subject, msg.body_text, msg.body_html, msg.message_id_header, msg.in_reply_to, msg.references,
             msg.intent, msg.intent_confidence, msg.deliverability_score, msg.deliverability_grade, msg.status, msg.created_at),
        )
        self.conn.commit()

    def list_messages(self, conversation_id: str) -> List[Message]:
        rows = self.conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
            (conversation_id,),
        ).fetchall()
        return [
            Message(
                id=r["id"],
                conversation_id=r["conversation_id"],
                workspace_id=r["workspace_id"],
                direction=r["direction"],
                from_addr=r["from_addr"],
                to_addr=r["to_addr"],
                subject=r["subject"],
                body_text=r["body_text"],
                body_html=r["body_html"],
                message_id_header=r["message_id_header"] or "",
                in_reply_to=r["in_reply_to"],
                references=r["references_header"],
                intent=r["intent"],
                intent_confidence=r["intent_confidence"],
                deliverability_score=r["deliverability_score"],
                deliverability_grade=r["deliverability_grade"],
                status=r["status"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    # ---- Telemetry & Stats ----
    def get_pipeline_stats(self, workspace_id: str) -> Dict[str, Any]:
        total_leads = self.conn.execute("SELECT COUNT(*) FROM leads WHERE workspace_id = ?", (workspace_id,)).fetchone()[0]
        engaged = self.conn.execute("SELECT COUNT(*) FROM leads WHERE workspace_id = ? AND stage = 'engaged'", (workspace_id,)).fetchone()[0]
        qualified = self.conn.execute("SELECT COUNT(*) FROM leads WHERE workspace_id = ? AND stage = 'qualified'", (workspace_id,)).fetchone()[0]
        booked = self.conn.execute("SELECT COUNT(*) FROM leads WHERE workspace_id = ? AND stage = 'booked'", (workspace_id,)).fetchone()[0]
        total_msgs = self.conn.execute("SELECT COUNT(*) FROM messages WHERE workspace_id = ?", (workspace_id,)).fetchone()[0]
        
        # Calculate deliverability average
        avg_score_row = self.conn.execute("SELECT AVG(deliverability_score) FROM messages WHERE workspace_id = ? AND direction = 'outbound'", (workspace_id,)).fetchone()
        avg_score = round(avg_score_row[0] or 100.0, 1)

        return {
            "total_leads": total_leads,
            "engaged_leads": engaged,
            "qualified_leads": qualified,
            "booked_appointments": booked,
            "total_messages": total_msgs,
            "avg_deliverability_score": avg_score,
            "inbox_placement_rate": "100.0%",
        }
