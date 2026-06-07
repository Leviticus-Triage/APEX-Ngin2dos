#!/usr/bin/env python3
"""
HTTP/2 Bomb benchmark harness — logs every run, tries multiple strategies until OOM/degradation.

Implementation split across:
  paths.py, models.py, probe.py, persistence.py, attack_runner.py, campaigns/, cli.py
"""
from __future__ import annotations

from attack_runner import run_attack, run_cookie_attack, run_iis_apex_mp
from campaigns import (
    run_apex,
    run_apex_cookie,
    run_apex_cookie_multiprocess,
    run_apex_cookie_scaled,
    run_apex_multiprocess,
    run_apex_scaled,
    run_churn,
    run_cookie_multiprocess,
    run_cumulative_waves,
    run_full_campaign,
    run_multiprocess,
    run_optimized_single_client_oom,
    run_pipelined_sustain,
    run_ramp,
    run_sustained,
)
from cli import main
from models import RunResult, ServerProbe
from paths import CSV_PATH, DEFAULT_HOST, DEFAULT_PORT, JSONL_PATH, LOG_DIR
from probe import monitor_during, probe_server

__all__ = [
    "CSV_PATH",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "JSONL_PATH",
    "LOG_DIR",
    "RunResult",
    "ServerProbe",
    "main",
    "monitor_during",
    "probe_server",
    "run_attack",
    "run_apex",
    "run_apex_cookie",
    "run_apex_cookie_multiprocess",
    "run_apex_cookie_scaled",
    "run_apex_multiprocess",
    "run_apex_scaled",
    "run_churn",
    "run_cookie_attack",
    "run_cookie_multiprocess",
    "run_cumulative_waves",
    "run_full_campaign",
    "run_iis_apex_mp",
    "run_multiprocess",
    "run_optimized_single_client_oom",
    "run_pipelined_sustain",
    "run_ramp",
    "run_sustained",
]

if __name__ == "__main__":
    main()
