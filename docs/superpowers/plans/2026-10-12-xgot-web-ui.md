# xGOT Web UI Implementation Plan

> **For agentic workers:** implement task-by-task; user approved Approach A + enable sync.

**Goal:** Hub, audit page, FW B–E logs in nav; enable research sync on VPS.

## Tasks

1. `app/xgot_web.py` — hub summary + audit markdown load/render helpers  
2. Parameterize `templates/xgot_bet_log.html`; add `xgot_forward.html`, `xgot_audit.html`  
3. Wire routes/APIs in `main.py`; resync jobs for `xgot_fw_*`  
4. Update `app_nav.html`  
5. Tests for hub summary + audit load  
6. Commit, deploy, set `XGOT_RESEARCH_SYNC_ENABLED=true`
