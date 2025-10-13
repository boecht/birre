"""Helpers for invoking BitSight OpenAPI endpoints via FastMCP."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any, Dict, Iterable

import httpx
from fastmcp import Context, FastMCP


def filter_none(params: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a copy of ``params`` without keys set to ``None``."""

    filtered: Dict[str, Any] = {}
    for key, value in params.items():
        if value is None:
            continue
        filtered[str(key)] = value
    return filtered


async def call_openapi_tool(
    api_server: FastMCP,
    tool_name: str,
    ctx: Context,
    params: Dict[str, Any],
    *,
    logger: logging.Logger,
) -> Any:
    """Invoke a FastMCP OpenAPI tool and normalize the result."""

    if not isinstance(tool_name, str) or not tool_name.strip():
        raise ValueError("tool_name must be a non-empty string")

    if not isinstance(params, Mapping):
        raise TypeError("params must be a mapping of argument names to values")

    resolved_tool_name = tool_name.strip()
    filtered_params = filter_none(params)

    try:
        await ctx.info(f"Calling FastMCP tool '{resolved_tool_name}'")
        async with Context(api_server):
            tool_result = await api_server._call_tool(
                resolved_tool_name, filtered_params
            )

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
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    await ctx.warning(
                        f"Failed to parse text content for '{resolved_tool_name}' as JSON"
                    )
                    logger.debug(
                        "Unable to deserialize JSON payload from FastMCP tool response",
                        extra={"tool": resolved_tool_name},
                        exc_info=True,
                    )
                    return text

        await ctx.warning(
            f"FastMCP tool '{resolved_tool_name}' returned no structured data; passing raw result"
        )
        logger.warning(
            "FastMCP tool returned unstructured payload; returning raw result",
            extra={"tool": resolved_tool_name},
        )
        return tool_result
    except httpx.HTTPStatusError as exc:
        await ctx.error(
            f"FastMCP tool '{resolved_tool_name}' returned HTTP {exc.response.status_code}: {exc}"
        )
        logger.error(
            "FastMCP tool returned HTTP error",
            extra={
                "tool": resolved_tool_name,
                "status_code": exc.response.status_code,
            },
            exc_info=True,
        )
        raise
    except Exception as exc:  # pragma: no cover - diagnostic fallback
        await ctx.error(
            f"FastMCP tool '{resolved_tool_name}' execution failed: {exc}"
        )
        logger.error(
            "FastMCP tool execution failed",
            extra={"tool": resolved_tool_name},
            exc_info=True,
        )
        raise


async def call_v1_openapi_tool(
    api_server: FastMCP,
    tool_name: str,
    ctx: Context,
    params: Dict[str, Any],
    *,
    logger: logging.Logger,
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
    params: Dict[str, Any],
    *,
    logger: logging.Logger,
) -> Any:
    """Invoke a BitSight v2 FastMCP tool and normalize the result."""

    return await call_openapi_tool(
        api_server,
        tool_name,
        ctx,
        params,
        logger=logger,
    )


__all__ = [
    "filter_none",
    "call_openapi_tool",
    "call_v1_openapi_tool",
    "call_v2_openapi_tool",
]
