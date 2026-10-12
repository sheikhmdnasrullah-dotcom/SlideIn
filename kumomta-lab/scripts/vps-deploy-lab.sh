#!/usr/bin/env bash
# Deploy the (hermetic) KumoMTA lab to the VPS. Does NOT touch Mailcow or port 25.
# The lab uses distinct ports (2587/8029/8467/9090/3000/9093/3100) and forces all
# outbound to the in-network sink MX, so it never reaches the real Internet.
#
# Usage: VPS_PASS=xxx ./vps-deploy-lab.sh [root@host]
set -euo pipefail
VPS="${1:-root@169.58.207.75}"
PASS="${VPS_PASS:?set VPS_PASS env var}"
LOCAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"      # kumomta-lab/
REPO_ROOT="$(cd "$LOCAL_ROOT/.." && pwd)"            # email-master raw/
REMOTE="/opt"

echo "==> copying kumomta-lab, kumomta, sink-mx to $VPS:$REMOTE =="
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$VPS" "mkdir -p $REMOTE/kumomta-lab"
sshpass -p "$PASS" scp -o StrictHostKeyChecking=no -r \
  "$LOCAL_ROOT/compose" "$LOCAL_ROOT/policy" "$LOCAL_ROOT/dkim" \
  "$LOCAL_ROOT/monitoring" "$LOCAL_ROOT/secrets" "$LOCAL_ROOT/scripts" "$LOCAL_ROOT/tests" \
  "$VPS:$REMOTE/kumomta-lab/"
sshpass -p "$PASS" scp -o StrictHostKeyChecking=no -r \
  "$REPO_ROOT/kumomta" "$REPO_ROOT/sink-mx" "$VPS:$REMOTE/"

echo "==> building + starting lab on VPS (Rust build of KumoMTA may take several minutes) =="
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$VPS" \
  "cd $REMOTE/kumomta-lab/compose && nohup docker compose up -d --build > $REMOTE/kumomta-lab/build.log 2>&1 &"
echo "==> build started in background. Monitor: ssh $VPS 'tail -f $REMOTE/kumomta-lab/build.log'"
