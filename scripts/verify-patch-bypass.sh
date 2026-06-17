#!/usr/bin/env bash
# Smoke verification for patch-bypass labs (authorized local Docker only).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== Unit tests (no Docker) ==="
RUN_LAB=0 ./scripts/verify.sh

echo ""
echo "=== nginx config syntax (patched + hardened) ==="
for conf in lab-replay-patched/nginx.conf lab-replay-patched/nginx-hardened.conf; do
  docker run --rm -v "$ROOT/lab-replay-patched:/lab:ro" nginx:latest sh -c "
    cp /lab/$(basename \"$conf\") /tmp/nginx.conf
    sed -i 's|/etc/nginx/server.crt|/etc/ssl/certs/ssl-cert-snakeoil.pem|g' /tmp/nginx.conf
    sed -i 's|/etc/nginx/server.key|/etc/ssl/private/ssl-cert-snakeoil.pem|g' /tmp/nginx.conf
    nginx -t -c /tmp/nginx.conf
  "
  echo "OK: $conf"
done

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker not available — skipping live lab smoke"
  exit 0
fi

echo ""
echo "=== Build & start patched lab (8445) ==="
./lab-replay-patched/replay.sh build
./lab-replay-patched/replay.sh start

echo ""
echo "=== Build & start hardened lab (8446) ==="
VARIANT=hardened ./lab-replay-patched/replay.sh build
VARIANT=hardened ./lab-replay-patched/replay.sh start

echo ""
echo "=== Quick probe attacks (safe scale) ==="
python3 - <<'PY'
from attack_config import profile_patch_bypass_nginx, profile_patch_bypass_nginx_hardened
from attack_runner import run_attack

# Patched default: small conn count — expect bomb OK, modest RSS
r1 = run_attack("smoke_patched", "127.0.0.1", 8445, 20, cfg=profile_patch_bypass_nginx(999), variant="nginx")
print(f"patched: bomb={r1.connections_bomb_ok}/{r1.connections_requested} wire={r1.wire_mb:.2f}MB")

# Hardened: 99 hdr — expect early GOAWAY or limited allocation at low conn
r2 = run_attack("smoke_hardened", "127.0.0.1", 8446, 30, cfg=profile_patch_bypass_nginx_hardened(99), variant="nginx")
print(f"hardened: bomb={r2.connections_bomb_ok}/{r2.connections_requested} wire={r2.wire_mb:.2f}MB oom={r2.oom_likely}")
PY

echo ""
echo "=== PATCH-BYPASS SMOKE OK ==="
