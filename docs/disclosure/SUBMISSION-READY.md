# CVE Submission — READY TO SEND

**Reporter:** Daniel F. Hensen <3xodu2904@gmail.com>  
**PGP:** `FCBC28648F3E7FD91E6C072FE0BC23D2A274D25D`  
**Date:** 2026-06-17

---

## 1. Apache (send first)

| Item | Path |
|------|------|
| Email body | `submission/apache/EMAIL-READY.txt` |
| Report | `submission/apache/VENDOR-REPORT-APACHE-CVE-CANDIDATE.md` |
| Evidence | `submission/apache/evidence_fa94b7ad.json`, `evidence_d6b2bce1.json` |
| Bundle (signed) | `submission/apache/apache-cve-evidence.tar.gz` + `.asc` |

**To:** security@apache.org  
**Subject:** Security: mod_http2 post-2.0.41 DoS via fat-cookie HPACK chain (CVE-2026-49975 incomplete fix)

---

## 2. nginx (send after Apache)

| Item | Path |
|------|------|
| Email body | `submission/nginx/EMAIL-READY.txt` |
| Report | `submission/nginx/VENDOR-REPORT-NGINX-COOKIE-BYPASS.md` |
| Evidence | `submission/nginx/r10_cookie_8447.json` |
| Bundle (signed) | `submission/nginx/nginx-cookie-bypass-evidence.tar.gz` + `.asc` |

**To:** security@nginx.org  
**Subject:** Security: max_headers bypass via HTTP/2 cookie crumbs (nginx >= 1.29.8)

---

## One-command send (opens mail client)

```bash
cd /home/danii/APEX-Ngin2dos
./scripts/send-cve-submission.sh apache   # review → Send
./scripts/send-cve-submission.sh nginx    # after Apache sent
```

Or both interactively:

```bash
./scripts/send-cve-submission.sh both
```

---

## Manual send (Gmail web)

1. Compose to security@apache.org
2. Paste body from `submission/apache/EMAIL-READY.txt`
3. Attach `apache-cve-evidence.tar.gz` and `.asc`
4. Send → repeat for nginx

---

## Post-send checklist

- [x] Apache mail sent (2026-06-17, d.hensen2904@gmail.com)
- [ ] nginx mail sent
- [ ] Log vendor ticket numbers when received
- [ ] No LinkedIn post until vendor responds or 90-day embargo

See `docs/disclosure/SUBMISSION-LOG.md` for details.
