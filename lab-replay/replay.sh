#!/usr/bin/env bash
# 1:1 Lab replay vs califio blog — nginx in Docker, memory cap, single worker
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN="$(cd "$DIR/.." && pwd)"
POC="$PLUGIN/vendor/califio-publications/MADBugs/http2-bomb/nginx/hpack_bomb.py"
PY="${PY:-$PLUGIN/.venv/bin/python3}"
CONTAINER=nginx-h2-lab-replay
IMAGE=nginx-h2-lab-replay
PORT="${PORT:-8443}"
MEM="${MEM:-8g}"
LOG_DIR="$DIR/logs"
mkdir -p "$LOG_DIR"

usage() {
  cat <<EOF
Usage: $0 <command> [args]

Commands:
  build              Build lab image (nginx 1.24)
  start [MEM]        Start container (default MEM=8g, e.g. 4g 8g 16g)
  stop               Remove container
  version            Show nginx version in container
  rss                Worker RSS (MiB)
  probe              curl HTTP/2 check
  attack <N>         Run N-connection PoC (default 15)
  replay             Full replay: attack1,5,15,50 with RSS logging
  compare            Same as replay + summary table

Env: PORT=8443 MEM=8g
EOF
}

worker_rss_mib() {
  docker exec "$CONTAINER" bash -c '
    total=0
    for p in $(pgrep -f "nginx: worker" 2>/dev/null); do
      r=$(awk "/VmRSS/ {print \$2}" /proc/$p/status 2>/dev/null)
      total=$((total + r))
    done
    echo $((total / 1024))
  ' 2>/dev/null || echo "0"
}

container_mem() {
  docker stats "$CONTAINER" --no-stream --format "{{.MemUsage}}" 2>/dev/null || echo "n/a"
}

probe() {
  curl -sS -m 5 -o /dev/null -w "code=%{http_code} time=%{time_total}s\n" \
    -k --http2 "https://127.0.0.1:${PORT}/" 2>&1 || echo "FAIL"
}

run_attack() {
  local n="${1:-15}"
  local hold="${2:-30}"
  local tag="attack${n}_mem${MEM}"
  local log="$LOG_DIR/${tag}_$(date +%Y%m%d_%H%M%S).log"
  echo "=== $tag hold=${hold}s ===" | tee "$log"
  echo "RSS before: $(worker_rss_mib) MiB | container: $(container_mem)" | tee -a "$log"
  probe | tee -a "$log"
  local t0
  t0=$(date +%s)
  "$PY" "$POC" --host 127.0.0.1 --port "$PORT" -n "$n" --hold "$hold" --drip-interval 50 -v 2>&1 | tee -a "$log" &
  local pid=$!
  while kill -0 "$pid" 2>/dev/null; do
    echo "[$(date +%H:%M:%S)] RSS=$(worker_rss_mib) MiB container=$(container_mem) probe=$(probe | tr '\n' ' ')" | tee -a "$log"
    sleep 5
  done
  wait "$pid" || true
  local elapsed=$(( $(date +%s) - t0 ))
  echo "RSS after: $(worker_rss_mib) MiB | elapsed=${elapsed}s" | tee -a "$log"
  probe | tee -a "$log"
  echo "Log: $log"
}

case "${1:-}" in
  build)
    docker build -t "$IMAGE" "$DIR"
    ;;
  start)
    MEM="${2:-$MEM}"
    docker rm -f "$CONTAINER" 2>/dev/null || true
    echo "Starting $CONTAINER memory=$MEM port=$PORT"
    docker run -d --name "$CONTAINER" --memory="$MEM" -p "${PORT}:443" "$IMAGE"
    sleep 2
    docker exec "$CONTAINER" nginx -v
    probe
    ;;
  stop)
    docker rm -f "$CONTAINER" 2>/dev/null || true
    ;;
  version)
    docker exec "$CONTAINER" nginx -v
    ;;
  rss)
    echo "Worker RSS: $(worker_rss_mib) MiB"
    echo "Container: $(container_mem)"
    ;;
  probe)
    probe
    ;;
  attack)
    run_attack "${2:-15}" "${3:-30}"
    ;;
  replay|compare)
    SUMMARY="$LOG_DIR/replay_summary_$(date +%Y%m%d_%H%M%S).txt"
    echo "Lab replay MEM=$MEM PORT=$PORT" | tee "$SUMMARY"
    echo "Blog target nginx: ~32GB in ~45s with 50 conn (16GB cap lab)" | tee -a "$SUMMARY"
    echo "" | tee -a "$SUMMARY"
    for n in 1 5 15 50; do
      run_attack "$n" 15
      sleep 10
      docker restart "$CONTAINER" >/dev/null 2>&1 || true
      sleep 3
    done | tee -a "$SUMMARY"
    echo "" | tee -a "$SUMMARY"
    echo "Summary written: $SUMMARY"
    echo "All logs: $LOG_DIR"
    ;;
  *)
    usage
    ;;
esac
