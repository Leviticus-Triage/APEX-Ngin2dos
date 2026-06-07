# Optimization roadmap

Release hardening roadmap for APEX Ngin2dos — **status: complete (v1.0.1)**.

## Priority list

| Prio | Item | Status |
|------|------|--------|
| **P0** | Safe defaults (`127.0.0.1:8443`, `--allow-remote` gate) | Done |
| **P0** | Remove committed runtime logs / anonymized samples | Done |
| **P1** | Shared authorization module | Done |
| **P1** | pytest + ruff + expanded CI | Done |
| **P1** | English operator strings (MCP/CLI) | Done |
| **P2** | Documentation sync | Done |
| **P3** | Split `benchmark_runner.py` into modules | Done |
| **P3** | CI lab-replay smoke (Docker nginx) | Done |
| **P3** | Proxmox deploy script (repo-native paths) | Done |

## Verification

```bash
pip install -r requirements-dev.txt
./scripts/verify.sh                    # pytest + ruff + Docker lab smoke
./lab-replay/deploy_proxmox.sh smoke   # Proxmox E2E (manual)
```

## Module layout

```
benchmark/
  paths.py, models.py, probe.py, persistence.py, authorization.py
  attack_runner.py, cli.py, benchmark_runner.py
  campaigns/   # waves, multiprocess, apex, special, full
```

## Future (optional)

- Self-hosted CI runner on Proxmox for full OOM campaign on every push
- PyPI package (`pip install apex-ngin2dos`)
- Neutral public product name for major release
