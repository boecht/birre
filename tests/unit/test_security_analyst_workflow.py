from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import typer
from typer.testing import CliRunner

from birre.domain.security_analyst.workflow import run_alert_workflow_action_payload


def _fixture_alerts() -> list[dict[str, Any]]:
    return [
        {
            "guid": "alert-derived",
            "company_guid": "company-alert",
            "alert_type": "TLS certificates",
            "details": {"rating_before": 800, "rating_after": 700},
        },
        {
            "guid": "history-larger",
            "company_guid": "company-history",
            "alert_type": "TLS certificates",
            "details": {"rating_before": 800, "rating_after": 750},
        },
        {
            "guid": "history-fallback",
            "company_guid": "company-fallback",
            "alert_type": "TLS certificates",
        },
        {
            "guid": "movement-missing",
            "company_guid": "company-missing",
            "alert_type": "TLS certificates",
        },
        {
            "guid": "out-of-scope",
            "company_guid": "company-out-of-scope",
            "alert_type": "DNSSEC",
        },
        {
            "guid": "web-ambiguous",
            "company_guid": "company-web",
            "alert_type": "web application security",
        },
        {
            "guid": "priority-filtered",
            "company_guid": "company-filtered",
            "alert_type": "TLS certificates",
        },
    ]


def _fixture_companies() -> dict[str, dict[str, Any]]:
    return {
        "company-alert": {"name": "Alert Co", "ratings": [{"rating": 800}, {"rating": 750}]},
        "company-history": {"name": "History Co", "ratings": [{"rating": 800}, {"rating": 650}]},
        "company-fallback": {"name": "Fallback Co", "ratings": [{"rating": 800}, {"rating": 700}]},
        "company-missing": {"name": "Missing Co"},
        "company-out-of-scope": {"name": "Out Of Scope Co"},
        "company-web": {"name": "Web Co"},
        "company-filtered": {"name": "Filtered Co"},
    }


async def _fixture_call_v2_tool(_: str, __: Any, params: dict[str, Any]) -> dict[str, Any]:
    if params["offset"] == 0:
        return {"results": _fixture_alerts(), "next": "next-page"}
    return {"results": [], "next": "still-more-pages"}


async def _fixture_fetch_company(company_guid: str) -> dict[str, Any]:
    return _fixture_companies()[company_guid]


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


@pytest.mark.asyncio
async def test_alert_workflow_fixture_matrix_returns_jira_actions_by_company_guid() -> None:
    payload = await run_alert_workflow_action_payload(
        _fixture_call_v2_tool,
        _fixture_fetch_company,
        max_pages=1,
        max_companies=7,
        max_returned_priority=3,
        supplier_criticality={"company-filtered": 3},
    )

    action_items = {item["company_guid"]: item for item in payload["action_items"]}
    assert set(action_items) == {
        "company-alert",
        "company-history",
        "company-fallback",
        "company-missing",
        "company-web",
    }
    assert action_items["company-alert"]["proposed_jira_body"]["movement_source"] == "alert_rating"
    assert (
        action_items["company-history"]["proposed_jira_body"]["movement_source"]
        == "company_history"
    )
    assert (
        action_items["company-fallback"]["proposed_jira_body"]["movement_source"]
        == "company_history"
    )
    assert action_items["company-missing"]["warning_codes"] == ["rating_movement_missing"]
    assert action_items["company-web"]["warning_codes"] == [
        "rating_movement_missing",
        "category_ambiguous",
    ]
    assert set(payload["metadata"]["warnings"]) == {
        "alert_page_cap_reached",
        "rating_movement_missing",
        "category_ambiguous",
    }
    assert payload["metadata"]["filtered_candidates"] == [
        {
            "company_guid": "company-out-of-scope",
            "priority": 0,
            "eligible": False,
            "action_item": None,
            "filter_reason": "out_of_scope_category",
        },
        {
            "company_guid": "company-filtered",
            "priority": 4,
            "eligible": False,
            "action_item": None,
            "filter_reason": "priority_filtered",
        },
    ]
    assert "groups" not in payload


@pytest.mark.asyncio
async def test_alert_workflow_fixture_caps_report_page_and_company_warnings() -> None:
    payload = await run_alert_workflow_action_payload(
        _fixture_call_v2_tool,
        _fixture_fetch_company,
        max_pages=1,
        max_companies=2,
    )

    assert {item["company_guid"] for item in payload["action_items"]} == {
        "company-alert",
        "company-history",
    }
    assert {"alert_page_cap_reached", "company_cap_reached"} <= set(payload["metadata"]["warnings"])


@pytest.mark.asyncio
async def test_fixture_workflow_performs_only_bit_sight_reads_and_no_file_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    async def call_v2_tool(name: str, ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
        calls.append(("v2", name))
        return await _fixture_call_v2_tool(name, ctx, params)

    async def fetch_company(company_guid: str) -> dict[str, Any]:
        calls.append(("v1", company_guid))
        return await _fixture_fetch_company(company_guid)

    def fail_write(*_: Any, **__: Any) -> None:
        raise AssertionError("workflow must not write durable state")

    monkeypatch.setattr(Path, "write_text", fail_write)
    monkeypatch.setattr(Path, "write_bytes", fail_write)
    monkeypatch.setattr(Path, "touch", fail_write)

    await run_alert_workflow_action_payload(
        call_v2_tool, fetch_company, max_pages=1, max_companies=2
    )

    assert calls == [
        ("v2", "getAlerts"),
        ("v1", "company-alert"),
        ("v1", "company-history"),
    ]


def test_fixture_cli_workflow_outputs_jira_actions_without_jira_or_state_clients() -> None:
    from birre.cli.commands.security_analyst import register

    app = typer.Typer()
    register(
        app,
        workflow_runner=lambda **options: run_alert_workflow_action_payload(
            _fixture_call_v2_tool,
            _fixture_fetch_company,
            **options,
        ),
    )

    result = CliRunner().invoke(
        app,
        ["--max-pages", "1", "--max-companies", "2", "--max-returned-priority", "3"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert {item["company_guid"] for item in payload["action_items"]} == {
        "company-alert",
        "company-history",
    }
    assert "groups" not in payload


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
