#!/usr/bin/env bash
# Deploy APEX-Ngin2dos to Proxmox ai-workstation and run the nginx lab there.
#
# Architecture (correct):
#   Laptop  →  ssh/rsync  →  ai-workstation (192.168.2.116)
#                              ├── Docker nginx lab (127.0.0.1:8443)
#                              ├── PoC / benchmark_runner (same VM, NOT your laptop)
#                              └── RSS/probe monitoring via docker exec (parallel, not confounded)
#
# Do NOT probe 127.0.0.1:8443 from your laptop unless Docker lab runs locally.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

REMOTE="${REMOTE:-danii@192.168.2.116}"
REMOTE_DIR="${REMOTE_DIR:-APEX-Ngin2dos}"
REMOTE_RSYNC="${REMOTE}:~/${REMOTE_DIR}/"
MEM="${MEM:-8g}"
PORT="${PORT:-8443}"
MODE="${MODE:-smoke}"   # smoke | campaign | deploy-only

usage() {
  cat <<EOF
Usage: $0 [MODE]

Deploy repo to Proxmox ai-workstation and run lab tests ON THE REMOTE VM.

Modes:
  smoke        Build/start nginx lab + probe + 5-conn attack with RSS log (default)
  campaign     Full run_proxmox_campaign.sh (15 + 50 conn, sustained)
  deploy-only  Rsync + venv + lab start, no attack

Env:
  REMOTE=$REMOTE
  REMOTE_DIR=$REMOTE_DIR
  MEM=$MEM  PORT=$PORT
  REPO_ROOT=$REPO_ROOT

Examples:
  $0 smoke
  REMOTE=danii@192.168.2.116 MODE=campaign $0
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

[[ -n "${1:-}" ]] && MODE="$1"

echo "=== Deploy APEX-Ngin2dos → $REMOTE:\$HOME/$REMOTE_DIR ==="
echo "    Repo: $REPO_ROOT"

ssh "$REMOTE" "mkdir -p ~/$REMOTE_DIR/{lab-replay/logs,benchmark/logs}"

rsync -az --delete \
  --exclude '.venv' --exclude '__pycache__' --exclude '.git' \
  "$REPO_ROOT/lab-replay/" "${REMOTE_RSYNC}lab-replay/"

rsync -az \
  --exclude '__pycache__' \
  "$REPO_ROOT/benchmark/" "${REMOTE_RSYNC}benchmark/"

rsync -az \
  "$REPO_ROOT/vendor/" "${REMOTE_RSYNC}vendor/"

rsync -az \
  "$REPO_ROOT/requirements.txt" "$REPO_ROOT/pyproject.toml" \
  "${REMOTE_RSYNC}"

echo "=== Remote setup: venv + Docker lab (mem=$MEM port=$PORT) ==="
ssh "$REMOTE" bash -s <<REMOTE_SETUP
set -euo pipefail
cd "\$HOME/$REMOTE_DIR"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
. .venv/bin/activate
pip install -q -r requirements.txt

cd lab-replay
chmod +x replay.sh run_proxmox_campaign.sh run_ab_compare.sh
./replay.sh stop 2>/dev/null || true
./replay.sh build
MEM=$MEM PORT=$PORT ./replay.sh start $MEM
REMOTE_SETUP

case "$MODE" in
  deploy-only)
    echo "=== Deploy complete. Probe from remote: ==="
    echo "  ssh $REMOTE 'cd ~/$REMOTE_DIR/lab-replay && ./replay.sh probe'"
    ;;
  campaign)
    echo "=== Full Proxmox campaign on remote ==="
    LOG="lab_replay_proxmox_$(date +%Y%m%d_%H%M%S).log"
    ssh "$REMOTE" "cd ~/$REMOTE_DIR/lab-replay && ./run_proxmox_campaign.sh" \
      | tee "$REPO_ROOT/lab-replay/logs/$LOG"
    echo "Local log: $REPO_ROOT/lab-replay/logs/$LOG"
    ;;
  smoke|*)
    echo "=== Smoke test on remote (probe + 5-conn attack + RSS) ==="
    LOG="proxmox_smoke_$(date +%Y%m%d_%H%M%S).log"
    ssh "$REMOTE" bash -s <<REMOTE_SMOKE | tee "$REPO_ROOT/lab-replay/logs/$LOG"
set -euo pipefail
cd ~/$REMOTE_DIR/lab-replay
. ../.venv/bin/activate

echo "--- probe ---"
./replay.sh probe

echo "--- attack N=5 (hold 20s) with RSS samples ---"
./replay.sh attack 5 20

echo "--- post-attack probe ---"
./replay.sh probe
./replay.sh rss

echo "=== SMOKE OK ==="
REMOTE_SMOKE
    echo "Log: $REPO_ROOT/lab-replay/logs/$LOG"
    ;;
esac

echo ""
echo "Done. Remote shell: ssh $REMOTE"
echo "Remote RSS:        ssh $REMOTE 'cd ~/$REMOTE_DIR/lab-replay && ./replay.sh rss'"
