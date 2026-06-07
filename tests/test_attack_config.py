from __future__ import annotations

from attack_config import (
    H2_MAX_STREAMS_PER_CONN,
    profile_apex,
    profile_apex_scaled,
    profile_churn,
)


def test_profile_apex_respects_stream_budget() -> None:
    cfg = profile_apex()
    assert cfg.total_streams_per_conn() <= H2_MAX_STREAMS_PER_CONN


def test_profile_apex_scaled_scales_with_connections() -> None:
    small = profile_apex_scaled(10)
    large = profile_apex_scaled(100)
    assert large.bomb_batch_size >= small.bomb_batch_size


def test_profile_churn_uses_fire_and_forget() -> None:
    cfg = profile_churn()
    assert cfg.hold_mode == "fire_and_forget"
    assert cfg.bomb_mode == "batched"
