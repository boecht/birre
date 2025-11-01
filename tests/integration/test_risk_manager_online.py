"""Online integration tests for BiRRe risk manager context tools."""

from __future__ import annotations

import os
from dataclasses import replace
from typing import Any

import pytest
import pytest_asyncio

try:
    from fastmcp.client import Client
    from fastmcp.client.client import CallToolResult
except ImportError:
    pytest.skip("fastmcp client not installed; skipping online tests", allow_module_level=True)

from birre import create_birre_server
from birre.config.settings import resolve_birre_settings
from birre.infrastructure.logging import get_logger

pytestmark = [pytest.mark.integration, pytest.mark.online]


@pytest.fixture(scope="session")
def require_api_key() -> str:
    """Ensure BitSight API key is available."""
    api_key = os.getenv("BITSIGHT_API_KEY")
    if not api_key:
        pytest.skip("BITSIGHT_API_KEY not configured; skipping online tests")
    return api_key


@pytest_asyncio.fixture
async def risk_manager_client(require_api_key: str):
    """Provide FastMCP client with risk_manager context."""
    base_settings = resolve_birre_settings()
    # Use dataclasses.replace to override frozen field
    settings = replace(base_settings, context="risk_manager")
    logger = get_logger("birre.online.risk_manager")
    server = create_birre_server(settings, logger=logger)
    async with Client(server) as client:
        yield client


def _extract_content(result: CallToolResult) -> dict[str, Any]:
    """Extract JSON content from CallToolResult."""
    import json

    # Try structured_content first
    if hasattr(result, "structured_content") and isinstance(result.structured_content, dict):
        return result.structured_content

    # Try data attribute (might be dict or list)
    if hasattr(result, "data"):
        data = result.data
        if isinstance(data, dict):
            return data
        if isinstance(data, list) and data:
            return _extract_from_list(data)

    # Try content blocks
    if hasattr(result, "content") and isinstance(result.content, list) and result.content:
        first_block = result.content[0]
        if hasattr(first_block, "text"):
            return json.loads(first_block.text)

    return {}


def _extract_from_list(data_list: list[Any]) -> dict[str, Any]:
    """Extract content from a list of data items."""
    import json

    first_item = data_list[0]
    if hasattr(first_item, "content"):
        content = first_item.content
        if hasattr(content, "text"):
            return json.loads(content.text)
    if isinstance(first_item, dict):
        return first_item
    return {}


@pytest.mark.asyncio
async def test_company_search_interactive_returns_metadata(
    risk_manager_client: Client,
) -> None:
    """Verify company_search_interactive includes folder membership."""
    result = await risk_manager_client.call_tool(
        "company_search_interactive",
        {"name": "GitHub"},
    )

    content = _extract_content(result)

    # The response should have a "results" key, not "companies"
    results = content.get("results", [])

    assert results, "Expected at least one result"
    first_result = results[0]
    assert "guid" in first_result
    assert "name" in first_result
    # Interactive search returns enhanced metadata
    assert isinstance(first_result, dict)


@pytest.mark.asyncio
async def test_manage_subscriptions_dry_run(risk_manager_client: Client) -> None:
    """Verify manage_subscriptions dry-run mode doesn't modify data."""
    # Use a test company GUID (this won't actually modify anything in dry-run)
    test_guid = "a940bb61-33c4-42c9-9231-c8194c305db3"  # Example GUID format

    result = await risk_manager_client.call_tool(
        "manage_subscriptions",
        {
            "action": "add",
            "guids": [test_guid],
            "folder": "API",  # Provide folder explicitly
            "dry_run": True,
        },
    )

    content = _extract_content(result)

    # Dry run should return preview without errors
    assert content.get("status") == "dry_run"
    assert "payload" in content


@pytest.mark.asyncio
async def test_request_company_dry_run(risk_manager_client: Client) -> None:
    """Verify request_company dry-run mode works."""
    result = await risk_manager_client.call_tool(
        "request_company",
        {
            "domain": "example-test-domain.com",
            "company_name": "Example Test Company",  # Provide company_name explicitly
            "folder": "API",  # Provide folder explicitly
            "dry_run": True,
        },
    )

    content = _extract_content(result)

    # Should return response without errors
    assert content is not None
    assert isinstance(content, dict)
