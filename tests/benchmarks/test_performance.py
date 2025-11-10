"""Performance benchmarks for critical BiRRe code paths.

QA-004: Performance Benchmarks

These benchmarks track performance regressions in:
1. Company search normalization
2. Rating retrieval data processing
3. Findings processing and ranking

Run with: pytest tests/benchmarks/ --benchmark-only
Compare: pytest tests/benchmarks/ --benchmark-compare
"""

from typing import Any

import pytest

from birre.domain.company_rating.service import (
    _build_finding_score_tuple,
    _build_finding_sort_key,
    _derive_numeric_severity_score,
    _normalize_finding_entry,
    _normalize_top_findings,
    _rank_severity_category_value,
)
from birre.domain.company_search.service import normalize_company_search_results

# =============================================================================
# Benchmark Fixtures - Realistic Data Samples
# =============================================================================


@pytest.fixture
def sample_search_results() -> dict[str, Any]:
    """Realistic company search API response with 10 results."""
    return {
        "results": [
            {
                "guid": f"guid-{i}",
                "name": f"Company {i}",
                "primary_domain": f"company{i}.com",
                "display_url": f"www.company{i}.com",
                "subscription_type": "continuous_monitoring" if i % 2 == 0 else None,
                "in_spm_portfolio": i % 3 == 0,
            }
            for i in range(10)
        ]
    }


@pytest.fixture
def sample_findings_data() -> list[dict[str, Any]]:
    """Realistic findings API response with 50 findings."""
    return [
        {
            "risk_vector": "web_application_security"
            if i % 4 == 0
            else "patching_cadence",
            "first_seen": "2025-09-15",
            "last_seen": "2025-10-30",
            "severity": ["severe", "material", "moderate", "low"][i % 4],
            "details": {
                "text": (
                    f"Finding description {i} with detailed information about the security issue"
                ),
                "cvss": {"base": 7.5 + (i % 3) * 0.5} if i % 2 == 0 else {},
                "grade": i % 10,
            },
            "assets": [
                {
                    "asset": f"server{i % 5}.example.com",
                    "importance": ["critical", "high", "medium", "low"][i % 4],
                }
            ],
        }
        for i in range(50)
    ]


@pytest.fixture
def sample_finding_entry() -> dict[str, Any]:
    """Single realistic finding entry."""
    return {
        "risk_vector": "web_application_security",
        "first_seen": "2025-09-15",
        "last_seen": "2025-10-30",
        "severity": "material",
        "details": {
            "text": "Detected service: HTTPS on port 443 with TLS 1.0 (deprecated protocol)",
            "remediation": "Upgrade to TLS 1.2 or higher to ensure secure communications",
            "cvss": {"base": 7.5, "version": "3.1"},
            "grade": 8,
        },
        "assets": [
            {"asset": "api.example.com", "importance": "critical"},
            {"asset": "www.example.com", "importance": "high"},
        ],
    }


# =============================================================================
# Company Search Performance Benchmarks
# =============================================================================


@pytest.mark.offline
@pytest.mark.benchmark(group="search")
def test_benchmark_search_normalization_small(
    benchmark: Any, sample_search_results: dict[str, Any]
) -> None:
    """Benchmark company search normalization with 10 results."""
    result = benchmark(normalize_company_search_results, sample_search_results)
    assert result["count"] == 10


@pytest.mark.offline
@pytest.mark.benchmark(group="search")
def test_benchmark_search_normalization_large(benchmark: Any) -> None:
    """Benchmark company search normalization with 100 results."""
    large_results = {
        "results": [
            {
                "guid": f"guid-{i}",
                "name": f"Company {i}",
                "primary_domain": f"company{i}.com",
            }
            for i in range(100)
        ]
    }
    result = benchmark(normalize_company_search_results, large_results)
    assert result["count"] == 100


# =============================================================================
# Findings Processing Performance Benchmarks
# =============================================================================


@pytest.mark.offline
@pytest.mark.benchmark(group="findings")
def test_benchmark_finding_normalization_single(
    benchmark: Any, sample_finding_entry: dict[str, Any]
) -> None:
    """Benchmark single finding normalization."""
    result = benchmark(_normalize_finding_entry, sample_finding_entry)
    assert "finding" in result
    assert "details" in result


@pytest.mark.offline
@pytest.mark.benchmark(group="findings")
def test_benchmark_findings_batch_normalization(
    benchmark: Any, sample_findings_data: list[dict[str, Any]]
) -> None:
    """Benchmark batch normalization of 50 findings."""
    result = benchmark(_normalize_top_findings, sample_findings_data)
    assert len(result) == 50


@pytest.mark.offline
@pytest.mark.benchmark(group="findings")
def test_benchmark_severity_ranking_batch(
    benchmark: Any, sample_findings_data: list[dict[str, Any]]
) -> None:
    """Benchmark severity ranking across 50 findings."""

    def rank_all_severities(findings: list[dict[str, Any]]) -> list[int]:
        return [_rank_severity_category_value(f.get("severity")) for f in findings]

    result = benchmark(rank_all_severities, sample_findings_data)
    assert len(result) == 50


@pytest.mark.offline
@pytest.mark.benchmark(group="findings")
def test_benchmark_numeric_severity_extraction(
    benchmark: Any, sample_findings_data: list[dict[str, Any]]
) -> None:
    """Benchmark numeric severity extraction across 50 findings."""

    def extract_all_scores(findings: list[dict[str, Any]]) -> list[float]:
        return [_derive_numeric_severity_score(f) for f in findings]

    result = benchmark(extract_all_scores, sample_findings_data)
    assert len(result) == 50


# =============================================================================
# Findings Ranking Performance Benchmarks
# =============================================================================


@pytest.mark.offline
@pytest.mark.benchmark(group="ranking")
def test_benchmark_finding_score_tuple_generation(
    benchmark: Any, sample_findings_data: list[dict[str, Any]]
) -> None:
    """Benchmark score tuple generation for sorting (50 findings)."""

    def generate_all_scores(findings: list[dict[str, Any]]) -> list[tuple]:
        return [_build_finding_score_tuple(f) for f in findings]

    result = benchmark(generate_all_scores, sample_findings_data)
    assert len(result) == 50


@pytest.mark.offline
@pytest.mark.benchmark(group="ranking")
def test_benchmark_finding_sort_key_generation(
    benchmark: Any, sample_findings_data: list[dict[str, Any]]
) -> None:
    """Benchmark sort key generation for final ordering (50 findings)."""

    def generate_all_keys(findings: list[dict[str, Any]]) -> list[tuple]:
        return [_build_finding_sort_key(f) for f in findings]

    result = benchmark(generate_all_keys, sample_findings_data)
    assert len(result) == 50


@pytest.mark.offline
@pytest.mark.benchmark(group="ranking")
def test_benchmark_findings_complete_ranking_pipeline(
    benchmark: Any, sample_findings_data: list[dict[str, Any]]
) -> None:
    """Benchmark complete findings ranking pipeline."""

    def rank_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # Simulate the complete ranking pipeline
        normalized = _normalize_top_findings(findings)
        scored = [(f, _build_finding_score_tuple(f)) for f in normalized]
        sorted_findings = sorted(scored, key=lambda x: x[1], reverse=True)
        return [f for f, _ in sorted_findings[:10]]

    result = benchmark(rank_findings, sample_findings_data)
    assert len(result) == 10


# =============================================================================
# Edge Case Performance Benchmarks
# =============================================================================


@pytest.mark.offline
@pytest.mark.benchmark(group="edge-cases")
def test_benchmark_empty_search_results(benchmark: Any) -> None:
    """Benchmark search normalization with empty results."""
    empty_results = {"results": []}
    result = benchmark(normalize_company_search_results, empty_results)
    assert result["count"] == 0


@pytest.mark.offline
@pytest.mark.benchmark(group="edge-cases")
def test_benchmark_minimal_finding_data(benchmark: Any) -> None:
    """Benchmark finding normalization with minimal data."""
    minimal_finding = {"risk_vector": "unknown"}
    result = benchmark(_normalize_finding_entry, minimal_finding)
    assert isinstance(result, dict)


@pytest.mark.offline
@pytest.mark.benchmark(group="edge-cases")
def test_benchmark_malformed_severity_handling(benchmark: Any) -> None:
    """Benchmark severity ranking with malformed inputs."""
    malformed_inputs = [
        None,
        "",
        "INVALID",
        123,
        {"nested": "dict"},
        ["list"],
    ] * 10

    def rank_all(inputs: list[Any]) -> list[int]:
        return [_rank_severity_category_value(x) for x in inputs]

    result = benchmark(rank_all, malformed_inputs)
    assert len(result) == 60
    assert all(x == -1 for x in result)  # All should return -1 for invalid


# =============================================================================
# Stress Test Benchmarks
# =============================================================================


@pytest.mark.offline
@pytest.mark.benchmark(group="stress")
def test_benchmark_findings_stress_1000(benchmark: Any) -> None:
    """Stress test: Normalize 1000 findings."""
    large_findings = [
        {
            "risk_vector": "patching_cadence",
            "severity": "moderate",
            "first_seen": "2025-01-01",
            "last_seen": "2025-10-30",
            "details": {"text": f"Finding {i}"},
            "assets": [{"asset": f"server{i}.com", "importance": "medium"}],
        }
        for i in range(1000)
    ]

    result = benchmark(_normalize_top_findings, large_findings)
    assert len(result) == 1000


@pytest.mark.offline
@pytest.mark.benchmark(group="stress")
def test_benchmark_search_stress_500(benchmark: Any) -> None:
    """Stress test: Normalize 500 search results."""
    large_search = {
        "results": [
            {
                "guid": f"guid-{i}",
                "name": f"Company {i}",
                "primary_domain": f"company{i}.com",
            }
            for i in range(500)
        ]
    }

    result = benchmark(normalize_company_search_results, large_search)
    assert result["count"] == 500
