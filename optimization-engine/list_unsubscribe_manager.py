#!/usr/bin/env python3
"""
list_unsubscribe_manager.py - One-Click Unsubscribe Management

Manages List-Unsubscribe headers and unsubscribe processing.
Required by Gmail/Yahoo bulk sender guidelines (2024+).
"""
from __future__ import annotations
import json, sqlite3, uuid, time
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "unsubscribe.db"

class UnsubscribeManager:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DB_PATH)
        self._init_db()
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS unsubscribes (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                timestamp REAL NOT NULL,
                source TEXT DEFAULT 'campaign',
                status TEXT DEFAULT 'active'
            );
            CREATE TABLE IF NOT EXISTS unsubscribers (
                email TEXT PRIMARY KEY,
                timestamp REAL NOT NULL,
                source TEXT DEFAULT 'campaign'
            );
            CREATE TABLE IF NOT EXISTS bounces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                timestamp REAL NOT NULL,
                bounce_type TEXT NOT NULL,
                reason TEXT
            );
        """)
        conn.commit()
        conn.close()
    
    def get_unsubscribe_header(self, sender: str = "hello@nasrullahtanim.me") -> dict:
        """Generate compliant List-Unsubscribe headers."""
        domain = sender.split("@")[1] if "@" in sender else "nasrullahtanim.me"
        unsub_id = str(uuid.uuid4())
        
        headers = {
            "Precedence": "bulk",
            "List-Unsubscribe": f"<mailto:unsubscribe@{domain}?subject=unsubscribe:{unsub_id}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            "List-Help": f"<mailto:help@{domain}>",
            "Feedback-ID": f"{domain}:{int(time.time())}",
        }
        return headers
    
    def add_unsubscriber(self, email: str, source: str = "campaign") -> bool:
        """Add email to unsubscribe list."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO unsubscribers (email, timestamp, source) VALUES (?, ?, ?)",
                (email, time.time(), source)
            )
            conn.commit()
            return True
        finally:
            conn.close()
    
    def is_unsubscribed(self, email: str) -> bool:
        """Check if email is unsubscribed."""
        conn = sqlite3.connect(self.db_path)
        try:
            result = conn.execute(
                "SELECT 1 FROM unsubscribers WHERE email = ?", (email,)
            ).fetchone()
            return result is not None
        finally:
            conn.close()
    
    def add_bounce(self, email: str, bounce_type: str, reason: str = ""):
        """Record a bounce."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO bounces (email, timestamp, bounce_type, reason) VALUES (?, ?, ?, ?)",
                (email, time.time(), bounce_type, reason)
            )
            conn.commit()
        finally:
            conn.close()
    
    def get_compliance_report(self) -> dict:
        """Get compliance statistics."""
        conn = sqlite3.connect(self.db_path)
        try:
            total_unsub = conn.execute("SELECT COUNT(*) FROM unsubscribers").fetchone()[0]
            total_bounces = conn.execute("SELECT COUNT(*) FROM bounces").fetchone()[0]
            hard_bounces = conn.execute("SELECT COUNT(*) FROM bounces WHERE bounce_type = 'hard_bounce'").fetchone()[0]
            return {
                "total_unsubscribed": total_unsub,
                "total_bounces": total_bounces,
                "hard_bounces": hard_bounces,
                "compliance_status": "good" if hard_bounces < 10 else "needs_attention",
            }
        finally:
            conn.close()
    
    def generate_unsubscribe_page(self) -> str:
        """Generate HTML unsubscribe confirmation page."""
        return """<!DOCTYPE html>
<html><head><title>Unsubscribe</title></head>
<body>
<h1>You've been unsubscribed</h1>
<p>You will no longer receive emails from us.</p>
<p>If you believe this is an error, contact <a href="mailto:hello@nasrullahtanim.me">hello@nasrullahtanim.me</a>.</p>
</body></html>"""

def main():
    """CLI entry point."""
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 list_unsubscribe_manager.py add <email>")
        print("       python3 list_unsubscribe_manager.py check <email>")
        print("       python3 list_unsubscribe_manager.py report")
        return
    
    manager = UnsubscribeManager()
    cmd = sys.argv[1]
    
    if cmd == "add" and len(sys.argv) >= 3:
        email = sys.argv[2]
        if manager.add_unsubscriber(email):
            print(f"[OK] {email} added to unsubscribe list")
    elif cmd == "check" and len(sys.argv) >= 3:
        email = sys.argv[2]
        if manager.is_unsubscribed(email):
            print(f"[UNSUBSCRIBED] {email}")
        else:
            print(f"[ACTIVE] {email}")
    elif cmd == "report":
        report = manager.get_compliance_report()
        print(json.dumps(report, indent=2))
    else:
        print("Unknown command")

if __name__ == "__main__":
    main()
