"""FastMCP environment helpers."""

from __future__ import annotations

import os

_OPENAPI_ENV_VAR = "FASTMCP_EXPERIMENTAL_ENABLE_NEW_OPENAPI_PARSER"


def enable_new_openapi_parser() -> None:
    """Force FastMCP to load the modern OpenAPI parser on import."""
    os.environ.setdefault(_OPENAPI_ENV_VAR, "true")


# Ensure the flag is enabled immediately when the helper is imported.
enable_new_openapi_parser()


__all__ = ["enable_new_openapi_parser"]
