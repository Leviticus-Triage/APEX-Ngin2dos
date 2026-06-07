# Architecture

## Overview

APEX Ngin2dos wraps upstream [califio HTTP/2 bomb PoCs](https://github.com/califio/publications/tree/main/MADBugs/http2-bomb) with a unified benchmark harness, enhanced attack engines, and multiple operator interfaces.

## Layer model

### 1. Operator interfaces

| Interface | Entry | Use case |
|-----------|-------|----------|
| **MCP** | `http2_bomb_mcp.py` | Cursor IDE, agent automation |
| **CLI** | `bin/http2-bomb` → `http2_bomb_cli.py` | Terminal, CI, non-IDE workflows |
| **Direct** | `benchmark/benchmark_runner.py` | Scripting, lab campaigns |

All paths enforce authorization (`authorization_confirmed`, `--scope`, `--yes` on CLI).

### 2. Benchmark harness

Modular layout under `benchmark/`:

| Module | Role |
|--------|------|
| `cli.py` | argparse + mode dispatch |
| `attack_runner.py` | Single-run nginx/cookie/IIS attacks |
| `campaigns/` | ramp, waves, multiprocess, apex, special, full campaign |
| `probe.py` | curl HTTP/2 probes + during-monitor thread |
| `persistence.py` | CSV + JSONL logging |
| `benchmark_runner.py` | Backward-compat entry + re-exports |

- Parses `--variant`, `--mode`, `--tunnel-*`
- Runs TLS/HTTP2 probes before, during, after attack
- Persists CSV + JSONL to `benchmark/logs/`
- Dispatches to variant-specific engine

### 3. Variant registry

`benchmark/variants.py` defines:

| ID | Kind | Engine | Default port |
|----|------|--------|--------------|
| nginx | nginx | h2_enhanced | 443 |
| pingora | nginx | h2_enhanced | 443 |
| httpd | cookie | cookie_bomb_enhanced | 10080 |
| envoy | cookie | cookie_bomb_enhanced | 10000 |
| iis | iis | iis_apex_orchestrator.ps1 | 443 |

POC paths resolve `vendor/...` with `poc/` fallback.

### 4. Attack engines

**h2_enhanced.py** (nginx/Pingora):

- Lazy-imports upstream `hpack_bomb` after `configure_h2_variant()`
- Multi-wave bombs per connection
- Batched parallel bombing (fixes nginx 128-stream / 44-conn ceiling)
- Hold modes: drip, hard_hold, fire_and_forget

**cookie_bomb_enhanced.py** (httpd/Envoy):

- Cookie-crumb HPACK blocks from vendor PoCs
- Same batched/hold semantics as nginx APEX

**iis_apex_orchestrator.ps1** (Windows):

- Spawns N parallel `iis_hpack_dos.py` processes
- Presets: 8gb (5 proc), 32gb, 64gb, 96gb

### 5. Configuration

`benchmark/attack_config.py` — frozen dataclass profiles:

- `profile_apex()`, `profile_apex_scaled(n)`
- `profile_apex_cookie_*()`, `profile_apex_cookie_scaled()`
- `IisApexPreset` for Windows orchestrator

### 6. Tunnel layer

`benchmark/tunnel.py` + `tunnel_runner.py`:

- PySocks for Python TLS sockets
- proxychains wrapper for subprocess PoCs
- Profiles in `config/tunnel.json`

### 7. Lab layer

Docker-based replay environments with memory caps for OOM verification. Proxmox deploy scripts rsync harness to ai-workstation.

## Data flow

```
Operator → benchmark_runner → set_poc_path(variant)
                           → engine.establish / bomb / hold
                           → probe_server (curl --http2)
                           → RunResult → CSV/JSONL
```

Multiprocess modes spawn `single_conn_worker.py` or `single_cookie_worker.py` per connection.

## Key design decisions

1. **No vendor patches** — upstream PoCs updated via `git pull` in `vendor/`
2. **128-stream budget** — `H2_MAX_STREAMS_PER_CONN = 128` in attack_config
3. **Batched bombs** — batch_size 12, 2s gap — avoids client SSL write stalls
4. **Linux IIS stub** — prints PowerShell command when not on win32
