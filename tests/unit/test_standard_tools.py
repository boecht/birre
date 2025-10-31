import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from birre.domain.company_rating.service import (
    _normalize_finding_entry,
    register_company_rating_tool,
)
from birre.domain.company_search import register_company_search_tool
from birre.domain.risk_manager import register_company_search_interactive_tool
from birre.infrastructure.logging import BoundLogger, get_logger
from fastmcp import Context, FastMCP


class StubContext(Context):
    def __init__(self) -> None:
        self.messages: dict[str, list[str]] = {"info": [], "warning": [], "error": []}
        self.metadata = {}
        self.tool = "standard"
        self._request_id = "standard-test"

    async def info(self, message: str) -> None:  # type: ignore[override]
        await asyncio.sleep(0)
        self.messages["info"].append(message)

    async def warning(self, message: str) -> None:  # type: ignore[override]
        await asyncio.sleep(0)
        self.messages["warning"].append(message)

    async def error(self, message: str) -> None:  # type: ignore[override]
        await asyncio.sleep(0)
        self.messages["error"].append(message)

    @property
    def request_id(self) -> str:  # type: ignore[override]
        return self._request_id

    @property
    def call_id(self) -> str:  # type: ignore[override]
        return self._request_id


def make_server() -> tuple[FastMCP, BoundLogger]:
    server = FastMCP(name="TestServer")
    logger = get_logger("birre.test.standard")
    return server, logger


@pytest.mark.asyncio
async def test_company_search_requires_query() -> None:
    server, logger = make_server()

    async def call_v1_tool(name: str, ctx: Context, params: dict[str, Any]):
        await asyncio.sleep(0)
        raise AssertionError("call_v1_tool should not be invoked without params")

    tool = register_company_search_tool(server, call_v1_tool, logger=logger)
    ctx = StubContext()

    result = await tool.fn(ctx)  # type: ignore[attr-defined]
    assert result == {
        "error": "At least one of 'name' or 'domain' must be provided",
    }
    assert ctx.messages["error"] == []


@pytest.mark.asyncio
async def test_company_search_returns_normalized_payload() -> None:
    server, logger = make_server()

    async def call_v1_tool(name: str, ctx: Context, params: dict[str, Any]):
        await asyncio.sleep(0)
        assert name == "companySearch"
        assert params == {"name": "Example", "domain": None}
        return {
            "results": [
                {"guid": "guid-1", "name": "Example Corp", "primary_domain": "example.com"},
                {"guid": "guid-2", "name": "Example Blog", "display_url": "blog.example.com"},
            ],
        }

    tool = register_company_search_tool(server, call_v1_tool, logger=logger)
    ctx = StubContext()

    result = await tool.fn(ctx, name="Example")  # type: ignore[attr-defined]
    assert result == {
        "companies": [
            {"guid": "guid-1", "name": "Example Corp", "domain": "example.com"},
            {"guid": "guid-2", "name": "Example Blog", "domain": "blog.example.com"},
        ],
        "count": 2,
    }
    assert not ctx.messages["error"]


@pytest.mark.asyncio
async def test_company_search_interactive_empty_result_contract() -> None:
    server, logger = make_server()

    async def call_v1_tool(name: str, ctx: Context, params: dict[str, Any]):
        await asyncio.sleep(0)
        assert name == "companySearch"
        assert params == {
            "expand": "details.employee_count,details.in_portfolio",
            "name": "Example",
        }
        return {"results": []}

    tool = register_company_search_interactive_tool(
        server,
        call_v1_tool,
        logger=logger,
        default_folder="Default",
        default_type="continuous",
    )
    ctx = StubContext()

    result = await tool.fn(ctx, name="Example")  # type: ignore[attr-defined]

    assert result == {
        "count": 0,
        "results": [],
        "search_term": "Example",
        "guidance": {
            "selection": "No matches were returned. "
            "Confirm the organization name or domain with the operator.",
            "if_missing": (
                "Invoke `request_company` to submit an onboarding request "
                "when the entity is absent."
            ),
            "default_folder": "Default",
            "default_subscription_type": "continuous",
        },
        "truncated": False,
    }
    assert ctx.messages["error"] == []


@pytest.mark.asyncio
async def test_get_company_rating_success_cleanup_subscription(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server, logger = make_server()

    async def call_v1_tool(name: str, ctx: Context, params: dict[str, Any]):
        await asyncio.sleep(0)
        raise AssertionError(f"Unexpected call_v1_tool invocation: {name}")

    tool = register_company_rating_tool(server, call_v1_tool, logger=logger)
    ctx = StubContext()

    # Patch internal helpers to isolate behaviour
    async def fake_create(*args, **kwargs):
        await asyncio.sleep(0)
        return SimpleNamespace(success=True, created=True, already_subscribed=False, message=None)

    async def fake_cleanup(*args, **kwargs):
        await asyncio.sleep(0)
        return True

    monkeypatch.setattr(
        "birre.domain.company_rating.service.create_ephemeral_subscription",
        fake_create,
    )
    monkeypatch.setattr(
        "birre.domain.company_rating.service.cleanup_ephemeral_subscription",
        fake_cleanup,
    )

    async def fake_fetch_company(*args, **kwargs):
        await asyncio.sleep(0)
        return {
            "name": "Example Corp",
            "primary_domain": "example.com",
            "current_rating": 740,
            "ratings": [
                {"rating_date": "2025-09-10", "rating": 720},
                {"rating_date": "2025-10-01", "rating": 740},
            ],
        }

    async def fake_top_findings(*args, **kwargs):
        await asyncio.sleep(0)
        return {
            "policy": {
                "severity_floor": "material",
                "supplements": [],
                "max_items": 5,
                "profile": "strict",
            },
            "count": 1,
            "findings": [
                {
                    "top": 1,
                    "finding": "Open Ports",
                    "details": "Detected service: HTTPS",
                    "asset": "example.com",
                    "first_seen": "2025-09-15",
                    "last_seen": "2025-10-01",
                }
            ],
        }

    monkeypatch.setattr(
        "birre.domain.company_rating.service._fetch_company_profile_dict",
        fake_fetch_company,
    )
    monkeypatch.setattr(
        "birre.domain.company_rating.service._assemble_top_findings_section",
        fake_top_findings,
    )

    result = await tool.fn(ctx, guid="guid-1")  # type: ignore[attr-defined]
    assert result["name"] == "Example Corp"
    assert result["domain"] == "example.com"
    assert result["current_rating"]["value"] == 740
    assert result["top_findings"]["count"] == 1
    assert result["top_findings"]["findings"][0]["asset"] == "example.com"
    assert result["top_findings"]["findings"][0]["last_seen"] == "2025-10-01"
    assert ctx.messages["error"] == []


@pytest.mark.asyncio
async def test_get_company_rating_subscription_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    server, logger = make_server()

    async def call_v1_tool(name: str, ctx: Context, params: dict[str, Any]):
        await asyncio.sleep(0)
        raise AssertionError("call_v1_tool should not run when subscription fails")

    tool = register_company_rating_tool(server, call_v1_tool, logger=logger)
    ctx = StubContext()

    async def fake_create_fail(*args, **kwargs):
        await asyncio.sleep(0)
        return SimpleNamespace(
            success=False, created=False, already_subscribed=False, message="no subscription"
        )

    monkeypatch.setattr(
        "birre.domain.company_rating.service.create_ephemeral_subscription",
        fake_create_fail,
    )

    result = await tool.fn(ctx, guid="guid-err")  # type: ignore[attr-defined]
    assert result == {"error": "no subscription"}
    assert "no subscription" in ctx.messages["error"]


def test_normalize_finding_entry_missing_dates() -> None:
    item = {
        "details": {
            "display_name": "Open port",
            "description": "Detected service: HTTPS",
        },
        "risk_vector": "web_appsec",
        "risk_vector_label": "Web Application Security",
    }

    normalized = _normalize_finding_entry(item)

    assert normalized["finding"] == "Open port"
    assert normalized["details"].startswith("Open port")
    assert normalized["asset"] is None
    assert normalized["first_seen"] is None
    assert normalized["last_seen"] is None
