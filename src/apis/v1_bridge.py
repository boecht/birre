"""Helpers for invoking BitSight v1 endpoints via FastMCP."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

import httpx
from fastmcp import Context, FastMCP


def filter_none(params: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of ``params`` without keys set to ``None``."""

    return {key: value for key, value in params.items() if value is not None}


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

    filtered_params = filter_none(params)

    try:
        await ctx.info(f"Calling FastMCP tool '{tool_name}'")
        async with Context(api_server):
            tool_result = await api_server._call_tool(tool_name, filtered_params)

        structured = getattr(tool_result, "structured_content", None)
        if structured:
            if isinstance(structured, dict) and "result" in structured:
                return structured["result"]
            return structured

        content_blocks = getattr(tool_result, "content", None) or []
        if content_blocks:
            first_block = content_blocks[0]
            text = getattr(first_block, "text", None)
            if text:
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    await ctx.warning(
                        f"Failed to parse text content for '{tool_name}' as JSON"
                    )

        await ctx.warning(
            f"FastMCP tool '{tool_name}' returned no structured data; passing raw result"
        )
        return tool_result
    except httpx.HTTPStatusError as exc:
        await ctx.error(
            f"FastMCP tool '{tool_name}' returned HTTP {exc.response.status_code}: {exc}"
        )
        raise
    except Exception as exc:  # pragma: no cover - diagnostic fallback
        await ctx.error(f"FastMCP tool '{tool_name}' execution failed: {exc}")
        logger.error(
            "FastMCP tool execution failed",
            extra={"tool_name": tool_name},
            exc_info=True,
        )
        raise


__all__ = ["filter_none", "call_v1_openapi_tool"]
