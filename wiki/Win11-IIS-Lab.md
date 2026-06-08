# Win11 IIS Lab

Windows IIS multiprocess HPACK bomb testing via PowerShell orchestrator.

## Lab topology

| Component | Detail |
|-----------|--------|
| Target | Windows 11 + IIS (W3SVC) |
| Orchestrator | `benchmark/iis_apex_orchestrator.ps1` |
| Python runner | `benchmark/iis_apex_runner.py` |
| Mode | `apex_iis_mp` |

## Setup (Win11 VM)

1. Enable IIS Web Server role + subfeatures (W3SVC)
2. Install Python 3.12+ to e.g. `C:\APEX-Ngin2dos\Python312\`
3. Clone/copy repo to `C:\APEX-Ngin2dos\`
4. Run `scripts/setup_win11_iis_lab.ps1` or `fix_iis_win11.bat`

## Run from Linux attacker

```bash
python -m benchmark.iis_apex_runner \
  --target-host 192.168.x.x \
  --preset apex_iis_mp \
  --processes 4
```

**Note:** PowerShell parameter is `-TargetHost` (alias `-Host`) because `$Host` is reserved.

## Verified behavior

- Pre-attack: HTTPS 200
- During `apex_iis_mp`: timeouts / service degradation
- Post-attack: W3SVC self-recovery without manual restart

## Logs

Orchestrator writes separate `_out.log` and `_err.log` per worker process.

## Proxmox guest exec

From Proxmox host:

```bash
ssh root@PROXMOX 'qm guest exec 101 -- cmd.exe /c hostname'
```

Deploy scripts via HTTP file server on Proxmox host port 8888.
