from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastmcp import Context

CallV1Tool = Callable[[str, Context, dict[str, Any]], Awaitable[Any]]
CallV2Tool = Callable[[str, Context, dict[str, Any]], Awaitable[Any]]
CallOpenApiTool = Callable[[str, Context, dict[str, Any]], Awaitable[Any]]

__all__ = [
    "CallOpenApiTool",
    "CallV1Tool",
    "CallV2Tool",
]
