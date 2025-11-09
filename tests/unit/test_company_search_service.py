from __future__ import annotations

from birre.domain.company_search import service as search_service


def test_company_summary_prefers_primary_domain() -> None:
    raw = {"guid": "1", "name": "Acme", "primary_domain": "acme.com"}
    summary = search_service.CompanySummary.model_validate(raw)
    assert summary.domain == "acme.com"


def test_response_capture_error() -> None:
    payload = {"error": "boom"}
    response = search_service.CompanySearchResponse.from_raw(payload)
    assert response.error and "boom" in response.error


def test_response_from_list_and_dicts() -> None:
    raw = {"results": [{"guid": "1", "name": "Acme", "domain": "acme.com"}], "count": 1}
    resp = search_service.CompanySearchResponse.from_raw(raw)
    assert resp.count == 1 and resp.companies[0].domain == "acme.com"


def test_normalize_company_search_results_handles_list() -> None:
    output = search_service.normalize_company_search_results([{"guid": "1"}])
    assert output["count"] == 1
