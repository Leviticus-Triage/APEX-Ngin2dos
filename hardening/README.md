# nginx hardening — HTTP/2 HPACK bomb (example)

Example configs for an **authorized lab/production target** running nginx **1.24.x** (vulnerable pre-1.29.8).

Replace `lab-target.example` with your hostname. Do not commit real customer hostnames or IPs to this repository.

## Priority

| Priority | Measure | Effect |
|----------|---------|--------|
| **1** | Upgrade nginx **≥ 1.29.8** + `http2_max_headers 100` | Upstream fix |
| **2** | `limit_conn` + lower `http2_max_concurrent_streams` | Slows amplification |
| **3** | `send_timeout 15s` | Shorter window stall |
| **4** | Emergency: disable HTTP/2 | Removes vector; affects h2 clients |

## Deployment (Ubuntu, nginx 1.24.0)

```bash
# 1. Copy configs (rename site snippet for your vhost)
sudo cp nginx-http2-bomb-mrx3k1.conf /etc/nginx/conf.d/
sudo cp mrx3k1.de.conf /etc/nginx/snippets/lab-target.example.conf

# 2. In /etc/nginx/nginx.conf under http { }:
#    include /etc/nginx/conf.d/nginx-http2-bomb-mrx3k1.conf;

# 3. Merge limit_conn/limit_req lines into your site block

# 4. Test & reload
sudo nginx -t && sudo systemctl reload nginx
```

## Upgrade path (recommended)

```bash
nginx -v   # target >= 1.29.8 after upgrade

# Apply nginx-1.29.8-post-upgrade.conf:
#   http2_max_headers 100;
```

## Verification after hardening

```bash
curl -sI --http2 https://lab-target.example/

# Authorized MCP/CLI:
# probe_http2 → run_http2_bomb_test profile=safe
# Expect: early abort / GOAWAY / fewer parallel streams
```

## Emergency: disable HTTP/2

Remove `http2` from the `listen` directive in the site config → TLS + HTTP/1.1 only.

## Reference

Benchmark results: `docs/LAB_RESULTS.md` and local `benchmark/logs/` (not committed).
