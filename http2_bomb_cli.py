#!/usr/bin/env python3
"""
HTTP/2 Bomb — standalone CLI (no IDE/MCP required).

Interactive menu + non-interactive subcommands for probe, PoC, benchmark, tunnel, labs.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parent
BENCH_DIR = PLUGIN_ROOT / "benchmark"
CONFIG_DIR = PLUGIN_ROOT / "config"
CLI_SETTINGS_PATH = CONFIG_DIR / "cli_settings.json"
TUNNEL_CONFIG_PATH = CONFIG_DIR / "tunnel.json"
BENCH_CSV = BENCH_DIR / "logs" / "benchmark_results.csv"
ALLOWLIST_PATH = PLUGIN_ROOT / "allowed_targets.json"

sys.path.insert(0, str(PLUGIN_ROOT))
sys.path.insert(0, str(BENCH_DIR))

from tunnel import (  # noqa: E402
    TUNNEL_MODES,
    activate_tunnel,
    load_tunnel_config,
    merge_tunnel_overrides,
    save_tunnel_config,
    test_tunnel_connectivity,
)


def _mcp():
    import http2_bomb_mcp as mcp_core

    return mcp_core

BANNER = r"""
 _   _ _____ ____ ___   ____   ___  ____  __  __
| | | |_   _|  _ \_ _| | __ ) / _ \| __ )|  \/  |
| |_| | | | | |_) | |  |  _ \| | | |  _ \| |\/| |
|  _  | | | |  __/| |  | |_) | |_| | |_) | |  | |
|_| |_| |_| |_|  |___| |____/ \___/|____/|_|  |_|

 HTTP/2 HPACK-Bomb — Terminal CLI (califio PoCs)
 Authorized targets only | v2 + Tunnel + Benchmark
"""

try:
    from rich.console import Console
    from rich.panel import Panel

    _console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


def _print(msg: str = "", style: str = "") -> None:
    if HAS_RICH and style:
        _console.print(msg, style=style)
    else:
        print(msg)


def _banner() -> None:
    if HAS_RICH:
        _console.print(Panel(BANNER.strip(), border_style="red", title="http2-bomb"))
    else:
        print(BANNER)


def load_cli_settings() -> dict[str, Any]:
    path = CLI_SETTINGS_PATH
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    example = CONFIG_DIR / "cli_settings.example.json"
    if example.is_file():
        try:
            return json.loads(example.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "default_host": "127.0.0.1",
        "default_port": 443,
        "default_variant": "nginx",
        "default_profile": "safe",
        "default_benchmark_mode": "apex_scaled",
        "default_connections": 50,
        "max_runtime_sec": 600,
    }


def save_cli_settings(data: dict[str, Any]) -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CLI_SETTINGS_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return CLI_SETTINGS_PATH


def _prompt(text: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"{text}{suffix}: ").strip()
    return val or default


def _prompt_yes(text: str) -> bool:
    return _prompt(f"{text} (y/n)", "n").lower() in ("y", "yes")


def _apply_saved_tunnel() -> None:
    activate_tunnel(load_tunnel_config())


def cmd_probe(args: argparse.Namespace) -> int:
    _apply_saved_tunnel()
    if args.tunnel_mode or args.proxy_url:
        activate_tunnel(
            merge_tunnel_overrides(
                load_tunnel_config(),
                mode=args.tunnel_mode or None,
                proxy_url=args.proxy_url or None,
            )
        )
    import asyncio

    result = asyncio.run(
        _mcp().probe_http2(
            args.host,
            args.port,
            args.server_name or "",
            tunnel_mode=args.tunnel_mode or "",
            proxy_url=args.proxy_url or "",
        )
    )
    print(result)
    return 0


def cmd_variants(_args: argparse.Namespace) -> int:
    import asyncio

    print(asyncio.run(_mcp().list_http2_bomb_variants()))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    settings = load_cli_settings()
    scope = args.scope or settings.get("scope_description", "")
    if not args.yes:
        if not _prompt_yes("Written authorization for this target?"):
            print("Cancelled — authorization_confirmed is required.")
            return 1
        scope = _prompt("Scope (ticket/customer, min. 12 characters)", scope)
    import asyncio

    result = asyncio.run(
        _mcp().run_http2_bomb_test(
            host=args.host,
            port=args.port,
            variant=args.variant,
            profile=args.profile,
            authorization_confirmed=True,
            scope_description=scope,
            server_name=args.server_name or "",
            path=args.path or "/",
            tunnel_mode=args.tunnel_mode or "",
            proxy_url=args.proxy_url or "",
            proxychains_conf=args.proxychains_conf or "",
        )
    )
    print(result)
    return 0 if not result.startswith("REJECTED") else 1


def cmd_benchmark(args: argparse.Namespace) -> int:
    scope = args.scope
    if not args.yes:
        if not _prompt_yes("Written authorization for this benchmark?"):
            return 1
        scope = _prompt("Scope", scope or "Lab benchmark authorized")
    import asyncio

    result = asyncio.run(
        _mcp().run_http2_bomb_benchmark(
            host=args.host,
            port=args.port,
            mode=args.mode,
            connections=args.connections,
            variant=args.variant,
            authorization_confirmed=True,
            scope_description=scope,
            tunnel_mode=args.tunnel_mode or "",
            proxy_url=args.proxy_url or "",
            proxychains_conf=args.proxychains_conf or "",
        )
    )
    print(result)
    return 0


def cmd_tunnel(args: argparse.Namespace) -> int:
    if args.tunnel_cmd == "show":
        cfg = load_tunnel_config()
        print(json.dumps(cfg.to_dict(), indent=2))
        print(f"\n{cfg.summary()}")
        return 0

    if args.tunnel_cmd == "set":
        cfg = merge_tunnel_overrides(
            load_tunnel_config(),
            mode=args.mode,
            proxy_url=args.proxy_url or None,
            proxychains_conf=args.proxychains_conf or None,
            cloudflared_proxy=args.cloudflared_proxy or None,
            ngrok_addr=args.ngrok_addr or None,
        )
        activate_tunnel(cfg)
        if not args.no_save:
            for p in (TUNNEL_CONFIG_PATH, Path.home() / ".config" / "http2-bomb" / "tunnel.json"):
                save_tunnel_config(cfg, p)
        print(f"Tunnel gesetzt: {cfg.summary()}")
        return 0

    if args.tunnel_cmd == "test":
        _apply_saved_tunnel()
        if args.mode:
            activate_tunnel(merge_tunnel_overrides(load_tunnel_config(), mode=args.mode))
        host = args.host or load_cli_settings().get("default_host", "127.0.0.1")
        port = args.port or load_cli_settings().get("default_port", 443)
        result = test_tunnel_connectivity(host, port)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    return 1


def cmd_logs(args: argparse.Namespace) -> int:
    import asyncio

    print(asyncio.run(_mcp().get_http2_bomb_benchmark_logs(last_n=args.last)))
    return 0


def cmd_mcp_info(_args: argparse.Namespace) -> int:
    py = sys.executable
    snippet = {
        "http2-bomb": {
            "command": py,
            "args": [str(PLUGIN_ROOT / "http2_bomb_mcp.py")],
            "description": "HTTP/2 HPACK-bomb PoC (califio) — authorized targets only",
            "timeout": 900,
        }
    }
    print("MCP server:", PLUGIN_ROOT / "http2_bomb_mcp.py")
    print("\n~/.cursor/mcp.json snippet:\n")
    print(json.dumps(snippet, indent=2))
    return 0


def cmd_lab(args: argparse.Namespace) -> int:
    labs = {
        "nginx": PLUGIN_ROOT / "lab-replay",
        "httpd": PLUGIN_ROOT / "lab-replay-httpd",
        "envoy": PLUGIN_ROOT / "lab-replay-envoy",
    }
    lab = labs.get(args.stack)
    if not lab or not lab.is_dir():
        print(f"Unbekanntes Lab: {args.stack}. Erlaubt: {', '.join(labs)}")
        return 1
    script = lab / "replay.sh"
    if not script.is_file():
        print(f"replay.sh fehlt in {lab}")
        return 1
    cmd = ["bash", str(script)]
    if args.action == "compare":
        cmd = ["bash", str(lab / "run_ab_compare.sh")]
    print(f"Starte: {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=str(lab))


def cmd_settings(args: argparse.Namespace) -> int:
    data = load_cli_settings()
    if args.show:
        print(json.dumps(data, indent=2))
        return 0
    if args.set:
        key, _, val = args.set.partition("=")
        if not key:
            print("Format: --set key=value")
            return 1
        if val.isdigit():
            data[key] = int(val)
        else:
            try:
                data[key] = json.loads(val)
            except json.JSONDecodeError:
                data[key] = val
        path = save_cli_settings(data)
        print(f"Gespeichert: {path}")
        return 0
    return 0


def interactive_menu() -> int:
    settings = load_cli_settings()
    while True:
        os.system("clear" if os.name != "nt" else "cls")
        _banner()
        tunnel = load_tunnel_config()
        print(f"Tunnel: {tunnel.summary()}")
        print(f"Default: {settings.get('default_host')}:{settings.get('default_port')} variant={settings.get('default_variant')}")
        print()
        menu = [
            ("1", "Probe / variants"),
            ("2", "PoC test (safe/moderate/aggressive)"),
            ("3", "Benchmark (apex, scaled, …)"),
            ("4", "Configure / test tunnel"),
            ("5", "Lab replay (nginx/httpd/envoy)"),
            ("6", "Logs / benchmark CSV"),
            ("7", "MCP server info"),
            ("8", "Settings"),
            ("0", "Exit"),
        ]
        for k, label in menu:
            print(f"  [{k}] {label}")
        choice = _prompt("\nAuswahl", "0")

        if choice == "0":
            return 0
        if choice == "1":
            sub = _prompt("probe oder variants", "probe")
            if sub == "variants":
                cmd_variants(argparse.Namespace())
            else:
                host = _prompt("Host", settings["default_host"])
                port = int(_prompt("Port", str(settings["default_port"])))
                ns = argparse.Namespace(
                    host=host, port=port, server_name="", tunnel_mode="", proxy_url=""
                )
                cmd_probe(ns)
            _prompt("Press Enter to continue")
        elif choice == "2":
            host = _prompt("Host", settings["default_host"])
            variant = _prompt("Variante", settings["default_variant"])
            profile = _prompt("Profil (safe/moderate/aggressive)", settings["default_profile"])
            ns = argparse.Namespace(
                host=host,
                port=int(_prompt("Port", str(settings["default_port"]))),
                variant=variant,
                profile=profile,
                scope="",
                server_name="",
                path="/",
                tunnel_mode="",
                proxy_url="",
                proxychains_conf="",
                yes=False,
            )
            cmd_run(ns)
            _prompt("Press Enter to continue")
        elif choice == "3":
            host = _prompt("Host", settings["default_host"])
            mode = _prompt("Mode", settings.get("default_benchmark_mode", "apex_scaled"))
            conns = int(_prompt("Connections", str(settings.get("default_connections", 50))))
            ns = argparse.Namespace(
                host=host,
                port=int(_prompt("Port", str(settings["default_port"]))),
                mode=mode,
                connections=conns,
                variant=_prompt("Variante", settings["default_variant"]),
                scope="",
                tunnel_mode="",
                proxy_url="",
                proxychains_conf="",
                yes=False,
            )
            cmd_benchmark(ns)
            _prompt("Press Enter to continue")
        elif choice == "4":
            print(f"Modi: {', '.join(TUNNEL_MODES)}")
            mode = _prompt("Tunnel-Mode", tunnel.mode)
            proxy = _prompt("Proxy-URL (optional)", tunnel.proxy_url)
            ns = argparse.Namespace(
                tunnel_cmd="set",
                mode=mode,
                proxy_url=proxy,
                proxychains_conf="",
                cloudflared_proxy="",
                ngrok_addr="",
                no_save=False,
            )
            cmd_tunnel(ns)
            if _prompt_yes("Connectivity-Test?"):
                th = _prompt("Test-Host", settings["default_host"])
                ns2 = argparse.Namespace(tunnel_cmd="test", host=th, port=settings["default_port"], mode="")
                cmd_tunnel(ns2)
            _prompt("Press Enter to continue")
        elif choice == "5":
            stack = _prompt("Stack (nginx/httpd/envoy)", "nginx")
            ns = argparse.Namespace(stack=stack, action="replay")
            cmd_lab(ns)
            _prompt("Press Enter to continue")
        elif choice == "6":
            cmd_logs(argparse.Namespace(last=10))
            _prompt("Press Enter to continue")
        elif choice == "7":
            cmd_mcp_info(argparse.Namespace())
            _prompt("Press Enter to continue")
        elif choice == "8":
            print(json.dumps(settings, indent=2))
            key = _prompt("Setting key (empty = skip)")
            if key:
                val = _prompt("Value")
                settings[key] = int(val) if val.isdigit() else val
                save_cli_settings(settings)
            _prompt("Press Enter to continue")
        else:
            print("Invalid choice")
            _prompt("Enter")


def build_parser() -> argparse.ArgumentParser:
    settings = load_cli_settings()
    p = argparse.ArgumentParser(
        description="HTTP/2 Bomb CLI — probe, PoC, benchmark, tunnel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """\
            Examples:
              %(prog)s menu
              %(prog)s probe --host 127.0.0.1 --port 8443
              %(prog)s run --host TARGET --profile safe --scope "Ticket INT-1234" --yes
              %(prog)s benchmark --host TARGET --mode apex_scaled --connections 100
              %(prog)s tunnel set --mode tor
              %(prog)s tunnel test --host example.com
            """
        ),
    )
    sub = p.add_subparsers(dest="command")

    sub.add_parser("menu", help="Interactive ASCII menu")
    sub.add_parser("variants", help="List variants")

    probe = sub.add_parser("probe", help="TLS/ALPN H2 probe")
    probe.add_argument("--host", default=settings["default_host"])
    probe.add_argument("--port", type=int, default=settings["default_port"])
    probe.add_argument("--server-name", default="")
    probe.add_argument("--tunnel-mode", default="")
    probe.add_argument("--proxy-url", default="")

    run = sub.add_parser("run", help="Run PoC test")
    run.add_argument("--host", required=True)
    run.add_argument("--port", type=int, default=settings["default_port"])
    run.add_argument("--variant", default=settings["default_variant"])
    run.add_argument("--profile", default=settings["default_profile"], choices=["probe", "safe", "moderate", "aggressive"])
    run.add_argument("--scope", default="")
    run.add_argument("--server-name", default="")
    run.add_argument("--path", default="/")
    run.add_argument("--tunnel-mode", default="")
    run.add_argument("--proxy-url", default="")
    run.add_argument("--proxychains-conf", default="")
    run.add_argument("--yes", action="store_true", help="Skip auth prompt")

    bench = sub.add_parser("benchmark", help="Run benchmark campaign")
    bench.add_argument("--host", required=True)
    bench.add_argument("--port", type=int, default=settings["default_port"])
    bench.add_argument("--variant", default=settings["default_variant"])
    bench.add_argument("--mode", default=settings.get("default_benchmark_mode", "apex_scaled"))
    bench.add_argument("--connections", type=int, default=settings.get("default_connections", 50))
    bench.add_argument("--scope", default="")
    bench.add_argument("--tunnel-mode", default="")
    bench.add_argument("--proxy-url", default="")
    bench.add_argument("--proxychains-conf", default="")
    bench.add_argument("--yes", action="store_true")

    tunnel = sub.add_parser("tunnel", help="Tunnel-Profil")
    tunnel_sub = tunnel.add_subparsers(dest="tunnel_cmd", required=True)
    tunnel_sub.add_parser("show")
    tset = tunnel_sub.add_parser("set")
    tset.add_argument("--mode", default="none", choices=list(TUNNEL_MODES))
    tset.add_argument("--proxy-url", default="")
    tset.add_argument("--proxychains-conf", default="")
    tset.add_argument("--cloudflared-proxy", default="")
    tset.add_argument("--ngrok-addr", default="")
    tset.add_argument("--no-save", action="store_true")
    ttest = tunnel_sub.add_parser("test")
    ttest.add_argument("--host", default="")
    ttest.add_argument("--port", type=int, default=0)
    ttest.add_argument("--mode", default="")

    logs = sub.add_parser("logs", help="Benchmark-CSV tail")
    logs.add_argument("--last", type=int, default=10)

    sub.add_parser("mcp-info", help="MCP JSON snippet")

    lab = sub.add_parser("lab", help="Lab replay docker")
    lab.add_argument("stack", choices=["nginx", "httpd", "envoy"])
    lab.add_argument("--action", choices=["replay", "compare"], default="replay")

    sett = sub.add_parser("settings", help="CLI settings")
    sett.add_argument("--show", action="store_true")
    sett.add_argument("--set", metavar="KEY=VALUE")

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        interactive_menu()
        return 0

    handlers = {
        "menu": lambda a: interactive_menu(),
        "variants": cmd_variants,
        "probe": cmd_probe,
        "run": cmd_run,
        "benchmark": cmd_benchmark,
        "tunnel": cmd_tunnel,
        "logs": cmd_logs,
        "mcp-info": cmd_mcp_info,
        "lab": cmd_lab,
        "settings": cmd_settings,
    }
    return handlers[args.command](args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
