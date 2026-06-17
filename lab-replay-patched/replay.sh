#!/usr/bin/env bash
# Patched nginx lab replay — default (8445) and hardened max_headers=100 (8446).
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"

variant="${VARIANT:-default}"
case "$variant" in
  default)
    CONTAINER=nginx-h2-patched-lab
    IMAGE=nginx-h2-patched-lab
    DOCKERFILE=Dockerfile
    PORT="${PORT:-8445}"
    ;;
  hardened)
    CONTAINER=nginx-h2-hardened-lab
    IMAGE=nginx-h2-hardened-lab
    DOCKERFILE=Dockerfile.hardened
    PORT="${PORT:-8446}"
    ;;
  *)
    echo "Unknown VARIANT=$variant (use default|hardened)" >&2
    exit 1
    ;;
esac

MEM="${MEM:-8g}"

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

usage() {
  cat <<EOF
Usage: VARIANT=default|$0 {build|start|stop|rss|probe}

  default lab  — nginx:latest (max_headers default 1000) @ port 8445
  hardened lab — max_headers 100 @ port 8446

Examples:
  $0 build && $0 start
  VARIANT=hardened $0 build && VARIANT=hardened $0 start
EOF
}

cmd="${1:-}"
case "$cmd" in
  build)
    docker build -f "$DIR/$DOCKERFILE" -t "$IMAGE" "$DIR"
    ;;
  start)
    MEM="${2:-$MEM}"
    docker rm -f "$CONTAINER" 2>/dev/null || true
    docker run -d --name "$CONTAINER" --memory="$MEM" -p "${PORT}:443" "$IMAGE"
    sleep 2
    curl -sk --http2 -o /dev/null -w "variant=${variant} code=%{http_code}\n" "https://127.0.0.1:${PORT}/"
    docker exec "$CONTAINER" nginx -v
    ;;
  stop)
    docker rm -f "$CONTAINER" 2>/dev/null || true
    ;;
  rss)
    echo "variant=${variant} RSS=$(worker_rss_mib) MiB | $(docker stats "$CONTAINER" --no-stream --format '{{.MemUsage}}' 2>/dev/null)"
    ;;
  probe)
    curl -skI --http2 "https://127.0.0.1:${PORT}/" | head -5
    ;;
  *)
    usage
    exit 1
    ;;
esac
