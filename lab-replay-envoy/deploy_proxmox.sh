#!/usr/bin/env bash
# Deploy Envoy H2 lab to Proxmox ai-workstation and run apex_cookie_scaled
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REMOTE="${REMOTE:-danii@192.168.2.116}"
REMOTE_DIR="${REMOTE_DIR:-~/http2-bomb-lab-envoy}"
LOCAL_PLUGIN="${LOCAL_PLUGIN:-$REPO_ROOT}"
PORT="${PORT:-10000}"
MEM="${MEM:-8g}"

echo "=== Deploy Envoy lab to $REMOTE ==="
ssh "$REMOTE" "mkdir -p $REMOTE_DIR/lab-replay-envoy $REMOTE_DIR/benchmark"

rsync -az "$LOCAL_PLUGIN/lab-replay-envoy/" "$REMOTE:$REMOTE_DIR/lab-replay-envoy/"
rsync -az "$LOCAL_PLUGIN/benchmark/" "$REMOTE:$REMOTE_DIR/benchmark/"
rsync -az "$LOCAL_PLUGIN/vendor/" "$REMOTE:$REMOTE_DIR/vendor/"

ssh "$REMOTE" bash -s <<REMOTE_EOF
set -euo pipefail
cd ~/http2-bomb-lab-envoy/lab-replay-envoy
chmod +x replay.sh
./replay.sh stop 2>/dev/null || true
./replay.sh build
./replay.sh start $MEM
REMOTE_EOF

echo "=== apex_cookie_scaled on lab (port $PORT) ==="
ssh "$REMOTE" "cd ~/http2-bomb-lab-envoy/lab-replay-envoy && python3 ../benchmark/benchmark_runner.py \
  --host 127.0.0.1 --port $PORT --variant envoy --mode apex_cookie_scaled --connections 44" \
  || echo "Benchmark run finished (check remote logs)"

echo "Done."
