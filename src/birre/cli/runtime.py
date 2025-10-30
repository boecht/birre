"""CLI runtime operations and diagnostics integration.

Provides runtime utilities for executing startup checks, initializing logging,
and preparing the FastMCP server with diagnostics integration.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from birre.application.diagnostics import (
    CONTEXT_CHOICES as DIAGNOSTIC_CONTEXT_CHOICES,
)
from birre.application.diagnostics import (
    collect_tool_map as diagnostics_collect_tool_map,
)
from birre.application.diagnostics import (
    prepare_server as diagnostics_prepare_server,
)
from birre.application.diagnostics import (
    run_offline_checks as diagnostics_run_offline_checks,
)
from birre.application.diagnostics import (
    run_online_checks as diagnostics_run_online_checks,
)
from birre.cli.sync_bridge import invoke_with_optional_run_sync
from birre.infrastructure.logging import configure_logging, get_logger

CONTEXT_CHOICES: frozenset[str] = frozenset(DIAGNOSTIC_CONTEXT_CHOICES)


def emit_runtime_messages(runtime_settings: Any, logger: Any) -> None:
    """Emit runtime informational and warning messages."""

    for message in getattr(runtime_settings, "overrides", ()):
        logger.info(message)
    for message in getattr(runtime_settings, "warnings", ()):
        logger.warning(message)


def run_offline_checks(runtime_settings: Any, logger: Any, **kwargs: Any) -> bool:
    """Execute offline startup checks with optional run_sync binding."""

    result: bool = invoke_with_optional_run_sync(
        diagnostics_run_offline_checks,
        runtime_settings,
        logger,
        **kwargs,
    )
    return result


def run_online_checks(
    runtime_settings: Any,
    logger: Any,
    *,
    v1_base_url: str | None = None,
    **kwargs: Any,
) -> bool:
    """Execute online startup checks with optional run_sync binding."""

    result: bool = invoke_with_optional_run_sync(
        diagnostics_run_online_checks,
        runtime_settings,
        logger,
        v1_base_url=v1_base_url,
        **kwargs,
    )
    return result


def initialize_logging(
    runtime_settings: Any,
    logging_settings: Any,
    *,
    show_banner: bool = True,
    banner_printer: Callable[[], None] | None = None,
) -> Any:  # Returns BoundLogger
    """Configure logging and emit runtime messages."""

    if show_banner and banner_printer is not None:
        banner_printer()
    configure_logging(logging_settings)
    logger = get_logger("birre")
    emit_runtime_messages(runtime_settings, logger)
    return logger


def collect_tool_map(server_instance: Any, **kwargs: Any) -> dict[str, Any]:
    """Collect tool map from a FastMCP server using CLI run-sync bridge."""

    result: dict[str, Any] = invoke_with_optional_run_sync(
        diagnostics_collect_tool_map,
        server_instance,
        **kwargs,
    )
    return result


def prepare_server(runtime_settings: Any, logger: Any, **create_kwargs: Any) -> Any:
    """Prepare the FastMCP server using diagnostics helpers."""

    return diagnostics_prepare_server(runtime_settings, logger, **create_kwargs)


__all__ = [
    "CONTEXT_CHOICES",
    "collect_tool_map",
    "emit_runtime_messages",
    "initialize_logging",
    "prepare_server",
    "run_offline_checks",
    "run_online_checks",
]
