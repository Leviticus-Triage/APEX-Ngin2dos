#!/usr/bin/env bash
# Probability-upgrade evidence pack for Apache mod_http2 report.
# Authorized lab use only.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-10080}"
CONNS="${CONNS:-200 400 800 1200}"
OUT="${ROOT}/lab-replay/logs/apache_probability_upgrade_$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "$OUT"

if ! docker ps --format '{{.Names}}' | grep -qx 'httpd-h2-lab-replay'; then
  echo "httpd lab not running. Start with:"
  echo "  ./lab-replay-httpd/replay.sh build && ./lab-replay-httpd/replay.sh start 8g"
  exit 1
fi

{
  echo "=== timestamp ==="
  date -u
  echo "=== host/port ==="
  echo "${HOST}:${PORT}"
  echo "=== httpd version ==="
  docker exec httpd-h2-lab-replay httpd -v 2>&1 || true
  echo "=== httpd modules ==="
  docker exec httpd-h2-lab-replay httpd -M 2>&1 | grep -i http2 || true
} > "${OUT}/environment.txt"

run_case() {
  local label="$1"
  local conns="$2"
  local profile="$3"
  local raw="${OUT}/${label}.raw"
  local clean="${OUT}/${label}.json"
  echo "[upgrade] running ${label} (${conns}, ${profile})"
  (
    cd "${ROOT}/benchmark"
    python3 - "$HOST" "$PORT" "$conns" "$label" "$profile" <<'PY'
import json
import sys
from attack_config import profile_apex_cookie_scaled, profile_patch_bypass_httpd_fat
from attack_runner import run_cookie_attack

host = sys.argv[1]
port = int(sys.argv[2])
conns = int(sys.argv[3])
label = sys.argv[4]
profile = sys.argv[5]

if profile == "fat":
    cfg = profile_patch_bypass_httpd_fat(conns)
else:
    cfg = profile_apex_cookie_scaled("httpd", conns)

r = run_cookie_attack(label, host, port, conns, cfg, variant_id="httpd")

counted_headers_per_stream_est = None
if hasattr(cfg, "refs"):
    # Approximation: pseudo/header overhead + cookie refs on counted path.
    counted_headers_per_stream_est = int(cfg.refs) + 5

out = {
    "run_id": r.run_id,
    "strategy": r.strategy,
    "target": r.target,
    "profile": profile,
    "connections_requested": r.connections_requested,
    "connections_established": r.connections_established,
    "connections_bomb_ok": r.connections_bomb_ok,
    "wire_mb": round(r.wire_mb, 2),
    "oom_likely": r.oom_likely,
    "server_down": r.server_down,
    "probe_worst_latency": r.probe_worst_latency,
    "duration_sec": round(r.duration_sec, 1),
    "est_server_mb": r.extra.get("est_server_mb"),
    "attack_config": r.extra.get("attack_config"),
    "counted_headers_per_stream_est": counted_headers_per_stream_est,
    "limit_request_fields_default": 100,
}
print(json.dumps(out, indent=2))
PY
  ) > "${raw}"

  # run_cookie_attack prints a full result JSON; keep only the last JSON object
  # (the normalized metrics payload emitted by this script).
  python3 - "${raw}" > "${clean}" <<'PY'
import json
import sys

text = open(sys.argv[1], "r", encoding="utf-8").read()
dec = json.JSONDecoder()
idx = 0
objs = []
while idx < len(text):
    while idx < len(text) and text[idx].isspace():
        idx += 1
    if idx >= len(text):
        break
    obj, end = dec.raw_decode(text, idx)
    objs.append(obj)
    idx = end

if not objs:
    raise SystemExit("no JSON object parsed from run output")

print(json.dumps(objs[-1], indent=2))
PY
  rm -f "${raw}"
}

# Control first: original empty-cookie vector should stay flat on patch.
run_case "empty_control_44" 44 "empty"

for c in $CONNS; do
  run_case "fat_${c}" "$c" "fat"
done

python3 - "$OUT" <<'PY'
import glob
import json
import os
import statistics
import sys

out = sys.argv[1]
fat_paths = sorted(glob.glob(os.path.join(out, "fat_*.json")))
fat = [json.load(open(p, "r", encoding="utf-8")) for p in fat_paths]
control_path = os.path.join(out, "empty_control_44.json")
control = json.load(open(control_path, "r", encoding="utf-8"))

def ratio(a, b):
    if not b:
        return None
    return round(a / b, 2)

for row in fat:
    row["bomb_success_rate"] = ratio(row["connections_bomb_ok"], row["connections_requested"])
    row["est_to_wire_ratio"] = ratio(row.get("est_server_mb") or 0, row["wire_mb"])

threshold = None
for row in fat:
    if row["server_down"] or row["oom_likely"] or ((row["probe_worst_latency"] or 0) >= 5.0):
        threshold = row
        break

summary = {
    "control_empty_cookie_baseline": {
        "run_id": control["run_id"],
        "connections_bomb_ok": control["connections_bomb_ok"],
        "oom_likely": control["oom_likely"],
        "server_down": control["server_down"],
    },
    "fat_matrix": fat,
    "first_degradation_threshold": threshold,
    "median_est_to_wire_ratio": round(
        statistics.median([r["est_to_wire_ratio"] for r in fat if r["est_to_wire_ratio"] is not None]), 2
    ) if fat else None,
}

with open(os.path.join(out, "probability_upgrade_summary.json"), "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2)

lines = []
lines.append("# Apache Probability Upgrade Summary")
lines.append("")
lines.append("## Metrics")
lines.append("- **M1 Reproducibility threshold:** first connection level that causes server_down/oom/high latency.")
lines.append("- **M2 Efficiency slope:** estimated server memory vs wire MB (`est_to_wire_ratio`).")
lines.append("- **M3 Limit compliance proof:** counted headers per stream estimate remains <= LimitRequestFields (100).")
lines.append("")
lines.append("## Control (empty-cookie baseline on patched)")
lines.append(
    f"- run `{control['run_id']}`: bomb_ok={control['connections_bomb_ok']}, "
    f"oom={control['oom_likely']}, down={control['server_down']}"
)
lines.append("")
lines.append("## Fat-cookie matrix")
for r in fat:
    lines.append(
        f"- `{r['strategy']}`: req={r['connections_requested']} ok={r['connections_bomb_ok']} "
        f"wire={r['wire_mb']}MB est={r.get('est_server_mb')}MB est/wire={r['est_to_wire_ratio']} "
        f"lat={r['probe_worst_latency']} oom={r['oom_likely']} down={r['server_down']}"
    )
lines.append("")
if threshold:
    lines.append("## First degradation threshold")
    lines.append(
        f"- `{threshold['strategy']}` @ {threshold['connections_requested']} connections "
        f"(oom={threshold['oom_likely']} down={threshold['server_down']} "
        f"lat={threshold['probe_worst_latency']})"
    )
else:
    lines.append("## First degradation threshold")
    lines.append("- No degradation threshold hit in this matrix.")

with open(os.path.join(out, "probability_upgrade_summary.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
PY

echo "[upgrade] wrote evidence to: ${OUT}"
echo "[upgrade] summary json: ${OUT}/probability_upgrade_summary.json"
echo "[upgrade] summary md:   ${OUT}/probability_upgrade_summary.md"
