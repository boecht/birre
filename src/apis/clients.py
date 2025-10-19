from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx
from fastmcp import FastMCP
from prance import ResolvingParser
from prance.util import resolver as prance_resolver


SCHEMA_REF_PREFIX = "#/components/schemas/"


def _wrap_schema_responses(spec: Any) -> None:
    if not isinstance(spec, Mapping):
        return

    components = spec.get("components")
    schemas: Mapping[str, Any] = {}
    if isinstance(components, Mapping):
        candidate = components.get("schemas")
        if isinstance(candidate, Mapping):
            schemas = candidate

    paths = spec.get("paths")
    if not isinstance(paths, Mapping):
        return

    for path_item in paths.values():
        if not isinstance(path_item, Mapping):
            continue
        for operation in path_item.values():
            if not isinstance(operation, Mapping):
                continue
            responses = operation.get("responses")
            if not isinstance(responses, Mapping):
                continue
            for status, response in list(responses.items()):
                if not isinstance(response, Mapping):
                    continue
                if "content" in response:
                    continue
                ref = response.get("$ref")
                if not (isinstance(ref, str) and ref.startswith(SCHEMA_REF_PREFIX)):
                    continue

                schema_name = ref.split("/")[-1]
                description = ""
                schema = schemas.get(schema_name)
                if isinstance(schema, Mapping):
                    maybe_description = schema.get("description")
                    if isinstance(maybe_description, str):
                        description = maybe_description

                responses[status] = {
                    "description": description,
                    "content": {"application/json": {"schema": {"$ref": ref}}},
                }


def _load_api_spec(path: str) -> Any:
    parser = ResolvingParser(
        str(Path(path).resolve()),
        strict=True,
        resolve_types=prance_resolver.RESOLVE_FILES | prance_resolver.RESOLVE_HTTP,
    )
    specification = parser.specification
    _wrap_schema_responses(specification)
    return specification


def _create_client(
    base_url: str, api_key: str, *, verify: bool | str = True
) -> httpx.AsyncClient:
    client_kwargs: dict[str, Any] = {
        "base_url": base_url,
        "auth": (api_key, ""),
        "headers": {"Accept": "application/json"},
        "timeout": 30.0,
        "verify": verify,
    }
    return httpx.AsyncClient(**client_kwargs)


def create_v1_api_server(
    api_key: str, *, verify: bool | str = True
) -> FastMCP:
    """Build the BitSight v1 FastMCP server."""

    spec = _load_api_spec("apis/bitsight.v1.schema.json")
    client = _create_client("https://api.bitsighttech.com/v1", api_key, verify=verify)

    return FastMCP.from_openapi(
        openapi_spec=spec,
        client=client,
        name="BitSight-v1-API",
    )


def create_v2_api_server(
    api_key: str, *, verify: bool | str = True
) -> FastMCP:
    """Build the BitSight v2 FastMCP server."""

    spec = _load_api_spec("apis/bitsight.v2.schema.json")
    client = _create_client("https://api.bitsighttech.com/v2", api_key, verify=verify)

    return FastMCP.from_openapi(
        openapi_spec=spec,
        client=client,
        name="BitSight-v2-API",
    )


__all__ = ["create_v1_api_server", "create_v2_api_server"]
