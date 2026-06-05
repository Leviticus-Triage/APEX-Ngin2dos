#!/usr/bin/env bash
# A/B benchmark: califio baseline vs apex v2 — RSS + probe timeseries
set -uo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
BENCH="$DIR/.."
POC="${POC:-$BENCH/poc/nginx/hpack_bomb.py}"
PY="${PY:-python3}"
CONTAINER=nginx-h2-lab-replay
PORT="${PORT:-8443}"
HOST="${HOST:-127.0.0.1}"
CONN="${CONN:-50}"
LOG_DIR="$DIR/logs"
mkdir -p "$LOG_DIR"

RUN_ID=$(date +%Y%m%d_%H%M%S)
COMPARE_LOG="$LOG_DIR/compare_${RUN_ID}.log"
CSV="$LOG_DIR/compare_${RUN_ID}.csv"

worker_rss_mib() {
  docker exec "$CONTAINER" bash -c '
    t=0
    for p in $(pgrep -f "nginx: worker" 2>/dev/null); do
      r=$(awk "/VmRSS/ {print \$2}" /proc/$p/status 2>/dev/null)
      t=$((t + r))
    done
    echo $((t / 1024))
  ' 2>/dev/null || echo "0"
}

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
  local ts rss cm p code lat
  ts=$(date -Iseconds)
  rss=$(worker_rss_mib)
  cm=$(container_mem_mib)
  p=$(probe)
  code=$(echo "$p" | awk '{print $1}')
  lat=$(echo "$p" | awk '{print $2}')
  [[ "$code" == "curl:"* ]] && code="000"
  echo "$ts,$label,$phase,$rss,$cm,$code,$lat" >> "$CSV"
  echo "[$ts] $label/$phase RSS=${rss}MiB container=${cm}MiB probe=$p" | tee -a "$COMPARE_LOG"
}

run_poc() {
  local label="$1" n="$2" streams="$3" headers="$4" hold="$5" drip="$6"
  shift 6
  local extra=("$@")

  echo "" | tee -a "$COMPARE_LOG"
  echo "========== $label: n=$n streams=$streams headers=$headers hold=${hold}s ==========" | tee -a "$COMPARE_LOG"

  docker restart "$CONTAINER" >/dev/null
  sleep 8
  log_row "$label" "baseline"

  local t0 t1
  t0=$(date +%s)
  $PY "$BENCH/benchmark_runner.py" --host "$HOST" --port "$PORT" --mode burst \
    --connections "$n" 2>/dev/null &
  local runner_pid=$!

  # Monitor every 5s while runner active
  while kill -0 "$runner_pid" 2>/dev/null; do
    log_row "$label" "during"
    sleep 5
  done
  wait "$runner_pid" || true
  t1=$(date +%s)

  log_row "$label" "after"
  sleep 5
  log_row "$label" "recovery+5s"
  sleep 25
  log_row "$label" "recovery+30s"

  echo "ELAPSED_${label}=$((t1 - t0))s" | tee -a "$COMPARE_LOG"
}

run_apex() {
  local label="apex_v2"
  echo "" | tee -a "$COMPARE_LOG"
  echo "========== $label: apex mode conn=$CONN ==========" | tee -a "$COMPARE_LOG"

  docker restart "$CONTAINER" >/dev/null
  sleep 8
  log_row "$label" "baseline"

  local t0 t1
  t0=$(date +%s)
  $PY "$BENCH/benchmark_runner.py" --host "$HOST" --port "$PORT" --mode apex \
    --connections "$CONN" 2>&1 | tee -a "$COMPARE_LOG" &
  local runner_pid=$!

  while kill -0 "$runner_pid" 2>/dev/null; do
    log_row "$label" "during"
    sleep 5
  done
  wait "$runner_pid" || true
  t1=$(date +%s)

  log_row "$label" "after"
  sleep 5
  log_row "$label" "recovery+5s"
  sleep 25
  log_row "$label" "recovery+30s"

  echo "ELAPSED_${label}=$((t1 - t0))s" | tee -a "$COMPARE_LOG"
}

run_califio_direct() {
  local label="califio_baseline"
  echo "" | tee -a "$COMPARE_LOG"
  echo "========== $label: direct PoC n=$CONN 128x32000 hold=120 drip=30 ==========" | tee -a "$COMPARE_LOG"

  docker restart "$CONTAINER" >/dev/null
  sleep 8
  log_row "$label" "baseline"

  local t0 t1
  t0=$(date +%s)
  $PY "$POC" --host "$HOST" --port "$PORT" -n "$CONN" --streams 128 --headers 32000 \
    --hold 120 --drip-interval 30 -v > "$LOG_DIR/poc_califio_${RUN_ID}.log" 2>&1 &
  local poc_pid=$!

  while kill -0 "$poc_pid" 2>/dev/null; do
    log_row "$label" "during"
    sleep 5
  done
  wait "$poc_pid" || true
  t1=$(date +%s)

  log_row "$label" "after"
  sleep 5
  log_row "$label" "recovery+5s"
  sleep 25
  log_row "$label" "recovery+30s"

  echo "ELAPSED_${label}=$((t1 - t0))s" | tee -a "$COMPARE_LOG"
  # Extract wire from poc log
  if grep -q "Total wire uploaded:" "$LOG_DIR/poc_califio_${RUN_ID}.log" 2>/dev/null; then
    grep "Total wire uploaded:" "$LOG_DIR/poc_califio_${RUN_ID}.log" | tee -a "$COMPARE_LOG"
  fi
}

echo "timestamp,run,phase,rss_mib,container_mib,probe_code,probe_latency" > "$CSV"
echo "=== A/B COMPARE RUN $RUN_ID ===" | tee "$COMPARE_LOG"
docker exec "$CONTAINER" nginx -v 2>&1 | tee -a "$COMPARE_LOG"

run_califio_direct
run_apex

echo "" | tee -a "$COMPARE_LOG"
echo "=== SUMMARY $RUN_ID ===" | tee -a "$COMPARE_LOG"
echo "CSV: $CSV" | tee -a "$COMPARE_LOG"
echo "LOG: $COMPARE_LOG" | tee -a "$COMPARE_LOG"

# Python summary
$PY - "$CSV" <<'PY'
import csv, sys
from pathlib import Path

csv_path = Path(sys.argv[1])
rows = list(csv.DictReader(csv_path.open()))

def stats(label):
    sub = [r for r in rows if r["run"] == label]
    during = [r for r in sub if r["phase"] == "during"]
    rss = [int(r["rss_mib"]) for r in during if r["rss_mib"].isdigit()]
    cm = [int(r["container_mib"]) for r in during if r["container_mib"].isdigit()]
    timeouts = sum(1 for r in during if r["probe_code"] in ("000", "curl:"))
    lats = [float(r["probe_latency"]) for r in during if r["probe_latency"] and r["probe_latency"].replace(".","").isdigit()]
    rec = [r for r in sub if r["phase"].startswith("recovery")]
    rec_ok = sum(1 for r in rec if r["probe_code"] == "200")
    return {
        "peak_rss": max(rss) if rss else 0,
        "peak_container": max(cm) if cm else 0,
        "timeout_samples": timeouts,
        "during_samples": len(during),
        "max_latency": max(lats) if lats else 0,
        "recovery_ok": rec_ok,
    }

for label in ("califio_baseline", "apex_v2"):
    if any(r["run"] == label for r in rows):
        s = stats(label)
        print(f"{label}: peak_rss={s['peak_rss']}MiB peak_container={s['peak_container']}MiB "
              f"timeouts={s['timeout_samples']}/{s['during_samples']} max_lat={s['max_latency']:.3f}s "
              f"recovery_probes_ok={s['recovery_ok']}")
PY
