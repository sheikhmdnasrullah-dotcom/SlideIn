#!/usr/bin/env python3
"""
engagement_tracker.py - Email Engagement & Feedback Loop Processor

Tracks opens, clicks, replies, bounces, and complaints.
Processes feedback loops from Gmail, Yahoo, Microsoft.
Updates sender reputation based on engagement metrics.
"""
from __future__ import annotations
import json, sqlite3, time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict

class EngagementTracker:
    """Tracks all email engagement metrics."""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(Path(__file__).parent / "engagement.db")
        self._init_db()
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sends (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                profile TEXT NOT NULL,
                subject TEXT,
                sent_at REAL NOT NULL,
                status TEXT DEFAULT 'sent'
            );
            CREATE TABLE IF NOT EXISTS opens (
                id TEXT PRIMARY KEY,
                send_id TEXT NOT NULL,
                email TEXT NOT NULL,
                opened_at REAL NOT NULL,
                user_agent TEXT,
                FOREIGN KEY (send_id) REFERENCES sends(id)
            );
            CREATE TABLE IF NOT EXISTS clicks (
                id TEXT PRIMARY KEY,
                send_id TEXT NOT NULL,
                email TEXT NOT NULL,
                clicked_at REAL NOT NULL,
                url TEXT,
                FOREIGN KEY (send_id) REFERENCES sends(id)
            );
            CREATE TABLE IF NOT EXISTS replies (
                id TEXT PRIMARY KEY,
                send_id TEXT NOT NULL,
                email TEXT NOT NULL,
                replied_at REAL NOT NULL,
                body TEXT,
                FOREIGN KEY (send_id) REFERENCES sends(id)
            );
            CREATE TABLE IF NOT EXISTS bounces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                send_id TEXT,
                bounced_at REAL NOT NULL,
                bounce_type TEXT NOT NULL,
                reason TEXT,
                FOREIGN KEY (send_id) REFERENCES sends(id)
            );
            CREATE TABLE IF NOT EXISTS complaints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                send_id TEXT,
                complained_at REAL NOT NULL,
                provider TEXT,
                FOREIGN KEY (send_id) REFERENCES sends(id)
            );
            CREATE TABLE IF NOT EXISTS reputation (
                domain TEXT PRIMARY KEY,
                sender_score REAL DEFAULT 100.0,
                last_updated REAL NOT NULL,
                total_sends INTEGER DEFAULT 0,
                total_opens INTEGER DEFAULT 0,
                total_clicks INTEGER DEFAULT 0,
                total_replies INTEGER DEFAULT 0,
                total_bounces INTEGER DEFAULT 0,
                total_complaints INTEGER DEFAULT 0,
                open_rate REAL DEFAULT 0.0,
                click_rate REAL DEFAULT 0.0,
                bounce_rate REAL DEFAULT 0.0,
                complaint_rate REAL DEFAULT 0.0,
                engagement_score REAL DEFAULT 0.0
            );
        """)
        conn.commit()
        conn.close()
    
    def record_send(self, send_id: str, email: str, profile: str, subject: str = ""):
        """Record a sent email."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO sends (id, email, profile, subject, sent_at) VALUES (?, ?, ?, ?, ?)",
                (send_id, email, profile, subject, time.time())
            )
            conn.commit()
        finally:
            conn.close()
    
    def record_open(self, send_id: str, email: str, user_agent: str = ""):
        """Record an email open."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO opens (id, send_id, email, opened_at, user_agent) VALUES (?, ?, ?, ?, ?)",
                (str(time.time()), send_id, email, time.time(), user_agent)
            )
            conn.commit()
        finally:
            conn.close()
    
    def record_click(self, send_id: str, email: str, url: str):
        """Record a click."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO clicks (id, send_id, email, clicked_at, url) VALUES (?, ?, ?, ?, ?)",
                (str(time.time()), send_id, email, time.time(), url)
            )
            conn.commit()
        finally:
            conn.close()
    
    def record_reply(self, send_id: str, email: str, body: str = ""):
        """Record a reply."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO replies (id, send_id, email, replied_at, body) VALUES (?, ?, ?, ?, ?)",
                (str(time.time()), send_id, email, time.time(), body)
            )
            conn.commit()
        finally:
            conn.close()
    
    def record_bounce(self, email: str, bounce_type: str, reason: str = ""):
        """Record a bounce."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO bounces (email, bounced_at, bounce_type, reason) VALUES (?, ?, ?, ?)",
                (email, time.time(), bounce_type, reason)
            )
            conn.commit()
        finally:
            conn.close()
    
    def record_complaint(self, email: str, provider: str = ""):
        """Record a complaint."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO complaints (email, complained_at, provider) VALUES (?, ?, ?)",
                (email, time.time(), provider)
            )
            conn.commit()
        finally:
            conn.close()
    
    def get_engagement_metrics(self, email: str) -> Dict:
        """Get engagement metrics for an email."""
        conn = sqlite3.connect(self.db_path)
        try:
            # Check if email exists in sends
            send = conn.execute("SELECT * FROM sends WHERE email = ?", (email,)).fetchone()
            if not send:
                return {"exists": False}
            
            send_id = send[0]
            opens = conn.execute("SELECT COUNT(*) FROM opens WHERE send_id = ?", (send_id,)).fetchone()[0]
            clicks = conn.execute("SELECT COUNT(*) FROM clicks WHERE send_id = ?", (send_id,)).fetchone()[0]
            replies = conn.execute("SELECT COUNT(*) FROM replies WHERE send_id = ?", (send_id,)).fetchone()[0]
            bounces = conn.execute("SELECT COUNT(*) FROM bounces WHERE email = ?", (email,)).fetchone()[0]
            complaints = conn.execute("SELECT COUNT(*) FROM complaints WHERE email = ?", (email,)).fetchone()[0]
            
            return {
                "exists": True,
                "opened": opens > 0,
                "clicked": clicks > 0,
                "replied": replies > 0,
                "bounced": bounces > 0,
                "complained": complaints > 0,
                "opens": opens,
                "clicks": clicks,
                "replies": replies,
                "bounces": bounces,
                "complaints": complaints,
            }
        finally:
            conn.close()
    
    def update_reputation(self, domain: str):
        """Update domain reputation based on engagement."""
        conn = sqlite3.connect(self.db_path)
        try:
            total_sends = conn.execute("SELECT COUNT(*) FROM sends").fetchone()[0]
            total_opens = conn.execute("SELECT COUNT(*) FROM opens").fetchone()[0]
            total_clicks = conn.execute("SELECT COUNT(*) FROM clicks").fetchone()[0]
            total_replies = conn.execute("SELECT COUNT(*) FROM replies").fetchone()[0]
            total_bounces = conn.execute("SELECT COUNT(*) FROM bounces").fetchone()[0]
            total_complaints = conn.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]
            
            open_rate = (total_opens / max(total_sends, 1)) * 100
            click_rate = (total_clicks / max(total_sends, 1)) * 100
            bounce_rate = (total_bounces / max(total_sends, 1)) * 100
            complaint_rate = (total_complaints / max(total_sends, 1)) * 100
            
            # Calculate engagement score (0-100)
            engagement_score = (
                open_rate * 0.4 + 
                click_rate * 0.3 + 
                (100 - bounce_rate) * 0.2 + 
                (100 - complaint_rate) * 0.1
            )
            
            # Sender score
            sender_score = max(0, min(100, engagement_score))
            
            # Adjust based on specific metrics
            if bounce_rate > 5:
                sender_score -= 20
            if complaint_rate > 0.1:
                sender_score -= 30
            if open_rate < 10:
                sender_score -= 15
            if click_rate > 5:
                sender_score += 10
            if reply_rate > 5:
                sender_score += 15
            
            conn.execute(
                """INSERT OR REPLACE INTO reputation 
                (domain, sender_score, last_updated, total_sends, total_opens, 
                 total_clicks, total_replies, total_bounces, total_complaints,
                 open_rate, click_rate, bounce_rate, complaint_rate, engagement_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (domain, sender_score, time.time(), total_sends, total_opens,
                 total_clicks, total_replies, total_bounces, total_complaints,
                 open_rate, click_rate, bounce_rate, complaint_rate, engagement_score)
            )
            conn.commit()
            
            return {
                "sender_score": sender_score,
                "open_rate": open_rate,
                "click_rate": click_rate,
                "bounce_rate": bounce_rate,
                "complaint_rate": complaint_rate,
                "engagement_score": engagement_score,
            }
        finally:
            conn.close()
    
    def get_engagement_dashboard(self) -> dict:
        """Get full engagement dashboard."""
        reputation = self.update_reputation("nasrullahtanim.me")
        
        conn = sqlite3.connect(self.db_path)
        try:
            total_sends = conn.execute("SELECT COUNT(*) FROM sends").fetchone()[0]
            total_opens = conn.execute("SELECT COUNT(*) FROM opens").fetchone()[0]
            total_clicks = conn.execute("SELECT COUNT(*) FROM clicks").fetchone()[0]
            total_replies = conn.execute("SELECT COUNT(*) FROM replies").fetchone()[0]
            total_bounces = conn.execute("SELECT COUNT(*) FROM bounces").fetchone()[0]
            total_complaints = conn.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]
            
            # Get bounce breakdown
            bounce_breakdown = conn.execute(
                "SELECT bounce_type, COUNT(*) FROM bounces GROUP BY bounce_type"
            ).fetchall()
            
            # Get recent sends
            recent = conn.execute(
                "SELECT email, profile, sent_at FROM sends ORDER BY sent_at DESC LIMIT 20"
            ).fetchall()
            
            return {
                "reputation": reputation,
                "total_sends": total_sends,
                "total_opens": total_opens,
                "total_clicks": total_clicks,
                "total_replies": total_replies,
                "total_bounces": total_bounces,
                "total_complaints": total_complaints,
                "bounce_breakdown": dict(bounce_breakdown),
                "recent_sends": recent,
                "reputation_grade": "A" if reputation["sender_score"] >= 80 else "B" if reputation["sender_score"] >= 60 else "C",
            }
        finally:
            conn.close()

def main():
    """CLI entry point."""
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 engagement_tracker.py dashboard")
        print("       python3 engagement_tracker.py record-send <email> <profile>")
        print("       python3 engagement_tracker.py record-open <send_id> <email>")
        print("       python3 engagement_tracker.py record-bounce <email> <type>")
        return
    
    tracker = EngagementTracker()
    cmd = sys.argv[1]
    
    if cmd == "dashboard":
        dashboard = tracker.get_engagement_dashboard()
        print(json.dumps(dashboard, indent=2, default=str))
    elif cmd == "record-send" and len(sys.argv) >= 4:
        email = sys.argv[2]
        profile = sys.argv[3]
        send_id = str(time.time())
        tracker.record_send(send_id, email, profile)
        print(f"[OK] Send recorded: {email} via {profile}")
    elif cmd == "record-open" and len(sys.argv) >= 4:
        send_id = sys.argv[2]
        email = sys.argv[3]
        tracker.record_open(send_id, email)
        print(f"[OK] Open recorded: {email}")
    elif cmd == "record-bounce" and len(sys.argv) >= 4:
        email = sys.argv[2]
        btype = sys.argv[3]
        tracker.record_bounce(email, btype)
        print(f"[OK] Bounce recorded: {email} ({btype})")
    else:
        print("Unknown command")

if __name__ == "__main__":
    main()
