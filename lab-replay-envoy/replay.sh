#!/usr/bin/env bash
# Envoy H2 cookie-bomb lab — port 10000
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN="$(cd "$DIR/.." && pwd)"
CONTAINER=envoy-h2-lab-replay
IMAGE=envoy-h2-lab-replay
PORT="${PORT:-10000}"
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
    docker run -d --name "$CONTAINER" --memory="$MEM" -p "${PORT}:10000" "$IMAGE"
    sleep 3
    probe
    ;;
  stop) docker rm -f "$CONTAINER" 2>/dev/null || true ;;
  probe) probe ;;
  apex_cookie_scaled)
    N="${2:-44}"
    "$PY" "$BENCH" --host 127.0.0.1 --port "$PORT" --variant envoy \
      --mode apex_cookie_scaled --connections "$N"
    ;;
  *) usage ;;
esac
