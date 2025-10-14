import logging
import os
from functools import partial

import pytest

from src import birre
from src.config import DEFAULT_MAX_FINDINGS, DEFAULT_RISK_VECTOR_FILTER


class DummyFastMCP:
    """Lightweight stand-in for FastMCP to capture constructor arguments."""

    def __init__(self, *, name: str, instructions: str, **kwargs):
        self.name = name
        self.instructions = instructions
        # Mirror FastMCP allowing optional kwargs while tracking unexpected input.
        self.extra_kwargs = kwargs


class AsyncCallRecorder:
    """Capture async call arguments for fake OpenAPI bridge functions."""

    def __init__(self, label: str):
        self.label = label
        self.calls: list[dict[str, object]] = []

    async def __call__(
        self,
        api_server: object,
        tool_name: str,
        ctx: object,
        params: dict[str, object],
        *,
        logger: logging.Logger,
    ) -> dict[str, object]:
        payload = {
            "api_server": api_server,
            "tool_name": tool_name,
            "ctx": ctx,
            "params": params,
            "logger": logger,
        }
        self.calls.append(payload)
        return {"label": self.label, "tool": tool_name, "params": params}


EXPECTED_V1_KEEP = {
    "companySearch",
    "manageSubscriptionsBulk",
    "getCompany",
    "getCompaniesFindings",
    "getFolders",
    "getCompanySubscriptions",
}


EXPECTED_V2_KEEP = {
    "getCompanyRequests",
    "createCompanyRequest",
    "createCompanyRequestBulk",
}


@pytest.fixture(autouse=True)
def restore_subscription_env(monkeypatch):
    monkeypatch.delenv("BIRRE_SUBSCRIPTION_FOLDER", raising=False)
    monkeypatch.delenv("BIRRE_SUBSCRIPTION_TYPE", raising=False)
    monkeypatch.delenv("BIRRE_ENABLE_V2", raising=False)


@pytest.fixture
def logger():
    return logging.getLogger("birre-tests")


@pytest.mark.asyncio
async def test_create_birre_server_standard_context(monkeypatch, logger):
    v1_server = object()
    recorded_calls = {}
    scheduled = []

    monkeypatch.setattr(birre, "FastMCP", DummyFastMCP)
    monkeypatch.setattr(
        birre,
        "create_v1_api_server",
        lambda api_key, verify: (api_key, verify, v1_server),
    )

    def fail_create_v2(*_args, **_kwargs):
        pytest.fail("create_v2_api_server should not be invoked for the standard context")

    monkeypatch.setattr(birre, "create_v2_api_server", fail_create_v2)

    def capture_schedule(server, keep):
        scheduled.append((server, set(keep)))

    monkeypatch.setattr(birre, "_schedule_tool_disablement", capture_schedule)

    v1_recorder = AsyncCallRecorder("v1")

    monkeypatch.setattr(birre, "call_v1_openapi_tool", v1_recorder)

    def capture_rating(server, call_v1_tool, *, logger, risk_vector_filter, max_findings):
        recorded_calls["rating"] = {
            "server": server,
            "call_v1_tool": call_v1_tool,
            "logger": logger,
            "risk_vector_filter": risk_vector_filter,
            "max_findings": max_findings,
        }

    monkeypatch.setattr(birre, "register_company_rating_tool", capture_rating)

    def capture_search(server, call_v1_tool, *, logger):
        recorded_calls["search"] = {
            "server": server,
            "call_v1_tool": call_v1_tool,
            "logger": logger,
        }

    monkeypatch.setattr(birre, "register_company_search_tool", capture_search)

    settings = {
        "api_key": "api-key",
        "subscription_folder": "/tmp/subscriptions",
        "subscription_type": "managed",
    }

    server = birre.create_birre_server(settings, logger)

    assert isinstance(server, DummyFastMCP)
    assert server.extra_kwargs == {}
    assert server.name == "io.github.boecht.birre"
    assert server.instructions == birre.INSTRUCTIONS_MAP["standard"]
    assert hasattr(server, "call_v1_tool")
    assert isinstance(server.call_v1_tool, partial)
    assert server.call_v1_tool.func is v1_recorder
    assert server.call_v1_tool.args == (("api-key", True, v1_server),)
    assert server.call_v1_tool.keywords == {"logger": logger}

    ctx = object()
    params = {"guid": "1234"}
    result = await server.call_v1_tool("companySearch", ctx, params)
    assert result == {"label": "v1", "tool": "companySearch", "params": params}
    assert v1_recorder.calls == [
        {
            "api_server": ("api-key", True, v1_server),
            "tool_name": "companySearch",
            "ctx": ctx,
            "params": params,
            "logger": logger,
        }
    ]

    assert recorded_calls["rating"]["risk_vector_filter"] == DEFAULT_RISK_VECTOR_FILTER
    assert recorded_calls["rating"]["max_findings"] == DEFAULT_MAX_FINDINGS
    assert "call_v1_tool" in recorded_calls["search"]
    call_v1_tool = recorded_calls["search"]["call_v1_tool"]
    assert isinstance(call_v1_tool, partial)
    assert call_v1_tool.func is v1_recorder
    assert call_v1_tool.args == (("api-key", True, v1_server),)
    assert call_v1_tool.keywords == {"logger": logger}

    assert scheduled == [(("api-key", True, v1_server), EXPECTED_V1_KEEP)]

    assert os.environ["BIRRE_SUBSCRIPTION_FOLDER"] == "/tmp/subscriptions"
    assert os.environ["BIRRE_SUBSCRIPTION_TYPE"] == "managed"
    assert not hasattr(server, "call_v2_tool")


@pytest.mark.asyncio
async def test_create_birre_server_risk_manager_context(monkeypatch, logger):
    v1_server = object()
    v2_server = object()
    scheduled = []
    captures = {}

    monkeypatch.setattr(birre, "FastMCP", DummyFastMCP)
    monkeypatch.setattr(
        birre,
        "create_v1_api_server",
        lambda api_key, verify: (api_key, verify, v1_server),
    )
    monkeypatch.setattr(
        birre,
        "create_v2_api_server",
        lambda api_key, verify: (api_key, verify, v2_server),
    )

    def capture_schedule(server, keep):
        scheduled.append((server, set(keep)))

    monkeypatch.setattr(birre, "_schedule_tool_disablement", capture_schedule)

    v1_recorder = AsyncCallRecorder("v1")
    v2_recorder = AsyncCallRecorder("v2")

    monkeypatch.setattr(birre, "call_v1_openapi_tool", v1_recorder)
    monkeypatch.setattr(birre, "call_v2_openapi_tool", v2_recorder)

    def capture_rating(server, call_v1_tool, *, logger, risk_vector_filter, max_findings):
        captures.setdefault("rating", []).append((server, risk_vector_filter, max_findings))

    monkeypatch.setattr(birre, "register_company_rating_tool", capture_rating)

    def capture_search(server, call_v1_tool, *, logger):
        captures.setdefault("search", []).append(server)

    monkeypatch.setattr(birre, "register_company_search_tool", capture_search)

    import src.business.risk_manager as risk_manager

    def capture_interactive(server, call_v1_tool, *, logger, default_folder, default_type, max_findings):
        captures.setdefault("interactive", []).append((default_folder, default_type, max_findings))

    def capture_manage(server, call_v1_tool, *, logger, default_folder, default_type):
        captures.setdefault("manage", []).append((default_folder, default_type))

    def capture_request(server, call_v1_tool, call_v2_tool, *, logger, default_folder, default_type):
        captures.setdefault("request", []).append((default_folder, default_type))

    monkeypatch.setattr(risk_manager, "register_company_search_interactive_tool", capture_interactive)
    monkeypatch.setattr(risk_manager, "register_manage_subscriptions_tool", capture_manage)
    monkeypatch.setattr(risk_manager, "register_request_company_tool", capture_request)

    settings = {
        "api_key": "key",
        "context": "risk_manager",
        "subscription_folder": "folder",
        "subscription_type": "type",
        "max_findings": 7,
        "risk_vector_filter": "compromised_hosts",
    }

    server = birre.create_birre_server(settings, logger)

    assert isinstance(server, DummyFastMCP)
    assert server.extra_kwargs == {}
    assert server.name == "io.github.boecht.birre"
    assert server.instructions == birre.INSTRUCTIONS_MAP["risk_manager"]
    assert hasattr(server, "call_v1_tool")
    assert hasattr(server, "call_v2_tool")
    assert server.call_v1_tool.func is v1_recorder
    assert server.call_v1_tool.args == (("key", True, v1_server),)
    assert server.call_v1_tool.keywords == {"logger": logger}
    assert server.call_v2_tool.func is v2_recorder
    assert server.call_v2_tool.args == (("key", True, v2_server),)
    assert server.call_v2_tool.keywords == {"logger": logger}

    ctx = object()
    params_v1 = {"tool": "search"}
    params_v2 = {"tool": "request"}
    await server.call_v1_tool("companySearch", ctx, params_v1)
    await server.call_v2_tool("getCompanyRequests", ctx, params_v2)

    assert v1_recorder.calls == [
        {
            "api_server": ("key", True, v1_server),
            "tool_name": "companySearch",
            "ctx": ctx,
            "params": params_v1,
            "logger": logger,
        }
    ]
    assert v2_recorder.calls == [
        {
            "api_server": ("key", True, v2_server),
            "tool_name": "getCompanyRequests",
            "ctx": ctx,
            "params": params_v2,
            "logger": logger,
        }
    ]

    assert captures["rating"] == [(server, "compromised_hosts", 7)]
    assert captures["search"] == [server]
    assert captures["interactive"] == [("folder", "type", 7)]
    assert captures["manage"] == [("folder", "type")]
    assert captures["request"] == [("folder", "type")]

    assert scheduled == [
        (("key", True, v1_server), EXPECTED_V1_KEEP),
        (("key", True, v2_server), EXPECTED_V2_KEEP),
    ]


@pytest.mark.asyncio
async def test_create_birre_server_enables_v2_via_env(monkeypatch, logger):
    v1_server = object()
    v2_server = object()
    scheduled = []

    monkeypatch.setattr(birre, "FastMCP", DummyFastMCP)
    monkeypatch.setattr(
        birre,
        "create_v1_api_server",
        lambda api_key, verify: (api_key, verify, v1_server),
    )

    def fake_create_v2(api_key, verify):
        return api_key, verify, v2_server

    monkeypatch.setattr(birre, "create_v2_api_server", fake_create_v2)

    def capture_schedule(server, keep):
        scheduled.append((server, set(keep)))

    monkeypatch.setattr(birre, "_schedule_tool_disablement", capture_schedule)

    v1_recorder = AsyncCallRecorder("v1")
    v2_recorder = AsyncCallRecorder("v2")

    monkeypatch.setattr(birre, "call_v1_openapi_tool", v1_recorder)
    monkeypatch.setattr(birre, "call_v2_openapi_tool", v2_recorder)
    monkeypatch.setattr(birre, "register_company_rating_tool", lambda *args, **kwargs: None)
    monkeypatch.setattr(birre, "register_company_search_tool", lambda *args, **kwargs: None)

    monkeypatch.setenv("BIRRE_ENABLE_V2", "true")

    server = birre.create_birre_server({"api_key": "key"}, logger)

    assert hasattr(server, "call_v2_tool")
    assert server.name == "io.github.boecht.birre"
    assert server.extra_kwargs == {}
    assert server.call_v1_tool.func is v1_recorder
    assert server.call_v1_tool.args == (("key", True, v1_server),)
    assert server.call_v1_tool.keywords == {"logger": logger}
    assert server.call_v2_tool.func is v2_recorder
    assert server.call_v2_tool.args == (("key", True, v2_server),)
    assert server.call_v2_tool.keywords == {"logger": logger}

    await server.call_v1_tool("companySearch", object(), {})
    await server.call_v2_tool("getCompanyRequests", object(), {})

    assert v1_recorder.calls[0]["api_server"] == ("key", True, v1_server)
    assert v2_recorder.calls[0]["api_server"] == ("key", True, v2_server)

    assert scheduled == [
        (("key", True, v1_server), EXPECTED_V1_KEEP),
        (("key", True, v2_server), EXPECTED_V2_KEEP),
    ]
