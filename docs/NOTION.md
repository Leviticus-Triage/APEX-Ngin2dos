# Notion Research Documentation

Primary living document for this project:

**[HTTP/2 Bomb — MCP Plugin & OOM Benchmark](https://app.notion.com/p/37530537269d8196a477e358073e8627)**

## Sync with this repository

| Notion section | Repo equivalent |
|----------------|-----------------|
| Project goals & MCP setup | `README.md` |
| Benchmark campaign results | `docs/LAB_RESULTS.md`, `lab-replay/logs/` |
| Hardening examples | `hardening/README.md` |
| Proxmox lab methodology | `lab-replay/logs/PROXMOX_CAMPAIGN_SUMMARY.md` |
| Multi-variant APEX rollout | `lab-replay/logs/MULTI_VARIANT_APEX_VERIFICATION.md` |
| Win11 IIS session | `lab-replay/logs/WIN11_IIS_LAB_20260605.md` |
| E2E verification | `lab-replay/logs/E2E_TEST_20260605.md` |

## Key Notion findings (summary)

- **Goal:** Operationalize califio PoCs as MCP plugin + logged OOM benchmark harness.
- **Authorized target:** private nginx 1.24.0 lab — vulnerable; patch in nginx ≥1.29.8 (hostname/IP not in repo).
- **Lab parity:** 50 connections fill 8 GiB Docker container on Proxmox ai-workstation.
- **Production ceiling:** ~31 concurrent full bombs from single public IP.
- **Best single-client strategy:** `optimized_oom` — 4096 headers × 256 streams × 80 conn/cycle.
- **Hardening priority:** Upgrade nginx + `http2_max_headers 100`; interim limit_conn / lower streams.

When updating Notion, cross-link to this GitHub repository for reproducible artifacts and version-controlled configs.
