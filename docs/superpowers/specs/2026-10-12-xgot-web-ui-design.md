# xGOT Forward / Audit web UI

Date: 2026-10-12  
Status: Approved — implementing  
Depends on: research validation (`xgot-fw-2026-10-12.1`)

## Goal

Surface forensic audit + forward-paper hub + variant B–E logs in the DG website. Enable research sync on VPS.

## Routes

| Route | Purpose |
|---|---|
| `/xgot-forward` | Hub: A vs B–E metrics (honest ROI), snapshots, links |
| `/xgot-audit` | Read-only render of `analysis/xgot_forensic_audit/REPORT.md` |
| `/xgot-bet-log` | Baseline A (unchanged) |
| `/xgot-fw-{b,c,d,e}-bet-log` | Research variant logs |

## Constraints

- No LIVE / Trade Picks
- Null odds ⇒ financial ROI N/A
- `XGOT_RESEARCH_SYNC_ENABLED=true` on VPS after deploy
