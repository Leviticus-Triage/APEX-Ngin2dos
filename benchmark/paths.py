"""Shared paths and lab defaults for the benchmark harness."""
from __future__ import annotations

from pathlib import Path

from authorization import DEFAULT_LAB_HOST, DEFAULT_LAB_PORT

PLUGIN = Path(__file__).resolve().parent.parent
BENCH_DIR = Path(__file__).resolve().parent
LOG_DIR = BENCH_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
CSV_PATH = LOG_DIR / "benchmark_results.csv"
JSONL_PATH = LOG_DIR / "benchmark_runs.jsonl"

DEFAULT_HOST = DEFAULT_LAB_HOST
DEFAULT_PORT = DEFAULT_LAB_PORT
SOCKET_TIMEOUT = 300
