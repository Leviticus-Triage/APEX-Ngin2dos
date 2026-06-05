# Contributing

Thank you for contributing to APEX Ngin2dos. This project focuses on **reproducible, authorized** HTTP/2 security research.

## What we welcome

- Lab result reproductions with CSV/JSONL artifacts (sanitized targets)
- New variant integrations following `benchmark/variants.py` patterns
- Documentation improvements
- Hardening configs for additional stacks
- Tunnel provider integrations

## What we do not accept

- Changes that remove authorization gates
- Default targets pointing at third-party infrastructure
- Committed secrets (`allowed_targets.json`, tunnel credentials)

## Development setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 -m py_compile benchmark/*.py http2_bomb_mcp.py http2_bomb_cli.py
```

## Pull request checklist

- [ ] Authorized-use warnings preserved
- [ ] Lab-only defaults for destructive modes
- [ ] Docs updated if CLI/MCP surface changes
- [ ] No secrets or production hostnames unless anonymized

## Lab data format

When adding benchmark results to `lab-replay/logs/`:

- Include date, variant, mode, connections, bomb_ok, wire_mb, peak RSS if available
- Reference run_id from `benchmark/logs/benchmark_runs.jsonl`
- Note container memory cap and server version
