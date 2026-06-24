# Apache Probability Upgrade Pack

Goal: increase acceptance confidence by adding three policy-aligned metrics to the existing report.

## Why these three metrics

1. **M1 — Reproducibility threshold**
   - Identify the first connection level where impact starts (`server_down`, `oom_likely`, or high probe latency).
   - This reduces "single lucky run" objections.

2. **M2 — Efficiency slope (impact vs wire)**
   - Report `est_server_mb / wire_mb` across 200/400/800/1200 connections.
   - Shows disproportionate resource consumption relative to traffic volume.

3. **M3 — Limit compliance proof**
   - Keep counted header estimate per stream at or below `LimitRequestFields=100`.
   - Demonstrates impact while nominal limits are respected.

These align with the httpd security model requirement that resource consumption should be bounded by configured request limits.

## Run it

```bash
cd /home/danii/APEX-Ngin2dos
chmod +x ./scripts/apache-probability-upgrade.sh
./lab-replay-httpd/replay.sh start 8g
./scripts/apache-probability-upgrade.sh
```

Optional custom matrix:

```bash
CONNS="300 600 900 1200" ./scripts/apache-probability-upgrade.sh
```

## Outputs

Script writes to:

- `lab-replay/logs/apache_probability_upgrade_<timestamp>/environment.txt`
- `.../empty_control_44.json`
- `.../fat_200.json`, `fat_400.json`, `fat_800.json`, `fat_1200.json`
- `.../probability_upgrade_summary.json`
- `.../probability_upgrade_summary.md`

## If the vendor requests additional evidence

- Quote the **first degradation threshold** (M1).
- Quote median **est/wire ratio** (M2).
- Quote **counted_headers_per_stream_est <= 100** from the fat runs (M3).
- Attach `probability_upgrade_summary.json` only when asked; do not volunteer unsolicited mail.
