# Lab Setup

Local replay environments for safe benchmarking.

## nginx lab (port 8443)

```bash
cd lab-replay
docker compose up -d
curl -k https://127.0.0.1:8443/
```

Run benchmark:

```bash
python -m benchmark.benchmark_runner --variant nginx --mode apex_scaled \
  --host 127.0.0.1 --port 8443 --connections 100
```

## httpd lab (port 10080)

```bash
cd lab-replay-httpd
docker compose up -d
```

Cookie variant:

```bash
python -m benchmark.benchmark_runner --variant httpd --mode apex_cookie_scaled \
  --host 127.0.0.1 --port 10080
```

## Envoy lab (port 10000)

```bash
cd lab-replay-envoy
docker compose up -d
```

## Pingora

See `lab-replay/pingora/` for Rust Pingora proxy setup and `apex` / `apex_mp` profiles.

## A/B comparison

```bash
python -m benchmark.benchmark_runner --compare --variant nginx \
  --host 127.0.0.1 --port 8443
```

Logs land in `lab-replay/logs/`.

## Proxmox deployment

Scripts under `scripts/proxmox/` deploy labs to a Proxmox host. See main repo `docs/LAB_RESULTS.md` for verified campaign results.
