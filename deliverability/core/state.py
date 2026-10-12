"""SQLite-backed state store for the deliverability system.

All decisions, seed results, circuit state, campaign state, and send events are
persisted here so the circuit breaker can preserve full context on a trip and so
future runs can reason about freshness (validity windows).
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, asdict
from typing import Optional


def _now() -> float:
    return time.time()


class Store:
    def __init__(self, path: str = "deliverability_state.db"):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self._migrate()
        self._migrate_schema()

    def _migrate(self) -> None:
        c = self.conn
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS gate_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL,
                email_hash TEXT,
                analyzer_grade TEXT,
                analyzer_score REAL,
                seed_pass INTEGER,
                seed_detail TEXT,
                approved INTEGER,
                reason TEXT
            );
            CREATE TABLE IF NOT EXISTS seed_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                ts REAL,
                provider TEXT,
                folder TEXT,
                message_id TEXT,
                passed INTEGER
            );
            CREATE TABLE IF NOT EXISTS circuit_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL,
                status TEXT,
                reason TEXT,
                metrics_json TEXT
            );
            CREATE TABLE IF NOT EXISTS campaign_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL,
                campaign_id TEXT,
                status TEXT,
                paused_reason TEXT,
                sent_count INTEGER
            );
            CREATE TABLE IF NOT EXISTS send_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL,
                recipient TEXT,
                provider TEXT,
                result TEXT,
                detail TEXT,
                bounce_type TEXT,
                dsn_status TEXT
            );
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL,
                bounce_rate REAL,
                complaint_rate REAL,
                deferral_rate REAL,
                seed_inbox_pct REAL,
                analyzer_grade TEXT
            );
            CREATE TABLE IF NOT EXISTS sender_rotation (
                domain TEXT PRIMARY KEY,
                sender TEXT,
                ts REAL
            );
            CREATE TABLE IF NOT EXISTS suppression (
                recipient TEXT PRIMARY KEY,
                reason TEXT,
                ts REAL,
                detail TEXT
            );
            """
        )
        self.conn.commit()

    def _migrate_schema(self) -> None:
        for table, col, coltype in [
            ("send_events", "bounce_type", "TEXT"),
            ("send_events", "dsn_status", "TEXT"),
        ]:
            try:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")
            except Exception:
                pass
        self.conn.commit()

    # ---- gate decisions ----
    def record_gate_decision(self, d: dict) -> None:
        self.conn.execute(
            """INSERT INTO gate_decisions
               (ts,email_hash,analyzer_grade,analyzer_score,seed_pass,seed_detail,approved,reason)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                _now(),
                d.get("email_hash"),
                d.get("analyzer_grade"),
                d.get("analyzer_score"),
                int(bool(d.get("seed_pass"))),
                json.dumps(d.get("seed_detail", {})),
                int(bool(d.get("approved"))),
                d.get("reason", ""),
            ),
        )
        self.conn.commit()

    def latest_gate_decision(self) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM gate_decisions ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    # ---- seed results ----
    def record_seed_results(self, run_id: str, results: list[dict]) -> None:
        for r in results:
            self.conn.execute(
                """INSERT INTO seed_results
                   (run_id,ts,provider,folder,message_id,passed)
                   VALUES (?,?,?,?,?,?)""",
                (
                    run_id,
                    _now(),
                    r["provider"],
                    r["folder"],
                    r.get("message_id", ""),
                    int(bool(r["passed"])),
                ),
            )
        self.conn.commit()

    def latest_seed_results(self, run_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM seed_results WHERE run_id=? ORDER BY id DESC", (run_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- circuit ----
    def set_circuit(self, status: str, reason: str, metrics: dict) -> None:
        self.conn.execute(
            "INSERT INTO circuit_state (ts,status,reason,metrics_json) VALUES (?,?,?,?)",
            (_now(), status, reason, json.dumps(metrics)),
        )
        self.conn.commit()

    def get_circuit(self) -> dict:
        row = self.conn.execute(
            "SELECT * FROM circuit_state ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return {"status": "closed", "reason": "initial", "metrics_json": "{}"}
        return dict(row)

    # ---- campaign ----
    def set_campaign(self, campaign_id: str, status: str, paused_reason: str = "",
                     sent_count: int = 0) -> None:
        self.conn.execute(
            "INSERT INTO campaign_state (ts,campaign_id,status,paused_reason,sent_count) VALUES (?,?,?,?,?)",
            (_now(), campaign_id, status, paused_reason, sent_count),
        )
        self.conn.commit()

    def latest_campaign(self, campaign_id: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM campaign_state WHERE campaign_id=? ORDER BY id DESC LIMIT 1",
            (campaign_id,),
        ).fetchone()
        return dict(row) if row else None

    # ---- send events ----
    def record_send_event(self, recipient: str, provider: str, result: str,
                          detail: str = "", bounce_type: str = "", dsn_status: str = "") -> None:
        self.conn.execute(
            "INSERT INTO send_events (ts,recipient,provider,result,detail,bounce_type,dsn_status) VALUES (?,?,?,?,?,?,?)",
            (_now(), recipient, provider, result, detail, bounce_type, dsn_status),
        )
        self.conn.commit()

    def recent_send_events(self, limit: int = 1000) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM send_events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- suppression ----
    def is_suppressed(self, recipient: str) -> bool:
        row = self.conn.execute(
            "SELECT recipient FROM suppression WHERE recipient=?", (recipient,)
        ).fetchone()
        return row is not None

    def suppress(self, recipient: str, reason: str, detail: str = "") -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO suppression (recipient,reason,ts,detail) VALUES (?,?,?,?)",
            (recipient, reason, _now(), detail),
        )
        self.conn.commit()

    def unsuppress(self, recipient: str) -> None:
        self.conn.execute("DELETE FROM suppression WHERE recipient=?", (recipient,))
        self.conn.commit()

    def suppressed_recipients(self) -> list[str]:
        rows = self.conn.execute("SELECT recipient FROM suppression").fetchall()
        return [r["recipient"] for r in rows]

    # ---- metrics ----
    def add_metric(self, m: dict) -> None:
        self.conn.execute(
            """INSERT INTO metrics
               (ts,bounce_rate,complaint_rate,deferral_rate,seed_inbox_pct,analyzer_grade)
               VALUES (?,?,?,?,?,?)""",
            (
                _now(),
                m.get("bounce_rate", 0.0),
                m.get("complaint_rate", 0.0),
                m.get("deferral_rate", 0.0),
                m.get("seed_inbox_pct", 100.0),
                m.get("analyzer_grade", ""),
            ),
        )
        self.conn.commit()

    # ---- sender rotation ----
    def record_sender_used(self, domain: str, sender: str) -> None:
        self.conn.execute(
            """INSERT INTO sender_rotation (domain, sender, ts) VALUES (?,?,?)
               ON CONFLICT(domain) DO UPDATE SET sender=excluded.sender, ts=excluded.ts""",
            (domain, sender, _now()),
        )
        self.conn.commit()

    def get_last_sender(self, domain: str) -> Optional[str]:
        row = self.conn.execute(
            "SELECT sender FROM sender_rotation WHERE domain=?", (domain,)
        ).fetchone()
        return row["sender"] if row else None

    def close(self):
        self.conn.close()
