#!/usr/bin/env bash
# httpd mod_http2 cookie-bomb lab — port 10080
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN="$(cd "$DIR/.." && pwd)"
CONTAINER=httpd-h2-lab-replay
IMAGE=httpd-h2-lab-replay
PORT="${PORT:-10080}"
MEM="${MEM:-8g}"
PY="${PY:-$PLUGIN/.venv/bin/python3}"
BENCH="$PLUGIN/benchmark/benchmark_runner.py"

usage() {
  echo "Usage: $0 {build|start|stop|probe|apex_cookie_scaled [N]}"
}

probe() {
  curl -sS -m 5 -o /dev/null -w "code=%{http_code} time=%{time_total}s\n" \
    -k --http2 "https://127.0.0.1:${PORT}/" 2>&1 || echo FAIL
}

case "${1:-}" in
  build) docker build -t "$IMAGE" "$DIR" ;;
  start)
    MEM="${2:-$MEM}"
    docker rm -f "$CONTAINER" 2>/dev/null || true
    docker run -d --name "$CONTAINER" --memory="$MEM" -p "${PORT}:10080" "$IMAGE"
    sleep 2
    probe
    ;;
  stop) docker rm -f "$CONTAINER" 2>/dev/null || true ;;
  probe) probe ;;
  apex_cookie_scaled)
    N="${2:-44}"
    "$PY" "$BENCH" --host 127.0.0.1 --port "$PORT" --variant httpd \
      --mode apex_cookie_scaled --connections "$N"
    ;;
  *) usage ;;
esac
