"""Live integration tests for BiRRe using the in-process FastMCP client."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Sequence
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from fastmcp.client import Client
    from fastmcp.client.client import CallToolResult
except ImportError:
    pytest.skip("fastmcp client not installed; skipping online tests", allow_module_level=True)

from birre import create_birre_server  # noqa: E402
from birre.config.settings import resolve_birre_settings  # noqa: E402
from birre.infrastructure.logging import get_logger  # noqa: E402

pytestmark = [pytest.mark.integration, pytest.mark.online]


def _unwrap(result: CallToolResult) -> dict[str, Any]:
    """Normalize a CallToolResult into a plain dictionary."""

    normalized = _normalize_data(result.data)
    if normalized is not None:
        return normalized

    normalized = _normalize_structured(result.structured_content)
    if normalized is not None:
        return normalized

    normalized = _normalize_blocks(result.content)
    if normalized is not None:
        return normalized

    raise AssertionError("Unable to unwrap CallToolResult into structured data")


def _normalize_data(data: Any) -> dict[str, Any] | None:
    if data is None:
        return None
    if is_dataclass(data):
        return asdict(data)
    if isinstance(data, BaseModel):
        return data.model_dump(mode="json")  # type: ignore[return-value]
    model_dump = getattr(data, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="json")  # type: ignore[call-arg]
        if isinstance(dumped, dict):
            return dumped
    if isinstance(data, dict):
        return data
    return None


def _normalize_structured(structured: Any) -> dict[str, Any] | None:
    if not structured or not isinstance(structured, dict):
        return None
    inner = structured.get("result")
    if isinstance(inner, dict):
        return inner
    return structured


def _normalize_blocks(
    blocks: Sequence[Any] | None,
) -> dict[str, Any] | None:
    if not blocks:
        return None
    text = getattr(blocks[0], "text", None)
    if not text:
        return None
    parsed = json.loads(text)
    return parsed if isinstance(parsed, dict) else None


@pytest.fixture(scope="session")
def require_online_api_key() -> str:
    """Ensure a BitSight API key is available for online integration runs."""

    api_key = os.getenv("BITSIGHT_API_KEY")
    if not api_key:
        pytest.skip("BITSIGHT_API_KEY not configured; skipping online tests")
    return api_key


@pytest_asyncio.fixture
async def birre_client(require_online_api_key: str):
    """Provide an in-process FastMCP client for BiRRe."""

    settings = resolve_birre_settings()
    logger = get_logger("birre.online.test")
    server = create_birre_server(settings, logger=logger)
    async with Client(server) as client:
        yield client


async def _fetch_first_company(client: Client, query: str = "GitHub") -> dict[str, Any]:
    result = await client.call_tool("company_search", {"name": query})
    payload = _unwrap(result)
    companies = payload.get("companies", [])
    assert companies, "expected at least one company from BitSight search"
    return companies[0]


async def _fetch_company_by_name(client: Client, query: str, target_name: str) -> dict[str, Any]:
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
    company = await _fetch_company_by_name(birre_client, "Rheinmetall", "Rheinmetall AG")
    guid = company["guid"]

    result = await birre_client.call_tool("get_company_rating", {"guid": guid})
    rating_payload = _unwrap(result)

    current = rating_payload["current_rating"]
    assert isinstance(current, dict)
    assert set(current.keys()) == {"value", "color"}
    assert current["value"] is None or isinstance(current["value"], int | float)

    trend = rating_payload.get("trend_8_weeks")
    assert isinstance(trend, dict)
    assert set(trend.keys()) == {"direction", "change"}
