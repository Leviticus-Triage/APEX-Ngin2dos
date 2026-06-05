# Variants Reference

## Variant registry

Defined in `benchmark/variants.py`.

| Variant | Stack | Primary modes |
|---------|-------|---------------|
| `nginx` | nginx 1.24–1.29 | `apex`, `apex_scaled`, `apex_mp`, `churn`, `optimized_oom` |
| `httpd` | Apache httpd | `apex_cookie`, `apex_cookie_scaled` |
| `envoy` | Envoy proxy | `apex_cookie`, `apex_cookie_scaled` |
| `pingora` | Pingora (Rust) | `apex`, `apex_mp` |
| `iis` | Windows IIS | `apex_iis_mp` |

## Mode descriptions

### apex / apex_scaled
Multi-wave HPACK bombs on single TLS connections. `apex_scaled` uses batched parallel bombing to reach 100/100 connections at ~200 MB wire.

### apex_mp
Multiprocess variant for Pingora/nginx stress.

### apex_cookie / apex_cookie_scaled
Cookie-crumb encoding path for httpd/Envoy instead of raw HPACK table bombs.

### apex_iis_mp
Windows-only: PowerShell orchestrator spawns multiple Python workers against IIS.

### churn / optimized_oom
Research modes for connection churn and memory pressure experiments.

## CLI usage

```bash
python -m benchmark.benchmark_runner --variant nginx --mode apex_scaled \
  --host HOST --port PORT --connections 100
```

## MCP usage

Set `variant` and `profile` in `run_http2_bomb_test` tool call.

## PoC scripts

Vendor PoCs live under `vendor/califio-publications/`. `variants.poc_script_path()` resolves the correct script per variant/mode.
