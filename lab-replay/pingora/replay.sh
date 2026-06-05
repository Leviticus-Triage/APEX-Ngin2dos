#!/usr/bin/env bash
# Pingora H2 lab stub — uses vendor docker-compose from califio PoC
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN="$(cd "$DIR/.." && pwd)"
VENDOR="$PLUGIN/vendor/califio-publications/MADBugs/http2-bomb/pingora"
CONTAINER=pingora-h2-lab-replay
PORT="${PORT:-8444}"
MEM="${MEM:-8g}"
PY="${PY:-$PLUGIN/.venv/bin/python3}"
BENCH="$PLUGIN/benchmark/benchmark_runner.py"

usage() {
  echo "Usage: $0 {build|start|stop|probe|apex_scaled [N]}"
  echo "Requires docker compose in vendor pingora directory."
}

probe() {
  curl -sS -m 5 -o /dev/null -w "code=%{http_code} time=%{time_total}s\n" \
    -k --http2 "https://127.0.0.1:${PORT}/" 2>&1 || echo FAIL
}

case "${1:-}" in
  build)
    (cd "$VENDOR" && docker compose build)
    ;;
  start)
    (cd "$VENDOR" && docker compose up -d)
    sleep 3
    probe
    ;;
  stop)
    (cd "$VENDOR" && docker compose down) 2>/dev/null || true
    ;;
  probe) probe ;;
  apex_scaled)
    N="${2:-50}"
    "$PY" "$BENCH" --host 127.0.0.1 --port "$PORT" --variant pingora \
      --mode apex_scaled --connections "$N"
    ;;
  *) usage ;;
esac
