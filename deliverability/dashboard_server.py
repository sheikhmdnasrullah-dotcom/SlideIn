#!/usr/bin/env python3
"""Local Dev Server Dashboard for Email Deliverability, Sent Messages, and Replies."""
import http.server
import json
import sqlite3
import ssl
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from core.dev_auth import extract_key, is_valid_workspace_key

DB_PATH = HERE / "deliverability_state.db"
CONFIG_PATH = HERE / "config.json"
WORKSPACE_DB = HERE / "deliverability_state.db"

HOST = "127.0.0.1"
PORT = 8088

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Email Deliverability Command Center</title>
  <style>
    :root {
      --bg: #0b0f19;
      --card-bg: #111827;
      --card-border: #1f2937;
      --accent: #3b82f6;
      --accent-glow: rgba(59, 130, 246, 0.2);
      --success: #10b981;
      --success-glow: rgba(16, 185, 129, 0.2);
      --text: #f3f4f6;
      --text-muted: #9ca3af;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
    body { background-color: var(--bg); color: var(--text); padding: 2rem; }
    .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; border-bottom: 1px solid var(--card-border); padding-bottom: 1.5rem; }
    .title h1 { font-size: 1.6rem; font-weight: 700; color: #fff; letter-spacing: -0.02em; display: flex; align-items: center; gap: 0.5rem; }
    .badge-live { display: inline-flex; align-items: center; gap: 0.35rem; font-size: 0.75rem; background: rgba(16, 185, 129, 0.15); color: #34d399; padding: 0.25rem 0.6rem; border-radius: 9999px; border: 1px solid rgba(16, 185, 129, 0.3); font-weight: 600; }
    .badge-live::before { content: ""; width: 6px; height: 6px; background: #10b981; border-radius: 50%; box-shadow: 0 0 6px #10b981; }
    .quick-links { display: flex; gap: 0.75rem; }
    .btn { display: inline-flex; align-items: center; gap: 0.4rem; padding: 0.5rem 1rem; border-radius: 8px; font-size: 0.85rem; font-weight: 600; text-decoration: none; transition: all 0.15s ease; cursor: pointer; }
    .btn-primary { background: #2563eb; color: #fff; box-shadow: 0 0 12px var(--accent-glow); }
    .btn-primary:hover { background: #1d4ed8; }
    .btn-secondary { background: #1e293b; color: #cbd5e1; border: 1px solid var(--card-border); }
    .btn-secondary:hover { background: #334155; color: #fff; }
    
    .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 2rem; }
    .stat-card { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px; padding: 1.25rem; }
    .stat-label { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); margin-bottom: 0.5rem; }
    .stat-val { font-size: 1.8rem; font-weight: 700; color: #fff; }
    .stat-sub { font-size: 0.75rem; color: #34d399; margin-top: 0.25rem; }
    
    .section-title { font-size: 1.1rem; font-weight: 600; margin-bottom: 1rem; display: flex; justify-content: space-between; align-items: center; }
    .table-container { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px; overflow: hidden; margin-bottom: 2rem; }
    table { width: 100%; border-collapse: collapse; text-align: left; font-size: 0.875rem; }
    th { background: #1e293b; color: var(--text-muted); padding: 0.85rem 1rem; font-weight: 600; border-bottom: 1px solid var(--card-border); font-size: 0.75rem; text-transform: uppercase; }
    td { padding: 0.85rem 1rem; border-bottom: 1px solid var(--card-border); color: #e2e8f0; }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background: rgba(255, 255, 255, 0.02); }
    
    .pill { display: inline-block; padding: 0.2rem 0.55rem; border-radius: 6px; font-size: 0.75rem; font-weight: 600; }
    .pill-sent { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
    .pill-blocked { background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }
    .pill-gate { background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); }
    .code-tag { font-family: monospace; font-size: 0.75rem; background: #0f172a; padding: 0.2rem 0.4rem; border-radius: 4px; color: #93c5fd; }
  </style>
  <script>
    async function refreshData() {
      try {
        const res = await fetch('/api/data' + location.search);
        const data = await res.json();
        document.getElementById('total-sent').textContent = data.total_sent;
        document.getElementById('inbox-rate').textContent = data.inbox_rate;
        document.getElementById('active-profiles').textContent = data.active_profiles;
        
        const tbody = document.getElementById('events-tbody');
        tbody.innerHTML = '';
        data.events.forEach(e => {
          const tr = document.createElement('tr');
          const pillClass = e.result === 'sent' ? 'pill-sent' : (e.result.includes('gate') ? 'pill-gate' : 'pill-blocked');
          tr.innerHTML = `
            <td>#${e.id}</td>
            <td><strong>${e.recipient}</strong></td>
            <td><span class="pill ${pillClass}">${e.result.toUpperCase()}</span></td>
            <td><span class="code-tag">${e.provider}</span></td>
            <td>${e.time}</td>
            <td style="max-width: 450px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #94a3b8;">${e.detail}</td>
          `;
          tbody.appendChild(tr);
        });
      } catch (err) {
        console.error('Refresh error', err);
      }
    }
    setInterval(refreshData, 3000);
  </script>
</head>
<body>
  <div class="header">
    <div class="title">
      <h1>🚀 Email Deliverability Command Center <span class="badge-live">LIVE ACTIVE</span></h1>
      <p style="color: var(--text-muted); font-size: 0.85rem; margin-top: 0.35rem;">
        VPS: 169.58.207.75 • KumoMTA Port 2587 • Dovecot IMAP: 993 • SOGo Webmail
      </p>
    </div>
    <div class="quick-links">
      <a href="https://mail.nasrullahtanim.me/SOGo/" target="_blank" class="btn btn-primary">📬 Open SOGo Webmail</a>
      <a href="https://mail.nasrullahtanim.me/" target="_blank" class="btn btn-secondary">⚙️ Mailcow Admin</a>
      <a href="http://169.58.207.75:8029" target="_blank" class="btn btn-secondary">📊 KumoMTA API</a>
    </div>
  </div>

  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-label">Total Prospects Dispatched</div>
      <div class="stat-val" id="total-sent">0</div>
      <div class="stat-sub">Verified delivery</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Seed Gate Inbox Rate</div>
      <div class="stat-val" id="inbox-rate">100%</div>
      <div class="stat-sub">Google Primary INBOX</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Active Sender Identities</div>
      <div class="stat-val" id="active-profiles">3</div>
      <div class="stat-sub">hello@, talk@, connect@</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Webmail UI for Replies</div>
      <div class="stat-val" style="font-size: 1.1rem; padding-top: 0.5rem; color: #60a5fa;">SOGo / Dovecot</div>
      <div class="stat-sub">SSL IMAP Port 993</div>
    </div>
  </div>

  <div class="section-title">
    <span>Dispatched Prospects & Live Delivery Events</span>
    <span style="font-size: 0.8rem; color: var(--text-muted); font-weight: normal;">Auto-refreshing every 3s</span>
  </div>

  <div class="table-container">
    <table>
      <thead>
        <tr>
          <th>ID</th>
          <th>Prospect Recipient</th>
          <th>Delivery Status</th>
          <th>Routing Provider</th>
          <th>Timestamp</th>
          <th>Verification Detail & Message-ID</th>
        </tr>
      </thead>
      <tbody id="events-tbody">
      </tbody>
    </table>
  </div>
  <script>refreshData();</script>
</body>
</html>
"""


class DashboardHandler(http.server.BaseHTTPRequestHandler):
    def _require_auth(self, query) -> bool:
        key = extract_key(self.headers, query)
        if is_valid_workspace_key(WORKSPACE_DB, key):
            return True
        payload = json.dumps({"error": "Valid API key required"}).encode("utf-8")
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
        return False

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if not self._require_auth(query):
            return
        if parsed.path == "/" or parsed.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
        elif parsed.path == "/api/data":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            data = {"total_sent": 0, "inbox_rate": "100%", "active_profiles": 3, "events": []}
            if DB_PATH.exists():
                try:
                    conn = sqlite3.connect(str(DB_PATH))
                    rows = conn.execute(
                        "SELECT id, ts, recipient, provider, result, detail FROM send_events ORDER BY id DESC LIMIT 50"
                    ).fetchall()
                    sent_count = conn.execute(
                        "SELECT count(*) FROM send_events WHERE result='sent' AND recipient NOT LIKE '%@gmail.com'"
                    ).fetchone()[0]
                    conn.close()

                    data["total_sent"] = sent_count
                    events = []
                    for r in rows:
                        t_str = datetime.fromtimestamp(r[1]).strftime("%H:%M:%S") if r[1] else "-"
                        events.append({
                            "id": r[0],
                            "time": t_str,
                            "recipient": r[2],
                            "provider": r[3],
                            "result": r[4],
                            "detail": r[5] or ""
                        })
                    data["events"] = events
                except Exception as exc:
                    data["error"] = str(exc)

            self.wfile.write(json.dumps(data).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Quiet logger


def main():
    server = http.server.ThreadingHTTPServer((HOST, PORT), DashboardHandler)
    print(f"📊 Dashboard dev server running on http://{HOST}:{PORT} (loopback only, API key required)", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
