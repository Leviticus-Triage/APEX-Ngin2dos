# APEX Ngin2dos

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![HTTP/2](https://img.shields.io/badge/HTTP%2F2-HPACK%20bomb-red.svg)](https://github.com/califio/publications/tree/main/MADBugs/http2-bomb)
[![Research](https://img.shields.io/badge/type-offensive%20security%20research-purple.svg)](#)
[![Authorized Use Only](https://img.shields.io/badge/use-authorized%20targets%20only-critical.svg)](#legal--authorized-use)

**Multi-variant HTTP/2 HPACK amplification benchmark harness** — extends [califio/publications MADBugs/http2-bomb](https://github.com/califio/publications/tree/main/MADBugs/http2-bomb) with the **APEX v2** attack engine, lab replay environments, tunnel routing, MCP + CLI interfaces, and reproducible OOM/degradation metrics.

Targets: **nginx**, **Pingora**, **Apache httpd**, **Envoy**, **Microsoft IIS**.

> **Research context:** HTTP/2 header compression (HPACK) can amplify small client uploads into large server-side allocations. This repository documents our lab-verified enhancements beyond the original PoCs — batched parallel bombs, multi-wave connections, cookie-crumb variants, and Windows IIS orchestration — for **authorized** defensive validation and patch verification.

---

## Table of contents

- [Key results](#key-results)
- [Architecture](#architecture)
- [Quick start](#quick-start)
- [APEX modes](#apex-modes)
- [Interfaces](#interfaces-mcp--cli)
- [Tunnel routing](#tunnel-routing)
- [Lab replay](#lab-replay)
- [Hardening](#hardening)
- [Documentation](#documentation)
- [Upstream & disclosure](#upstream--disclosure)
- [Legal & authorized use](#legal--authorized-use)

---

## Key results

Lab-verified on Proxmox (8 GiB Docker caps unless noted):

| Variant | Mode | Result | Notes |
|---------|------|--------|-------|
| **nginx** | `apex_scaled` | **100/100** bomb OK @ ~200 MB wire | Fixed 44-conn ceiling via batched bombs + 128-stream budget |
| **nginx** | `apex_scaled` | **20/20** @ 40 MB wire | run_id `dacca1b8`, port 8443 |
| **nginx** | Proxmox campaign | **8 GiB container filled** | 50 conn, worker RSS ~8170 MiB |
| **httpd** | `apex_cookie_scaled` | **12/12** bomb OK | port 10080, run_id `01ea8a01` |
| **Win11 IIS** | `apex_iis_mp` | **Service degradation** | 5 processes @ preset 8gb; HTTPS timeout post-attack, self-recovery |

See [`docs/LAB_RESULTS.md`](docs/LAB_RESULTS.md) for full metrics, A/B comparisons (califio baseline vs APEX v2), and E2E reports.

**Notion project page:** [HTTP/2 Bomb — MCP Plugin & OOM Benchmark](https://app.notion.com/p/37530537269d8196a477e358073e8627)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  MCP (FastMCP)  │  CLI (bin/http2-bomb)  │  benchmark_runner│
└────────────────────────────┬────────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
        h2_enhanced   cookie_bomb_enhanced   iis_apex_orchestrator.ps1
        (nginx/pingora)  (httpd/envoy)       (Windows IIS)
              │              │              │
              └──────────────┼──────────────┘
                             ▼
              attack_config.py + variants.py + tunnel.py
                             ▼
              vendor/califio-publications/MADBugs/http2-bomb/
```

Full detail: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

---

## Quick start

```bash
git clone https://github.com/Leviticus-Triage/APEX-Ngin2dos.git
cd APEX-Ngin2dos
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# Unit tests (no nginx/apache required — runs on your machine)
pytest -q

# Real HTTP/2 lab validation → Proxmox ai-workstation (NOT localhost on your laptop)
chmod +x lab-replay/deploy_proxmox.sh
./lab-replay/deploy_proxmox.sh smoke          # deploy + 5-conn smoke on remote
./lab-replay/deploy_proxmox.sh campaign       # full OOM campaign on remote
```

**Where things run**

| Step | Where | Target |
|------|--------|--------|
| `pytest` | Your laptop | No server needed |
| `deploy_proxmox.sh` | rsync → **192.168.2.116** | Docker nginx @ `127.0.0.1:8443` *on the VM* |
| RSS / probe monitoring | Same VM, parallel loop | Does not run from your laptop |

Do **not** run `./bin/http2-bomb probe --host 127.0.0.1 --port 8443` on your laptop unless you started `lab-replay/replay.sh start` locally. Default `127.0.0.1:8443` in `benchmark_runner.py` means **lab loopback on the machine running the harness** (typically ai-workstation after deploy).

Optional local Docker lab (same VM layout, on your machine):

```bash
./lab-replay/replay.sh start 8g
./lab-replay/replay.sh probe
./lab-replay/replay.sh attack 5
```

### Verification tiers

| Tier | Command | Needs |
|------|---------|-------|
| Unit | `pytest -q` | Python venv only |
| Full local | `./scripts/verify.sh` | + Docker for lab smoke |
| Proxmox E2E | `./lab-replay/deploy_proxmox.sh smoke` | SSH to ai-workstation |
| CI | GitHub Actions `test` + `lab-smoke` jobs | automatic on push |

**Authorization required** for any attack profile — see [Legal](#legal--authorized-use).

---

## APEX modes

| Mode | Variants | Description |
|------|----------|-------------|
| `apex` | nginx, pingora | Multi-wave (64×2) + batched bombs + hard_hold |
| `apex_scaled` | nginx, pingora | N connections, ~2 MB wire each (~200 MB @100) |
| `apex_mp` | nginx, pingora | One OS process per connection |
| `apex_cookie` | httpd, envoy | Cookie-crumb HPACK apex |
| `apex_cookie_scaled` | httpd, envoy | Scaled cookie connections (batched) |
| `apex_cookie_mp` | httpd, envoy | Multiprocess cookie workers |
| `apex_iis_mp` | IIS (Windows) | PowerShell multiprocess orchestrator |
| `churn` | nginx | fire-and-forget + multi-wave allocation churn |
| `optimized_oom` | nginx | Efficiency profile for single-client OOM cycles |

Registry: `benchmark/variants.py` — `--variant nginx|pingora|httpd|envoy|iis`

---

## Interfaces (MCP + CLI)

### Cursor MCP

Add to `~/.cursor/mcp.json`:

```json
"http2-bomb": {
  "command": "/path/to/APEX-Ngin2dos/.venv/bin/python3",
  "args": ["/path/to/APEX-Ngin2dos/http2_bomb_mcp.py"],
  "description": "APEX HTTP/2 HPACK bomb — authorized targets only",
  "timeout": 900
}
```

Tools: `probe_http2`, `run_http2_bomb_test`, `run_http2_bomb_benchmark`, `configure_http2_bomb_tunnel`, `list_http2_bomb_variants`, `get_http2_bomb_disclosure`.

### Standalone CLI

Works in any terminal (Codex, Gemini CLI, Claude Code, SSH):

```bash
./bin/http2-bomb variants
./bin/http2-bomb run --host TARGET --profile safe --scope "Ticket-123" --yes
./bin/http2-bomb benchmark --host TARGET --mode apex_scaled --connections 100 --yes
./bin/http2-bomb tunnel set --mode tor
./bin/http2-bomb logs --last 10
```

Settings: copy `config/cli_settings.example.json` → `config/cli_settings.json`.

---

## Tunnel routing

Route traffic through SOCKS5, HTTP proxy, Tor, proxychains, ngrok, or cloudflared:

```bash
cp config/tunnel.example.json config/tunnel.json
./bin/http2-bomb tunnel set --mode socks5 --proxy-url socks5://127.0.0.1:1080
./bin/http2-bomb tunnel test --host staging.example.com

python3 benchmark/benchmark_runner.py --host TARGET --mode apex_scaled \
  --tunnel-mode tor --connections 50
```

Requires `PySocks` for Python socket routing. See [`benchmark/README.md`](benchmark/README.md).

---

## Lab replay

| Directory | Stack | Port | Command |
|-----------|-------|------|---------|
| `lab-replay/` | nginx 1.24 | 8443 | `./lab-replay/replay.sh start 8g` |
| `lab-replay-httpd/` | Apache httpd | 10080 | `./lab-replay-httpd/replay.sh start 8g` |
| `lab-replay-envoy/` | Envoy | 10000 | `./lab-replay-envoy/replay.sh start 8g` |
| `lab-replay/pingora/` | Pingora (vendor compose) | 8444 | `./lab-replay/pingora/replay.sh start` |

Proxmox deploy: `lab-replay/deploy_proxmox.sh`, `lab-replay-httpd/deploy_proxmox.sh`.

Windows IIS lab: `benchmark/setup_win11_iis_lab.ps1` + `benchmark/iis_apex_orchestrator.ps1`.

---

## Hardening

Sample nginx mitigation configs for vulnerable stacks (pre-1.29.8):

- [`hardening/README.md`](hardening/README.md)
- `hardening/nginx-1.29.8-post-upgrade.conf` — `http2_max_headers 100`
- `hardening/nginx-http2-bomb-mrx3k1.conf` — defense-in-depth for nginx 1.24

---

## Documentation

| Document | Content |
|----------|---------|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Components, data flow, variant dispatch |
| [`docs/LAB_RESULTS.md`](docs/LAB_RESULTS.md) | Verified metrics, A/B, Proxmox, Win11 IIS |
| [`docs/DISCLOSURE.md`](docs/DISCLOSURE.md) | CVE/fix status per stack |
| [`docs/NOTION.md`](docs/NOTION.md) | Link + sync with Notion research page |
| [`docs/OPTIMIZATION.md`](docs/OPTIMIZATION.md) | Release roadmap (P0–P3) |
| [`RELEASE_NOTES_v1.0.1.md`](RELEASE_NOTES_v1.0.1.md) | v1.0.1 changelog |
| [`benchmark/README.md`](benchmark/README.md) | Harness modes, CSV/JSONL logging |
| [`SECURITY.md`](SECURITY.md) | Responsible use policy |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | How to contribute lab data |

---

## Upstream & disclosure

PoCs originate from **[califio/publications](https://github.com/califio/publications/tree/main/MADBugs/http2-bomb)** (included under `vendor/`). Update upstream:

```bash
cd vendor/califio-publications && git pull
```

| Stack | Fix status |
|-------|------------|
| nginx | Fixed **1.29.8** — `max_headers` / `http2_max_headers` |
| Apache httpd | Fixed mod_http2 **v2.0.41** — cookie accounting |
| IIS, Envoy, Pingora | Reported May 2026 — status unknown |

Details: [`docs/DISCLOSURE.md`](docs/DISCLOSURE.md)

---

## Legal & authorized use

**This software is for authorized security research and defensive validation only.**

- Test **only** systems you own or have **written permission** to assess.
- Every attack invocation requires explicit scope documentation (`--scope`, `scope_description`, or ticket reference).
- Unauthorized use against third-party infrastructure may violate computer crime laws.
- The authors assume **no liability** for misuse.

By using this repository you agree to these terms. See [`SECURITY.md`](SECURITY.md).

---

## Citation

If you reference this work:

```bibtex
@software{apex_ngin2dos_2026,
  title  = {APEX Ngin2dos: Multi-Variant HTTP/2 HPACK Benchmark Harness},
  author = {Leviticus-Triage},
  year   = {2026},
  url    = {https://github.com/Leviticus-Triage/APEX-Ngin2dos}
}
```

Built on [califio/publications HTTP/2 Bomb](https://github.com/califio/publications/tree/main/MADBugs/http2-bomb).
