---
name: http2-bomb
description: Run authorized HTTP/2 HPACK-bomb DoS checks via http2-bomb MCP (califio PoCs). Use for nginx/httpd/envoy/pingora/IIS hardening tests on owned or contracted targets.
---

# HTTP/2 Bomb MCP

## When to use

- Kunde oder eigenes System auf **HTTP/2 HPACK amplification + window stall** (MADBugs/http2-bomb) prüfen
- Nach Patch: `probe` / `safe` zur Regression
- Vor vollem PoC: `estimate_http2_bomb_impact` und `list_http2_bomb_variants`

## Workflow

1. `probe_http2` — TLS + ALPN `h2`, kein Angriff
2. `list_http2_bomb_variants` — richtige Variante wählen (nginx vs httpd cookie vs envoy …)
3. Optional: `allowed_targets.json` aus `.example` kopieren und Hosts eintragen
4. `run_http2_bomb_test` mit `authorization_confirmed=true` und `scope_description` (Ticket/Kunde)
5. Profil starten mit `safe`, nur bei Bedarf `moderate` / `aggressive`

## Variant mapping

| Stack | variant |
|-------|---------|
| nginx | nginx |
| Apache httpd mod_http2 | httpd |
| Envoy | envoy |
| Pingora | pingora |
| IIS | microsoft-iis (Windows) |

## Enhanced benchmark (v2)

Module: `variants.py`, `attack_config.py`, `h2_enhanced.py`, `cookie_bomb_enhanced.py`

| Stack | variant | Apex benchmark modes |
|-------|---------|----------------------|
| nginx / Pingora | `nginx`, `pingora` | `apex`, `apex_scaled`, `apex_mp` |
| httpd / Envoy | `httpd`, `envoy` | `apex_cookie`, `apex_cookie_scaled`, `apex_cookie_mp` |
| IIS | `microsoft-iis` | `apex_iis_mp` (Windows PowerShell) |

```bash
python3 benchmark/benchmark_runner.py --host TARGET --variant nginx --mode apex_scaled --connections 100 --port 443
python3 benchmark/benchmark_runner.py --host 127.0.0.1 --variant httpd --mode apex_cookie_scaled --connections 44 --port 10080
```

MCP: `run_http2_bomb_benchmark` mit `variant=` und `mode=` (siehe `list_http2_bomb_variants` für Modi pro Variante)

## Tunnel

Module: `benchmark/tunnel.py`, `benchmark/tunnel_runner.py`

```bash
./bin/http2-bomb tunnel set --mode tor
python3 benchmark/benchmark_runner.py --host TARGET --tunnel-mode socks5 \
  --proxy-url socks5://127.0.0.1:1080 --mode apex --connections 55
```

MCP: `configure_http2_bomb_tunnel`, optional `tunnel_mode`/`proxy_url` on `probe_http2`, `run_http2_bomb_test`, `run_http2_bomb_benchmark`.

## Terminal CLI

```bash
./bin/http2-bomb menu
./bin/http2-bomb probe --host 127.0.0.1
```

## Legal

Nur Systeme mit **schriftlicher Erlaubnis**. Kein Scanning fremder Infrastruktur.
