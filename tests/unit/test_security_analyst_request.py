import pytest

from birre.domain.security_analyst.request import (
    build_alert_workflow_request,
    resolve_supplier_criticality,
)


def test_build_alert_workflow_request_uses_defaults() -> None:
    request = build_alert_workflow_request()

    assert (request.page_size, request.max_pages, request.max_companies) == (50, 10, 100)
    assert (request.max_returned_priority, request.human_factor) == (4, 1)


def test_build_alert_workflow_request_preserves_overrides_and_guid_criticality() -> None:
    request = build_alert_workflow_request(
        page_size=25,
        max_pages=2,
        max_companies=5,
        max_returned_priority=3,
        human_factor=0,
        supplier_criticality={"c-1": 2, "c-2": 3},
    )

    assert (request.page_size, request.max_pages, request.max_companies) == (25, 2, 5)
    assert (request.max_returned_priority, request.human_factor) == (3, 0)
    assert dict(request.supplier_criticality) == {"c-1": 2, "c-2": 3}
    assert "Company One" not in request.supplier_criticality


def test_build_alert_workflow_request_rejects_zero_page_size() -> None:
    with pytest.raises(ValueError, match="page_size"):
        build_alert_workflow_request(page_size=0)


def test_resolve_supplier_criticality_defaults_missing_guid_to_one() -> None:
    assert resolve_supplier_criticality({"c-1": 2, "c-2": 3}, "c-3") == 1
