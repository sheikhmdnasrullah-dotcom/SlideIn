"""Warmup + volume tracker for the deliverability system.

Tracks daily send volume per domain/IP and enforces ramp limits during warmup.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Optional


def _now() -> float:
    return time.time()


@dataclass
class WarmupConfig:
    daily_limit: int = 20
    ramp_step_days: int = 3
    ramp_increment: int = 20
    max_daily_limit: int = 500
    cooldown_hours: float = 24.0


class WarmupTracker:
    def __init__(self, conn: sqlite3.Connection, cfg: Optional[WarmupConfig] = None):
        self.conn = conn
        self.cfg = cfg or WarmupConfig()
        self._migrate()

    def _migrate(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS warmup_state (
                domain TEXT PRIMARY KEY,
                start_ts REAL,
                current_daily_limit INTEGER,
                last_send_ts REAL
            );
            CREATE TABLE IF NOT EXISTS daily_sends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL,
                domain TEXT,
                sender TEXT,
                recipient TEXT
            );
            """
        )
        self.conn.commit()

    def daily_sent_count(self, domain: str) -> int:
        day_start = _now() - (24 * 3600)
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM daily_sends WHERE domain=? AND ts>=?",
            (domain, day_start),
        ).fetchone()
        return row["cnt"] if row else 0

    def can_send(self, domain: str, store) -> tuple[bool, str]:
        """Check if warmup allows another send today."""
        count = self.daily_sent_count(domain)
        state_row = self.conn.execute(
            "SELECT current_daily_limit FROM warmup_state WHERE domain=?", (domain,)
        ).fetchone()
        limit = state_row["current_daily_limit"] if state_row else self.cfg.daily_limit
        if count >= limit:
            return False, f"warmup daily limit {limit} reached for {domain} ({count}/{limit} sent)"
        return True, ""

    def record_send(self, domain: str, sender: str, recipient: str) -> None:
        self.conn.execute(
            "INSERT INTO daily_sends (ts,domain,sender,recipient) VALUES (?,?,?,?)",
            (_now(), domain, sender, recipient),
        )
        self.conn.commit()

    def initialize_domain(self, domain: str) -> None:
        row = self.conn.execute(
            "SELECT start_ts, current_daily_limit FROM warmup_state WHERE domain=?", (domain,)
        ).fetchone()
        if row:
            return
        self.conn.execute(
            "INSERT INTO warmup_state (domain,start_ts,current_daily_limit,last_send_ts) VALUES (?,?,?,?)",
            (domain, _now(), self.cfg.daily_limit, 0),
        )
        self.conn.commit()

    def ramp_up(self, domain: str) -> None:
        """Increase daily limit after ramp_step_days if not at max."""
        row = self.conn.execute(
            "SELECT start_ts, current_daily_limit FROM warmup_state WHERE domain=?", (domain,)
        ).fetchone()
        if not row:
            return
        start_ts = row["start_ts"]
        current = row["current_daily_limit"]
        if (time.time() - start_ts) >= (self.cfg.ramp_step_days * 24 * 3600):
            new_limit = min(current + self.cfg.ramp_increment, self.cfg.max_daily_limit)
            self.conn.execute(
                "UPDATE warmup_state SET current_daily_limit=? WHERE domain=?",
                (new_limit, domain),
            )
            self.conn.commit()

    def status(self, domain: str) -> dict:
        row = self.conn.execute(
            "SELECT * FROM warmup_state WHERE domain=?", (domain,)
        ).fetchone()
        sent_today = self.daily_sent_count(domain)
        if not row:
            return {"domain": domain, "status": "not_initialized", "sent_today": sent_today}
        return {
            "domain": domain,
            "status": "active",
            "start_ts": row["start_ts"],
            "current_daily_limit": row["current_daily_limit"],
            "sent_today": sent_today,
        }
