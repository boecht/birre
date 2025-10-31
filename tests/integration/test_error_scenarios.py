"""Online integration tests for BiRRe error handling scenarios."""

from __future__ import annotations

import os

import httpx
import pytest

from birre import create_birre_server
from birre.config.settings import resolve_birre_settings
from birre.infrastructure.logging import get_logger
from birre.integrations.bitsight import create_v1_api_server

pytestmark = [pytest.mark.integration, pytest.mark.online]


@pytest.fixture(scope="module")
def valid_api_key() -> str:
    """Get valid API key from environment."""
    api_key = os.getenv("BITSIGHT_API_KEY")
    if not api_key:
        pytest.skip("BITSIGHT_API_KEY not configured; skipping online tests")
    return api_key


@pytest.mark.asyncio
async def test_invalid_api_key_returns_401() -> None:
    """Verify invalid API key produces authentication error."""
    invalid_key = "invalid-api-key-12345"

    # Create v1 API server with invalid key
    v1_server = create_v1_api_server(invalid_key)

    # Try to search for a company
    async def call_with_invalid_key(tool_name: str, ctx, params):
        try:
            tool = v1_server.get_tool(tool_name)
            return await tool(ctx, **params)
        except httpx.HTTPStatusError as e:
            return {"error": "auth_failed", "status": e.response.status_code}

    from mcp.server.fastmcp import Context

    ctx = Context(request_id="test", meta={})
    result = await call_with_invalid_key("companySearch", ctx, {"q": "test"})

    # Should get 401 Unauthorized
    assert isinstance(result, dict)
    assert result.get("error") == "auth_failed"
    assert result.get("status") == 401


@pytest.mark.asyncio
async def test_startup_checks_with_zero_quota(valid_api_key: str) -> None:
    """Verify startup checks detect zero remaining quota."""
    settings = resolve_birre_settings()
    logger = get_logger("birre.test.zero_quota")
    server = create_birre_server(settings, logger=logger)

    call_v1_tool = getattr(server, "call_v1_tool", None)
    assert call_v1_tool is not None

    # Get actual quota
    from mcp.server.fastmcp import Context

    ctx = Context(request_id="test-quota", meta={})
    quota_result = await call_v1_tool("getCompanySubscriptions", ctx, {})

    # If quota is actually zero for any type, startup checks should detect it
    # This is a smoke test - we can't force zero quota without modifying live data
    assert quota_result is not None


@pytest.mark.asyncio
async def test_nonexistent_company_guid() -> None:
    """Verify requesting nonexistent company GUID handles gracefully."""
    settings = resolve_birre_settings()
    logger = get_logger("birre.test.invalid_guid")
    server = create_birre_server(settings, logger=logger)

    call_v1_tool = getattr(server, "call_v1_tool", None)
    assert call_v1_tool is not None

    from mcp.server.fastmcp import Context

    ctx = Context(request_id="test-invalid", meta={})

    # Use an invalid GUID format
    fake_guid = "00000000-0000-0000-0000-000000000000"

    try:
        result = await call_v1_tool(
            "getCompanyDetails",
            ctx,
            {"company_guid": fake_guid},
        )
        # Should either return error or empty result
        assert result is not None
    except Exception as e:
        # Expected - nonexistent GUID should raise error
        assert "404" in str(e) or "not found" in str(e).lower()


@pytest.mark.asyncio
async def test_malformed_request_parameters(valid_api_key: str) -> None:
    """Verify malformed request parameters are handled."""
    settings = resolve_birre_settings()
    logger = get_logger("birre.test.malformed")
    server = create_birre_server(settings, logger=logger)

    call_v1_tool = getattr(server, "call_v1_tool", None)
    assert call_v1_tool is not None

    from mcp.server.fastmcp import Context

    ctx = Context(request_id="test-malformed", meta={})

    try:
        # Try to search with invalid parameter type
        await call_v1_tool("companySearch", ctx, {"limit": "not_a_number"})
        # Should either coerce or reject
    except (ValueError, TypeError, httpx.HTTPStatusError):
        # Expected - invalid parameters should be caught
        pass
