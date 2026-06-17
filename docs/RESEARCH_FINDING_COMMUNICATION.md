# Honest Communication Draft – HTTP/2 HPACK Amplification Research (June 2026)

## Title options (pick one)
- "HTTP/2 HPACK amplification: Patches help, but are not sufficient alone"
- "From PoC to practical impact: What the nginx and httpd fixes actually stopped (and what they didn't)"
- "Responsible research update: Volume-based HPACK resource exhaustion after per-request mitigations"

## One-paragraph summary (for post / email / report)

In 2026, following the original califio HTTP/2 bomb research and subsequent vendor fixes (nginx `http2_max_headers` in 1.29.8, mod_http2 cookie accounting in 2.0.41), we performed extensive lab validation of the remaining attack surface.

The per-request limits effectively stop the extreme single-stream bombs (32k+ headers or thousands of empty cookie crumbs). However, when deployments apply only the header-count / field-count limit and leave high `http2_max_concurrent_streams` together with weak per-IP or global concurrency controls, reliable high-volume delivery of *max-legal* requests can still produce significant memory pressure and service degradation.

This is not a bypass of the per-request limit itself, but a demonstration that the published fixes address only part of the problem. Additional aggregate controls (stream concurrency, connection limits, timeouts, memory accounting) remain necessary for robust defense.

All testing was performed exclusively against isolated lab targets under our control. Full logs, configurations, and reproduction material are available in the APEX-Ngin2dos repository.

## Key distinctions (be explicit about this)

- We did **not** find a way to exceed the configured `http2_max_headers` or `LimitRequestFields` per request on the patched versions.
- The amplification we achieved on nginx comes from sending the maximum number of headers the limit still permits, across a large number of concurrent streams/connections.
- On patched Apache httpd the effect was dramatically smaller under equivalent "within limits" profiles.
- This work extends the original disclosure by showing the operational gap between "the primitive is fixed per-request" and "the system is safe in realistic configurations".

## What this means for defenders

If you only set `http2_max_headers 100;` (or equivalent) and did nothing else, you are not fully protected against volume-based variants.

Recommended layered controls:
- Significantly lower `http2_max_concurrent_streams` (e.g. 16–32)
- Per-IP connection limits (`limit_conn`)
- Tight timeouts
- Worker / container memory limits + monitoring for RSS growth without corresponding traffic
- For Apache: ensure mod_http2 ≥ 2.0.41 and keep `LimitRequestFields` reasonably low

## Scope & responsible disclosure notes

- All experiments were run in local Docker labs against containers we control.
- The original HPACK amplification class was previously reported (califio + our follow-up in May 2026).
- No new zero-day in the limit enforcement code of nginx or httpd was identified in this phase.
- We are publishing methodology, numbers, and reproduction material to help defenders validate their full set of controls, not to claim a new unpatched vulnerability in the already-fixed code paths.

## Suggested tone for different audiences

**LinkedIn / technical post:**
Focus on the gap between "per-request fix" and "realistic defense". Be clear that we are not claiming the patches are broken, but that they are incomplete without additional measures.

**Vendor / security list follow-up (if sending):**
Frame it as "additional validation and defense-in-depth research following the 2026 fixes". Offer the exact configurations and logs.

**Blog / detailed write-up:**
Use the structure from `NEW_GAP_FINDING.md` and `PATCH_BYPASS_REPORT.md`, with the explicit disclaimer that we stayed inside the per-request limits.

## Contact / coordination language

"We are publishing this as defensive research with full reproduction material. If any vendor believes a specific implementation detail in their current code constitutes a new security issue beyond configuration guidance, we are happy to coordinate privately."

---

This text is written to be accurate, non-sensational, and defensible. It positions the work as valuable hardening research rather than a new 0-day claim.