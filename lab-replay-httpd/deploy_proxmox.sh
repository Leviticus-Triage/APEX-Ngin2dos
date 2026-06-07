#!/usr/bin/env bash
# Deploy httpd H2 lab to Proxmox ai-workstation and run apex_cookie_scaled
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REMOTE="${REMOTE:-danii@192.168.2.116}"
REMOTE_DIR="${REMOTE_DIR:-~/http2-bomb-lab-httpd}"
LOCAL_PLUGIN="${LOCAL_PLUGIN:-$REPO_ROOT}"
CONTAINER=httpd-h2-lab-replay
PORT="${PORT:-10080}"
MEM="${MEM:-8g}"

echo "=== Deploy httpd lab to $REMOTE ==="
ssh "$REMOTE" "mkdir -p $REMOTE_DIR/lab-replay-httpd $REMOTE_DIR/benchmark"

rsync -az "$LOCAL_PLUGIN/lab-replay-httpd/" "$REMOTE:$REMOTE_DIR/lab-replay-httpd/"
rsync -az "$LOCAL_PLUGIN/benchmark/" "$REMOTE:$REMOTE_DIR/benchmark/"
rsync -az "$LOCAL_PLUGIN/vendor/" "$REMOTE:$REMOTE_DIR/vendor/"

ssh "$REMOTE" bash -s <<REMOTE_EOF
set -euo pipefail
cd ~/http2-bomb-lab-httpd/lab-replay-httpd
chmod +x replay.sh
./replay.sh stop 2>/dev/null || true
./replay.sh build
./replay.sh start $MEM
REMOTE_EOF

echo "=== apex_cookie_scaled on lab (port $PORT) ==="
ssh "$REMOTE" "cd ~/http2-bomb-lab-httpd/lab-replay-httpd && python3 ../benchmark/benchmark_runner.py \
  --host 127.0.0.1 --port $PORT --variant httpd --mode apex_cookie_scaled --connections 44" \
  || echo "Benchmark run finished (check remote logs)"

echo "Done. ssh $REMOTE 'docker stats $CONTAINER'"
