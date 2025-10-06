from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from fastmcp import Context

CallV1Tool = Callable[[str, Context, Dict[str, Any]], Awaitable[Any]]
CallV2Tool = Callable[[str, Context, Dict[str, Any]], Awaitable[Any]]
CallOpenApiTool = Callable[[str, Context, Dict[str, Any]], Awaitable[Any]]

__all__ = [
    "CallOpenApiTool",
    "CallV1Tool",
    "CallV2Tool",
]
