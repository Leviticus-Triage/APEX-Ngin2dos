# HTTP/2 Bomb Benchmark — Enhanced Attack Engine

## Neu (v2) — über califio hinaus

| Erweiterung | Wirkung |
|-------------|---------|
| **Multi-Wave pro TLS-Conn** | 2× Streams ohne zweites Handshake → doppelte RAM/Conn |
| **Efficiency-Profile** | 4096 headers × 256 streams → ~4× mehr Conn bei gleichem Wire |
| **Fire-and-forget (churn)** | Bomb → sofort disconnect → glibc behält RSS (nginx README) |
| **Hard-hold** | Drip alle 10s → send_timeout Reset, längere aktive Downtime |
| **Pipelined sustain** | Background-Holder + Churn-Wellen gleichzeitig |

Module: `attack_config.py`, `h2_enhanced.py`

## Varianten (`--variant`)

| Variant | Engine | Default port | Apex modes |
|---------|--------|--------------|------------|
| `nginx` | `h2_enhanced` | 443 | apex, apex_scaled, apex_mp |
| `pingora` | `h2_enhanced` (pingora POC) | 443 | apex, apex_scaled, apex_mp |
| `httpd` | `cookie_bomb_enhanced` | 10080 | apex_cookie, apex_cookie_scaled, apex_cookie_mp |
| `envoy` | `cookie_bomb_enhanced` | 10000 | apex_cookie, apex_cookie_scaled, apex_cookie_mp |
| `microsoft-iis` / `iis` | `iis_apex_orchestrator.ps1` | 443 | apex_iis_mp (Windows) |

Registry: `variants.py` — POC-Pfad mit `vendor/` → `poc/` Fallback.

## Modi

| Mode | Beschreibung |
|------|--------------|
| `apex` | nginx/pingora: multi-wave + batched + hard_hold |
| `apex_scaled` | 100+ conn, ~200 MB wire (nginx lab: 100/100) |
| `apex_mp` | Ein Prozess pro Verbindung |
| `apex_cookie` | httpd/envoy cookie-crumb apex |
| `apex_cookie_scaled` | Skalierte Cookie-Verbindungen (batched) |
| `apex_cookie_mp` | Cookie-Worker multiprocess |
| `apex_iis_mp` | PowerShell-Orchestrator (Windows) |
| `churn` | fire-and-forget + multi-wave |
| `optimized_oom` | 80 conn/cycle, 25 Zyklen |
| `pipelined_sustain` | Holder + Churn |
| `ramp`, `burst`, `cumulative`, `full_campaign` | wie bisher |

```bash
cd ~/.cursor/plugins/local/http2-bomb-mcp/benchmark
../.venv/bin/python3 benchmark_runner.py --host TARGET --variant nginx --mode apex_scaled --connections 100
../.venv/bin/python3 benchmark_runner.py --host 127.0.0.1 --port 10080 --variant httpd --mode apex_cookie_scaled --connections 44
../.venv/bin/python3 benchmark_runner.py --host 127.0.0.1 --port 8443 --variant nginx --mode apex_scaled --connections 20  # nginx lab
```

Labs: `lab-replay/` (nginx), `lab-replay-httpd/` (10080), `lab-replay-envoy/` (10000).

## Tunnel (`benchmark/tunnel.py`)

| Mode | Beschreibung |
|------|--------------|
| `none` | Direkt |
| `socks5` / `http` | `--proxy-url` für Python (PySocks) + curl |
| `tor` | SOCKS5 127.0.0.1:9050 |
| `proxychains` | Subprocess-Wrapper |
| `cloudflared` / `ngrok` | Outbound-Proxy / ngrok API |

```bash
../bin/http2-bomb tunnel set --mode tor
../.venv/bin/python3 benchmark_runner.py --host TARGET --tunnel-mode tor --mode apex_scaled --connections 50
```

Profil: `config/tunnel.json` oder `~/.config/http2-bomb/tunnel.json`

## Terminal CLI

```bash
./bin/http2-bomb menu
./bin/http2-bomb benchmark --host 127.0.0.1 --port 8443 --mode apex_scaled --connections 20 --yes
```

## Logs

| Datei | Format |
|-------|--------|
| `logs/benchmark_results.csv` | Tabellarisch |
| `logs/benchmark_runs.jsonl` | inkl. `attack_config` in extra |
| `logs/mp_*/worker_*.log` | Multiprocess mit hold_mode/waves |

## CSV-Spalten

- `connections_bomb_ok` — erfolgreiche HPACK-Bombs
- `wire_mb` — Wire-Upload
- `probe_worst_latency` — schlechteste Latenz während Run
- `server_down` / `oom_likely` — Degradation-Indikatoren

JSONL `extra.attack_config` enthält streams/headers/waves/hold_mode.
