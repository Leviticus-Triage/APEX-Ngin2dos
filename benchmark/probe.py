"""HTTP/2 reachability probes (curl + ALPN)."""
from __future__ import annotations

import threading
import time

from models import ServerProbe
from paths import DEFAULT_PORT
from tunnel import curl_proxy_args
from tunnel_runner import run as tunnel_run


def probe_server(host: str, port: int = 443, timeout: float = 15.0) -> ServerProbe:
    t0 = time.monotonic()
    try:
        proc = tunnel_run(
            [
                "curl", "-sS", "-m", str(int(timeout)), "-o", "/dev/null",
                "-w", "%{http_code}",
                "-k", "--http2", *curl_proxy_args(), f"https://{host}:{port}/",
            ],
            capture_output=True,
            text=True,
            timeout=timeout + 2,
        )
        lat = time.monotonic() - t0
        code = int(proc.stdout.strip()) if proc.stdout.strip().isdigit() else None
        err = proc.stderr.strip() if proc.returncode != 0 else None
        return ServerProbe(ok=proc.returncode == 0 and code is not None, http_code=code, latency_sec=lat, error=err)
    except Exception as exc:
        return ServerProbe(ok=False, http_code=None, latency_sec=time.monotonic() - t0, error=str(exc))


def monitor_during(
    host: str,
    stop: threading.Event,
    samples: list[ServerProbe],
    interval: float = 8.0,
    port: int = DEFAULT_PORT,
) -> None:
    while not stop.is_set():
        samples.append(probe_server(host, port))
        stop.wait(interval)
