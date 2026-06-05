"""Tunnel/proxy routing for HTTP/2 bomb traffic (direct, SOCKS5, HTTP, proxychains, Tor, ngrok, cloudflared)."""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TUNNEL_PATHS: list[Path] = [
    PLUGIN_ROOT / "config" / "tunnel.json",
    Path.home() / ".config" / "http2-bomb" / "tunnel.json",
]

TUNNEL_MODES = ("none", "socks5", "http", "proxychains", "cloudflared", "ngrok", "tor")

try:
    import socks  # PySocks

    HAS_PYSOCKS = True
except ImportError:
    HAS_PYSOCKS = False

_active: TunnelConfig | None = None
_proxychains_temp: Path | None = None


@dataclass
class TunnelConfig:
    mode: str = "none"
    name: str = "default"
    proxy_url: str = ""
    proxy_host: str = "127.0.0.1"
    proxy_port: int = 9050
    proxy_user: str = ""
    proxy_pass: str = ""
    proxychains_conf: str = ""
    cloudflared_proxy: str = ""
    ngrok_addr: str = ""
    ngrok_api_url: str = "http://127.0.0.1:4040"

    def normalized_mode(self) -> str:
        m = (self.mode or "none").strip().lower()
        if m == "tor":
            return "socks5"
        return m if m in TUNNEL_MODES else "none"

    def effective_proxy_url(self) -> str | None:
        mode = self.normalized_mode()
        if mode in ("none", "proxychains"):
            return None
        if self.proxy_url.strip():
            return self.proxy_url.strip()
        if mode == "cloudflared" and self.cloudflared_proxy.strip():
            return self.cloudflared_proxy.strip()
        if mode == "ngrok":
            addr = self.ngrok_addr.strip() or _discover_ngrok_addr(self.ngrok_api_url)
            if addr:
                return f"socks5://{addr}" if "://" not in addr else addr
            return None
        if mode in ("socks5", "http") or self.mode == "tor":
            scheme = "socks5" if mode == "socks5" or self.mode == "tor" else "http"
            host = self.proxy_host or "127.0.0.1"
            port = self.proxy_port or (9050 if self.mode == "tor" else 1080)
            if self.proxy_user:
                auth = f"{self.proxy_user}:{self.proxy_pass}@"
                return f"{scheme}://{auth}{host}:{port}"
            return f"{scheme}://{host}:{port}"
        return None

    def uses_proxychains_wrapper(self) -> bool:
        return self.mode == "proxychains" or (self.mode == "tor" and not HAS_PYSOCKS)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> TunnelConfig:
        if not data:
            return cls()
        fields = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in fields})

    def summary(self) -> str:
        url = self.effective_proxy_url()
        extra = ""
        if self.mode == "proxychains" and self.proxychains_conf:
            extra = f" conf={self.proxychains_conf}"
        elif self.uses_proxychains_wrapper():
            extra = " (proxychains fallback)"
        return f"mode={self.mode} proxy={url or 'direct'}{extra}"


def _discover_ngrok_addr(api_url: str) -> str | None:
    try:
        with urllib.request.urlopen(f"{api_url.rstrip('/')}/api/tunnels", timeout=3) as resp:
            data = json.loads(resp.read().decode())
        for tun in data.get("tunnels", []):
            public = tun.get("public_url") or ""
            if public.startswith("tcp://"):
                return public.replace("tcp://", "")
            cfg = tun.get("config", {})
            addr = cfg.get("addr")
            if addr:
                return str(addr)
    except (urllib.error.URLError, json.JSONDecodeError, OSError, TimeoutError):
        return None
    return None


def default_tunnel_path() -> Path:
    for p in DEFAULT_TUNNEL_PATHS:
        if p.is_file():
            return p
    return DEFAULT_TUNNEL_PATHS[0]


def load_tunnel_config(path: str | Path | None = None) -> TunnelConfig:
    candidates = [Path(path)] if path else DEFAULT_TUNNEL_PATHS
    for p in candidates:
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                cfg = TunnelConfig.from_dict(data if isinstance(data, dict) else {})
                cfg.name = cfg.name or p.stem
                return cfg
            except (json.JSONDecodeError, OSError):
                continue
    return TunnelConfig()


def save_tunnel_config(cfg: TunnelConfig, path: str | Path | None = None) -> Path:
    dest = Path(path) if path else default_tunnel_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(cfg.to_dict(), indent=2) + "\n", encoding="utf-8")
    return dest


def merge_tunnel_overrides(
    base: TunnelConfig,
    *,
    mode: str | None = None,
    proxy_url: str | None = None,
    proxy_host: str | None = None,
    proxy_port: int | None = None,
    proxychains_conf: str | None = None,
    cloudflared_proxy: str | None = None,
    ngrok_addr: str | None = None,
) -> TunnelConfig:
    d = base.to_dict()
    if mode is not None:
        d["mode"] = mode
    if proxy_url is not None:
        d["proxy_url"] = proxy_url
    if proxy_host is not None:
        d["proxy_host"] = proxy_host
    if proxy_port is not None:
        d["proxy_port"] = proxy_port
    if proxychains_conf is not None:
        d["proxychains_conf"] = proxychains_conf
    if cloudflared_proxy is not None:
        d["cloudflared_proxy"] = cloudflared_proxy
    if ngrok_addr is not None:
        d["ngrok_addr"] = ngrok_addr
    if proxy_url:
        parsed = urlparse(proxy_url)
        if parsed.scheme in ("socks5", "socks5h", "http", "https"):
            d["mode"] = "socks5" if "socks" in parsed.scheme else "http"
            d["proxy_host"] = parsed.hostname or d.get("proxy_host", "127.0.0.1")
            d["proxy_port"] = parsed.port or d.get("proxy_port", 1080)
            if parsed.username:
                d["proxy_user"] = parsed.username
                d["proxy_pass"] = parsed.password or ""
    if mode == "tor":
        d["proxy_host"] = d.get("proxy_host") or "127.0.0.1"
        d["proxy_port"] = d.get("proxy_port") or 9050
    return TunnelConfig.from_dict(d)


def activate_tunnel(cfg: TunnelConfig | None) -> TunnelConfig:
    global _active, _proxychains_temp
    _active = cfg or TunnelConfig()
    _proxychains_temp = None
    if _active.mode == "tor" and _active.uses_proxychains_wrapper():
        _proxychains_temp = write_tor_proxychains_conf(_active)
    for key, val in proxy_env_vars(_active).items():
        os.environ[key] = val
    return _active


def get_active_tunnel() -> TunnelConfig | None:
    return _active


def proxy_env_vars(cfg: TunnelConfig) -> dict[str, str]:
    env: dict[str, str] = {}
    url = cfg.effective_proxy_url()
    if not url:
        return env
    env["HTTP_PROXY"] = url
    env["HTTPS_PROXY"] = url
    env["ALL_PROXY"] = url
    env["http_proxy"] = url
    env["https_proxy"] = url
    env["all_proxy"] = url
    return env


def merge_subprocess_env(base: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(base or os.environ)
    if _active:
        env.update(proxy_env_vars(_active))
    env.setdefault("PYTHONUNBUFFERED", "1")
    return env


def find_proxychains() -> str | None:
    for name in ("proxychains4", "proxychains"):
        path = shutil.which(name)
        if path:
            return path
    return None


def write_tor_proxychains_conf(cfg: TunnelConfig) -> Path:
    host = cfg.proxy_host or "127.0.0.1"
    port = cfg.proxy_port or 9050
    content = f"""# Auto-generated by http2-bomb tunnel (tor preset)
strict_chain
proxy_dns
tcp_read_time_out 15000
tcp_connect_time_out 8000
[ProxyList]
socks5 {host} {port}
"""
    fd, path = tempfile.mkstemp(prefix="http2bomb_proxychains_", suffix=".conf")
    os.close(fd)
    p = Path(path)
    p.write_text(content, encoding="utf-8")
    return p


def proxychains_conf_path(cfg: TunnelConfig) -> Path | None:
    if cfg.proxychains_conf and Path(cfg.proxychains_conf).is_file():
        return Path(cfg.proxychains_conf)
    if _proxychains_temp and _proxychains_temp.is_file():
        return _proxychains_temp
    if cfg.mode == "tor":
        return write_tor_proxychains_conf(cfg)
    return None


def wrap_subprocess_argv(argv: list[str]) -> list[str]:
    if not _active or _active.normalized_mode() == "none":
        return argv
    if not _active.uses_proxychains_wrapper():
        return argv
    pc = find_proxychains()
    conf = proxychains_conf_path(_active)
    if not pc or not conf:
        return argv
    return [pc, "-f", str(conf), "-q", *argv]


def _parse_proxy_url(url: str) -> tuple[int, str, int, str | None, str | None]:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme in ("socks5", "socks5h"):
        ptype = socks.PROXY_TYPE_SOCKS5 if HAS_PYSOCKS else 0
    elif scheme in ("http", "https"):
        ptype = socks.PROXY_TYPE_HTTP if HAS_PYSOCKS else 0
    else:
        raise ValueError(f"Unsupported proxy scheme: {scheme}")
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (9050 if "socks" in scheme else 8080)
    return ptype, host, port, parsed.username, parsed.password


def create_connection(
    host: str,
    port: int,
    timeout: float = 30.0,
    bind_ip: str | None = None,
) -> socket.socket:
    """Create TCP (optionally TLS-ready) socket, routed through active tunnel if set."""
    cfg = _active
    url = cfg.effective_proxy_url() if cfg else None

    if url and HAS_PYSOCKS and not (cfg and cfg.uses_proxychains_wrapper()):
        ptype, phost, pport, user, password = _parse_proxy_url(url)
        sock = socks.socksocket(socket.AF_INET, socket.SOCK_STREAM)
        sock.set_proxy(ptype, phost, pport, username=user, password=password)
        sock.settimeout(timeout)
        if bind_ip:
            sock.bind((bind_ip, 0))
        sock.connect((host, port))
        return sock

    raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    raw.settimeout(timeout)
    if bind_ip:
        raw.bind((bind_ip, 0))
    raw.connect((host, port))
    return raw


def curl_proxy_args(cfg: TunnelConfig | None = None) -> list[str]:
    cfg = cfg or _active
    if not cfg:
        return []
    url = cfg.effective_proxy_url()
    if url:
        return ["--proxy", url]
    return []


def test_tunnel_connectivity(host: str, port: int = 443, timeout: float = 10.0) -> dict[str, Any]:
    cfg = _active or TunnelConfig()
    result: dict[str, Any] = {
        "tunnel": cfg.summary(),
        "target": f"{host}:{port}",
        "pysocks_available": HAS_PYSOCKS,
        "proxychains": find_proxychains(),
        "ok": False,
        "error": None,
        "latency_ms": None,
    }
    import time

    t0 = time.monotonic()
    try:
        sock = create_connection(host, port, timeout=timeout)
        sock.close()
        result["ok"] = True
        result["latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
    except Exception as exc:
        result["error"] = str(exc)
        result["latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
    return result


def start_ngrok_tcp(local_port: int = 443, region: str = "eu") -> subprocess.Popen | None:
    ngrok = shutil.which("ngrok")
    if not ngrok:
        return None
    return subprocess.Popen(
        [ngrok, "tcp", str(local_port), "--region", region, "--log=stdout"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def stop_process(proc: subprocess.Popen | None) -> None:
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
