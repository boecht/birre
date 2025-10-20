from typing import Any, Callable, Dict

import pytest
from fastmcp import Context, FastMCP

from src.business.risk_manager import (
    register_company_search_interactive_tool,
    register_manage_subscriptions_tool,
    register_request_company_tool,
)
from src.logging import get_logger


class FakeContext(Context):
    def __init__(self) -> None:
        self.infos = []
        self.warnings = []
        self.errors = []
        self.metadata = {}
        self._request_id = "offline-test"
        self.tool = "test"

    async def info(self, message: str) -> None:
        self.infos.append(message)

    async def warning(self, message: str) -> None:
        self.warnings.append(message)

    async def error(self, message: str) -> None:
        self.errors.append(message)

    @property
    def request_id(self) -> str:  # type: ignore[override]
        return self._request_id

    @property
    def call_id(self) -> str:  # type: ignore[override]
        return self._request_id


class BridgeStub:
    def __init__(self, handlers: Dict[str, Callable[[Dict[str, Any]], Any]]):
        self.handlers = handlers
        self.calls = []

    async def __call__(
        self, tool_name: str, ctx: Context, params: Dict[str, Any]
    ) -> Any:
        self.calls.append((tool_name, params))
        handler = self.handlers.get(tool_name)
        if handler is None:
            raise AssertionError(f"Unexpected tool call: {tool_name}")
        return handler(params)


@pytest.mark.asyncio
async def test_company_search_interactive_enriches_results() -> None:
    logger = get_logger("test.company_search_interactive")
    server = FastMCP(name="TestServer")

    def company_search_handler(params: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "results": [
                {
                    "guid": "guid-1",
                    "name": "Acme Holdings",
                    "primary_domain": "acme.com",
                    "details": {"employee_count": 1200},
                }
            ]
        }

    def get_company_handler(params: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "guid": params["guid"],
            "name": "Acme Holdings",
            "primary_domain": "acme.com",
            "homepage": "https://www.acme.com",
            "description": "Security services",
            "people_count": 1100,
            "subscription_type": "continuous_monitoring",
            "in_spm_portfolio": True,
        }

    def get_folders_handler(_: Dict[str, Any]) -> Any:
        return [
            {
                "name": "API",
                "guid": "folder-1",
                "companies": ["guid-1"],
            }
        ]

    call_v1 = BridgeStub(
        {
            "companySearch": company_search_handler,
            "getCompany": get_company_handler,
            "getFolders": get_folders_handler,
        }
    )
    tool = register_company_search_interactive_tool(
        server,
        call_v1,
        logger=logger,
        default_folder="API",
        default_type="continuous_monitoring",
        max_findings=10,
    )

    ctx = FakeContext()
    result = await tool.fn(ctx, domain="acme.com")
    assert result["count"] == 1
    entry = result["results"][0]
    assert entry["label"].startswith("Acme Holdings (")
    assert entry["employee_count"] == 1200
    assert entry["subscription"]["folders"] == ["API"]
    assert result["guidance"]["if_missing"].startswith("If the correct organization")


@pytest.mark.asyncio
async def test_manage_subscriptions_dry_run_and_apply() -> None:
    logger = get_logger("test.manage_subscriptions")
    server = FastMCP(name="TestServer")

    def manage_handler(params: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "added": [guid["guid"] for guid in params.get("add", [])],
            "deleted": [guid["guid"] for guid in params.get("delete", [])],
            "errors": [],
        }

    call_v1 = BridgeStub({"manageSubscriptionsBulk": manage_handler})

    tool = register_manage_subscriptions_tool(
        server,
        call_v1,
        logger=logger,
        default_folder="API",
        default_type="continuous_monitoring",
    )

    ctx = FakeContext()
    dry_result = await tool.fn(ctx, action="subscribe", guids=["guid-1"], dry_run=True)
    assert dry_result["status"] == "dry_run"
    assert dry_result["payload"]["add"][0]["folder"] == ["API"]

    applied = await tool.fn(ctx, action="subscribe", guids=["guid-1"])
    assert applied["status"] == "applied"
    assert applied["summary"]["added"] == ["guid-1"]


@pytest.mark.asyncio
async def test_request_company_falls_back_to_single_endpoint() -> None:
    logger = get_logger("test.request_company")
    server = FastMCP(name="TestServer")

    call_v1 = BridgeStub(
        {
            "getFolders": lambda _: [
                {
                    "name": "API",
                    "guid": "folder-1",
                    "companies": [],
                }
            ]
        }
    )

    def bulk_fail(_: Dict[str, Any]) -> Any:
        raise RuntimeError("bulk endpoint unavailable")

    call_v2 = BridgeStub(
        {
            "getCompanyRequests": lambda _: [],
            "createCompanyRequestBulk": bulk_fail,
            "createCompanyRequest": lambda params: {"request": params},
        }
    )

    tool = register_request_company_tool(
        server,
        call_v1,
        call_v2,
        logger=logger,
        default_folder="API",
        default_type="continuous_monitoring",
    )

    ctx = FakeContext()
    result = await tool.fn(
        ctx,
        domain="missing.example",
        company_name="Missing Corp",
    )
    assert result["status"] == "submitted_v2_single"
    assert result["warning"].startswith("The folder could not be specified")
    assert call_v2.calls[-1][0] == "createCompanyRequest"
