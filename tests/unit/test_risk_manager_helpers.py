from __future__ import annotations

import pytest

from birre.domain.risk_manager import service as risk_service


@pytest.mark.asyncio
async def test_resolve_request_company_folder_uses_cached_guid() -> None:
    guid, created, error = await risk_service._resolve_request_company_folder(
        call_v1_tool=None,
        ctx=None,
        logger=None,
        selected_folder="Managed",
        default_folder="Managed",
        default_folder_guid="cached-guid",
        submitted_domains=["example.com"],
        existing_entries=[],
    )

    assert guid == "cached-guid"
    assert created is False
    assert error is None


def test_request_company_dry_run_response_includes_preview() -> None:
    response = risk_service._request_company_dry_run_response(
        submitted_domains=["a.com", "b.com"],
        existing_entries=[risk_service.RequestCompanyExistingEntry(domain="dup")],
        remaining_domains=["b.com"],
        selected_folder="Ops",
        folder_guid="guid-1",
        folder_created=False,
        csv_body="domain\nb.com",
    )

    assert response["status"] == "dry_run"
    assert response["csv_preview"].startswith("domain")
    assert response["successfully_requested"] == ["b.com"]
    assert response["folder"] == "Ops"
    assert response["folder_guid"] == "guid-1"
