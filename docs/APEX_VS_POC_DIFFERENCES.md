# APEX v2 vs. califio PoC — What is actually different and why it matters

This document exists because people keep asking "wasn't that already in the PoC?"

## Short answer
The PoC demonstrates a **memory amplification primitive**.
APEX demonstrates an **operationally effective client** that can deliver that primitive at scale against real server constraints (128-stream budget, GIL, write contention, timeouts, connection lifecycle).

If you only tested the PoC, you tested the *best case for the defender*.

## Concrete, logged differences

1. **Connection establishment & delivery fairness**
   - PoC: sequential or naive parallel → many conns stall or get dropped before full bomb. In 50-conn runs often only ~20 clean deliveries.
   - APEX: `conn_stagger_sec` + `bomb_mode=batched` (8-20 at a time) + `bomb_batch_gap_sec` → 50/50 and 88-100/100 clean bomb_ok rates.

2. **Per-connection throughput (streams without exceeding server limits)**
   - PoC: usually one wave.
   - APEX: `waves_per_conn=2` (e.g. 64+64) to reach the 128-stream ceiling without sending more than the server allows in one go.

3. **Sustained pressure (the "quiet" part)**
   - PoC: standard drip.
   - APEX: `hold_mode=hard_hold` — active WINDOW_UPDATE + drain loop that survives longer against `send_timeout` and RSTs. This is what turns "a spike" into "minutes of downtime".

4. **Cookie-crumb variant for httpd**
   - The original PoC had a cookie path; APEX added batching, scaling logic, and tuned `refs`/`streams` for the specific mod_http2 merge amplification (~4000:1+ in lab on 2.4.62).

5. **Patch verification & bypass testing built-in**
   - Profiles: `profile_patch_bypass_nginx`, `profile_patch_bypass_httpd_hpack`, etc.
   - Lab images for vulnerable vs. current/patched.
   - Before/after numbers are first-class (see pro repro report).

6. **Observability & defensibility**
   - Every run produces `RunResult` → CSV + JSONL with exact config, probes before/during/after, RSS samples, bomb_ok count, wire bytes, errors.
   - Reproducible session scripts + env snapshots.

## Numbers that illustrate the gap (lab, 8 GiB cap)

From June 2026 sessions:

- 12 conn, vuln nginx:
  - APEX scaled: 12/12, ~24 MB wire, server OOM / down
  - califio: many GOAWAYs during hold, shorter effective pressure

- 30-50 conn:
  - califio: partial success (conn drops)
  - APEX scaled: near 100% delivery → deterministic OOM

- Mitigated nginx (stream cap + buffers):
  - 20 conn APEX: 20/20 delivered, but probe recovers (200), no OOM. Duration short.

- httpd cookie 12 conn:
  - vuln 2.4.62: 0.19 MB wire → GiB class
  - 2.4.68: fast GOAWAY, tiny RSS

## Why this matters for real assessments

- A defender who only runs the raw PoC may conclude "our rate limiting / timeouts saved us".
- A realistic adversary uses the techniques in APEX (batching, staggering, hold modes, scaling) and gets the published numbers.

The harness makes both the attack surface **and** the effect of mitigations measurable and repeatable.

## Reproduce the comparison yourself

See `lab-replay/professional_repro_20260617.sh` and `benchmark/benchmark_runner.py --mode apex_scaled` vs the direct `hpack_bomb.py`.

All data is in `lab-replay/logs/...` + `benchmark/logs/benchmark_runs.jsonl`.
