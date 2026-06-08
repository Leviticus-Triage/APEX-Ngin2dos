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
pip install -r requirements-dev.txt
pytest -q
ruff check .
```

**Integration / OOM tests** run on Proxmox ai-workstation, not on your laptop:

```bash
./lab-replay/deploy_proxmox.sh smoke      # quick remote validation
./lab-replay/deploy_proxmox.sh campaign   # full logged campaign
```

See [`docs/OPTIMIZATION.md`](docs/OPTIMIZATION.md) for the v1.0.1 release roadmap.

Full local check (unit + Docker lab smoke):

```bash
chmod +x scripts/verify.sh
./scripts/verify.sh
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
