# Disclosure & Fix Status

Based on [califio/publications HTTP/2 Bomb](https://github.com/califio/publications/tree/main/MADBugs/http2-bomb) and upstream vendor responses (May 2026).

## nginx

| Item | Detail |
|------|--------|
| **Issue** | HPACK header amplification + window stall → memory exhaustion |
| **Fix** | nginx **1.29.8** — `max_headers` / `http2_max_headers` directive |
| **Commit** | https://github.com/nginx/nginx/commit/365694160a85229a7cb006738de9260d49ff5fa2 |
| **Mitigation (pre-patch)** | Lower `http2_max_concurrent_streams`, `limit_conn`, `send_timeout`, `http2_max_headers` if backported |

## Apache httpd (mod_http2)

| Item | Detail |
|------|--------|
| **Issue** | Cookie-crumb HPACK merge amplification |
| **Fix** | mod_http2 **v2.0.41** — cookie accounting vs `LimitRequestFields` |
| **Commit** | https://github.com/apache/httpd/commit/47d3100b252dc6668a9e46ae885242be9eeca9cd |

## Envoy

| Item | Detail |
|------|--------|
| **Issue** | Cookie HPACK bomb (~5700:1 published) |
| **Fix status** | Reported May 2026 — **unknown** |
| **Lab** | `lab-replay-envoy/` for authorized replay |

## Cloudflare Pingora

| Item | Detail |
|------|--------|
| **Issue** | nginx-class hpack_bomb adapted PoC |
| **Fix status** | Reported May 2026 — **unknown** |
| **Lab** | `lab-replay/pingora/` via vendor docker-compose |

## Microsoft IIS

| Item | Detail |
|------|--------|
| **Issue** | HPACK DoS via `iis_hpack_dos.py` PoC |
| **Fix status** | Reported May 2026 — **unknown** |
| **Lab** | Windows VM + `iis_apex_orchestrator.ps1` |

## References

- https://github.com/califio/publications/tree/main/MADBugs/http2-bomb

## Responsible disclosure

If you validate these issues on production systems, coordinate with vendors through established security channels. Do not disclose exploitable details before patch availability without vendor agreement.
