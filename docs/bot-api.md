# DG Bot API — Trade Picks for Polymarket / polybot

Stable HTTP API for external bots (e.g. **polybot**) to pull capital-bucket trade picks and place flat **$1 USD** stakes on Polymarket.

**Base URL (prod):** `https://dgs.staxa.cloud`  
**Base URL (local):** `http://127.0.0.1:8000`

---

## Auth

All `/api/bot/*` routes use the same key as the prematch feed.

| Header | Value |
| --- | --- |
| `X-Api-Key` | Value of env `BOT_API_KEY` on the DG server |

- If `BOT_API_KEY` is **set** on the server → requests **must** send a matching `X-Api-Key` or the API returns `401`.
- If `BOT_API_KEY` is **empty/unset** → auth is disabled (dev only). Do not rely on this in production.

```bash
curl -sS -H "X-Api-Key: $BOT_API_KEY" \
  "https://dgs.staxa.cloud/api/bot/trade-picks"
```

---

## Primary endpoint: Trade Picks

### `GET /api/bot/trade-picks`

Returns LIVE capital-bucket picks ready for placement.

#### Query parameters

| Param | Type | Default | Description |
| --- | --- | --- | --- |
| `open_only` | bool | `true` | `true` = open (placeable) picks only. Use this for trading. |
| `date` | string | — | Optional kickoff date `YYYY-MM-DD` in **IST**. Filters to that day’s fixtures. |
| `category` | string | — | Filter by LIVE category id (see below). |
| `strategy` | string | — | Filter: `main` \| `cs` \| `ev` \| `h2h` \| `arahus`. |

#### Examples

```bash
# Placeable queue (recommended for polybot)
curl -sS -H "X-Api-Key: $BOT_API_KEY" \
  "https://dgs.staxa.cloud/api/bot/trade-picks?open_only=true"

# One IST day, open only
curl -sS -H "X-Api-Key: $BOT_API_KEY" \
  "https://dgs.staxa.cloud/api/bot/trade-picks?date=2026-09-21&open_only=true"

# Single category
curl -sS -H "X-Api-Key: $BOT_API_KEY" \
  "https://dgs.staxa.cloud/api/bot/trade-picks?category=Main_filtered&strategy=main"
```

#### Response envelope

```json
{
  "schema_version": 1,
  "kind": "trade_picks",
  "generated_at": "2026-09-21T17:45:00+00:00",
  "flat_stake_usd": 1.0,
  "currency": "USD",
  "open_only": true,
  "pick_date": null,
  "live_category_ids": [
    "Main_filtered",
    "CS_CorrectScore_0_1",
    "CS_CorrectScore_2_1",
    "H2H_Over_2_5",
    "Arahus_filtered"
  ],
  "filters": { "category": null, "strategy": null },
  "count": 2,
  "picks": [ /* see pick object */ ]
}
```

| Field | Meaning |
| --- | --- |
| `schema_version` | Bump when breaking pick shape. Currently `1`. |
| `kind` | Always `"trade_picks"`. |
| `flat_stake_usd` | Always `1.0` — do not Kelly or re-size. |
| `live_category_ids` | Categories currently in LIVE state (stakeable). |
| `count` | `len(picks)`. |
| `picks` | Array of placeable (or filtered) picks. |

#### Pick object

```json
{
  "id": "83a05a11-d184-442a-82c4-7c7516dd33e8",
  "live_category": "Arahus_filtered",
  "strategy": "arahus",
  "strategy_label": "Arahus",
  "log_type": "arahus",
  "fixture_id": 1234567,
  "fixture": "Nijmegen vs GO Ahead",
  "home_team": "Nijmegen",
  "away_team": "GO Ahead",
  "league": "Eredivisie",
  "kickoff": "2026-09-20T14:45:00+00:00",
  "kickoff_ist_date": "2026-09-20",
  "kickoff_ist_time": "20:15",
  "market": "Over 2.5",
  "bet_type": "arahus_o25",
  "team": null,
  "odds": 1.42,
  "stake_usd": 1.0,
  "currency": "USD",
  "status": "open",
  "result": null
}
```

| Field | Type | Notes for implementers |
| --- | --- | --- |
| `id` | string | Stable DG bet id — use as client order idempotency key. |
| `live_category` | string | Capital bucket that qualified this pick. |
| `strategy` | string | `main` \| `cs` \| `ev` \| `h2h` \| `arahus` (family). |
| `log_type` | string | Underlying DG log (`arahus_v2`, `arahus_live_v1`, etc.). |
| `fixture_id` | int/string/null | DataGaffer id when slate-matched; may be `null`. |
| `fixture` | string | `"Home vs Away"`. |
| `home_team` / `away_team` | string/null | Parsed from `fixture`. |
| `league` | string | League name. |
| `kickoff` | string/null | ISO kickoff (prefer UTC/offset from source). |
| `kickoff_ist_date` | string | `YYYY-MM-DD` in Asia/Kolkata. |
| `market` | string | Human market label (`Over 2.5`, `Correct score 0-1`, `Team Over 1.5`, …). |
| `bet_type` | string | Internal DG bet type code. |
| `team` | string/null | Side/team when relevant (team totals, ML, CS scoreline). |
| `odds` | number/null | Decimal odds at log time. Skip if missing/`null`. |
| `stake_usd` | number | Always `1.0`. |
| `status` | string | `open` for placement; `settled` only if `open_only=false`. |
| `result` | string/null | `won` \| `lost` \| `push` when settled. |

---

## LIVE categories (stakeable)

Only these states appear in Trade Picks when LIVE. Demoted categories (e.g. `EV_Over_3_5` → LOGGING) are **excluded**.

| Category id | Strategy | Rule (summary) |
| --- | --- | --- |
| `Main_filtered` | main | Odds 1.30–1.49 **or** Over 2.5 **or** fav leagues; excludes Moneyline/BTTS/cups |
| `CS_CorrectScore_0_1` | cs | Correct score `0-1` |
| `CS_CorrectScore_2_1` | cs | Correct score `2-1` (decay watch) |
| `H2H_Over_2_5` | h2h | Over 2.5 |
| `Arahus_filtered` | arahus | Over 2.5 @ 1.30–1.49 **or** fav leagues; excludes BTTS |

Always trust `live_category_ids` in the response over this table — runtime promotions/demotions can change the set.

---

## Recommended polybot flow

1. **Poll** `GET /api/bot/trade-picks?open_only=true` on an interval (e.g. every 1–5 minutes).
2. **Dedupe** by `id` — never place twice for the same DG bet id.
3. **Skip** picks with `odds == null` or `status != "open"`.
4. **Map** `market` / `bet_type` / `team` / `home_team` / `away_team` / `kickoff` to a Polymarket market (your mapper).
5. **Size** every order at `stake_usd` ($1). Do not rescale.
6. Optionally cross-check model context via `GET /api/bot/prematch` using `fixture_id` when present.
7. Optionally resolve exact-score token prices via `GET /api/polymarket/exact-score?slug=…` for CS picks.

### Minimal TypeScript consumer sketch

```ts
type TradePick = {
  id: string;
  live_category: string;
  strategy: string;
  fixture: string;
  home_team: string | null;
  away_team: string | null;
  fixture_id: number | string | null;
  kickoff: string | null;
  market: string;
  bet_type: string;
  team: string | null;
  odds: number | null;
  stake_usd: number;
  status: string;
};

async function fetchTradePicks(baseUrl: string, apiKey: string): Promise<TradePick[]> {
  const res = await fetch(`${baseUrl}/api/bot/trade-picks?open_only=true`, {
    headers: { "X-Api-Key": apiKey },
  });
  if (res.status === 401) throw new Error("Invalid or missing X-Api-Key");
  if (!res.ok) throw new Error(`trade-picks HTTP ${res.status}`);
  const body = await res.json();
  if (body.kind !== "trade_picks") throw new Error("Unexpected feed kind");
  return (body.picks ?? []).filter(
    (p: TradePick) => p.status === "open" && p.odds != null && p.odds > 1
  );
}
```

---

## Related bot endpoints

Same auth header.

### `GET /api/bot/prematch`

Full pre-match model feed (fixtures, probs, book odds, optional +EV).

| Param | Default | Description |
| --- | --- | --- |
| `slate_only` | `false` | Limit to today’s slate window. |
| `plus_ev` | `true` | Include +EV market list per fixture. |

### `GET /api/bot/prematch/{fixture_id}`

Single fixture prematch payload.

### `GET /api/polymarket/exact-score?slug=`

Football exact-score Yes prices (Gamma + CLOB). Useful for CS picks.

### `GET /api/polymarket/exact-score/prices?slug=`

Prices array only.

### UI / unauthenticated helpers (not for production bot trading)

| Endpoint | Notes |
| --- | --- |
| `GET /api/trade-picks` | Dashboard JSON (no bot key). Prefer `/api/bot/trade-picks`. |
| `GET /api/trade-picks/export` | CSV download for humans. |
| `GET /trade-picks` | HTML UI. |
| `GET /health` | `{ "ok": true }` — no auth. |

---

## Errors

| HTTP | When |
| --- | --- |
| `200` | Success. |
| `401` | Missing/invalid `X-Api-Key` when `BOT_API_KEY` is configured. |
| `422` | Invalid query types (FastAPI validation). |
| `500` | Server error — retry with backoff. |

Empty book is still `200` with `"count": 0` and `"picks": []`.

---

## Compatibility notes

- **Schema:** if `schema_version` increases, read the changelog before deploying polybot.
- **Idempotency:** treat `id` as unique per pick forever.
- **Timezone:** filter `date=` is **IST** (`Asia/Kolkata`); `kickoff` is source ISO.
- **LM / NO strategies** are never included.
- **Demoted LIVE categories** (LOGGING/TRACKING) never appear in this feed.

---

## Changelog

| Date | Change |
| --- | --- |
| 2026-09-21 | Initial `GET /api/bot/trade-picks` (`schema_version: 1`). `EV_Over_3_5` demoted from LIVE. |
