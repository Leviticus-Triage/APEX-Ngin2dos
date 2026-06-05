# Proxmox Lab Campaign Summary — 2026-06-04

**Run ID:** 20260604_202513  
**Host:** danii@192.168.2.116 (ai-workstation)  
**Target:** nginx-h2-lab-replay (nginx/1.24.0, 8 GiB memory cap, single worker)

## Success Criteria — MET

- [x] 50 connections fill 8 GiB container cap
- [x] HTTP probe timeouts during attack (10s)
- [x] Worker RSS ~8.1 GiB
- [x] Sustained 3×50 without restart keeps memory at cap
- [x] Full CSV timeseries logging

## Timeline

| Time (UTC) | Phase | Conn | RSS (MiB) | Container | Probe |
|------------|-------|------|-----------|-----------|-------|
| 20:25:21 | during | 15 | 4222 | 4.1 GiB | timeout |
| 20:27:27 | after | 15 | 663 | 659 MiB | 200 OK |
| 20:28:05 | during | 50 | 8162 | **8 GiB FULL** | timeout |
| 20:29:58 | after | 50 | 8170 | 8 GiB FULL | timeout |
| 20:32:31 | recovered | 50 | 5 | 1.7 MiB | 200 OK (after restart) |
| 20:33:42 | sustained | 50 | 8158 | 7.997 GiB | timeout |
| 20:36:28 | sustained | 50 | 8149 | 8 GiB | timeout |

## Commands

```bash
ssh danii@192.168.2.116
cd ~/http2-bomb-lab/lab-replay
./replay.sh start 8g
./run_proxmox_campaign.sh
```

## Log Files

- Remote: `~/http2-bomb-lab/lab-replay/logs/campaign_20260604_202513.log`
- Local: `lab-replay/logs/campaign_20260604_202513.log`
- CSV: `lab-replay/logs/proxmox_lab_timeseries.csv`
