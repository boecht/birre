from __future__ import annotations

from typing import Any

import pytest

from birre.domain.security_analyst.workflow import run_alert_workflow_action_payload


@pytest.mark.asyncio
async def test_alert_workflow_builds_payload_and_propagates_stage_warnings() -> None:
    async def call_v2_tool(_: str, __: Any, ___: dict[str, Any]) -> dict[str, Any]:
        return {
            "results": [
                {
                    "guid": "alert-1",
                    "company_guid": "company-1",
                    "alert_type": "web application security",
                },
                {"guid": "alert-2", "alert_type": "malware"},
            ],
            "next": "next-page",
        }

    async def fetch_company(_: str) -> Any:
        raise RuntimeError("unavailable")

    payload = await run_alert_workflow_action_payload(
        call_v2_tool,
        fetch_company,
        max_pages=1,
    )

    assert payload["action_items"][0]["company_guid"] == "company-1"
    assert payload["action_items"][0]["proposed_jira_body"]["movement_source"] is None
    assert set(payload["metadata"]["warnings"]) == {
        "alert_page_cap_reached",
        "company_guid_missing_anomaly",
        "company_enrichment_failed",
        "rating_movement_missing",
        "category_ambiguous",
    }
