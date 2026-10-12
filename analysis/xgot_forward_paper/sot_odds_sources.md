# SOT odds sources for xGOT research (variant E)

Date: 2026-10-12  
Status: research track only — not LIVE

## Findings

### 1. DataGaffer `all_odds.json`

- Feed is already ingested (`app/dg_feeds.py` → `all_odds_by_match`).
- Current book-odds helper (`app/h2h_book_odds.py`) prices **corners** only: one main corners O/U line per fixture.
- Slate match rows expose `sot_over_odds` for xGOT (`build_xgot_picks`), but production fills for SOT from DG are typically **null** — SOT volume was logged for research without priced ROI.
- Fixture dashboard iterates `all_odds.markets` generically; no dedicated SOT market extractor exists today.

**Conclusion:** Do not assume SOT prices are available from `all_odds` until a sample scrape shows `shots_on_target` / SOT market keys. Treat as unverified.

### 2. Polymarket

- H2H strategy documents SOT as **manual odds only** — not listed on Polymarket (`app/h2h_strat.py` header).
- Same constraint applies to xGOT variant E for financial ROI.

### 3. API-Football / settlement path

- API-Football supplies **settlement** stats (`shots on goal` / `shots on target`) via `auto_resolve` / H2H prop enrichment — useful for W/L outcome, not entry odds.
- No existing AF odds endpoint is wired for SOT lines in this repo.

### 4. Manual / pending-odds workflow (recommended interim)

- Reuse H2H pattern: `set_h2h_manual_odds` style API for open SOT rows, or a small admin path that updates `bet_entries.odds` for `xgot_sot_*` / `xgot_fw_e` only.
- Until odds are filled: **outcome tracked; financial ROI = N/A** (enforced by `app/xgot_metrics.financial_pnl`).

## Recommendation

| Priority | Action |
|---|---|
| P0 | Keep variant E outcome-only; reports mark ROI unavailable when odds null |
| P1 | Sample a live `all_odds.json` for SOT/shots markets; if present, add extractor parallel to corners |
| P2 | Add pending-odds UI/API (mirror H2H SOT) for research ledgers only |
| — | Do **not** synthetic-price at 2.0; do **not** enable LIVE |

## Strategy version

Tied to forward paper freeze: `xgot-fw-2026-10-12.1`.
