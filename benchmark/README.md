# HTTP/2 Bomb Benchmark — Enhanced Attack Engine

## APEX v2 (beyond califio baseline)

| Enhancement | Effect |
|-------------|--------|
| **Multi-wave per TLS conn** | 2× streams without second handshake → 2× RAM/conn |
| **Efficiency profile** | 4096 headers × 256 streams → ~4× more conn at same wire |
| **Fire-and-forget (churn)** | Bomb → immediate disconnect → glibc retains RSS |
| **Hard-hold** | Drip every 10s → send_timeout reset, longer active downtime |
| **Pipelined sustain** | Background holders + churn waves concurrently |
| **Batched parallel bombs** | Fixes nginx 128-stream / 44-conn ceiling → 100/100 @ ~200 MB wire |

Core modules: `attack_config.py`, `h2_enhanced.py`, `cookie_bomb_enhanced.py`

## Package layout

| Module | Role |
|--------|------|
| `cli.py` | argparse + mode dispatch |
| `attack_runner.py` | Single-run nginx/cookie/IIS attacks |
| `campaigns/` | ramp, waves, multiprocess, apex, special, full campaign |
| `probe.py` | curl HTTP/2 probes + during-monitor thread |
| `persistence.py` | CSV + JSONL logging |
| `authorization.py` | scope + allowlist gates |
| `benchmark_runner.py` | Backward-compat entry + re-exports |

## Variants (`--variant`)

| Variant | Engine | Default port | Apex modes |
|---------|--------|--------------|------------|
| `nginx` | `h2_enhanced` | 443 | apex, apex_scaled, apex_mp |
| `pingora` | `h2_enhanced` | 443 | apex, apex_scaled, apex_mp |
| `httpd` | `cookie_bomb_enhanced` | 10080 | apex_cookie, apex_cookie_scaled, apex_cookie_mp |
| `envoy` | `cookie_bomb_enhanced` | 10000 | apex_cookie, apex_cookie_scaled, apex_cookie_mp |
| `microsoft-iis` / `iis` | `iis_apex_orchestrator.ps1` | 443 | apex_iis_mp (Windows) |

Registry: `variants.py` — POC path resolves `vendor/` with `poc/` fallback.

## Modes

| Mode | Description |
|------|-------------|
| `apex` | nginx/pingora: multi-wave + batched + hard_hold |
| `apex_scaled` | N conn, ~2 MB wire each (lab: 100/100 on 8 GiB cap) |
| `apex_mp` | One OS process per connection |
| `apex_cookie*` | httpd/envoy cookie-crumb apex |
| `apex_iis_mp` | PowerShell orchestrator (Windows) |
| `churn` | fire-and-forget + multi-wave |
| `optimized_oom` | 80 conn/cycle efficiency profile |
| `pipelined_sustain` | Holders + churn |
| `ramp`, `burst`, `cumulative`, `full_campaign` | Campaign strategies |

## Where to run

| Environment | Command |
|-------------|---------|
| **Proxmox ai-workstation** (recommended E2E) | From laptop: `../lab-replay/deploy_proxmox.sh smoke\|campaign` |
| **Local Docker lab** | `./lab-replay/replay.sh start 8g` then harness on same machine |
| **CI** | `./scripts/ci-lab-smoke.sh` (Docker nginx + burst 2 conn) |

Default harness target `127.0.0.1:8443` is **loopback on the machine running the harness** (lab VM or CI runner), not your laptop unless Docker lab runs locally.

```bash
# On lab VM or after lab-replay start (nginx @ 8443)
python3 benchmark/benchmark_runner.py --host 127.0.0.1 --port 8443 \
  --variant nginx --mode apex_scaled --connections 20

python3 benchmark/benchmark_runner.py --host 127.0.0.1 --port 10080 \
  --variant httpd --mode apex_cookie_scaled --connections 12

# Remote authorized target (explicit gate)
python3 benchmark/benchmark_runner.py --host TARGET --allow-remote \
  --variant nginx --mode apex_scaled --connections 50
```

Labs: `lab-replay/` (nginx :8443), `lab-replay-httpd/` (:10080), `lab-replay-envoy/` (:10000).

## Tunnel (`tunnel.py`)

| Mode | Description |
|------|-------------|
| `none` | Direct |
| `socks5` / `http` | `--proxy-url` (PySocks + curl) |
| `tor` | SOCKS5 127.0.0.1:9050 |
| `proxychains` | Subprocess wrapper |
| `cloudflared` / `ngrok` | Outbound proxy / ngrok API |

```bash
./bin/http2-bomb tunnel set --mode tor
python3 benchmark/benchmark_runner.py --host TARGET --tunnel-mode tor \
  --allow-remote --mode apex_scaled --connections 50
```

Profile: `config/tunnel.json` or `~/.config/http2-bomb/tunnel.json`

## Terminal CLI / MCP

```bash
./bin/http2-bomb menu
./bin/http2-bomb benchmark --host TARGET --mode apex_scaled --connections 20 --scope "Ticket-123" --yes
```

MCP tools: `probe_http2`, `run_http2_bomb_test`, `run_http2_bomb_benchmark` — require `authorization_confirmed` + scope.

## Logs

Runtime artifacts (gitignored locally):

| File | Format |
|------|--------|
| `logs/benchmark_results.csv` | Tabular summary |
| `logs/benchmark_runs.jsonl` | Full run + `attack_config` in extra |
| `logs/mp_*/worker_*.log` | Multiprocess workers |

Sample format: `logs/samples/*.example`

## CSV columns

- `connections_bomb_ok` — successful HPACK bombs
- `wire_mb` — wire upload
- `probe_worst_latency` — worst latency during run
- `server_down` / `oom_likely` — degradation indicators

JSONL `extra.attack_config` contains streams/headers/waves/hold_mode.
