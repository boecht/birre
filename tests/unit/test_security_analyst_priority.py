import pytest

from birre.domain.security_analyst.priority import (
    compute_priority_level,
    score_event_category,
    score_human_factor,
    score_rating_change,
    score_supplier_criticality,
)


@pytest.mark.parametrize(
    ("criticality", "expected"),
    [(1, 0), (2, 1), (3, 3), (None, 1)],
)
def test_score_supplier_criticality(criticality: int | None, expected: int) -> None:
    assert score_supplier_criticality(criticality) == expected


@pytest.mark.parametrize(
    ("category", "expected"),
    [
        ("public disclosure", -1),
        ("security incident", -1),
        ("botnet infection", 0),
        ("malware", 0),
        ("potentially exploited", 0),
        ("open ports", 1),
        ("patching cadence", 1),
        ("server software", 1),
        ("insecure systems", 1),
        ("TLS certificates", 3),
        ("TLS configuration", 3),
        ("spam propagation", 3),
        ("mobile app security", 3),
        ("desktop software", 3),
        ("mobile software", 3),
        ("exposed credentials", 3),
        ("web application headers", 3),
        ("web application security", 3),
    ],
)
def test_score_event_category(category: str, expected: int) -> None:
    assert score_event_category(category) == {"points": expected, "out_of_scope": False}


@pytest.mark.parametrize(
    "category",
    [
        "DNSSEC",
        "DMARC",
        "DKIM",
        "SPF",
        "domain squatting",
        "unsolicited communication",
        "file sharing",
    ],
)
def test_score_event_category_marks_out_of_scope(category: str) -> None:
    assert score_event_category(category) == {"points": 0, "out_of_scope": True}


@pytest.mark.parametrize("drop, expected", [(151, -1), (101, 0), (41, 1), (40, 3)])
def test_score_rating_change(drop: int, expected: int) -> None:
    assert score_rating_change(drop) == expected


@pytest.mark.parametrize("total_points, expected", [(1, 0), (2, 1), (3, 2), (4, 3), (5, 3), (6, 4)])
def test_compute_priority_level(total_points: int, expected: int) -> None:
    assert compute_priority_level(total_points) == expected


@pytest.mark.parametrize(
    ("factor", "expected"),
    [(None, 1), ("many_events", 0), ("normal", 1), ("low_relevance", 3)],
)
def test_score_human_factor(factor: str | None, expected: int) -> None:
    assert score_human_factor(factor) == expected
