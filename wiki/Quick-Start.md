# Quick Start

## Prerequisites

- Python 3.10+
- OpenSSL / TLS-capable target (for probes)
- **Written authorization** for any non-local target

## Install

```bash
git clone https://github.com/Leviticus-Triage/APEX-Ngin2dos.git
cd APEX-Ngin2dos
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Interactive menu

```bash
./bin/http2-bomb menu
```

## Probe only (safe)

Check HTTP/2 support without sending bombs:

```bash
python -m benchmark.http2_bomb_cli probe --host 127.0.0.1 --port 8443
```

## Run a scaled nginx variant

```bash
python -m benchmark.benchmark_runner \
  --variant nginx \
  --mode apex_scaled \
  --host 127.0.0.1 \
  --port 8443 \
  --connections 100
```

## MCP (Cursor)

Add to Cursor MCP settings — see [MCP Configuration](MCP-Config).

## Next steps

- [Lab Setup](Lab-Setup) — spin up local replay targets
- [Variants](Variants) — choose the right attack profile
