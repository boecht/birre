"""Pytest configuration and compatibility stubs for optional dependencies.

The offline unit tests run without the third-party `fastmcp`, `httpx`, or
`python-dotenv` packages. When those imports are unavailable we provide minimal
stubs so imports succeed, while automatically skipping any tests marked
`@pytest.mark.live`. When the real dependencies are present (for live testing),
the stubs remain unused.
"""

import asyncio
import sys
import types

import pytest

try:  # pragma: no cover - best-effort import for live tests
    import fastmcp  # type: ignore
except ImportError:  # pragma: no cover - fallback stub
    fastmcp = None  # type: ignore[assignment]

STUB_FASTMCP = fastmcp is None

if STUB_FASTMCP:
    fastmcp = types.ModuleType("fastmcp")
    fastmcp.__path__ = []  # type: ignore[attr-defined]
    sys.modules["fastmcp"] = fastmcp

    tools_package = types.ModuleType("fastmcp.tools")
    tools_package.__dict__["__all__"] = []
    sys.modules["fastmcp.tools"] = tools_package

    tool_module = types.ModuleType("fastmcp.tools.tool")

    class FunctionTool:  # type: ignore[override]
        def __init__(self, func, name: str | None = None):
            self.fn = func
            self.name = name or getattr(func, "__name__", "tool")

    setattr(tool_module, "FunctionTool", FunctionTool)
    sys.modules["fastmcp.tools.tool"] = tool_module

    class Context:  # type: ignore[override]
        """Minimal stub of fastmcp.Context for offline unit tests."""

    class FastMCP:  # type: ignore[override]
        def __init__(self, *args, **kwargs):
            self.name = kwargs.get("name")
            self.instructions = kwargs.get("instructions")

        def get_tools(self):
            return {}

        def tool(self, *args, **kwargs):
            def decorator(func):
                return FunctionTool(func, kwargs.get("name"))

            return decorator

    setattr(fastmcp, "Context", Context)
    setattr(fastmcp, "FastMCP", FastMCP)
    setattr(fastmcp, "__FASTMCP_STUB__", True)

    client_module = types.ModuleType("fastmcp.client")

    class _MissingClient:
        def __init__(self, *args, **kwargs):
            raise ModuleNotFoundError("fastmcp client not installed for tests")

    setattr(client_module, "Client", _MissingClient)
    setattr(client_module, "__FASTMCP_STUB__", True)
    sys.modules["fastmcp.client"] = client_module
    sys.modules["fastmcp.client.client"] = client_module

if "dotenv" not in sys.modules:
    dotenv = types.ModuleType("dotenv")

    def load_dotenv(*args, **kwargs):
        return False

    setattr(dotenv, "load_dotenv", load_dotenv)
    sys.modules["dotenv"] = dotenv
    sys.modules["dotenv.main"] = dotenv

if "httpx" not in sys.modules:
    httpx = types.ModuleType("httpx")

    class HTTPError(Exception):
        pass

    class RequestError(HTTPError):
        pass

    class Response:
        def __init__(self, status_code: int = 200, text: str = ""):
            self.status_code = status_code
            self.text = text

    def get(*args, **kwargs):
        raise RequestError("httpx stub used during testing")

    setattr(httpx, "HTTPError", HTTPError)
    setattr(httpx, "RequestError", RequestError)
    setattr(httpx, "Response", Response)
    setattr(httpx, "get", get)
    sys.modules["httpx"] = httpx


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if not STUB_FASTMCP:
        return
    skip_live = pytest.mark.skip(reason="fastmcp dependency not installed")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)
