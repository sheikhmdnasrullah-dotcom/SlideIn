#!/usr/bin/env bash
set -euo pipefail

VPS="${1:-root@169.58.207.75}"
PASS="${VPS_PASS:?set VPS_PASS env var}"

echo "=== Deploying Optimization Engine ==="

# Copy files
sshpass -p "$PASS" scp -o StrictHostKeyChecking=no -r \
  /Users/nasrullahtanim/Downloads/email-master\ raw/optimization-engine/* \
  "$VPS:/opt/optimization-engine/"

# Install dependencies
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$VPS" "
mkdir -p /opt/optimization-engine
cd /opt/optimization-engine
npm install 2>/dev/null || echo 'npm not needed for Python components'
pip3 install better-sqlite3 2>/dev/null || echo 'already installed'

# Create systemd services
cat > /etc/systemd/system/optimization-engine.service << 'EOF'
[Unit]
Description=Inbox Placement Optimization Engine
After=kumomta.service gophish.service
Requires=kumomta.service

[Service]
Type=simple
WorkingDirectory=/opt/optimization-engine
ExecStart=/usr/bin/node /opt/optimization-engine/src/index.js
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Copy Python optimization tools
cp /opt/optimization-engine/email_optimizer.py /opt/deliverability/email_optimizer.py
cp /opt/optimization-engine/list_unsubscribe_manager.py /opt/deliverability/list_unsubscribe_manager.py
cp /opt/optimization-engine/engagement_tracker.py /opt/deliverability/engagement_tracker.py
cp /opt/optimization-engine/warmup_engine.py /opt/deliverability/warmup_engine.py
cp /opt/optimization-engine/placement_optimizer.py /opt/deliverability/placement_optimizer.py

# Create wrapper for all optimization tools
cat > /opt/deliverability/optimize_send.py << 'PYEOF'
#!/usr/bin/env python3
\"\"\"Complete inbox placement optimization - single entry point.\"\"\"
import sys
sys.path.insert(0, '/opt/deliverability')
from placement_optimizer import PlacementOptimizer

optimizer = PlacementOptimizer()

if len(sys.argv) < 2:
    print('Usage: python3 optimize_send.py --subject \"...\" --text \"...\" --to email@example.com')
    sys.exit(1)

# Parse args
import argparse
ap = argparse.ArgumentParser()
ap.add_argument('--subject')
ap.add_argument('--text')
ap.add_argument('--html', default='')
ap.add_argument('--from', dest='frm', default='hello@nasrullahtanim.me')
ap.add_argument('--to')
ap.add_argument('--preflight', action='store_true')
ap.add_argument('--send', action='store_true')
ap.add_argument('--report', action='store_true')
args = ap.parse_args()

if args.report:
    print(json.dumps(optimizer.get_optimization_report(), indent=2, default=str))
elif args.preflight:
    print(json.dumps(optimizer.pre_flight_check(args.subject, args.text, args.html, args.frm), indent=2))
elif args.send:
    print(json.dumps(optimizer.send_optimized(args.frm, args.to, args.subject, args.text, args.html), indent=2))
PYEOF

chmod +x /opt/deliverability/optimize_send.py

# Start optimization engine
systemctl daemon-reload
systemctl enable optimization-engine.service
systemctl restart optimization-engine.service

echo '[OK] Optimization Engine deployed and running'
"
echo "=== Deployment Complete ==="
