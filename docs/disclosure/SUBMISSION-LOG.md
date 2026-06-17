# CVE Vendor Submission Log

| Date (UTC) | Vendor | To | Subject | Status | Notes |
|------------|--------|-----|---------|--------|-------|
| 2026-06-17 | Apache httpd | security@apache.org | mod_http2 post-2.0.41 fat-cookie DoS (CVE-2026-49975 incomplete fix) | **Sent** | From d.hensen2904@gmail.com; runs fa94b7ad, d6b2bce1; 90-day embargo |
| — | nginx | security@nginx.org | max_headers cookie crumb bypass (R10) | Pending | Send after Apache response or separate track |

## Apache attachments sent

- `VENDOR-REPORT-APACHE-CVE-CANDIDATE.md`
- `evidence_fa94b7ad.json`
- `evidence_d6b2bce1.json`
- `apache-cve-evidence.tar.gz`

## Post-send repo fixes (2026-06-17)

- `scripts/vendor-repro-apache.sh` — one-command vendor repro
- `docs/disclosure/submission/apache/REPRODUCTION.md` — corrected import path (`cd benchmark`)

If Apache reports `ImportError` on email repro snippet, reply with link to `REPRODUCTION.md` or `./scripts/vendor-repro-apache.sh`.
