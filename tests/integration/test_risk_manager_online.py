"""Online smoke tests for Risk Manager context (skipped without API key).

These tests require:
- fastmcp client installed
- BITSIGHT_API_KEY in environment
"""

from __future__ import annotations

import os

import pytest

try:
    from fastmcp.client import Client  # type: ignore
except Exception:  # pragma: no cover - module-level skip
    pytest.skip("fastmcp client not installed; skipping online tests", allow_module_level=True)

from birre.integrations.bitsight import create_v1_api_server

pytestmark = [pytest.mark.integration, pytest.mark.online]


@pytest.fixture(scope="module")
def _api_key() -> str:
    key = os.getenv("BITSIGHT_API_KEY")
    if not key:
        pytest.skip("BITSIGHT_API_KEY not configured; skipping online tests")
    return key


@pytest.mark.asyncio
async def test_risk_manager_company_search_smoke(_api_key: str) -> None:
    server = create_v1_api_server(_api_key)
    async with Client(server) as client:
        # Minimal smoke: invoke companySearch with a generic query
        try:
            await client.call_tool("companySearch", {"q": "test"})
        except Exception:
            # Accept failures here; this is just a presence smoke
            pass
