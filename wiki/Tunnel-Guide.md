# Tunnel Guide

Route benchmark traffic through proxies for red-team lab scenarios.

## CLI tunnel menu

```bash
./bin/http2-bomb menu
# Select "Tunnel routing"
```

## SOCKS5

```bash
python -m benchmark.tunnel_runner --socks5 127.0.0.1:1080 \
  --host target.lab --port 443 --mode probe
```

## HTTP proxy

```bash
python -m benchmark.tunnel_runner --http-proxy http://127.0.0.1:8080 ...
```

## Tor (proxychains)

Ensure `proxychains4` is configured, then:

```bash
python -m benchmark.tunnel_runner --tor --host target.lab --port 443
```

## ngrok

Expose local lab or tunnel outbound:

```bash
python -m benchmark.tunnel_runner --ngrok --ngrok-region eu ...
```

## cloudflared

```bash
python -m benchmark.tunnel_runner --cloudflared ...
```

## Implementation

See `benchmark/tunnel.py` and `benchmark/tunnel_runner.py` for routing logic. All tunnel modes still enforce the authorization gate for bomb profiles.
