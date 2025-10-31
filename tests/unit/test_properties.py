"""Property-based tests using Hypothesis to find edge cases in data processing logic.

QA-003: Property-Based Testing

These tests use Hypothesis to generate random inputs and verify invariants hold across
all possible inputs. This helps discover edge cases that manual test writing might miss.
"""

from typing import Any

import pytest
from birre.domain.company_rating.service import (
    _derive_numeric_severity_score,
    _normalize_finding_entry,
    _rank_severity_category_value,
)
from hypothesis import given
from hypothesis import strategies as st

# =============================================================================
# Property Tests for Severity Scoring
# =============================================================================


@pytest.mark.offline
@given(st.text())
def test_severity_category_always_returns_int(severity_text: str) -> None:
    """Severity ranking always returns an integer, never crashes."""
    result = _rank_severity_category_value(severity_text)
    assert isinstance(result, int)
    assert -1 <= result <= 3


@pytest.mark.offline
@given(st.one_of(st.integers(), st.floats(allow_nan=False, allow_infinity=False), st.none()))
def test_severity_category_handles_non_strings(value: Any) -> None:
    """Severity ranking handles non-string inputs gracefully."""
    result = _rank_severity_category_value(value)
    assert isinstance(result, int)
    assert result == -1  # Non-strings should return -1


@pytest.mark.offline
@given(st.sampled_from(["severe", "material", "moderate", "low"]))
def test_severity_category_recognized_values(category: str) -> None:
    """Recognized severity categories return consistent positive values."""
    result = _rank_severity_category_value(category)
    assert result >= 0
    assert result <= 3


@pytest.mark.offline
@given(st.sampled_from(["severe", "material", "moderate", "low"]))
def test_severity_category_case_insensitive(category: str) -> None:
    """Severity ranking is case-insensitive."""
    lower = _rank_severity_category_value(category.lower())
    upper = _rank_severity_category_value(category.upper())
    mixed = _rank_severity_category_value(category.title())
    assert lower == upper == mixed


@pytest.mark.offline
@given(st.sampled_from(["severe", "material", "moderate", "low"]))
def test_severity_ordering_invariant(category: str) -> None:
    """Severity categories maintain strict ordering."""
    ordering = {
        "severe": 3,
        "material": 2,
        "moderate": 1,
        "low": 0,
    }
    result = _rank_severity_category_value(category)
    assert result == ordering[category]


@pytest.mark.offline
@given(st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False))
def test_numeric_severity_extracts_direct_float(score: float) -> None:
    """Direct numeric severity values are extracted correctly."""
    finding = {"severity": score}
    result = _derive_numeric_severity_score(finding)
    assert result == pytest.approx(score, abs=1e-6)


@pytest.mark.offline
@given(st.integers(min_value=-1000, max_value=1000))
def test_numeric_severity_extracts_direct_int(score: int) -> None:
    """Direct integer severity values are extracted correctly."""
    finding = {"severity": score}
    result = _derive_numeric_severity_score(finding)
    assert result == pytest.approx(float(score), abs=1e-6)


@pytest.mark.offline
@given(st.dictionaries(st.text(max_size=50), st.one_of(st.none(), st.text(), st.booleans())))
def test_numeric_severity_handles_arbitrary_dicts(finding_data: dict[str, Any]) -> None:
    """Numeric severity extraction doesn't crash on arbitrary dict inputs."""
    result = _derive_numeric_severity_score(finding_data)
    assert isinstance(result, float)
    # Should either extract a valid score or return -1.0
    assert result >= -1.0


@pytest.mark.offline
@given(st.one_of(st.none(), st.text(), st.integers(), st.lists(st.integers())))
def test_numeric_severity_handles_non_dict_inputs(value: Any) -> None:
    """Numeric severity extraction returns -1.0 for non-dict inputs."""
    result = _derive_numeric_severity_score(value)
    assert result == -1.0


@pytest.mark.offline
@given(
    st.floats(min_value=0, max_value=10, allow_nan=False, allow_infinity=False),
    st.sampled_from(["base", "score", "version"]),
)
def test_numeric_severity_cvss_extraction(cvss_score: float, cvss_key: str) -> None:
    """CVSS base scores are extracted from nested details.cvss.base."""
    finding = {"details": {"cvss": {cvss_key: cvss_score}}}
    result = _derive_numeric_severity_score(finding)
    if cvss_key == "base":
        assert result == pytest.approx(cvss_score, abs=1e-6)
    else:
        assert result == -1.0  # Only 'base' is extracted


# =============================================================================
# Property Tests for Finding Normalization
# =============================================================================


@pytest.mark.offline
@given(
    st.dictionaries(
        st.text(min_size=1, max_size=20),
        st.one_of(st.text(max_size=100), st.none()),
        min_size=0,
        max_size=10,
    )
)
def test_normalize_finding_always_returns_required_keys(finding: dict[str, Any]) -> None:
    """Finding normalization always returns the required 5 keys."""
    result = _normalize_finding_entry(finding)
    assert isinstance(result, dict)
    assert set(result.keys()) == {"finding", "details", "asset", "first_seen", "last_seen"}


@pytest.mark.offline
@given(st.dictionaries(st.text(), st.one_of(st.text(), st.none(), st.integers()), max_size=20))
def test_normalize_finding_never_crashes(finding: dict[str, Any]) -> None:
    """Finding normalization handles arbitrary dict inputs without crashing."""
    result = _normalize_finding_entry(finding)
    assert isinstance(result, dict)


@pytest.mark.offline
@given(st.text(min_size=1, max_size=100))
def test_normalize_finding_preserves_first_seen_string(timestamp: str) -> None:
    """String first_seen values are preserved as-is."""
    finding = {"first_seen": timestamp}
    result = _normalize_finding_entry(finding)
    assert result["first_seen"] == timestamp


@pytest.mark.offline
@given(st.one_of(st.integers(), st.floats(), st.booleans(), st.none()))
def test_normalize_finding_first_seen_non_string_becomes_none(value: Any) -> None:
    """Non-string first_seen values become None."""
    finding = {"first_seen": value}
    result = _normalize_finding_entry(finding)
    assert result["first_seen"] is None


@pytest.mark.offline
@given(st.text(min_size=1, max_size=100))
def test_normalize_finding_preserves_last_seen_string(timestamp: str) -> None:
    """String last_seen values are preserved as-is."""
    finding = {"last_seen": timestamp}
    result = _normalize_finding_entry(finding)
    assert result["last_seen"] == timestamp


@pytest.mark.offline
@given(st.one_of(st.integers(), st.floats(), st.booleans(), st.none()))
def test_normalize_finding_last_seen_non_string_becomes_none(value: Any) -> None:
    """Non-string last_seen values become None."""
    finding = {"last_seen": value}
    result = _normalize_finding_entry(finding)
    assert result["last_seen"] is None


# =============================================================================
# Property Tests for Severity Ordering Relationships
# =============================================================================


@pytest.mark.offline
@given(
    st.sampled_from(["severe", "material", "moderate", "low"]),
    st.sampled_from(["severe", "material", "moderate", "low"]),
)
def test_severity_ordering_transitive(cat1: str, cat2: str) -> None:
    """Severity ordering is transitive: if A > B and B > C, then A > C."""
    rank1 = _rank_severity_category_value(cat1)
    rank2 = _rank_severity_category_value(cat2)

    # Higher severity should have higher rank
    severity_order = {"low": 0, "moderate": 1, "material": 2, "severe": 3}
    expected_relation = severity_order[cat1] - severity_order[cat2]
    actual_relation = rank1 - rank2

    assert expected_relation == actual_relation


@pytest.mark.offline
@given(st.floats(min_value=-100, max_value=100, allow_nan=False, allow_infinity=False))
def test_severity_score_boundaries(score: float) -> None:
    """Severity scores maintain consistent boundary behavior."""
    finding = {"severity": score}
    result = _derive_numeric_severity_score(finding)

    # Result should either be the score itself or -1.0
    assert result == pytest.approx(score, abs=1e-6) or result == -1.0


@pytest.mark.offline
@given(
    st.text(min_size=0, max_size=100),
    st.text(min_size=0, max_size=100),
)
def test_finding_normalization_deterministic(details1: str, details2: str) -> None:
    """Same input to finding normalization produces same output."""
    finding1 = {"details": {"text": details1, "info": details2}}
    finding2 = {"details": {"text": details1, "info": details2}}

    result1 = _normalize_finding_entry(finding1)
    result2 = _normalize_finding_entry(finding2)

    assert result1 == result2


# =============================================================================
# Property Tests for Edge Cases and Boundaries
# =============================================================================


@pytest.mark.offline
@given(st.text(alphabet=st.characters(whitelist_categories=("Zs",)), min_size=1, max_size=20))
def test_severity_category_whitespace_only(whitespace: str) -> None:
    """Whitespace-only strings are not recognized as valid severity categories."""
    result = _rank_severity_category_value(whitespace)
    assert result == -1


@pytest.mark.offline
@given(st.text(min_size=1, max_size=50))
def test_severity_category_arbitrary_text_safe(text: str) -> None:
    """Arbitrary text input to severity ranking is safe and deterministic."""
    result1 = _rank_severity_category_value(text)
    result2 = _rank_severity_category_value(text)
    assert result1 == result2
    assert isinstance(result1, int)


@pytest.mark.offline
@given(st.lists(st.dictionaries(st.text(), st.integers(), max_size=5), max_size=10))
def test_numeric_severity_handles_complex_nesting(nested_data: list[dict[str, Any]]) -> None:
    """Numeric severity extraction handles deeply nested structures safely."""
    finding = {"details": {"data": nested_data}}
    result = _derive_numeric_severity_score(finding)
    assert isinstance(result, float)
    # Should return -1.0 when no valid severity found in nested structure
    assert result >= -1.0


@pytest.mark.offline
@given(st.dictionaries(st.text(), st.recursive(st.none(), lambda x: st.lists(x, max_size=3))))
def test_finding_normalization_recursive_structures(recursive_dict: dict[str, Any]) -> None:
    """Finding normalization handles recursive/nested structures safely."""
    result = _normalize_finding_entry(recursive_dict)
    assert isinstance(result, dict)
    assert len(result) == 5
