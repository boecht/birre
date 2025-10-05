from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from fastmcp import Context

CallV1Tool = Callable[[str, Context, Dict[str, Any]], Awaitable[Any]]

__all__ = [
    "CallV1Tool",
]
