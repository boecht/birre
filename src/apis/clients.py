from __future__ import annotations

import json
from typing import Any

import httpx
from fastmcp import FastMCP

from ..logging import get_logger

_LOGGER = get_logger(__name__)


def _load_api_spec(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _create_client(base_url: str, api_key: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=base_url,
        auth=(api_key, ""),
        headers={"Accept": "application/json"},
        timeout=30.0,
    )


def create_v1_api_server(api_key: str) -> FastMCP:
    """Build the BitSight v1 FastMCP server."""

    spec = _load_api_spec("apis/bitsight.v1.schema.json")
    client = _create_client("https://api.bitsighttech.com/v1", api_key)

    return FastMCP.from_openapi(
        openapi_spec=spec,
        client=client,
        name="BitSight-v1-API",
    )


def create_v2_api_server(api_key: str) -> FastMCP:
    """Build the BitSight v2 FastMCP server."""

    spec = _load_api_spec("apis/bitsight.v2.schema.json")
    client = _create_client("https://api.bitsighttech.com/v2", api_key)

    return FastMCP.from_openapi(
        openapi_spec=spec,
        client=client,
        name="BitSight-v2-API",
    )


__all__ = ["create_v1_api_server", "create_v2_api_server"]
