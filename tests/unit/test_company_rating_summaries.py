from __future__ import annotations

from datetime import UTC, datetime

import birre.domain.company_rating.service as s


def test_summarize_current_rating_and_legend() -> None:
    company = {"current_rating": 735}
    value, color = s._summarize_current_rating(company)
    assert value == 735 and color == "yellow"
    legend = s._build_rating_legend_entries()
    assert [e.color for e in legend] == ["red", "yellow", "green"]


def test_extract_policy_profile() -> None:
    assert s._extract_policy_profile({}) is None
    payload = {"policy": {"profile": "relaxed"}}
    assert s._extract_policy_profile(payload) == "relaxed"


def test_calculate_rating_trend_summaries(monkeypatch) -> None:  # noqa: ANN001
    # Bypass module's datetime.UTC usage by stubbing _aggregate_ratings
    def _fake_agg(raw, horizon_days, mode):  # noqa: ANN001
        a = (datetime(2025, 1, 1, tzinfo=UTC), 700.0)
        b = (datetime(2025, 1, 15, tzinfo=UTC), 720.0)
        return [a, b]

    monkeypatch.setattr(s, "_aggregate_ratings", _fake_agg)
    company = {"ratings": []}
    weekly, yearly = s._calculate_rating_trend_summaries(company)
    assert weekly.direction in {
        "up",
        "slightly up",
        "stable",
        "slightly down",
        "down",
        "insufficient data",
    }
    assert yearly.direction in {
        "up",
        "slightly up",
        "stable",
        "slightly down",
        "down",
        "insufficient data",
    }
