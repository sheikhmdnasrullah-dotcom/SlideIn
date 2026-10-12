"""Monitoring dashboard for transactional email delivery.

Provides a simple HTML dashboard with real-time stats and event history.
Can be served standalone or integrated with the webhook server.
"""
from __future__ import annotations

import json
import os
import sys
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from core.webhook import WebhookProcessor


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Email Delivery Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; color: #333; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        h1 { font-size: 24px; margin-bottom: 20px; color: #1a1a1a; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }
        .stat-card { background: white; border-radius: 8px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .stat-label { font-size: 12px; color: #666; text-transform: uppercase; letter-spacing: 1px; }
        .stat-value { font-size: 32px; font-weight: 600; margin-top: 8px; }
        .stat-rate { font-size: 14px; color: #666; margin-top: 4px; }
        .stat-card.success .stat-value { color: #28a745; }
        .stat-card.warning .stat-value { color: #ffc107; }
        .stat-card.danger .stat-value { color: #dc3545; }
        .stat-card.info .stat-value { color: #17a2b8; }
        .events-table { width: 100%; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .events-table th { background: #f8f9fa; padding: 12px 16px; text-align: left; font-size: 12px; text-transform: uppercase; color: #666; }
        .events-table td { padding: 12px 16px; border-top: 1px solid #eee; font-size: 14px; }
        .events-table tr:hover { background: #f8f9fa; }
        .badge { display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: 500; }
        .badge-success { background: #d4edda; color: #155724; }
        .badge-danger { background: #f8d7da; color: #721c24; }
        .badge-warning { background: #fff3cd; color: #856404; }
        .badge-info { background: #d1ecf1; color: #0c5460; }
        .refresh-btn { background: #0066cc; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 14px; }
        .refresh-btn:hover { background: #0055aa; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
        .last-updated { color: #666; font-size: 12px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Email Delivery Dashboard</h1>
            <div>
                <span class="last-updated" id="lastUpdated"></span>
                <button class="refresh-btn" onclick="refresh()">Refresh</button>
            </div>
        </div>
        
        <div class="stats-grid" id="statsGrid">
            <div class="stat-card info">
                <div class="stat-label">Total Sent</div>
                <div class="stat-value" id="totalSent">-</div>
            </div>
            <div class="stat-card success">
                <div class="stat-label">Delivered</div>
                <div class="stat-value" id="totalDelivered">-</div>
                <div class="stat-rate" id="deliveryRate">-</div>
            </div>
            <div class="stat-card danger">
                <div class="stat-label">Bounced</div>
                <div class="stat-value" id="totalBounces">-</div>
                <div class="stat-rate" id="bounceRate">-</div>
            </div>
            <div class="stat-card warning">
                <div class="stat-label">Complaints</div>
                <div class="stat-value" id="totalComplaints">-</div>
                <div class="stat-rate" id="complaintRate">-</div>
            </div>
            <div class="stat-card info">
                <div class="stat-label">Opens</div>
                <div class="stat-value" id="totalOpens">-</div>
                <div class="stat-rate" id="openRate">-</div>
            </div>
            <div class="stat-card info">
                <div class="stat-label">Clicks</div>
                <div class="stat-value" id="totalClicks">-</div>
                <div class="stat-rate" id="clickRate">-</div>
            </div>
        </div>
        
        <h2 style="margin-bottom: 16px; font-size: 18px;">Recent Events</h2>
        <table class="events-table">
            <thead>
                <tr>
                    <th>Time</th>
                    <th>Type</th>
                    <th>Recipient</th>
                    <th>Status</th>
                    <th>Detail</th>
                </tr>
            </thead>
            <tbody id="eventsBody">
                <tr><td colspan="5" style="text-align: center; color: #666;">Loading...</td></tr>
            </tbody>
        </table>
    </div>
    
    <script>
        async function refresh() {
            try {
                const [statsRes, eventsRes] = await Promise.all([
                    fetch('/api/stats'),
                    fetch('/api/events?limit=50')
                ]);
                
                const stats = await statsRes.json();
                const events = await eventsRes.json();
                
                // Update stats
                document.getElementById('totalSent').textContent = stats.total_sent.toLocaleString();
                document.getElementById('totalDelivered').textContent = stats.total_delivered.toLocaleString();
                document.getElementById('totalBounces').textContent = stats.total_bounces.toLocaleString();
                document.getElementById('totalComplaints').textContent = stats.total_complaints.toLocaleString();
                document.getElementById('totalOpens').textContent = stats.total_opens.toLocaleString();
                document.getElementById('totalClicks').textContent = stats.total_clicks.toLocaleString();
                
                document.getElementById('deliveryRate').textContent = (stats.delivery_rate * 100).toFixed(1) + '%';
                document.getElementById('bounceRate').textContent = (stats.bounce_rate * 100).toFixed(1) + '%';
                document.getElementById('complaintRate').textContent = (stats.complaint_rate * 100).toFixed(2) + '%';
                document.getElementById('openRate').textContent = (stats.open_rate * 100).toFixed(1) + '%';
                document.getElementById('clickRate').textContent = (stats.click_rate * 100).toFixed(1) + '%';
                
                // Update events
                const tbody = document.getElementById('eventsBody');
                if (events.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: #666;">No events yet</td></tr>';
                } else {
                    tbody.innerHTML = events.map(e => {
                        const time = new Date(e.timestamp * 1000).toLocaleString();
                        const badge = e.status === 'success' ? 'badge-success' : 
                                     e.status === 'failed' ? 'badge-danger' : 'badge-warning';
                        return `<tr>
                            <td>${time}</td>
                            <td>${e.event_type}</td>
                            <td>${e.recipient}</td>
                            <td><span class="badge ${badge}">${e.status}</span></td>
                            <td>${e.detail || '-'}</td>
                        </tr>`;
                    }).join('');
                }
                
                document.getElementById('lastUpdated').textContent = 'Updated: ' + new Date().toLocaleTimeString();
            } catch (err) {
                console.error('Failed to refresh:', err);
            }
        }
        
        refresh();
        setInterval(refresh, 30000); // Auto-refresh every 30 seconds
    </script>
</body>
</html>"""


class DashboardHandler(BaseHTTPRequestHandler):
    """HTTP handler for dashboard."""
    
    processor: Optional[WebhookProcessor] = None
    
    def log_message(self, format, *args):
        pass
    
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        
        if path == "/" or path == "/dashboard":
            self._serve_html()
        elif path == "/api/stats":
            self._serve_stats(params)
        elif path == "/api/events":
            self._serve_events(params)
        elif path == "/health":
            self._send_json(200, {"status": "ok"})
        else:
            self._send_json(404, {"error": "not found"})
    
    def _serve_html(self):
        response = DASHBOARD_HTML.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)
    
    def _serve_stats(self, params: dict):
        domain = params.get("domain", [""])[0]
        days = int(params.get("days", ["30"])[0])
        stats = self.processor.get_stats(domain, days)
        self._send_json(200, stats)
    
    def _serve_events(self, params: dict):
        limit = int(params.get("limit", ["100"])[0])
        events = self.processor.get_recent_events(limit)
        self._send_json(200, events)
    
    def _send_json(self, status_code: int, data):
        response = json.dumps(data, default=str).encode()
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Email delivery monitoring dashboard")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--db", default=os.path.join(HERE, "deliverability_state.db"))
    args = parser.parse_args()
    
    DashboardHandler.processor = WebhookProcessor(args.db)
    
    server = HTTPServer((args.host, args.port), DashboardHandler)
    print(f"Dashboard listening on http://{args.host}:{args.port}")
    print(f"  Dashboard: http://{args.host}:{args.port}/")
    print(f"  API Stats: http://{args.host}:{args.port}/api/stats")
    print(f"  API Events: http://{args.host}:{args.port}/api/events")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()
        DashboardHandler.processor.close()


if __name__ == "__main__":
    main()
