from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import httpx
from fastmcp import FastMCP


SCHEMA_REF_PREFIX = "#/components/schemas/"


def _normalize_schema_response_refs(openapi_spec: Any) -> None:
    """Ensure response objects don't reference schemas directly.

    Some BitSight OpenAPI responses incorrectly point 4xx entries straight to a
    schema definition. FastMCP expects a full Response object and emits warnings
    when it encounters those bare schema references. This helper wraps such
    references in a minimal JSON response with a sensible description so the
    parser treats them as proper responses.
    """

    if not isinstance(openapi_spec, dict):  # Defensive guard for malformed specs
        return

    components = openapi_spec.get("components")
    schemas = None
    if isinstance(components, Mapping):
        schemas = components.get("schemas")
    if not isinstance(schemas, Mapping):
        schemas = {}

    paths = openapi_spec.get("paths", {})
    if not isinstance(paths, Mapping):
        return

    for path_item in paths.values():
        if not isinstance(path_item, Mapping):
            continue
        for method, operation in path_item.items():
            if method == "parameters" or not isinstance(operation, Mapping):
                continue
            responses = operation.get("responses")
            if not isinstance(responses, Mapping):
                continue
            for status_code, response in list(responses.items()):
                if (
                    isinstance(response, Mapping)
                    and set(response.keys()) == {"$ref"}
                    and isinstance(response["$ref"], str)
                    and response["$ref"].startswith(SCHEMA_REF_PREFIX)
                ):
                    schema_ref: str = response["$ref"]
                    schema_name = schema_ref.split("/")[-1]
                    schema_meta = schemas.get(schema_name)
                    description: str | None = None
                    if isinstance(schema_meta, Mapping):
                        meta_description = schema_meta.get("description")
                        if isinstance(meta_description, str) and meta_description.strip():
                            description = meta_description.strip()
                    if description is None:
                        description = (
                            f"HTTP {status_code} response referencing schema {schema_name}"
                        )

                    responses[status_code] = {
                        "description": description,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": schema_ref}
                            }
                        },
                    }


def _load_api_spec(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        spec = json.load(handle)
    _normalize_schema_response_refs(spec)
    return spec


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
