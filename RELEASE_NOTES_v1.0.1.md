# APEX Ngin2dos v1.0.1

Release v1.0.1 — modular benchmark harness, safer defaults, and automated lab validation.

## Highlights

### Safety & hygiene
- Default harness target `127.0.0.1:8443` (lab loopback on runner VM, not laptop)
- `--allow-remote` gate for non-localhost targets
- Runtime logs gitignored; anonymized samples under `benchmark/logs/samples/`
- Shared `benchmark/authorization.py` for MCP/CLI gates
- English operator strings (MCP/CLI)

### Benchmark harness refactor
- Split monolithic `benchmark_runner.py` into:
  - `attack_runner.py`, `campaigns/`, `cli.py`, `probe.py`, `persistence.py`
- Backward-compatible `benchmark_runner.py` entry point
- CLI: `--hold` / `--drip` for burst mode; port fix (8443 no longer overridden to 443)

### Testing & CI
- `pytest` + `ruff` in CI
- New job **`lab-smoke`**: Docker nginx lab + burst 2 conn (`scripts/ci-lab-smoke.sh`)
- Proxmox deploy rewritten: `lab-replay/deploy_proxmox.sh smoke|campaign|deploy-only`

### Documentation
- `docs/OPTIMIZATION.md` — roadmap (P0–P3 status)
- README Quick Start: pytest → Proxmox deploy (not laptop localhost probe)
- `config/proxmox.env.example`
- Updated `docs/ARCHITECTURE.md`, `benchmark/README.md`, SKILL

## Upgrade

```bash
git pull
pip install -r requirements-dev.txt
pytest -q

# E2E on Proxmox
./lab-replay/deploy_proxmox.sh smoke
```

## Breaking changes

- MCP/CLI rejection prefix: `REJECTED:` (was `ABGELEHNT:`)
- Committed `benchmark/logs/*.csv` / `*.jsonl` removed — use `logs/samples/` for format reference

## Full changelog

- P0 safe defaults, log hygiene, authorization module
- P1 pytest (24 tests), ruff (full tree), expanded CI
- P3 harness modularization, CI lab-replay smoke
- Proxmox deploy uses repo root (not legacy plugin path)
- Hardening/docs anonymized for public repo
