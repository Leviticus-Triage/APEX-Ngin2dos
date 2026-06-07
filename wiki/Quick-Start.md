# Quick Start

## Prerequisites

- Python 3.10+
- **Written authorization** for any non-local target
- Proxmox ai-workstation SSH access for full E2E (recommended)

## Install

```bash
git clone https://github.com/Leviticus-Triage/APEX-Ngin2dos.git
cd APEX-Ngin2dos
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

## Proxmox E2E (recommended)

Deploy and run tests **on ai-workstation** — not on your laptop localhost:

```bash
chmod +x lab-replay/deploy_proxmox.sh
./lab-replay/deploy_proxmox.sh smoke
./lab-replay/deploy_proxmox.sh campaign   # full OOM campaign
```

## Local Docker lab (optional)

```bash
./lab-replay/replay.sh start 8g
./lab-replay/replay.sh probe
./lab-replay/replay.sh attack 5
```

## Harness on lab VM

```bash
python3 benchmark/benchmark_runner.py --host 127.0.0.1 --port 8443 \
  --variant nginx --mode apex_scaled --connections 20
```

## Interactive CLI

```bash
./bin/http2-bomb menu
./bin/http2-bomb benchmark --host TARGET --scope "Ticket-123" --yes \
  --mode apex_scaled --connections 20
```

## MCP (Cursor)

Add to Cursor MCP settings — see [MCP Configuration](MCP-Config).

## Next steps

- [Lab Setup](Lab-Setup) — nginx/httpd/envoy replay targets
- [Variants](Variants) — choose the right attack profile
