#!/usr/bin/env bash
# CI smoke: Docker nginx lab + probe + minimal benchmark run (localhost on runner).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LAB="$ROOT/lab-replay"
PORT="${PORT:-8443}"
MEM="${MEM:-4g}"
CONNECTIONS="${CONNECTIONS:-2}"
HOLD="${HOLD:-8}"

cd "$ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not available — skip lab smoke"
  exit 0
fi

python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt

echo "=== Build nginx lab image ==="
"$LAB/replay.sh" build

echo "=== Start lab (mem=$MEM port=$PORT) ==="
"$LAB/replay.sh" stop 2>/dev/null || true
MEM="$MEM" PORT="$PORT" "$LAB/replay.sh" start "$MEM"

cleanup() {
  "$LAB/replay.sh" stop 2>/dev/null || true
}
trap cleanup EXIT

echo "=== Probe ==="
"$LAB/replay.sh" probe | grep -q 'code=200'

echo "=== Benchmark smoke (burst $CONNECTIONS conn, hold=${HOLD}s) ==="
OUT=$(python3 benchmark/benchmark_runner.py \
  --host 127.0.0.1 \
  --port "$PORT" \
  --mode burst \
  --connections "$CONNECTIONS" \
  --hold "$HOLD" \
  --drip 5 2>&1)
echo "$OUT"
python3 -c "import json, re, sys; m=re.search(r'\{.*\}', sys.stdin.read(), re.S); assert m, 'no JSON'; d=json.loads(m.group()); assert d['connections_bomb_ok']>=1, d; assert str($PORT) in d['target']" <<< "$OUT"

echo "=== Post-run probe ==="
"$LAB/replay.sh" probe | grep -q 'code=200'

echo "=== CI LAB SMOKE OK ==="
