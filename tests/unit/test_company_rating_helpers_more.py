from __future__ import annotations

from datetime import date, timedelta

import birre.domain.company_rating.service as s


def test_infection_narrative_variants() -> None:
    # Not an infection vector → unchanged
    assert (
        s._apply_infection_narrative_preference(
            "base", "patching_cadence", {"infection": {"description": "d"}}
        )
        == "base"
    )
    # Infection vector with only description → appended/returned gracefully
    out = s._apply_infection_narrative_preference(
        "Base", "botnet_infections", {"infection": {"description": "note"}}
    )
    assert "note" in (out or "")


def test_primary_port_and_asset_fallbacks() -> None:
    # No details → None
    assert s._determine_primary_asset({}, {}) is None
    # Non-int ports ignored
    assert s._determine_primary_port({"port_list": ["22"]}) is None
    # Detected service summary formatting fallback
    txt = s._normalize_detected_service_summary(
        "Detected service: SSH, version 1", None
    )
    assert "Detected service: SSH, version 1" in txt


def test_extract_policy_profile_from_dict_and_model() -> None:
    d = {
        "policy": {
            "profile": "relaxed",
            "severity_floor": "material",
            "supplements": [],
            "max_items": 0,
        }
    }
    assert s._extract_policy_profile(d) == "relaxed"
    model = s.TopFindings.model_validate(d | {"count": 0, "findings": []})
    assert s._extract_policy_profile(model) == "relaxed"


def test_aggregate_ratings_real_path_and_trend() -> None:
    base = date(2025, 8, 1)
    raw = [
        {"rating_date": (base + timedelta(days=i)).isoformat(), "rating": 700 + i}
        for i in range(0, 40, 5)
    ]
    series = s._aggregate_ratings(raw, horizon_days=56, mode="weekly")
    tr = s._compute_trend(series)
    assert set(tr.keys()) == {"direction", "change"}
