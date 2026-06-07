"""Benchmark run datatypes."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
