# Patched nginx lab (≥ 1.29.8)

Docker labs for reproducing HTTP/2 HPACK amplification on **patched** nginx builds.

| Variant | Image | Port | Config |
|---------|-------|------|--------|
| `default` | `nginx:latest` (1.31.x) | **8445** | Default `max_headers` = 1000 |
| `hardened` | same base + `max_headers 100` | **8446** | Recommended mitigation |

## Quick start

```bash
# Default patched stack (bypass with 999 headers/stream)
./lab-replay-patched/replay.sh build
./lab-replay-patched/replay.sh start

# Hardened stack (verify mitigation — 99 headers/stream max)
VARIANT=hardened ./lab-replay-patched/replay.sh build
VARIANT=hardened ./lab-replay-patched/replay.sh start
```

## Smoke test (authorized lab only)

```bash
./scripts/verify-patch-bypass.sh
```

Full campaign:

```bash
python3 benchmark/patch_bypass_runner.py --target nginx
VARIANT=hardened python3 benchmark/patch_bypass_runner.py --target nginx-hardened
```

## Directive note

nginx **1.29.8+** uses the directive **`max_headers`**, not `http2_max_headers`. The latter is rejected at config parse time on current nginx builds.

See `docs/PATCH_BYPASS_REPRODUCTION.md` for full reproduction steps and results.
