#!/usr/bin/env bash
# Proxmox lab campaign — logged until blog-like OOM (nginx 1.24, 8g cap)
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
CONTAINER=nginx-h2-lab-replay
PORT="${PORT:-8443}"
POC="${POC:-$HOME/http2-bomb-lab/poc/nginx/hpack_bomb.py}"
PY="${PY:-python3}"
LOG_DIR="$DIR/logs"
CSV="$LOG_DIR/proxmox_lab_timeseries.csv"
mkdir -p "$LOG_DIR"

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
  curl -sS -m 10 -o /dev/null -w "%{http_code} %{time_total}" \
    -k --http2 "https://127.0.0.1:${PORT}/" 2>&1 | tr '\n' ' ' || echo "000 timeout"
}

log_sample() {
  local phase="$1" run_id="$2" conn="$3"
  local ts rss cmem p
  ts=$(date -Iseconds)
  rss=$(worker_rss_mib)
  cmem=$(container_mem)
  p=$(probe)
  if [[ ! -f "$CSV" ]]; then
    echo "timestamp,run_id,phase,connections,rss_mib,container_mem,probe_code,probe_time" > "$CSV"
  fi
  echo "$ts,$run_id,$phase,$conn,$rss,\"$cmem\",$(echo $p | awk '{print $1}'),$(echo $p | awk '{print $2}')" >> "$CSV"
  echo "[$ts] phase=$phase conn=$conn RSS=${rss}MiB container=$cmem probe=$p"
}

run_id=$(date +%Y%m%d_%H%M%S)
RUN_LOG="$LOG_DIR/campaign_${run_id}.log"

echo "=== PROXMOX LAB CAMPAIGN $run_id ===" | tee "$RUN_LOG"
echo "Host: $(hostname) | Container: $CONTAINER | Port: $PORT" | tee -a "$RUN_LOG"
docker exec "$CONTAINER" nginx -v 2>&1 | tee -a "$RUN_LOG"

# Ensure container healthy
if ! docker ps --filter name="$CONTAINER" --filter status=running -q | grep -q .; then
  echo "Container not running — start with: ./replay.sh start 8g" | tee -a "$RUN_LOG"
  exit 1
fi

for N in 15 50; do
  echo "" | tee -a "$RUN_LOG"
  echo "========== RUN attack N=$N hold=120s ==========" | tee -a "$RUN_LOG"
  log_sample "before" "$run_id" "$N" | tee -a "$RUN_LOG"

  T0=$(date +%s)
  $PY "$POC" --host 127.0.0.1 --port "$PORT" -n "$N" --hold 120 --drip-interval 30 -v \
    > "$LOG_DIR/poc_${run_id}_n${N}.log" 2>&1 &
  PID=$!

  while kill -0 "$PID" 2>/dev/null; do
    log_sample "during" "$run_id" "$N" | tee -a "$RUN_LOG"
    sleep 5
  done
  wait "$PID" || true

  EL=$(( $(date +%s) - T0 ))
  log_sample "after" "$run_id" "$N" | tee -a "$RUN_LOG"
  echo "Elapsed: ${EL}s | PoC log: $LOG_DIR/poc_${run_id}_n${N}.log" | tee -a "$RUN_LOG"

  # Success criteria for blog-like lab
  RSS=$(worker_rss_mib)
  CMEM=$(container_mem)
  if [[ "$N" == "50" ]] && echo "$CMEM" | grep -qE "8(\.| )?GiB|7\.[5-9]"; then
    echo ">>> SUCCESS: 50-conn hit ~8GiB container cap <<<" | tee -a "$RUN_LOG"
  fi

  echo "Restarting container for next run..." | tee -a "$RUN_LOG"
  docker restart "$CONTAINER" >/dev/null
  sleep 8
  log_sample "recovered" "$run_id" "$N" | tee -a "$RUN_LOG"
done

# Sustained 3x50 to test glibc retention + sustained pressure
echo "" | tee -a "$RUN_LOG"
echo "========== SUSTAINED 3x50 (no restart between) ==========" | tee -a "$RUN_LOG"
for i in 1 2 3; do
  echo "--- sustained round $i/3 ---" | tee -a "$RUN_LOG"
  log_sample "sustained_before" "$run_id" "50" | tee -a "$RUN_LOG"
  $PY "$POC" --host 127.0.0.1 --port "$PORT" -n 50 --hold 60 --drip-interval 20 \
    >> "$LOG_DIR/poc_${run_id}_sustained.log" 2>&1 || true
  log_sample "sustained_after" "$run_id" "50" | tee -a "$RUN_LOG"
  sleep 5
done

echo "" | tee -a "$RUN_LOG"
echo "=== CAMPAIGN DONE ===" | tee -a "$RUN_LOG"
echo "CSV: $CSV" | tee -a "$RUN_LOG"
echo "Run log: $RUN_LOG" | tee -a "$RUN_LOG"

# Summary
echo "" | tee -a "$RUN_LOG"
echo "=== SUMMARY ===" | tee -a "$RUN_LOG"
grep "SUCCESS\|probe=000\|RSS=" "$RUN_LOG" | tail -30 | tee -a "$RUN_LOG"
