"""Reusable helper utilities for the BiRRe CLI."""

from __future__ import annotations

import asyncio
import atexit
import inspect
import logging
import threading
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import replace
from pathlib import Path
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
from birre.cli import options as cli_options
from birre.cli.models import (
    AuthOverrides,
    CliInvocation,
    LoggingOverrides,
    RuntimeOverrides,
    SubscriptionOverrides,
    TlsOverrides,
)
from birre.config.settings import (
    LoggingInputs,
    RuntimeInputs,
    SubscriptionInputs,
    TlsInputs,
    apply_cli_overrides,
    is_logfile_disabled_value,
    load_settings,
    logging_from_settings,
    runtime_from_settings,
)
from birre.infrastructure.logging import configure_logging, get_logger

_SYNC_BRIDGE_LOOP: asyncio.AbstractEventLoop | None = None
_SYNC_BRIDGE_LOCK = threading.Lock()
_loop_logger = logging.getLogger("birre.loop")

CONTEXT_CHOICES: frozenset[str] = frozenset(DIAGNOSTIC_CONTEXT_CHOICES)


def close_sync_bridge_loop() -> None:
    """Dispose of the shared event loop used by :func:`await_sync`."""

    global _SYNC_BRIDGE_LOOP
    loop = _SYNC_BRIDGE_LOOP
    if loop is None:
        return
    if loop.is_closed():
        _SYNC_BRIDGE_LOOP = None
        return

    for handler in _loop_logger.handlers:
        stream = getattr(handler, "stream", None)
        if stream is not None and getattr(stream, "closed", False):
            continue
        _loop_logger.debug("sync_bridge.loop_close")
        break

    pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
    for task in pending:
        task.cancel()
    with suppress(Exception):
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    loop.close()
    _SYNC_BRIDGE_LOOP = None


atexit.register(close_sync_bridge_loop)


def await_sync(coro: Awaitable[Any]) -> Any:
    """Execute an awaitable from synchronous code on a reusable loop."""

    global _SYNC_BRIDGE_LOOP
    with _SYNC_BRIDGE_LOCK:
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop is not None:
            raise RuntimeError("await_sync cannot be used inside a running event loop")

        if _SYNC_BRIDGE_LOOP is None or _SYNC_BRIDGE_LOOP.is_closed():
            _SYNC_BRIDGE_LOOP = asyncio.new_event_loop()
            _loop_logger.debug("sync_bridge.loop_created")

        loop = _SYNC_BRIDGE_LOOP
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(coro)
        finally:
            pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
            if pending:
                for task in pending:
                    task.cancel()
                with suppress(Exception):
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            asyncio.set_event_loop(None)
        return result


def invoke_with_optional_run_sync(func: Callable[..., Any], *args, **kwargs):
    """Invoke *func*, binding :func:`await_sync` when it declares ``run_sync``."""

    kwargs = dict(kwargs)
    kwargs.pop("run_sync", None)
    try:
        params = inspect.signature(func).parameters
    except (TypeError, ValueError):
        params = {}
    if "run_sync" in params:
        return func(*args, run_sync=await_sync, **kwargs)
    return func(*args, **kwargs)


def build_invocation(
    *,
    config_path: Path | str | None,
    api_key: str | None,
    subscription_folder: str | None,
    subscription_type: str | None,
    context: str | None,
    debug: bool | None,
    risk_vector_filter: str | None,
    max_findings: int | None,
    skip_startup_checks: bool | None,
    allow_insecure_tls: bool | None,
    ca_bundle: str | None,
    log_level: str | None,
    log_format: str | None,
    log_file: str | None,
    log_max_bytes: int | None,
    log_backup_count: int | None,
    profile_path: Path | None = None,
) -> CliInvocation:
    """Construct a :class:`CliInvocation` with normalized CLI parameters."""

    normalized_context = cli_options.normalize_context(context, choices=CONTEXT_CHOICES)
    normalized_log_format = cli_options.normalize_log_format(log_format)
    normalized_log_level = cli_options.normalize_log_level(log_level)
    normalized_max_findings = cli_options.validate_positive("max_findings", max_findings)
    normalized_log_max_bytes = cli_options.validate_positive("log_max_bytes", log_max_bytes)
    normalized_log_backup_count = cli_options.validate_positive(
        "log_backup_count", log_backup_count
    )

    clean_log_file = cli_options.clean_string(log_file)

    return CliInvocation(
        config_path=str(config_path) if config_path is not None else None,
        auth=AuthOverrides(api_key=cli_options.clean_string(api_key)),
        subscription=SubscriptionOverrides(
            folder=cli_options.clean_string(subscription_folder),
            type=cli_options.clean_string(subscription_type),
        ),
        runtime=RuntimeOverrides(
            context=normalized_context,
            debug=debug,
            risk_vector_filter=cli_options.clean_string(risk_vector_filter),
            max_findings=normalized_max_findings,
            skip_startup_checks=skip_startup_checks,
        ),
        tls=TlsOverrides(
            allow_insecure=allow_insecure_tls,
            ca_bundle_path=cli_options.clean_string(ca_bundle),
        ),
        logging=LoggingOverrides(
            level=normalized_log_level,
            format=normalized_log_format,
            file_path=clean_log_file,
            max_bytes=normalized_log_max_bytes,
            backup_count=normalized_log_backup_count,
        ),
        profile_path=profile_path,
    )


def subscription_inputs(overrides: SubscriptionOverrides) -> SubscriptionInputs | None:
    """Convert CLI subscription overrides to :class:`SubscriptionInputs`."""

    if overrides.folder is None and overrides.type is None:
        return None
    return SubscriptionInputs(folder=overrides.folder, type=overrides.type)


def runtime_inputs(overrides: RuntimeOverrides) -> RuntimeInputs | None:
    """Convert CLI runtime overrides to :class:`RuntimeInputs`."""

    if (
        overrides.context is None
        and overrides.debug is None
        and overrides.risk_vector_filter is None
        and overrides.max_findings is None
        and overrides.skip_startup_checks is None
    ):
        return None
    return RuntimeInputs(
        context=overrides.context,
        debug=overrides.debug,
        risk_vector_filter=overrides.risk_vector_filter,
        max_findings=overrides.max_findings,
        skip_startup_checks=overrides.skip_startup_checks,
    )


def tls_inputs(overrides: TlsOverrides) -> TlsInputs | None:
    """Convert CLI TLS overrides to :class:`TlsInputs`."""

    if overrides.allow_insecure is None and overrides.ca_bundle_path is None:
        return None
    return TlsInputs(
        allow_insecure=overrides.allow_insecure,
        ca_bundle_path=overrides.ca_bundle_path,
    )


def logging_inputs(overrides: LoggingOverrides) -> LoggingInputs | None:
    """Convert CLI logging overrides to :class:`LoggingInputs`."""

    if (
        overrides.level is None
        and overrides.format is None
        and overrides.file_path is None
        and overrides.max_bytes is None
        and overrides.backup_count is None
    ):
        return None

    file_override: str | None
    if overrides.file_path is None:
        file_override = None
    elif is_logfile_disabled_value(overrides.file_path):
        file_override = ""
    else:
        file_override = overrides.file_path

    return LoggingInputs(
        level=overrides.level,
        format=overrides.format,
        file_path=file_override,
        max_bytes=overrides.max_bytes,
        backup_count=overrides.backup_count,
    )


def load_settings_from_invocation(invocation: CliInvocation):
    """Load settings and apply CLI overrides."""

    settings = load_settings(invocation.config_path)
    apply_cli_overrides(
        settings,
        api_key_input=invocation.auth.api_key,
        subscription_inputs=subscription_inputs(invocation.subscription),
        runtime_inputs=runtime_inputs(invocation.runtime),
        tls_inputs=tls_inputs(invocation.tls),
        logging_inputs=logging_inputs(invocation.logging),
    )
    return settings


def resolve_runtime_and_logging(invocation: CliInvocation):
    """Resolve runtime and logging settings from a CLI invocation."""

    settings = load_settings_from_invocation(invocation)
    runtime_settings = runtime_from_settings(settings)
    logging_settings = logging_from_settings(settings)
    if runtime_settings.debug and logging_settings.level > logging.DEBUG:
        logging_settings = replace(logging_settings, level=logging.DEBUG)
    return runtime_settings, logging_settings, settings


def emit_runtime_messages(runtime_settings, logger) -> None:
    """Emit runtime informational and warning messages."""

    for message in getattr(runtime_settings, "overrides", ()):  # type: ignore[attr-defined]
        logger.info(message)
    for message in getattr(runtime_settings, "warnings", ()):  # type: ignore[attr-defined]
        logger.warning(message)


def run_offline_checks(runtime_settings, logger, **kwargs) -> bool:
    """Execute offline startup checks with optional run_sync binding."""

    return invoke_with_optional_run_sync(
        diagnostics_run_offline_checks,
        runtime_settings,
        logger,
        **kwargs,
    )


def run_online_checks(
    runtime_settings,
    logger,
    *,
    v1_base_url: str | None = None,
    **kwargs,
) -> bool:
    """Execute online startup checks with optional run_sync binding."""

    return invoke_with_optional_run_sync(
        diagnostics_run_online_checks,
        runtime_settings,
        logger,
        v1_base_url=v1_base_url,
        **kwargs,
    )


def initialize_logging(
    runtime_settings,
    logging_settings,
    *,
    show_banner: bool = True,
    banner_printer: Callable[[], None] | None = None,
):
    """Configure logging and emit runtime messages."""

    if show_banner and banner_printer is not None:
        banner_printer()
    configure_logging(logging_settings)
    logger = get_logger("birre")
    emit_runtime_messages(runtime_settings, logger)
    return logger


def collect_tool_map(server_instance: Any, **kwargs) -> dict[str, Any]:
    """Collect tool map from a FastMCP server using CLI run-sync bridge."""

    return invoke_with_optional_run_sync(
        diagnostics_collect_tool_map,
        server_instance,
        **kwargs,
    )


def prepare_server(runtime_settings, logger, **create_kwargs):
    """Prepare the FastMCP server using diagnostics helpers."""

    return diagnostics_prepare_server(runtime_settings, logger, **create_kwargs)


__all__ = [
    "CONTEXT_CHOICES",
    "await_sync",
    "build_invocation",
    "close_sync_bridge_loop",
    "collect_tool_map",
    "emit_runtime_messages",
    "initialize_logging",
    "invoke_with_optional_run_sync",
    "load_settings_from_invocation",
    "logging_inputs",
    "prepare_server",
    "resolve_runtime_and_logging",
    "run_offline_checks",
    "run_online_checks",
    "runtime_inputs",
    "subscription_inputs",
    "tls_inputs",
]
