# Lab Results

Consolidated verification data from Proxmox ai-workstation and Win11 IIS lab (June 2026).

Full raw logs: `lab-replay/logs/`

## nginx — apex_scaled

### Design target (100 connections)

| Parameter | Value |
|-----------|-------|
| streams × headers | 128 × 16384 |
| wire per conn | ~2 MB |
| total wire @100 | ~200 MB |
| bomb mode | batched (8–20 per batch) |

**Lab verified:** 100/100 bomb OK, ~200 MB wire, peak RSS ~8.16 GiB (8 GiB Docker cap) — see `lab-replay/logs/scaled_20260604_213145.csv`, `apex_mp_fix_20260604_220048.csv`.

### Documented run (20 connections)

| Metric | Value |
|--------|-------|
| connections_bomb_ok | **20/20** |
| wire_mb | **40.06** |
| probe_before / after | 200 / 200 |
| run_id | dacca1b8 |
| target | 127.0.0.1:8443 |

### A/B: califio baseline vs APEX v2 (50 conn)

| Run | bomb_ok | wire_mb | peak RSS | server_down |
|-----|---------|---------|----------|-------------|
| califio direct PoC | 50/50 | ~195 MB | ~8.16 GiB | yes |
| apex_v2 (pre-fix) | 44/50 | ~99 MB | ~2.4 GiB | partial |
| apex_scaled (fixed) | 100/100 | ~200 MB | ~8.16 GiB | yes |

Source: `lab-replay/logs/ab_20260604_210143.csv`, `fairness_20260604_211755.csv`

### Proxmox OOM campaign (50 conn)

- Worker RSS: **8170 MiB**
- Container: **8 GiB FULL**
- Probe timeouts during hold
- Sustained 3×50 without container restart (glibc RSS retention)

Source: `lab-replay/logs/PROXMOX_CAMPAIGN_SUMMARY.md`

### Authorized production note (anonymized)

On a single public IPv4 address, observed ceiling ~**31** concurrent full bombs; no persistent OOM from one client. Lab Docker/Proxmox runs prove vulnerability at scale; production impact is limited by source IP count and nginx worker model. Details remain in private lab notes — do not commit customer hostnames or IPs.

---

## httpd — apex_cookie_scaled

| Metric | Value |
|--------|-------|
| connections_bomb_ok | **12/12** |
| wire_mb | 0.19 |
| container | httpd-h2-lab-replay, 8 GiB |
| port | 10080 |
| run_id | 01ea8a01 |

Cookie merge amplification is server-side; wire bytes are small by design.

---

## Win11 IIS — apex_iis_mp

| Phase | Result |
|-------|--------|
| VM | Proxmox 101 @ 192.168.2.104 |
| Python | 3.12.10 @ C:\http2-bomb-mcp\Python312 |
| Pre-attack HTTPS | HTTP/2 **200** (~52 ms) |
| Attack | orchestrator preset **8gb** (5 processes) |
| Post-attack | External probe **timeout** (8s); guest agent timeout |
| Recovery | Self-recovery without reboot; HTTPS 200 restored |

Source: `lab-replay/logs/WIN11_IIS_LAB_20260605.md`

---

## E2E harness verification (2026-06-05)

| Check | Result |
|-------|--------|
| CLI + py_compile | OK |
| MCP import | OK |
| Tunnel test 1.1.1.1:443 | OK ~12 ms |

Source: `lab-replay/logs/E2E_TEST_20260605.md`

---

## Reproducing

```bash
# nginx lab
./lab-replay/replay.sh start 8g
python3 benchmark/benchmark_runner.py --host 127.0.0.1 --port 8443 \
  --variant nginx --mode apex_scaled --connections 20

# httpd lab
./lab-replay-httpd/replay.sh start 8g
python3 benchmark/benchmark_runner.py --host 127.0.0.1 --port 10080 \
  --variant httpd --mode apex_cookie_scaled --connections 12
```

Always run on isolated lab targets with explicit authorization.
