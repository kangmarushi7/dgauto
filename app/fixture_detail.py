from __future__ import annotations

from typing import Any

from app.dg_feeds import lookup_extra_for_fixture
from app.fixture_math import edge, fmt, implied_prob, num
from app.fixture_dashboard import build_fixture_dashboard

# Re-export for any legacy imports
_edge = edge
_fmt = fmt
_implied_prob = implied_prob
_num = num


def build_fixture_detail(
    raw: dict[str, Any],
    match: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Institutional dashboard payload (consolidated)."""
    return build_fixture_dashboard(raw, match, extra)


def find_raw_fixture(fixtures_by_id: dict[str, Any], fixture_id: str | int) -> dict[str, Any] | None:
    key = str(fixture_id)
    if key in fixtures_by_id:
        return fixtures_by_id[key]
    try:
        return fixtures_by_id.get(str(int(fixture_id)))
    except (TypeError, ValueError):
        return None


def get_fixture_detail_from_state(state: dict[str, Any], fixture_id: str | int) -> dict[str, Any] | None:
    fixtures_by_id = state.get("fixtures_by_id") or {}
    raw = find_raw_fixture(fixtures_by_id, fixture_id)
    if not raw:
        return None
    match = None
    for m in state.get("matches") or []:
        if str(m.get("fixture_id")) == str(fixture_id):
            match = m
            break
    indexes = state.get("dg_extra_indexes") or {}
    extra = lookup_extra_for_fixture(raw, indexes) if indexes else {}
    return build_fixture_detail(raw, match, extra=extra)
