from __future__ import annotations

import json
from collections.abc import Mapping, MutableMapping
from typing import Any, Iterator

import httpx
from fastmcp import FastMCP


SCHEMA_REF_PREFIX = "#/components/schemas/"
def _extract_schemas(openapi_spec: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the schemas mapping from the OpenAPI spec if available."""

    components = openapi_spec.get("components")
    if not isinstance(components, Mapping):
        return {}
    schemas = components.get("schemas")
    if isinstance(schemas, Mapping):
        return schemas
    return {}


def _iter_response_maps(paths: Mapping[str, Any]) -> Iterator[MutableMapping[str, Any]]:
    """Yield mutable response maps from the OpenAPI paths section."""

    for path_item in paths.values():
        if not isinstance(path_item, Mapping):
            continue
        for method, operation in path_item.items():
            if method == "parameters" or not isinstance(operation, Mapping):
                continue
            responses = operation.get("responses")
            if isinstance(responses, MutableMapping):
                yield responses


def _requires_schema_wrap(response: Any) -> bool:
    if not isinstance(response, Mapping):
        return False
    if set(response.keys()) != {"$ref"}:
        return False
    ref_value = response.get("$ref")
    return isinstance(ref_value, str) and ref_value.startswith(SCHEMA_REF_PREFIX)


def _resolve_description(
    *,
    schema_name: str,
    status_code: str,
    schemas: Mapping[str, Any],
) -> str:
    schema_meta = schemas.get(schema_name)
    if isinstance(schema_meta, Mapping):
        meta_description = schema_meta.get("description")
        if isinstance(meta_description, str):
            stripped = meta_description.strip()
            if stripped:
                return stripped
    return f"HTTP {status_code} response referencing schema {schema_name}"


def _wrap_schema_reference(schema_ref: str, description: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {
            "application/json": {
                "schema": {"$ref": schema_ref}
            }
        },
    }


def _normalize_schema_response_refs(openapi_spec: Any) -> None:
    """Ensure response objects don't reference schemas directly."""

    if not isinstance(openapi_spec, Mapping):  # Defensive guard for malformed specs
        return

    schemas = _extract_schemas(openapi_spec)
    paths = openapi_spec.get("paths")
    if not isinstance(paths, Mapping):
        return

    for responses in _iter_response_maps(paths):
        for status_code, response in responses.items():
            if not _requires_schema_wrap(response):
                continue
            schema_ref = response["$ref"]
            schema_name = schema_ref.split("/")[-1]
            description = _resolve_description(
                schema_name=schema_name,
                status_code=str(status_code),
                schemas=schemas,
            )
            responses[status_code] = _wrap_schema_reference(schema_ref, description)


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
