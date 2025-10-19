"""Live integration tests for BiRRe using the in-process FastMCP client."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

import pytest
import pytest_asyncio

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from fastmcp.client import Client
    from fastmcp.client.client import CallToolResult
except ImportError:
    pytest.skip(
        "fastmcp client not installed; skipping live tests", allow_module_level=True
    )

from src.birre import create_birre_server  # ruff: noqa: E402
from src.settings import resolve_birre_settings  # ruff: noqa: E402
from src.logging import get_logger  # ruff: noqa: E402


pytestmark = pytest.mark.live


def _unwrap(result: CallToolResult) -> Dict[str, Any]:
    """Normalize a CallToolResult into a plain dictionary."""

    if result.data is not None:
        return result.data  # type: ignore[return-value]

    structured = result.structured_content
    if structured:
        if isinstance(structured, dict) and "result" in structured:
            inner = structured["result"]
            if isinstance(inner, dict):
                return inner
        if isinstance(structured, dict):
            return structured  # type: ignore[return-value]

    blocks = result.content or []
    if blocks:
        text = getattr(blocks[0], "text", None)
        if text:
            return json.loads(text)

    raise AssertionError("Unable to unwrap CallToolResult into structured data")


@pytest.fixture(scope="session")
def require_live_api_key() -> str:
    api_key = os.getenv("BITSIGHT_API_KEY")
    if not api_key:
        pytest.skip("BITSIGHT_API_KEY not configured; skipping live tests")
    return api_key


@pytest_asyncio.fixture
async def birre_client(require_live_api_key: str):
    """Provide an in-process FastMCP client for BiRRe."""

    settings = resolve_birre_settings()
    logger = get_logger("birre.live.test")
    server = create_birre_server(settings, logger=logger)
    async with Client(server) as client:
        yield client


async def _fetch_first_company(client: Client, query: str = "GitHub") -> Dict[str, Any]:
    result = await client.call_tool("company_search", {"name": query})
    payload = _unwrap(result)
    companies = payload.get("companies", [])
    assert companies, "expected at least one company from BitSight search"
    return companies[0]


async def _fetch_company_by_name(
    client: Client, query: str, target_name: str
) -> Dict[str, Any]:
    result = await client.call_tool("company_search", {"name": query})
    payload = _unwrap(result)
    for company in payload.get("companies", []):
        if company.get("name") == target_name:
            return company
    pytest.skip(f"Company '{target_name}' not found in BitSight search results")


@pytest.mark.asyncio
async def test_company_search_returns_results(birre_client: Client) -> None:
    company = await _fetch_first_company(birre_client, "Rheinmetall")
    assert company["guid"], "company GUID missing"
    assert company["name"].lower().startswith("rheinmetall")


@pytest.mark.asyncio
async def test_company_rating_contains_rating_data(birre_client: Client) -> None:
    company = await _fetch_company_by_name(
        birre_client, "Rheinmetall", "Rheinmetall AG"
    )
    guid = company["guid"]

    result = await birre_client.call_tool("get_company_rating", {"guid": guid})
    rating_payload = _unwrap(result)

    current = rating_payload["current_rating"]
    assert isinstance(current, dict)
    assert set(current.keys()) == {"value", "color"}
    assert current["value"] is None or isinstance(current["value"], (int, float))

    trend = rating_payload.get("trend_8_weeks")
    assert isinstance(trend, dict)
    assert set(trend.keys()) == {"direction", "change"}
