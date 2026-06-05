# APEX Ngin2dos v1.0.0

**Initial public research release** — multi-variant HTTP/2 HPACK benchmark harness extending [califio/publications](https://github.com/califio/publications/tree/main/MADBugs/http2-bomb).

## Highlights

### APEX v2 attack engine
- Multi-wave bombs per TLS connection (nginx/Pingora)
- **Batched parallel bombing** — fixes 44-conn ceiling → **100/100** at ~200 MB wire
- Cookie-crumb apex for **httpd** and **Envoy**
- Windows **IIS multiprocess orchestrator** (`apex_iis_mp`)
- Modes: `apex`, `apex_scaled`, `apex_mp`, `apex_cookie*`, `churn`, `optimized_oom`

### Operator interfaces
- **MCP server** for Cursor IDE
- **Standalone CLI** (`bin/http2-bomb`) with ASCII menu
- **Tunnel routing**: SOCKS5, HTTP, Tor, proxychains, ngrok, cloudflared

### Lab replay environments
- nginx (:8443), httpd (:10080), Envoy (:10000), Pingora
- Proxmox deploy scripts + A/B compare tooling
- Win11 IIS lab documentation

### Verified lab results
| Variant | Result |
|---------|--------|
| nginx `apex_scaled` | **100/100** bomb OK, ~200 MB wire, 8 GiB OOM |
| httpd `apex_cookie_scaled` | **12/12** bomb OK |
| Win11 IIS `apex_iis_mp` | Service degradation + self-recovery |

### Hardening
- Sample nginx configs for 1.24 (defense-in-depth) and 1.29.8+ (`http2_max_headers`)

## Install

```bash
git clone https://github.com/Leviticus-Triage/APEX-Ngin2dos.git
cd APEX-Ngin2dos
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
./bin/http2-bomb menu
```

## Documentation

- [README](https://github.com/Leviticus-Triage/APEX-Ngin2dos#readme)
- [Architecture](https://github.com/Leviticus-Triage/APEX-Ngin2dos/blob/main/docs/ARCHITECTURE.md)
- [Lab results](https://github.com/Leviticus-Triage/APEX-Ngin2dos/blob/main/docs/LAB_RESULTS.md)
- [Wiki](https://github.com/Leviticus-Triage/APEX-Ngin2dos/wiki)

## Legal

**Authorized targets only.** See [SECURITY.md](https://github.com/Leviticus-Triage/APEX-Ngin2dos/blob/main/SECURITY.md).

## Full changelog

- Initial release from http2-bomb-mcp research project
- 123 files: harness, MCP, CLI, labs, vendor PoCs, lab logs
- CI: Python syntax check on push
