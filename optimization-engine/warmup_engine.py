#!/usr/bin/env python3
"""
warmup_engine.py - Optimized Warmup Engine

Manages email warmup schedules to build sender reputation.
Gradually increases volume while monitoring inbox placement.
Uses feedback loops to adjust pace.
"""
from __future__ import annotations
import json, time, sqlite3, random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

class WarmupEngine:
    """Optimized warmup engine for cold email reputation building."""
    
    WARMUP_STAGES = [
        # Stage: (daily_limit, step_days, min_delay, max_delay, notes)
        {"stage": 1, "daily_limit": 10, "step_days": 1, "min_delay": 120, "max_delay": 180, "notes": "Absolute minimum volume"},
        {"stage": 2, "daily_limit": 15, "step_days": 1, "min_delay": 90, "max_delay": 150, "notes": "Building baseline"},
        {"stage": 3, "daily_limit": 20, "step_days": 2, "min_delay": 60, "max_delay": 120, "notes": "Normal warmup"},
        {"stage": 4, "daily_limit": 30, "step_days": 2, "min_delay": 45, "max_delay": 90, "notes": "Increasing volume"},
        {"stage": 5, "daily_limit": 50, "step_days": 3, "min_delay": 30, "max_delay": 60, "notes": "Good engagement"},
        {"stage": 6, "daily_limit": 80, "step_days": 3, "min_delay": 20, "max_delay": 45, "notes": "Building momentum"},
        {"stage": 7, "daily_limit": 120, "step_days": 3, "min_delay": 15, "max_delay": 30, "notes": "Strong engagement"},
        {"stage": 8, "daily_limit": 200, "step_days": 5, "min_delay": 10, "max_delay": 20, "notes": "Steady state"},
    ]
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(Path(__file__).parent / "warmup_state.db")
        self._init_db()
        self._load_state()
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS warmup_state (
                domain TEXT PRIMARY KEY,
                current_stage INTEGER DEFAULT 1,
                day_count INTEGER DEFAULT 0,
                daily_sends INTEGER DEFAULT 0,
                last_send_ts REAL,
                start_ts REAL
            );
            CREATE TABLE IF NOT EXISTS daily_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT,
                date TEXT,
                sends INTEGER,
                opens INTEGER DEFAULT 0,
                clicks INTEGER DEFAULT 0,
                bounces INTEGER DEFAULT 0,
                complaints INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS placement_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT,
                date TEXT,
                inbox_pct REAL,
                promotions_pct REAL,
                spam_pct REAL,
                notes TEXT
            );
        """)
        conn.commit()
        conn.close()
    
    def _load_state(self):
        conn = sqlite3.connect(self.db_path)
        try:
            state = conn.execute("SELECT * FROM warmup_state WHERE domain = 'nasrullahtanim.me'").fetchone()
            if state:
                self.current_stage = state[1]
                self.day_count = state[2]
                self.daily_sends = state[3]
                self.last_send_ts = state[4]
                self.start_ts = state[5]
            else:
                self.current_stage = 1
                self.day_count = 0
                self.daily_sends = 0
                self.last_send_ts = 0
                self.start_ts = time.time()
                conn.execute(
                    "INSERT INTO warmup_state (domain, current_stage, day_count, daily_sends, last_send_ts, start_ts) VALUES (?, ?, ?, ?, ?, ?)",
                    ("nasrullahtanim.me", 1, 0, 0, time.time(), time.time())
                )
                conn.commit()
        finally:
            conn.close()
    
    def _save_state(self):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO warmup_state (domain, current_stage, day_count, daily_sends, last_send_ts, start_ts) VALUES (?, ?, ?, ?, ?, ?)",
                ("nasrullahtanim.me", self.current_stage, self.day_count, self.daily_sends, time.time(), self.start_ts)
            )
            conn.commit()
        finally:
            conn.close()
    
    def get_current_stage(self) -> Dict:
        """Get current warmup stage configuration."""
        if self.current_stage <= len(self.WARMUP_STAGES):
            return self.WARMUP_STAGES[self.current_stage - 1]
        return self.WARMUP_STAGES[-1]
    
    def get_daily_limit(self) -> int:
        """Get today's send limit."""
        stage = self.get_current_stage()
        # Adjust for day count
        adjusted = stage["daily_limit"]
        if self.day_count > stage["step_days"]:
            # Can increase if engagement is good
            adjusted = min(adjusted + 10, 200)
        return adjusted
    
    def can_send(self) -> bool:
        """Check if we can send more emails today."""
        if self.daily_sends >= self.get_daily_limit():
            return False
        # Check pacing
        if self.last_send_ts > 0:
            stage = self.get_current_stage()
            min_delay = stage["min_delay"]
            elapsed = time.time() - self.last_send_ts
            if elapsed < min_delay:
                return False
        return True
    
    def get_next_send_delay(self) -> int:
        """Get delay before next send."""
        stage = self.get_current_stage()
        return random.randint(stage["min_delay"], stage["max_delay"])
    
    def record_send(self):
        """Record a send."""
        self.daily_sends += 1
        self.last_send_ts = time.time()
        self._save_state()
    
    def new_day(self):
        """Advance to next day."""
        today = datetime.now().strftime("%Y-%m-%d")
        conn = sqlite3.connect(self.db_path)
        try:
            # Check if we already logged today
            today_log = conn.execute(
                "SELECT 1 FROM daily_log WHERE domain = ? AND date = ?",
                ("nasrullahtanim.me", today)
            ).fetchone()
            
            if not today_log:
                self.day_count += 1
                self.daily_sends = 0
                
                # Check if we should advance stage
                stage = self.get_current_stage()
                if self.day_count >= stage["step_days"]:
                    if self.current_stage < len(self.WARMUP_STAGES):
                        self.current_stage += 1
                
                # Log daily stats
                conn.execute(
                    "INSERT INTO daily_log (domain, date, sends) VALUES (?, ?, ?)",
                    ("nasrullahtanim.me", today, self.daily_sends)
                )
                conn.commit()
                self._save_state()
        finally:
            conn.close()
    
    def record_placement(self, inbox_pct: float, promotions_pct: float, spam_pct: float, notes: str = ""):
        """Record inbox placement data."""
        conn = sqlite3.connect(self.db_path)
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            conn.execute(
                "INSERT INTO placement_log (domain, date, inbox_pct, promotions_pct, spam_pct, notes) VALUES (?, ?, ?, ?, ?, ?)",
                ("nasrullahtanim.me", today, inbox_pct, promotions_pct, spam_pct, notes)
            )
            conn.commit()
        finally:
            conn.close()
    
    def get_recommendation(self) -> Dict:
        """Get optimization recommendation."""
        stage = self.get_current_stage()
        
        # Check placement history
        conn = sqlite3.connect(self.db_path)
        try:
            recent = conn.execute(
                "SELECT inbox_pct, promotions_pct, spam_pct FROM placement_log ORDER BY id DESC LIMIT 7"
            ).fetchall()
            
            avg_inbox = sum(r[0] for r in recent) / max(len(recent), 1) if recent else 0
            avg_promotions = sum(r[1] for r in recent) / max(len(recent), 1) if recent else 0
            avg_spam = sum(r[2] for r in recent) / max(len(recent), 1) if recent else 0
            
            recommendation = {
                "current_stage": self.current_stage,
                "stage_name": stage["notes"],
                "daily_limit": self.get_daily_limit(),
                "daily_sends": self.daily_sends,
                "can_send": self.can_send(),
                "next_delay": self.get_next_send_delay(),
                "avg_inbox_pct": avg_inbox,
                "avg_promotions_pct": avg_promotions,
                "avg_spam_pct": avg_spam,
                "recommendation": "",
            }
            
            # Generate recommendation
            if avg_inbox >= 95:
                recommendation["recommendation"] = "Excellent placement! Can increase volume."
            elif avg_inbox >= 85:
                recommendation["recommendation"] = "Good placement. Maintain current volume."
            elif avg_inbox >= 70:
                recommendation["recommendation"] = "Fair placement. Review content and pacing."
            elif avg_inbox >= 50:
                recommendation["recommendation"] = "Poor placement. Reduce volume and check content."
            else:
                recommendation["recommendation"] = "Critical placement. Stop sending and investigate."
            
            # Suggestions
            suggestions = []
            if avg_promotions > 20:
                suggestions.append("Reduce promotional language to avoid Gmail Promotions tab")
            if avg_spam > 10:
                suggestions.append("Review content for spam trigger words")
            if avg_inbox < 80 and self.current_stage > 1:
                suggestions.append("Consider stepping back one warmup stage")
            if suggestions:
                recommendation["suggestions"] = suggestions
            
            return recommendation
        finally:
            conn.close()
    
    def get_7_day_trend(self) -> List[Dict]:
        """Get 7-day placement trend."""
        conn = sqlite3.connect(self.db_path)
        try:
            trend = conn.execute(
                "SELECT date, inbox_pct, promotions_pct, spam_pct FROM placement_log ORDER BY id DESC LIMIT 7"
            ).fetchall()
            return [{"date": r[0], "inbox": r[1], "promotions": r[2], "spam": r[3]} for r in trend]
        finally:
            conn.close()

def main():
    """CLI entry point."""
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 warmup_engine.py status")
        print("       python3 warmup_engine.py record-send")
        print("       python3 warmup_engine.py recommendation")
        print("       python3 warmup_engine.py trend")
        return
    
    engine = WarmupEngine()
    cmd = sys.argv[1]
    
    if cmd == "status":
        stage = engine.get_current_stage()
        print(json.dumps({
            "stage": engine.current_stage,
            "stage_name": stage["notes"],
            "daily_limit": engine.get_daily_limit(),
            "daily_sends": engine.daily_sends,
            "can_send": engine.can_send(),
            "next_delay": engine.get_next_send_delay(),
        }, indent=2))
    elif cmd == "record-send":
        engine.record_send()
        print("[OK] Send recorded")
    elif cmd == "recommendation":
        rec = engine.get_recommendation()
        print(json.dumps(rec, indent=2))
    elif cmd == "trend":
        trend = engine.get_7_day_trend()
        print(json.dumps(trend, indent=2))
    else:
        print("Unknown command")

if __name__ == "__main__":
    main()
