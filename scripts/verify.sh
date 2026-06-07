#!/usr/bin/env bash
# Full local verification: unit tests, lint, compile, optional Docker lab smoke.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

RUN_LAB="${RUN_LAB:-1}"

echo "=== pytest ==="
python3 -m venv .venv 2>/dev/null || true
. .venv/bin/activate
pip install -q -r requirements-dev.txt
pytest -q

echo "=== ruff ==="
ruff check tests/ benchmark/authorization.py http2_bomb_mcp.py http2_bomb_cli.py

echo "=== py_compile ==="
python3 -m py_compile http2_bomb_mcp.py http2_bomb_cli.py
python3 -m py_compile benchmark/*.py benchmark/campaigns/*.py

echo "=== CLI ==="
./bin/http2-bomb --help >/dev/null

if [[ "$RUN_LAB" == "1" ]] && command -v docker >/dev/null 2>&1; then
  echo "=== lab-replay smoke ==="
  ./scripts/ci-lab-smoke.sh
else
  echo "=== lab-replay smoke skipped (RUN_LAB=$RUN_LAB or no docker) ==="
fi

echo ""
echo "=== VERIFY OK ==="
