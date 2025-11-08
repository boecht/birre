"""Helpers for invoking BitSight OpenAPI endpoints via FastMCP."""

from __future__ import annotations

import json
import logging
import ssl
import traceback
from collections.abc import Iterable, Mapping
from typing import Any

import httpx
from fastmcp import Context, FastMCP

from birre.infrastructure.errors import (
    BirreError,
    classify_request_error,
)
from birre.infrastructure.logging import BoundLogger


def filter_none(params: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of ``params`` without keys set to ``None``."""

    filtered: dict[str, Any] = {}
    for key, value in params.items():
        if value is None:
            continue
        filtered[str(key)] = value
    return filtered


async def _parse_text_content(
    text: str, tool_name: str, ctx: Context, logger: BoundLogger
) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        await ctx.warning(f"Failed to parse text content for '{tool_name}' as JSON")
        logger.debug(
            "Unable to deserialize JSON payload from FastMCP tool response",
            tool=tool_name,
            exc_info=True,
        )
        return text


async def _normalize_tool_result(
    tool_result: Any, tool_name: str, ctx: Context, logger: BoundLogger
) -> Any:
    structured = getattr(tool_result, "structured_content", None)
    if structured is not None:
        if isinstance(structured, dict) and "result" in structured:
            return structured["result"]
        return structured

    content_blocks: Iterable[Any] | None = getattr(tool_result, "content", None)
    if content_blocks:
        first_block = next(iter(content_blocks), None)
        text = getattr(first_block, "text", None)
        if text is not None:
            return await _parse_text_content(text, tool_name, ctx, logger)

    await ctx.warning(
        f"FastMCP tool '{tool_name}' returned no structured data; passing raw result"
    )
    logger.warning(
        "FastMCP tool returned unstructured payload; returning raw result",
        tool=tool_name,
    )
    return tool_result


def _log_tls_error(
    mapped_error: BirreError,
    *,
    logger: BoundLogger,
    debug_enabled: bool,
    exc: Exception,
) -> None:
    log_fields = mapped_error.log_fields()
    summary = getattr(mapped_error, "summary", str(mapped_error))
    logger.error(summary, **log_fields)
    if debug_enabled:
        trace_text = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )
        logger.debug(
            "TLS handshake traceback",
            trace=trace_text,
            **log_fields,
        )
    for hint in mapped_error.hints:
        logger.error(f"Hint: {hint}", **log_fields)


async def call_openapi_tool(
    api_server: FastMCP,
    tool_name: str,
    ctx: Context,
    params: dict[str, Any],
    *,
    logger: BoundLogger,
) -> Any:
    """Invoke a FastMCP OpenAPI tool and normalize the result."""

    if not isinstance(tool_name, str) or not tool_name.strip():
        raise ValueError("tool_name must be a non-empty string")

    if not isinstance(params, Mapping):
        raise TypeError("params must be a mapping of argument names to values")

    resolved_tool_name = tool_name.strip()
    filtered_params = filter_none(params)

    debug_enabled = logging.getLogger().isEnabledFor(logging.DEBUG)

    try:
        await ctx.info(f"Calling FastMCP tool '{resolved_tool_name}'")
        async with Context(api_server):
            tool_result = await api_server._call_tool_middleware(
                resolved_tool_name,
                filtered_params,
            )

        return await _normalize_tool_result(
            tool_result, resolved_tool_name, ctx, logger
        )
    except httpx.HTTPStatusError as exc:
        await ctx.error(
            f"FastMCP tool '{resolved_tool_name}' returned HTTP {exc.response.status_code}: {exc}"
        )
        logger.error(
            "FastMCP tool returned HTTP error",
            tool=resolved_tool_name,
            status_code=exc.response.status_code,
            exc_info=debug_enabled,
        )
        raise
    except (httpx.RequestError, ssl.SSLError) as exc:
        mapped = classify_request_error(exc, tool_name=resolved_tool_name)
        if mapped is None:
            raise

        _log_tls_error(
            mapped,
            logger=logger,
            debug_enabled=debug_enabled,
            exc=exc,
        )
        await ctx.error(mapped.user_message)
        raise mapped from exc
    except Exception as exc:  # pragma: no cover - diagnostic fallback
        await ctx.error(f"FastMCP tool '{resolved_tool_name}' execution failed: {exc}")
        logger.error(
            "FastMCP tool execution failed",
            tool=resolved_tool_name,
            exc_info=True if debug_enabled else False,
        )
        raise


async def call_v1_openapi_tool(
    api_server: FastMCP,
    tool_name: str,
    ctx: Context,
    params: dict[str, Any],
    *,
    logger: BoundLogger,
) -> Any:
    """Invoke a BitSight v1 FastMCP tool and normalize the result.

    Parameters
    ----------
    api_server:
        FastMCP server generated from the BitSight v1 OpenAPI spec.
    tool_name:
        Name of the tool exposed by the generated server (e.g. ``"companySearch"``).
    ctx:
        Call context inherited from the business server; used for logging and
        nested tool execution.
    params:
        Raw parameters to forward to the FastMCP tool. ``None`` values are
        removed before invocation to satisfy strict argument validation.
    logger:
        Logger used for diagnostic messages.

    Returns
    -------
    Any
        Structured content returned by the tool, the inner ``result`` payload
        when present, or the raw ``ToolResult`` object as a last resort.

    Raises
    ------
    httpx.HTTPStatusError
        The FastMCP bridge raised an HTTP error while calling the BitSight v1
        API.
    Exception
        Any other error encountered during invocation is propagated after being
        logged via ``ctx`` and the provided ``logger``.
    """

    return await call_openapi_tool(
        api_server,
        tool_name,
        ctx,
        params,
        logger=logger,
    )


async def call_v2_openapi_tool(
    api_server: FastMCP,
    tool_name: str,
    ctx: Context,
    params: dict[str, Any],
    *,
    logger: BoundLogger,
) -> Any:
    """Invoke a BitSight v2 FastMCP tool and normalize the result."""

    resolved_tool_name = tool_name.strip()
    if resolved_tool_name == "createCompanyRequestBulk":
        return await _call_company_request_bulk(api_server, ctx, params, logger)

    return await call_openapi_tool(
        api_server,
        resolved_tool_name,
        ctx,
        params,
        logger=logger,
    )


async def _call_company_request_bulk(
    api_server: FastMCP,
    ctx: Context,
    params: dict[str, Any],
    logger: BoundLogger,
) -> Any:
    file_content = params.get("file")
    if not isinstance(file_content, str) or not file_content.strip():
        raise ValueError("createCompanyRequestBulk requires CSV content under 'file'")

    extra_fields = {}
    for key in ("folder_guid", "subscription_type", "tier_guid"):
        value = params.get(key)
        if value:
            extra_fields[key] = value

    client = getattr(api_server, "_client", None)
    if client is None:
        raise RuntimeError("FastMCP v2 server is missing HTTP client")

    timeout = getattr(api_server, "_timeout", None)
    debug_enabled = logging.getLogger().isEnabledFor(logging.DEBUG)
    await ctx.info("Calling FastMCP tool 'createCompanyRequestBulk'")
    files = {
        "file": (
            "company_requests.csv",
            file_content.encode("utf-8"),
            "text/csv",
        )
    }
    try:
        response = await client.post(
            "/company-requests/bulk",
            data=extra_fields or None,
            files=files,
            timeout=timeout,
        )
        response.raise_for_status()
        try:
            return response.json()
        except json.JSONDecodeError:
            return response.text
    except httpx.HTTPStatusError as exc:
        await ctx.error(
            "FastMCP tool 'createCompanyRequestBulk' returned HTTP "
            f"{exc.response.status_code}: {exc}"
        )
        logger.error(
            "FastMCP tool returned HTTP error",
            tool="createCompanyRequestBulk",
            status_code=exc.response.status_code,
            exc_info=debug_enabled,
        )
        raise
    except (httpx.RequestError, ssl.SSLError) as exc:
        mapped = classify_request_error(exc, tool_name="createCompanyRequestBulk")
        if mapped is None:
            raise

        _log_tls_error(
            mapped,
            logger=logger,
            debug_enabled=debug_enabled,
            exc=exc,
        )
        await ctx.error(mapped.user_message)
        raise mapped from exc
    except Exception as exc:  # pragma: no cover - diagnostic fallback
        await ctx.error(
            f"FastMCP tool 'createCompanyRequestBulk' execution failed: {exc}"
        )
        logger.error(
            "FastMCP tool execution failed",
            tool="createCompanyRequestBulk",
            exc_info=debug_enabled,
        )
        raise


__all__ = [
    "filter_none",
    "call_openapi_tool",
    "call_v1_openapi_tool",
    "call_v2_openapi_tool",
]
