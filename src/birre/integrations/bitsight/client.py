"""BitSight FastMCP client wiring and schema loaders."""

from __future__ import annotations

import ssl
from collections.abc import Iterator, Mapping, MutableMapping
from importlib import resources
from typing import Any

import httpx
from fastmcp import FastMCP
from prance import ResolvingParser
from prance.util import resolver as prance_resolver

SCHEMA_REF_PREFIX = "#/components/schemas/"
DEFAULT_V1_API_BASE_URL = "https://api.bitsighttech.com/v1"
DEFAULT_V2_API_BASE_URL = "https://api.bitsighttech.com/v2"


def _get_schema_definitions(spec: Any) -> Mapping[str, Any]:
    if not isinstance(spec, Mapping):
        return {}

    components = spec.get("components")
    if not isinstance(components, Mapping):
        return {}

    schemas = components.get("schemas")
    if not isinstance(schemas, Mapping):
        return {}

    return schemas


def _iter_api_responses(spec: Any) -> Iterator[MutableMapping[str, Any]]:
    if not isinstance(spec, Mapping):
        return

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
            if isinstance(responses, MutableMapping):
                yield responses


def _schema_description(schemas: Mapping[str, Any], ref: str) -> str:
    schema_name = ref.split("/")[-1]
    schema = schemas.get(schema_name)
    if isinstance(schema, Mapping):
        maybe_description = schema.get("description")
        if isinstance(maybe_description, str):
            return maybe_description
    return ""


def _convert_response(
    response: Mapping[str, Any], schemas: Mapping[str, Any]
) -> Mapping[str, Any] | None:
    if "content" in response:
        return None

    ref = response.get("$ref")
    if not (isinstance(ref, str) and ref.startswith(SCHEMA_REF_PREFIX)):
        return None

    description = _schema_description(schemas, ref)
    return {
        "description": description,
        "content": {"application/json": {"schema": {"$ref": ref}}},
    }


def _wrap_schema_responses(spec: Any) -> None:
    schemas = _get_schema_definitions(spec)
    for responses in _iter_api_responses(spec):
        for status, response in responses.items():
            if not isinstance(response, Mapping):
                continue
            replacement = _convert_response(response, schemas)
            if replacement is not None:
                responses[status] = replacement


def _load_api_spec(resource_name: str) -> Any:
    """Load an OpenAPI specification bundled with the package."""

    resource_path = resources.files("birre.resources") / "apis" / resource_name
    with resources.as_file(resource_path) as spec_path:
        parser = ResolvingParser(
            str(spec_path),
            strict=True,
            resolve_types=prance_resolver.RESOLVE_FILES | prance_resolver.RESOLVE_HTTP,
        )
        specification = parser.specification
    _wrap_schema_responses(specification)
    return specification


def _enforce_tls12(context: ssl.SSLContext) -> ssl.SSLContext:
    """Ensure TLS 1.2+ is required regardless of interpreter defaults."""

    tls_version = getattr(ssl, "TLSVersion", None)
    if tls_version is not None:
        context.minimum_version = tls_version.TLSv1_2
    else:
        context.options |= getattr(ssl, "OP_NO_TLSv1", 0)
        context.options |= getattr(ssl, "OP_NO_TLSv1_1", 0)
    return context


def _build_verify_option(verify: bool | str) -> bool | ssl.SSLContext:
    if verify is True:
        return _enforce_tls12(ssl.create_default_context())  # NOSONAR

    if verify is False:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)  # NOSONAR
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE  # NOSONAR
        return _enforce_tls12(context)

    if isinstance(verify, str):
        context = ssl.create_default_context(cafile=verify)  # NOSONAR
        return _enforce_tls12(context)

    return verify


def _create_client(
    base_url: str, api_key: str, *, verify: bool | str = True
) -> httpx.AsyncClient:
    verify_option = _build_verify_option(verify)

    client_kwargs: dict[str, Any] = {
        "base_url": base_url,
        "auth": (api_key, ""),
        "headers": {"Accept": "application/json"},
        "timeout": 30.0,
        "verify": verify_option,
    }
    return httpx.AsyncClient(**client_kwargs)


def create_v1_api_server(
    api_key: str,
    *,
    verify: bool | str = True,
    base_url: str = DEFAULT_V1_API_BASE_URL,
) -> FastMCP:
    """Build the BitSight v1 FastMCP server."""

    spec = _load_api_spec("bitsight.v1.schema.json")
    client = _create_client(base_url, api_key, verify=verify)

    return FastMCP.from_openapi(
        openapi_spec=spec,
        client=client,
        name="BitSight-v1-API",
    )


def create_v2_api_server(
    api_key: str,
    *,
    verify: bool | str = True,
    base_url: str = DEFAULT_V2_API_BASE_URL,
) -> FastMCP:
    """Build the BitSight v2 FastMCP server."""

    spec = _load_api_spec("bitsight.v2.schema.json")
    client = _create_client(base_url, api_key, verify=verify)

    return FastMCP.from_openapi(
        openapi_spec=spec,
        client=client,
        name="BitSight-v2-API",
    )


__all__ = ["create_v1_api_server", "create_v2_api_server"]
