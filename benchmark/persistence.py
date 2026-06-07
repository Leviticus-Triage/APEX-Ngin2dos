"""CSV / JSONL run logging."""
from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import datetime, timezone

from models import RunResult
from paths import CSV_PATH, JSONL_PATH


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def persist_run(result: RunResult) -> None:
    row = {
        "run_id": result.run_id,
        "timestamp": result.timestamp,
        "strategy": result.strategy,
        "target": result.target,
        "connections_requested": result.connections_requested,
        "connections_established": result.connections_established,
        "connections_bomb_ok": result.connections_bomb_ok,
        "connections_active_end": result.connections_active_end,
        "wire_mb": round(result.wire_mb, 2),
        "hold_sec": result.hold_sec,
        "probe_before_code": result.probe_before.http_code,
        "probe_after_code": result.probe_after.http_code,
        "probe_worst_latency": round(result.probe_worst_latency or 0, 3),
        "server_down": result.server_down,
        "oom_likely": result.oom_likely,
        "duration_sec": round(result.duration_sec, 1),
        "notes": result.notes,
    }

    write_header = not CSV_PATH.exists()
    with CSV_PATH.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row.keys()))
        if write_header:
            writer.writeheader()
        writer.writerow(row)

    with JSONL_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({**row, "full": asdict(result)}, default=str) + "\n")

    print(json.dumps(row, indent=2), flush=True)
