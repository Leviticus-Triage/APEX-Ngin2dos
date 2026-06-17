# Vendor Security Report — Apache mod_http2 (Incomplete Fix)

**Candidate:** Incomplete remediation of **CVE-2026-49975** on httpd **2.4.68** / mod_http2 **2.0.41**  
**Reporter:** Daniel F. Hensen  
**Date:** 2026-06-17  
**Harness:** APEX-Ngin2dos (authorized lab reproduction)  
**Related CVE:** CVE-2026-49975 (fixed per advisory in 2.4.68)

---

## Executive Summary

Apache httpd **2.4.68** with mod_http2 **2.0.41** is advertised as fixing CVE-2026-49975 (cookie-crumb HPACK DoS). We confirm the **empty-cookie** amplification path is mitigated. However, a **fat-cookie indexed-reference chain** that stays within default `LimitRequestFields` and `LimitRequestFieldSize` still causes **remote memory exhaustion and service unavailability** from a single client with **~10 MB** of wire traffic.

This indicates the 2.0.41 fix addresses **field-count accounting for empty crumbs only**, not **aggregate memory retention** on the cookie-merge code path documented in the original HTTP/2 Bomb research.

We request CVE evaluation as either:
- A **new CVE** for incomplete remediation, or
- Official clarification that CVE-2026-49975 remains partially open on default configurations.

---

## Affected

| Component | Affected | Not affected |
|-----------|----------|--------------|
| mod_http2 | **≤ 2.0.41** (verified httpd **2.4.68** Docker, default `httpd.conf`) | HTTP/2 disabled (`Protocols http/1.1`) |
| Attack surface | TLS + HTTP/2 (ALPN `h2`) | HTTP/1.1 only |

**Not affected by this specific chain:** Pre-2.0.41 empty-cookie bomb (different mechanism; fixed).

---

## What CVE-2026-49975 fixed (verified)

Commit [47d3100b25](https://github.com/apache/httpd/commit/47d3100b252dc6668a9e46ae885242be9eeca9cd) in `h2_util.c`:

```c
if (existing) {
    if (!nv->valuelen)
        return APR_SUCCESS;   /* empty crumbs no longer merge/amplify */
    ...
    apr_table_setn(headers, "Cookie", apr_psprintf(...));
    *pwas_added = 1;          /* non-empty crumbs now count */
    return APR_SUCCESS;
}
```

**Lab verification (httpd 2.4.68, 2026-06-17):**

| Profile | Connections | Wire | Peak RSS / outcome |
|---------|-------------|------|-------------------|
| Original empty-cookie PoC | 44 | 1.7 MB | Flat (~52 MiB), probe OK — **patch effective** |

---

## What remains exploitable (fat-cookie merge retention)

### Mechanism

1. Client negotiates HTTP/2 with `SETTINGS_INITIAL_WINDOW_SIZE=0` (flow-control stall).
2. Per stream: HPACK inserts one **4058-byte** `cookie` value into the dynamic table.
3. Client sends **95 indexed references** per stream (under `LimitRequestFields=100`).
4. Each reference triggers cookie merge via `apr_psprintf`, allocating a new pool string; **prior merge strings remain live** until stream cleanup (documented Apache behavior in califio/publications).
5. Scale: **25 streams/connection** × **N parallel connections** (batched, `hard_hold`).

All header fields remain within default Apache limits. This is not a parser escape — it is **unbounded aggregate allocation** on a code path the 2.0.41 fix did not harden.

### Root cause (candidate)

| Layer | Gap |
|-------|-----|
| Field count | 2.0.41 fix ✓ — crumbs count against `LimitRequestFields` |
| Field size | `LimitRequestFieldSize=8190` — fat values allowed |
| **Merge memory** | **No per-stream or per-connection budget on merge-string retention** |
| Flow control | Window stall pins allocations (known class, RFC-compliant) |

**CWE:** CWE-770 (Allocation without limits), CWE-400 (Uncontrolled resource consumption)

---

## Proof of Concept (lab metrics)

Environment: Docker `httpd:2.4` (Apache **2.4.68**), mod_http2, **8 GiB** cgroup, `127.0.0.1:10080`, default module config.

| Test | Connections | bomb_ok | Wire | Outcome |
|------|-------------|---------|------|---------|
| Empty cookie (control) | 44 | 44/44 | 1.7 MB | No OOM |
| **Fat cookie** | **100** | **100/100** | **10.0 MB** | **`oom_likely`, `server_down`** |
| Fat cookie | 500 | 500/500 | 200 MB | ~3.4 GiB RSS |
| Fat cookie | 800 | 800/800 | 320 MB | ~4.7 GiB RSS |
| Fat cookie | 1200 | 899/1200 | 359 MB | `server_down` |

### Reproduction

```bash
git clone https://github.com/Leviticus-Triage/APEX-Ngin2dos.git
cd APEX-Ngin2dos
./lab-replay-httpd/replay.sh build && ./lab-replay-httpd/replay.sh start 8g
./scripts/collect-cve-evidence.sh --apache-threshold
```

Core profile (`benchmark/attack_config.py`):

```python
profile_patch_bypass_httpd_fat(N)
# cookie_value_size=4058, refs=95, streams=min(100, N//4)
```

Implementation: `benchmark/cookie_bomb_enhanced.py` → `build_httpd_fat_block()`

---

## Impact

- **Single unauthenticated client**, low sustained bandwidth
- **Default configuration** on a release marketed as fixing CVE-2026-49975
- Worker memory exhaustion → denial of service

**CVSS 3.1 (estimate):** `AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` → **7.5 High**

---

## Recommended Remediation

1. **Bound aggregate cookie merge memory** per stream (reject or RST when decoded/merged cookie bytes exceed budget).
2. **Free or reuse** prior merge strings instead of retaining all intermediate `apr_psprintf` results until stream end.
3. **Decoded-size ratio check** (wire bytes vs allocated header bytes) as recommended in califio/nginx advisory.
4. **Document** that 2.0.41 does not fully close cookie-class HPACK DoS under default limits.
5. Short-term: lower `H2MaxSessionStreams`, connection limits, `Protocols http/1.1`.

---

## Distinction from prior public research

Calif.IO documented that `LimitRequestFieldSize` is only a partial mitigation when scaling across connections. **This report adds:**

1. Quantified **post-2.4.68** failure at **100 connections / 10 MB wire** on defaults.
2. Proof that **empty-cookie** and **fat-cookie** paths diverge after 2.0.41.
3. Independent reproduction harness with automated evidence collection.
4. Explicit mapping to **incomplete fix** of CVE-2026-49975, not a claim of unrelated 0-day class.

---

## Timeline

| Date | Action |
|------|--------|
| 2026-06-17 | Private report to security@apache.org |
| T+90 days | Public write-up if no objection |

---

## References

- CVE-2026-49975 — https://httpd.apache.org/security/vulnerabilities_24.html  
- mod_http2 2.0.41 commit — https://github.com/apache/httpd/commit/47d3100b252dc6668a9e46ae885242be9eeca9cd  
- califio HTTP/2 Bomb — https://github.com/califio/publications/tree/main/MADBugs/http2-bomb  
- APEX-Ngin2dos — https://github.com/Leviticus-Triage/APEX-Ngin2dos
