from collections.abc import Callable
from typing import Any

import pytest
from fastmcp import Context, FastMCP

from birre.domain.risk_manager import (
    register_company_search_interactive_tool,
    register_manage_subscriptions_tool,
    register_request_company_tool,
)
from birre.infrastructure.logging import get_logger


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
    def __init__(self, handlers: dict[str, Callable[[dict[str, Any]], Any]]):
        self.handlers = handlers
        self.calls = []

    async def __call__(
        self, tool_name: str, ctx: Context, params: dict[str, Any]
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

    def company_search_handler(params: dict[str, Any]) -> dict[str, Any]:
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

    def get_company_handler(params: dict[str, Any]) -> dict[str, Any]:
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

    def get_folders_handler(_: dict[str, Any]) -> Any:
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

    def manage_handler(params: dict[str, Any]) -> dict[str, Any]:
        return {
            "added": [guid["guid"] for guid in params.get("add", [])],
            "deleted": [guid["guid"] for guid in params.get("delete", [])],
            "errors": [],
        }

    call_v1 = BridgeStub(
        {
            "getFolders": lambda _: [
                {
                    "name": "API",
                    "guid": "folder-1",
                    "companies": [],
                }
            ],
            "manageSubscriptionsBulk": manage_handler,
        }
    )

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
    assert dry_result["payload"]["add"][0]["folder"] == ["folder-1"]
    assert dry_result["folder_guid"] == "folder-1"
    assert dry_result.get("folder_created") is None
    assert any(call_name == "getFolders" for call_name, _ in call_v1.calls)
    assert all(call_name != "createFolder" for call_name, _ in call_v1.calls)

    applied = await tool.fn(ctx, action="subscribe", guids=["guid-1"])
    assert applied["status"] == "applied"
    assert applied["summary"]["added"] == ["guid-1"]
    assert applied["folder_guid"] == "folder-1"
    assert applied.get("folder_created") is None


@pytest.mark.asyncio
async def test_manage_subscriptions_dry_run_reports_missing_folder() -> None:
    logger = get_logger("test.manage_subscriptions")
    server = FastMCP(name="TestServer")

    def _forbid_create(_: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("createFolder should not be called during dry run")

    call_v1 = BridgeStub(
        {
            "getFolders": lambda _: [],
            "createFolder": _forbid_create,
        }
    )

    tool = register_manage_subscriptions_tool(
        server,
        call_v1,
        logger=logger,
        default_folder=None,
        default_type="continuous_monitoring",
    )

    ctx = FakeContext()
    result = await tool.fn(
        ctx,
        action="subscribe",
        guids=["guid-2"],
        folder="Ops",
        dry_run=True,
    )

    assert result["status"] == "dry_run"
    assert result["folder_guid"] is None
    guidance = result.get("guidance") or {}
    assert "Ops" in (guidance.get("next_steps") or "")
    assert any(call_name == "getFolders" for call_name, _ in call_v1.calls)
    assert all(call_name != "createFolder" for call_name, _ in call_v1.calls)
    assert "folder" not in result["payload"]["add"][0]


@pytest.mark.asyncio
async def test_manage_subscriptions_delete_skips_folder_resolution() -> None:
    logger = get_logger("test.manage_subscriptions")
    server = FastMCP(name="TestServer")

    def manage_handler(params: dict[str, Any]) -> dict[str, Any]:
        return {
            "added": [],
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
    dry = await tool.fn(
        ctx,
        action="delete",
        guids=["guid-1"],
        folder="Ops",
        dry_run=True,
    )

    assert dry["status"] == "dry_run"
    assert dry["payload"] == {"delete": [{"guid": "guid-1"}]}
    assert dry.get("folder") is None
    assert not call_v1.calls

    applied = await tool.fn(
        ctx,
        action="delete",
        guids=["guid-1"],
        folder="Ops",
    )

    assert applied["status"] == "applied"
    assert applied["summary"]["deleted"] == ["guid-1"]
    assert any(call_name == "manageSubscriptionsBulk" for call_name, _ in call_v1.calls)
    assert all(call_name != "getFolders" for call_name, _ in call_v1.calls)


@pytest.mark.asyncio
async def test_request_company_filters_existing_and_submits_remaining() -> None:
    logger = get_logger("test.request_company")
    server = FastMCP(name="TestServer")

    def company_search_handler(params: dict[str, Any]) -> dict[str, Any]:
        domain = params.get("domain")
        if domain == "existing.example":
            return {
                "results": [
                    {
                        "primary_domain": "existing.example",
                        "name": "Existing Corp",
                    }
                ]
            }
        return {"results": []}

    call_v1 = BridgeStub(
        {
            "getFolders": lambda _: [
                {
                    "name": "API",
                    "guid": "folder-1",
                    "companies": [],
                }
            ],
            "companySearch": company_search_handler,
        }
    )

    captured_payload: dict[str, Any] = {}

    def bulk_submit(params: dict[str, Any]) -> dict[str, Any]:
        nonlocal captured_payload
        captured_payload = params
        return {"accepted": params.get("file")}

    call_v2 = BridgeStub({"createCompanyRequestBulk": bulk_submit})

    tool = register_request_company_tool(
        server,
        call_v1,
        call_v2,
        logger=logger,
        default_folder="API",
    )

    ctx = FakeContext()
    result = await tool.fn(
        ctx,
        domains="existing.example,new.example,duplicate.example,duplicate.example",
    )

    assert result["status"] == "submitted_v2_bulk"
    assert result["successfully_requested"] == [
        "new.example",
        "duplicate.example",
    ]
    assert result["submitted"] == [
        "existing.example",
        "new.example",
        "duplicate.example",
        "duplicate.example",
    ]
    assert result["already_existing"] == [
        {"domain": "duplicate.example"},
        {"domain": "existing.example", "company_name": "Existing Corp"},
    ]
    payload_csv = captured_payload["file"].replace("\r\n", "\n")
    assert payload_csv.startswith("domain\n")
    assert "duplicate.example" in captured_payload["file"]
    assert result["folder_guid"] == "folder-1"
    assert result.get("folder_created") is None
    assert call_v2.calls[-1][0] == "createCompanyRequestBulk"


@pytest.mark.asyncio
async def test_request_company_dry_run_returns_preview() -> None:
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
            ],
            "companySearch": lambda _: {"results": []},
        }
    )
    call_v2 = BridgeStub({"createCompanyRequestBulk": lambda params: params})

    tool = register_request_company_tool(
        server,
        call_v1,
        call_v2,
        logger=logger,
        default_folder="API",
    )

    ctx = FakeContext()
    result = await tool.fn(
        ctx,
        domains="future.example",
        dry_run=True,
    )

    assert result["status"] == "dry_run"
    assert result["dry_run"] is True
    preview = result["csv_preview"].replace("\r\n", "\n")
    assert preview.startswith("domain\nfuture.example")
    assert result["successfully_requested"] == ["future.example"]
    assert result["folder_guid"] == "folder-1"
    assert result.get("folder_created") in (None, False)
    assert call_v2.calls == []
    assert any(tool_name == "getFolders" for tool_name, _ in call_v1.calls)
    assert all(tool_name != "createFolder" for tool_name, _ in call_v1.calls)


@pytest.mark.asyncio
async def test_request_company_dry_run_reports_missing_folder() -> None:
    logger = get_logger("test.request_company")
    server = FastMCP(name="TestServer")

    def _no_create(_: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("should not create")

    call_v1 = BridgeStub(
        {
            "companySearch": lambda _: {"results": []},
            "getFolders": lambda _: [],
            "createFolder": _no_create,
        }
    )
    call_v2 = BridgeStub({})

    tool = register_request_company_tool(
        server,
        call_v1,
        call_v2,
        logger=logger,
        default_folder=None,
    )

    ctx = FakeContext()
    result = await tool.fn(
        ctx,
        domains="manual.example",
        folder="Ops",
        dry_run=True,
    )

    assert result["status"] == "dry_run"
    assert result["folder_guid"] is None
    assert result["guidance"]
    assert "Ops" in (result["guidance"]["next_steps"] or "")
    assert any(tool_name == "getFolders" for tool_name, _ in call_v1.calls)
    assert call_v2.calls == []


@pytest.mark.asyncio
async def test_request_company_all_existing_skips_folder_resolution() -> None:
    logger = get_logger("test.request_company")
    server = FastMCP(name="TestServer")

    def existing_handler(params: dict[str, Any]) -> dict[str, Any]:
        domain = params.get("domain")
        return {
            "results": [
                {
                    "primary_domain": domain,
                    "name": f"{domain} Corp",
                }
            ]
        }

    call_v1 = BridgeStub({"companySearch": existing_handler})
    call_v2 = BridgeStub({})

    tool = register_request_company_tool(
        server,
        call_v1,
        call_v2,
        logger=logger,
        default_folder=None,
    )

    ctx = FakeContext()
    result = await tool.fn(ctx, domains="existing.example", folder="Ops")

    assert result["status"] == "already_existing"
    assert result["folder_guid"] is None
    assert all(tool_name != "getFolders" for tool_name, _ in call_v1.calls)
    assert call_v2.calls == []


@pytest.mark.asyncio
async def test_request_company_auto_creates_folder_when_missing() -> None:
    logger = get_logger("test.request_company")
    server = FastMCP(name="TestServer")

    call_v1 = BridgeStub(
        {
            "getFolders": lambda _: [],
            "createFolder": lambda params: {
                "guid": "auto-folder",
                "name": params["name"],
            },
            "companySearch": lambda _: {"results": []},
        }
    )
    call_v2 = BridgeStub({"createCompanyRequestBulk": lambda params: params})

    tool = register_request_company_tool(
        server,
        call_v1,
        call_v2,
        logger=logger,
        default_folder=None,
    )

    ctx = FakeContext()
    result = await tool.fn(ctx, domains="auto.example", folder="Operations")

    assert result["status"] == "submitted_v2_bulk"
    assert result["folder_guid"] == "auto-folder"
    assert result["folder_created"] is True
    assert any(call[0] == "createFolder" for call in call_v1.calls)


@pytest.mark.asyncio
async def test_manage_subscriptions_auto_creates_folder() -> None:
    logger = get_logger("test.manage_subscriptions")
    server = FastMCP(name="TestServer")

    def get_folders(_: dict[str, Any]) -> list[dict[str, Any]]:
        return []

    def create_folder(params: dict[str, Any]) -> dict[str, Any]:
        assert params["name"] == "Ops"
        assert "manage_subscriptions" in params["description"]
        return {"guid": "ops-folder"}

    def manage_bulk(params: dict[str, Any]) -> dict[str, Any]:
        assert params["add"][0]["folder"] == ["ops-folder"]
        return {"added": [entry["guid"] for entry in params["add"]]}

    call_v1 = BridgeStub(
        {
            "getFolders": get_folders,
            "createFolder": create_folder,
            "manageSubscriptionsBulk": manage_bulk,
        }
    )

    tool = register_manage_subscriptions_tool(
        server,
        call_v1,
        logger=logger,
        default_folder=None,
        default_type="continuous_monitoring",
    )

    ctx = FakeContext()
    result = await tool.fn(
        ctx,
        action="subscribe",
        guids=["guid-9"],
        folder="Ops",
    )

    assert result["status"] == "applied"
    assert result["folder_guid"] == "ops-folder"
    assert result["folder_created"] is True
    assert any(call[0] == "createFolder" for call in call_v1.calls)
