from __future__ import annotations

import birre.domain.company_rating.service as s


def test_severity_category_and_numeric_extraction_variants() -> None:
    assert s._rank_severity_category_value("severe") > s._rank_severity_category_value("low")
    # Unknowns map to the lowest rank; must be <= low
    assert s._rank_severity_category_value("unknown") <= s._rank_severity_category_value("low")

    # direct numeric
    assert s._derive_numeric_severity_score({"severity": 7}) == 7
    # details.severity
    assert s._derive_numeric_severity_score({"details": {"severity": 6}}) == 6
    # details.grade
    assert s._derive_numeric_severity_score({"details": {"grade": 5}}) == 5
    # details.cvss.base
    assert abs(s._derive_numeric_severity_score({"details": {"cvss": {"base": 4.2}}}) - 4.2) < 0.01
    # fallback
    assert s._derive_numeric_severity_score("bad") == s.SEVERITY_SCORE_UNKNOWN


def test_timestamp_parsing_variants() -> None:
    assert s._parse_timestamp_seconds("2025-01-02") > 0
    assert s._parse_timestamp_seconds("2025-01-02T03:04:05+00:00") > 0
    assert s._parse_timestamp_seconds("2025-01-02T03:04:05") > 0
    assert s._parse_timestamp_seconds("2025-01-02 03:04:05") > 0
    assert s._parse_timestamp_seconds("bad") == s.TIMESTAMP_INVALID


def test_asset_importance_derivation() -> None:
    obj = {"assets": {"combined_importance": 9}}
    assert s._derive_asset_importance_score(obj) == 9
    obj2 = {"assets": {"importance": 3}}
    assert s._derive_asset_importance_score(obj2) == 3
    assert abs(s._derive_asset_importance_score({}) - 0.0) < 0.01


def test_sort_and_score_keys_and_candidate_selection() -> None:
    a = {"severity": "severe", "details": {"cvss": {"base": 9.0}}, "last_seen": "2025-01-03"}
    b = {"severity": "moderate", "details": {"cvss": {"base": 7.0}}, "last_seen": "2025-01-04"}
    c = {"severity": "material", "details": {"cvss": {"base": 8.0}}, "last_seen": "2025-01-02"}
    key_a = s._build_finding_sort_key(a)
    key_b = s._build_finding_sort_key(b)
    assert key_a < key_b  # because we negate severities for descending
    tup = s._build_finding_score_tuple(a)
    assert isinstance(tup, tuple) and len(tup) == 4

    selected = s._select_top_finding_candidates([a, b, c], 2)
    assert len(selected) == 2
    # top by numeric severity: a(9.0) then c(8.0)
    assert selected[0] is a


def test_details_text_and_label_helpers() -> None:
    item = {"risk_vector_label": "RV"}
    details = {"display_name": "DNS", "description": "Issue", "searchable_details": "S"}
    assert s._determine_finding_label(item, details) == "DNS"
    assert s._compose_base_details_text(details).startswith("DNS — Issue")

    details2 = {"remediations": [{"help_text": "Fix it"}]}
    assert s._find_first_remediation_text(details2) == "Fix it"

    txt = s._normalize_detected_service_summary("Detected service: SSH, version 1", "Patch")
    assert "Patch" in txt

    # append hint punctuation
    assert s._append_remediation_hint("Base.", "Hint") == "Base. Hint"


def test_normalize_top_findings_shapes() -> None:
    raw = [
        {
            "severity": "severe",
            "risk_vector": "x",
            "details": {"display_name": "Open Ports", "description": "desc"},
            "first_seen": "2025-01-01",
            "last_seen": "2025-01-02",
        }
    ]
    out = s._normalize_top_findings(raw)
    assert out and set(out[0].keys()) >= {"finding", "details", "asset", "first_seen", "last_seen"}
