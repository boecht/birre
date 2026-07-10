from __future__ import annotations

import json
from typing import Any

import pytest
import typer
from typer.testing import CliRunner

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


def test_injected_cli_runner_needs_no_jira_or_durable_state_client() -> None:
    from birre.cli.commands.security_analyst import register

    runner_calls: list[dict[str, object]] = []
    app = typer.Typer()
    register(
        app,
        workflow_runner=lambda **options: (
            runner_calls.append(options) or {"action_items": [], "metadata": {"warnings": []}}
        ),
    )

    result = CliRunner().invoke(app, ["--page-size", "25"])

    assert result.exit_code == 0
    assert runner_calls == [
        {
            "alert_date_gte": None,
            "page_size": 25,
            "max_pages": 10,
            "max_companies": 100,
            "max_returned_priority": 4,
        }
    ]
    assert json.loads(result.stdout) == {"action_items": [], "metadata": {"warnings": []}}
