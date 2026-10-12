#!/usr/bin/env python3
"""
placement_optimizer.py - Complete Inbox Placement Optimization Pipeline

Ties together all optimization components:
1. Content optimization (spam/promotion/AI slop scoring)
2. Header compliance (List-Unsubscribe, Precedence, etc.)
3. Engagement tracking
4. Warmup management
5. Reputation monitoring
6. Feedback loop processing
7. Final send decision

Usage:
  python3 placement_optimizer.py <message.eml>
  python3 placement_optimizer.py --subject "..." --text "..." --profile hello@nasrullahtanim.me
"""
from __future__ import annotations
import os
import sys, json, time, uuid, smtplib, ssl, sqlite3
from pathlib import Path
from typing import Optional, Dict

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from email_optimizer import optimize_message, OptimizationResult
from list_unsubscribe_manager import UnsubscribeManager
from engagement_tracker import EngagementTracker
from warmup_engine import WarmupEngine

class PlacementOptimizer:
    """Complete inbox placement optimization pipeline."""
    
    def __init__(self):
        self.content_optimizer = optimize_message
        self.unsub_manager = UnsubscribeManager()
        self.engagement = EngagementTracker()
        self.warmup = WarmupEngine()
        self.gate_score = 85  # Minimum score to send
    
    def pre_flight_check(self, subject: str, plain_text: str, html_text: str = "",
                         sender: str = "hello@nasrullahtanim.me") -> Dict:
        """Run complete pre-flight check before sending."""
        result = {}
        
        # 1. Content optimization
        opt_result = optimize_message(subject=subject, plain_text=plain_text, html_text=html_text)
        result["content_score"] = opt_result.score
        result["content_grade"] = opt_result.grade
        result["content_findings"] = opt_result.findings
        result["content_warnings"] = opt_result.warnings
        
        # 2. Unsubscribe check
        result["has_unsubscribe"] = bool(self.unsub_manager.get_unsubscribe_header(sender).get("List-Unsubscribe"))
        if not result["has_unsubscribe"]:
            result["content_warnings"].append("Missing List-Unsubscribe header")
        
        # 3. Warmup check
        stage = self.warmup.get_current_stage()
        result["warmup_stage"] = self.warmup.current_stage
        result["daily_limit"] = self.warmup.get_daily_limit()
        result["daily_sends"] = self.warmup.daily_sends
        result["can_send"] = self.warmup.can_send()
        
        # 4. Engagement check
        engagement = self.engagement.get_engagement_dashboard()
        result["reputation"] = engagement["reputation"]["sender_score"]
        result["open_rate"] = engagement["reputation"]["open_rate"]
        result["bounce_rate"] = engagement["reputation"]["bounce_rate"]
        result["complaint_rate"] = engagement["reputation"]["complaint_rate"]
        
        # 5. Overall assessment
        overall_score = (
            opt_result.score * 0.4 +
            result["reputation"] * 0.3 +
            (100 - result["bounce_rate"] * 10) * 0.15 +
            (100 - result["complaint_rate"] * 1000) * 0.15
        )
        result["overall_score"] = max(0, min(100, overall_score))
        result["overall_grade"] = "A" if overall_score >= 85 else "B" if overall_score >= 70 else "C" if overall_score >= 55 else "F"
        
        # 6. Send decision
        result["send_decision"] = "GO" if (
            opt_result.grade in ("A", "B") and 
            result["can_send"] and 
            overall_score >= self.gate_score and
            result["reputation"] >= 60
        ) else "HOLD"
        
        return result
    
    def send_optimized(self, from_addr: str, to_addr: str, subject: str,
                       plain_text: str, html_text: str = "") -> Dict:
        """Send an optimized email through KumoMTA."""
        
        # 1. Pre-flight check
        check = self.pre_flight_check(subject, plain_text, html_text, from_addr)
        
        if check["send_decision"] == "HOLD":
            return {
                "status": "HOLD",
                "reason": f"Pre-flight check failed: grade={check['content_grade']}, score={check['overall_score']:.1f}",
                "recommendation": check.get("recommendation", ""),
            }
        
        # 2. Add compliance headers
        unsub_headers = self.unsub_manager.get_unsubscribe_header(from_addr)
        
        # 3. Build message
        import email.mime.multipart as mp
        import email.mime.text as mt
        import email.utils as eu
        
        msg = mp.MIMEMultipart("alternative")
        msg["From"] = from_addr
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg["Message-ID"] = f"<{uuid.uuid4().hex}@nasrullahtanim.me>"
        msg["Date"] = eu.formatdate(localtime=True)
        msg["Precedence"] = "bulk"
        
        # Add compliance headers
        for key, value in unsub_headers.items():
            msg[key] = value
        
        msg.attach(mt.MIMEText(plain_text, "plain", "utf-8"))
        if html_text:
            msg.attach(mt.MIMEText(html_text, "html", "utf-8"))
        
        # 4. Send through KumoMTA
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            s = smtplib.SMTP("169.58.207.75", 2587, timeout=30)
            s.ehlo()
            s.starttls(context=ctx)
            s.ehlo()
            s.login("outbound", os.environ.get("KUMO_AUTH_PASS", "local-dev-password"))
            s.sendmail(from_addr, [to_addr], msg.as_string())
            s.quit()
            
            # 5. Record engagement
            send_id = str(time.time())
            self.engagement.record_send(send_id, to_addr, from_addr, subject)
            self.warmup.record_send()
            
            return {
                "status": "SENT",
                "send_id": send_id,
                "to": to_addr,
                "subject": subject,
                "score": check["overall_score"],
                "grade": check["overall_grade"],
            }
        except Exception as e:
            return {
                "status": "FAILED",
                "error": str(e),
            }
    
    def process_feedback_loop(self, feedback_data: Dict):
        """Process feedback loop data (bounces, complaints, opens)."""
        if feedback_data.get("type") == "bounce":
            self.engagement.record_bounce(
                feedback_data["email"],
                feedback_data.get("bounce_type", "unknown"),
                feedback_data.get("reason", "")
            )
            self.warmup.new_day()  # Check if day advanced
        
        elif feedback_data.get("type") == "complaint":
            self.engagement.record_complaint(
                feedback_data["email"],
                feedback_data.get("provider", "")
            )
        
        elif feedback_data.get("type") == "open":
            self.engagement.record_open(
                feedback_data.get("send_id", ""),
                feedback_data["email"],
                feedback_data.get("user_agent", "")
            )
        
        # Update reputation
        reputation = self.engagement.update_reputation("nasrullahtanim.me")
        
        # Check if we need to adjust warmup
        if reputation["bounce_rate"] > 5 or reputation["complaint_rate"] > 0.1:
            # Step back warmup stage
            if self.warmup.current_stage > 1:
                self.warmup.current_stage -= 1
        
        return reputation
    
    def get_optimization_report(self) -> Dict:
        """Get complete optimization report."""
        warmup_rec = self.warmup.get_recommendation()
        engagement = self.engagement.get_engagement_dashboard()
        trend = self.warmup.get_7_day_trend()
        
        return {
            "warmup": warmup_rec,
            "engagement": engagement,
            "placement_trend": trend,
            "recommendation": warmup_rec.get("recommendation", ""),
            "suggestions": warmup_rec.get("suggestions", []),
        }

def main():
    """CLI entry point."""
    import argparse
    ap = argparse.ArgumentParser(description="Inbox Placement Optimizer")
    ap.add_argument("--subject", default="")
    ap.add_argument("--text", default="")
    ap.add_argument("--html", default="")
    ap.add_argument("--from", dest="frm", default="hello@nasrullahtanim.me")
    ap.add_argument("--to", default="")
    ap.add_argument("--file", default="")
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--send", action="store_true")
    
    args = ap.parse_args()
    optimizer = PlacementOptimizer()
    
    if args.report:
        report = optimizer.get_optimization_report()
        print(json.dumps(report, indent=2, default=str))
    elif args.preflight:
        if not args.subject and not args.text:
            print("Error: --subject and --text required for pre-flight")
            return
        check = optimizer.pre_flight_check(args.subject, args.text, args.html, args.frm)
        print(json.dumps(check, indent=2))
    elif args.send:
        if not args.to or not args.subject:
            print("Error: --to and --subject required for send")
            return
        result = optimizer.send_optimized(args.frm, args.to, args.subject, args.text, args.html)
        print(json.dumps(result, indent=2))
    elif args.file:
        import email
        with open(args.file, "rb") as f:
            msg = email.message_from_binary_file(f)
        check = optimizer.pre_flight_check(
            msg.get("Subject", ""),
            "",
            "",
            msg.get("From", "hello@nasrullahtanim.me")
        )
        print(json.dumps(check, indent=2))
    else:
        # Show status
        check = optimizer.warmup.get_recommendation()
        print(f"Warmup Stage: {optimizer.warmup.current_stage}")
        print(f"Daily Limit: {check['daily_limit']}")
        print(f"Daily Sends: {check['daily_sends']}")
        print(f"Can Send: {check['can_send']}")
        print(f"Next Delay: {check['next_delay']}s")
        print(f"Recommendation: {check['recommendation']}")

if __name__ == "__main__":
    main()
