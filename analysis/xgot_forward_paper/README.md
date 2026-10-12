# xGOT forward paper book

Isolated research ledgers for frozen candidates B–E (`xgot_fw_*`), plus honest metrics that never treat null odds as 2.0.

## Env flags

| Variable | Default | Meaning |
|---|---|---|
| `XGOT_RESEARCH_SYNC_ENABLED` | `false` | When true, post-refresh sync inserts variants B–E |
| `XGOT_RESEARCH_ALLOW_POST_KICKOFF` | `false` | When false, research sync drops post-kickoff picks |

Baseline `log_type=xgot` always syncs (pick rules unchanged). Never enable LIVE / Trade Picks for xGOT.

## Report

```bash
python analysis/xgot_forward_paper/run_report.py
```

Writes dated JSON/MD under `output/`.

## Deploy checklist

1. Pull code; migrate runs via `init_db` (`dg_fixture_snapshots` + bet metadata cols).
2. Confirm refresh writes snapshots (log line `DG snapshot saved`).
3. Leave `XGOT_RESEARCH_SYNC_ENABLED=false` until forward collection is approved.
4. After approval: set env true, restart, verify `xgot_fw_b`…`e` receive inserts and auto-resolve includes them.
5. Run first dated report; note `XGOT_FW_VERSION=xgot-fw-2026-10-12.1`.
