from __future__ import annotations

from datetime import UTC, datetime

from birre.domain.company_rating import service as rating_service


def test_rating_color_ranges() -> None:
    assert rating_service._rating_color(None) is None
    assert rating_service._rating_color(750) == "green"
    assert rating_service._rating_color(700) == "yellow"
    assert rating_service._rating_color(600) == "red"


def test_aggregate_and_trend_helpers() -> None:
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    raw = [{"rating_date": today, "rating": 700}, {"rating_date": today, "rating": 720}]
    series = rating_service._aggregate_ratings(raw, horizon_days=10, mode="daily")
    assert series and isinstance(series[0][1], float)
    trend = rating_service._compute_trend(series)
    assert "direction" in trend


def test_severity_scores_and_sorting() -> None:
    item = {"severity": 9, "details": {"cvss": {"base": 5}}}
    assert rating_service._derive_numeric_severity_score(item) == 9
    assert rating_service._build_finding_sort_key(item)
    assert rating_service._select_top_finding_candidates([item], k=1)


def test_normalize_finding_entry_returns_fields() -> None:
    item = {
        "details": {
            "display_name": "Alert",
            "description": "Details",
            "remediations": [{"help_text": "Fix it"}],
        },
        "risk_vector": "botnet_infections",
        "first_seen": "2024-01-01",
    }
    normalized = rating_service._normalize_finding_entry(item)
    assert normalized["finding"] == "Alert"
    assert "Fix it" in normalized["details"]


def test_normalize_top_findings_returns_entries() -> None:
    results = [{"details": {"name": "X"}, "severity": 1}]
    normalized = rating_service._normalize_top_findings(results)
    assert normalized and "finding" in normalized[0]
