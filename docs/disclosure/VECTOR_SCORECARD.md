# Vector Scorecard — R-Enantiomer Hunt

**Gate:** Vendor-Mail erst wenn mindestens ein Eintrag **GOLD** oder **PLATIN** ist.

| ID | Vektor | Target | Status | Wire/Decoded | Limit bypass? | OOM patched? | CVE tier |
|----|--------|--------|--------|--------------|---------------|--------------|----------|
| R1 | Wire/decoded ratio | nginx 1.31.1 | ⏳ pending | — | — | — | — |
| R1 | Wire/decoded ratio | httpd 2.4.68 | ⏳ pending | — | — | — | — |
| R2 | Trailer header bomb | nginx 1.31.1 | ⏳ pending | — | — | — | — |
| R2 | Trailer header bomb | httpd 2.4.68 | ⏳ pending | — | — | — | — |
| R3 | CONTINUATION split 32k | nginx 1.31.1 | ❌ invalid test | — | no | no | — |
| R3 | CONTINUATION split 32k | httpd 2.4.68 | ⏳ pending (real HPACK) | — | — | — | — |
| R4 | Apache indexed-ref gap | httpd 2.4.68 | ⚠️ partial | — | unclear | no @44 empty | — |
| R5 | Fat-cookie merge retention | httpd 2.4.68 | ✅ repro | low | no (legal count) | yes @100 conn | BRONZE |
| R6 | Pingora 0.8.1 no secure default | pingora 0.8.1 | ⏳ pending | — | — | — | — |
| R7 | Envoy post-477774 bypass | envoy 1.37.4 | ❌ no OOM @200 | — | no | no | — |
| R8 | HTTP/3 QPACK | nginx 1.31.1 | ⏳ pending | — | — | — | — |
| R9 | IIS post-patch | WS2025 | ⏳ no VM | — | — | — | — |

## Notes

- R3 nginx run with `cve_hunt_runner` used **invalid HPACK** (fake literals) — must rerun with `evasion_hpack.py`.
- R5 confirmed 2026-06-17: 100 conn fat-cookie → `oom_likely`, `server_down`; not sufficient alone for CVE.
- R7 Envoy 1.37.4: 200 conn fat-cookie, no OOM in lab.

## Next actions

1. Implement `benchmark/evasion_hpack.py` + `benchmark/ratio_probe.py`
2. Rerun R1–R3
3. Pin Pingora 0.8.1 for R6
