# Multi-Variant Apex Rollout — Verification Summary

**Date:** 2026-06-05  
**Plugin:** `http2-bomb-mcp` benchmark harness

## Implementation complete

| Phase | Deliverable | Status |
|-------|-------------|--------|
| 1 | `variants.py`, `--variant`, dynamic POC path in `h2_enhanced` | Done |
| 2 | Pingora via `profile_apex_pingora()` + `lab-replay/pingora/replay.sh` | Done |
| 3 | `cookie_bomb_enhanced.py`, `single_cookie_worker.py`, cookie profiles | Done |
| 4 | MCP `variant` + cookie/IIS modes, README/SKILL | Done |
| 5 | `iis_apex_orchestrator.ps1`, `iis_apex_runner.py`, `apex_iis_mp` | Done |
| 6 | `lab-replay-httpd/`, `lab-replay-envoy/`, deploy + A/B scripts | Done |
| 7 | Lab runs + this summary | Done |

## Lab verification (Proxmox ai-workstation 192.168.2.116)

### nginx — `apex_scaled` (20 conn, port 8443)

| Metric | Result |
|--------|--------|
| connections_bomb_ok | **20/20** |
| wire_mb | **40.06** (~2 MB/conn) |
| probe_before | 200 |
| probe_after | 200 (degraded during hold) |
| run_id | dacca1b8 |

### httpd — `apex_cookie_scaled` (12 conn, port 10080)

| Metric | Result |
|--------|--------|
| connections_bomb_ok | **12/12** |
| wire_mb | 0.19 (cookie wire small; server merge is the payload) |
| probe_before/after | 200 / 200 |
| run_id | 01ea8a01 |
| container | `httpd-h2-lab-replay` (8 GiB cap) |

### envoy / pingora / IIS

- **envoy:** `lab-replay-envoy/replay.sh` + `run_ab_compare.sh` ready; deploy via `deploy_proxmox.sh`
- **pingora:** vendor `docker-compose` via `lab-replay/pingora/replay.sh`
- **IIS:** Linux stub prints PowerShell command; Windows execution via `iis_apex_orchestrator.ps1`

## CLI examples

```bash
python3 benchmark_runner.py --host 127.0.0.1 --port 8443 --variant nginx --mode apex_scaled --connections 100
python3 benchmark_runner.py --host 127.0.0.1 --port 10080 --variant httpd --mode apex_cookie_scaled --connections 44
python3 benchmark_runner.py --host 127.0.0.1 --port 10000 --variant envoy --mode apex_cookie_mp --connections 44
python3 benchmark_runner.py --host TARGET --variant iis --mode apex_iis_mp --iis-preset 8gb
```

## MCP

`run_http2_bomb_benchmark(host, variant=..., mode=..., port=..., authorization_confirmed=true, scope_description=...)`

Modes per variant: `list_http2_bomb_variants`

---

## E2E re-verification (2026-06-05, agent run)

See full log: `lab-replay/logs/E2E_TEST_20260605.md`

| Area | Result |
|------|--------|
| CLI + py_compile + MCP import | OK |
| Tunnel test 127.0.0.1:443 | Expected fail (connection refused) |
| Tunnel test 1.1.1.1:443 direct | OK, ~12 ms |
| ai-workstation 192.168.2.116 | **Unreachable** (no route / down) — benchmark skipped |
| Win11 VM 101 | No stable ping; nmap: host up, **no open** 80/443/3389/5985 |
| IIS `apex_iis_mp` Linux stub | OK (prints PS orchestrator); bomb_ok=0 (no IIS listener) |
| Proxmox SSH/API | Not attempted (no credentials in env; 192.168.2.1:22 refused) |

