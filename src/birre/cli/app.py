"""BiRRe FastMCP server Typer CLI entrypoint."""

from __future__ import annotations

import cProfile
import errno
import inspect
import json
import logging
import os
import re
import shutil
import ssl
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Final

import click
import httpx
import typer
from click.core import ParameterSource
from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text
from typer.main import get_command

import birre.application.diagnostics as diagnostics_module

# FastMCP checks this flag during import time, so ensure it is enabled before
# importing any modules that depend on FastMCP.
os.environ["FASTMCP_EXPERIMENTAL_ENABLE_NEW_OPENAPI_PARSER"] = "true"

from birre.application.diagnostics import (
    EXPECTED_TOOLS_BY_CONTEXT as _DIAGNOSTIC_EXPECTED_TOOLS,
)
from birre.application.diagnostics import (
    DiagnosticFailure,
    HealthcheckRunner,
    aggregate_tool_outcomes,
    classify_failure,
    discover_context_tools,
    record_failure,
    run_company_search_diagnostics,
    run_company_search_interactive_diagnostics,
    run_context_tool_diagnostics,
    run_manage_subscriptions_diagnostics,
    run_rating_diagnostics,
    run_request_company_diagnostics,
    summarize_failure,
)

from birre.cli.helpers import (
    CONTEXT_CHOICES,
    await_sync,
    build_invocation,
    collect_tool_map,
    initialize_logging,
    invoke_with_optional_run_sync,
    prepare_server,
    resolve_runtime_and_logging,
    run_offline_checks,
    run_online_checks,
)
run_offline_startup_checks = run_offline_checks
run_online_startup_checks = run_online_checks

from birre.cli import options as cli_options
from birre.cli.commands import run as run_command
from birre.cli.models import (
    AuthOverrides,
    CliInvocation,
    LogViewLine,
    LoggingOverrides,
    RuntimeOverrides,
    SubscriptionOverrides,
    TlsOverrides,
)
from birre.config.constants import DEFAULT_CONFIG_FILENAME, LOCAL_CONFIG_FILENAME
from birre.config.settings import (
    BITSIGHT_API_KEY_KEY,
    BITSIGHT_SUBSCRIPTION_FOLDER_KEY,
    BITSIGHT_SUBSCRIPTION_TYPE_KEY,
    LOGGING_BACKUP_COUNT_KEY,
    LOGGING_FILE_KEY,
    LOGGING_FORMAT_KEY,
    LOGGING_LEVEL_KEY,
    LOGGING_MAX_BYTES_KEY,
    ROLE_CONTEXT_KEY,
    ROLE_MAX_FINDINGS_KEY,
    ROLE_RISK_VECTOR_FILTER_KEY,
    RUNTIME_ALLOW_INSECURE_TLS_KEY,
    RUNTIME_CA_BUNDLE_PATH_KEY,
    RUNTIME_DEBUG_KEY,
    RUNTIME_SKIP_STARTUP_CHECKS_KEY,
    LoggingInputs,
    RuntimeInputs,
    SubscriptionInputs,
    TlsInputs,
    apply_cli_overrides,
    is_logfile_disabled_value,
    load_settings,
    logging_from_settings,
    resolve_config_file_candidates,
    runtime_from_settings,
)
from birre.infrastructure.errors import (
    BirreError,
    ErrorCode,
)
from birre.infrastructure.logging import BoundLogger, configure_logging, get_logger
from birre.integrations.bitsight import DEFAULT_V1_API_BASE_URL

PROJECT_ROOT = Path(__file__).resolve().parents[3]

stderr_console = Console(stderr=True)
stdout_console = Console(stderr=False)

app = typer.Typer(
    help="Model Context Protocol server for BitSight rating retrieval",
    rich_markup_mode="rich",
)
config_app = typer.Typer(
    help="Manage BiRRe configuration files and settings.",
    invoke_without_command=True,
    no_args_is_help=True,
)
app.add_typer(config_app, name="config")
logs_app = typer.Typer(
    help="Inspect and maintain BiRRe log files.",
    invoke_without_command=True,
    no_args_is_help=True,
)
app.add_typer(logs_app, name="logs")


@config_app.callback(invoke_without_command=True)
def config_group_callback(ctx: typer.Context) -> None:
    """Display help when config group is invoked without a subcommand."""
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


@logs_app.callback(invoke_without_command=True)
def logs_group_callback(ctx: typer.Context) -> None:
    """Display help when logs group is invoked without a subcommand."""
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()

class _RichStyles:
    ACCENT = "bold cyan"
    SECONDARY = "magenta"
    SUCCESS = "green"
    EMPHASIS = "bold"
    DETAIL = "white"


_CLI_PROG_NAME = Path(__file__).name
_SENSITIVE_KEY_PATTERNS = ("api_key", "secret", "token", "password")

SOURCE_USER_INPUT: Final = "User Input"

HEALTHCHECK_TESTING_V1_BASE_URL = "https://service.bitsighttech.com/customer-api/v1/"
HEALTHCHECK_PRODUCTION_V1_BASE_URL = DEFAULT_V1_API_BASE_URL

_HEALTHCHECK_COMPANY_NAME: Final = "GitHub"
_HEALTHCHECK_COMPANY_DOMAIN: Final = "github.com"
_HEALTHCHECK_COMPANY_GUID: Final = "6ca077e2-b5a7-42c2-ae1e-a974c3a91dc1"
_HEALTHCHECK_REQUEST_DOMAIN: Final = "healthcheck-birre-example.com"

# Error/status message constants
MSG_NOT_A_DICT: Final = "not a dict"
MSG_TOOL_INVOCATION_FAILED: Final = "tool invocation failed"
MSG_UNEXPECTED_PAYLOAD_STRUCTURE: Final = "unexpected payload structure"
MSG_EXPECTED_TOOL_NOT_REGISTERED: Final = "expected tool not registered"
MSG_TOOL_NOT_REGISTERED: Final = "tool not registered"
MSG_CONFIG_CA_BUNDLE: Final = "config.ca_bundle"

_EXPECTED_TOOLS_BY_CONTEXT: dict[str, frozenset[str]] = {
    context: frozenset(tools)
    for context, tools in _DIAGNOSTIC_EXPECTED_TOOLS.items()
}


# Reusable option annotations -------------------------------------------------

def _mask_sensitive_string(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"


def _format_display_value(key: str, value: Any) -> str:
    lowered_key = key.lower()
    if key == LOGGING_FILE_KEY:
        if value is None:
            return "<stderr>"
        if isinstance(value, str) and not value.strip():
            return "<stderr>"

    if value is None:
        text = "<unset>"
    elif isinstance(value, bool):
        text = "true" if value else "false"
    else:
        text = str(value)

    if any(pattern in lowered_key for pattern in _SENSITIVE_KEY_PATTERNS):
        original = value if isinstance(value, str) else text
        return _mask_sensitive_string(original)
    return text


def _flatten_to_dotted(mapping: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in mapping.items():
        dotted = f"{prefix}.{key}" if prefix else key
        if isinstance(value, Mapping):
            flattened.update(_flatten_to_dotted(value, dotted))
        else:
            flattened[dotted] = value
    return flattened


def _collect_config_file_entries(files: Sequence[Path]) -> dict[str, tuple[Any, str]]:
    import tomllib

    entries: dict[str, tuple[Any, str]] = {}
    for file in files:
        if not file.exists():
            continue
        with file.open("rb") as handle:
            parsed = tomllib.load(handle)
        flattened = _flatten_to_dotted(parsed)
        for key, value in flattened.items():
            entries[key] = (value, file.name)
    return entries


def _collect_cli_override_values(invocation: CliInvocation) -> dict[str, Any]:
    details: dict[str, Any] = {}
    if invocation.auth.api_key:
        details[BITSIGHT_API_KEY_KEY] = invocation.auth.api_key
    if invocation.subscription.folder:
        details[BITSIGHT_SUBSCRIPTION_FOLDER_KEY] = invocation.subscription.folder
    if invocation.subscription.type:
        details[BITSIGHT_SUBSCRIPTION_TYPE_KEY] = invocation.subscription.type
    if invocation.runtime.context:
        details[ROLE_CONTEXT_KEY] = invocation.runtime.context
    if invocation.runtime.risk_vector_filter:
        details[ROLE_RISK_VECTOR_FILTER_KEY] = invocation.runtime.risk_vector_filter
    if invocation.runtime.max_findings is not None:
        details[ROLE_MAX_FINDINGS_KEY] = invocation.runtime.max_findings
    if invocation.runtime.debug is not None:
        details[RUNTIME_DEBUG_KEY] = invocation.runtime.debug
    if invocation.runtime.skip_startup_checks is not None:
        details[RUNTIME_SKIP_STARTUP_CHECKS_KEY] = invocation.runtime.skip_startup_checks
    if invocation.tls.allow_insecure is not None:
        details[RUNTIME_ALLOW_INSECURE_TLS_KEY] = invocation.tls.allow_insecure
    if invocation.tls.ca_bundle_path:
        details[RUNTIME_CA_BUNDLE_PATH_KEY] = invocation.tls.ca_bundle_path
    if invocation.logging.level:
        details[LOGGING_LEVEL_KEY] = invocation.logging.level
    if invocation.logging.format:
        details[LOGGING_FORMAT_KEY] = invocation.logging.format
    if invocation.logging.file_path is not None:
        details[LOGGING_FILE_KEY] = invocation.logging.file_path
    if invocation.logging.max_bytes is not None:
        details[LOGGING_MAX_BYTES_KEY] = invocation.logging.max_bytes
    if invocation.logging.backup_count is not None:
        details[LOGGING_BACKUP_COUNT_KEY] = invocation.logging.backup_count
    return details


def _build_cli_source_labels(invocation: CliInvocation) -> dict[str, str]:
    labels: dict[str, str] = {}
    if invocation.auth.api_key:
        labels[BITSIGHT_API_KEY_KEY] = "CLI"
    if invocation.subscription.folder:
        labels[BITSIGHT_SUBSCRIPTION_FOLDER_KEY] = "CLI"
    if invocation.subscription.type:
        labels[BITSIGHT_SUBSCRIPTION_TYPE_KEY] = "CLI"
    if invocation.runtime.context:
        labels[ROLE_CONTEXT_KEY] = "CLI"
    if invocation.runtime.risk_vector_filter:
        labels[ROLE_RISK_VECTOR_FILTER_KEY] = "CLI"
    if invocation.runtime.max_findings is not None:
        labels[ROLE_MAX_FINDINGS_KEY] = "CLI"
    if invocation.runtime.debug is not None:
        labels[RUNTIME_DEBUG_KEY] = "CLI"
    if invocation.runtime.skip_startup_checks is not None:
        labels[RUNTIME_SKIP_STARTUP_CHECKS_KEY] = "CLI"
    if invocation.tls.allow_insecure is not None:
        labels[RUNTIME_ALLOW_INSECURE_TLS_KEY] = "CLI"
    if invocation.tls.ca_bundle_path:
        labels[RUNTIME_CA_BUNDLE_PATH_KEY] = "CLI"
    if invocation.logging.level:
        labels[LOGGING_LEVEL_KEY] = "CLI"
    if invocation.logging.format:
        labels[LOGGING_FORMAT_KEY] = "CLI"
    if invocation.logging.file_path is not None:
        labels[LOGGING_FILE_KEY] = "CLI"
    if invocation.logging.max_bytes is not None:
        labels[LOGGING_MAX_BYTES_KEY] = "CLI"
    if invocation.logging.backup_count is not None:
        labels[LOGGING_BACKUP_COUNT_KEY] = "CLI"
    return labels


def _build_env_source_labels(env_overrides: Mapping[str, str]) -> dict[str, str]:
    from birre.config.settings import ENVVAR_TO_SETTINGS_KEY

    labels: dict[str, str] = {}
    for env_var in env_overrides:
        config_key = ENVVAR_TO_SETTINGS_KEY.get(env_var)
        if config_key:
            labels[config_key] = f"ENV ({env_var})"
    return labels


def _build_cli_override_rows(invocation: CliInvocation) -> Sequence[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for key, value in _collect_cli_override_values(invocation).items():
        rows.append((key, _format_display_value(key, value), "CLI"))
    return rows


def _build_env_override_rows(env_overrides: Mapping[str, str]) -> Sequence[tuple[str, str, str]]:
    from birre.config.settings import ENVVAR_TO_SETTINGS_KEY

    rows: list[tuple[str, str, str]] = []
    for env_var, value in env_overrides.items():
        config_key = ENVVAR_TO_SETTINGS_KEY.get(env_var)
        if not config_key:
            continue
        rows.append((config_key, _format_display_value(config_key, value), f"ENV ({env_var})"))
    return rows


_EFFECTIVE_CONFIG_KEY_ORDER: tuple[str, ...] = (
    BITSIGHT_API_KEY_KEY,
    BITSIGHT_SUBSCRIPTION_FOLDER_KEY,
    BITSIGHT_SUBSCRIPTION_TYPE_KEY,
    ROLE_CONTEXT_KEY,
    ROLE_RISK_VECTOR_FILTER_KEY,
    ROLE_MAX_FINDINGS_KEY,
    RUNTIME_DEBUG_KEY,
    RUNTIME_SKIP_STARTUP_CHECKS_KEY,
    RUNTIME_ALLOW_INSECURE_TLS_KEY,
    RUNTIME_CA_BUNDLE_PATH_KEY,
    LOGGING_LEVEL_KEY,
    LOGGING_FORMAT_KEY,
    LOGGING_FILE_KEY,
    LOGGING_MAX_BYTES_KEY,
    LOGGING_BACKUP_COUNT_KEY,
)


def _effective_configuration_values(runtime_settings, logging_settings) -> dict[str, Any]:
    values: dict[str, Any] = {
        BITSIGHT_API_KEY_KEY: getattr(runtime_settings, "api_key", None),
        BITSIGHT_SUBSCRIPTION_FOLDER_KEY: getattr(runtime_settings, "subscription_folder", None),
        BITSIGHT_SUBSCRIPTION_TYPE_KEY: getattr(runtime_settings, "subscription_type", None),
        ROLE_CONTEXT_KEY: getattr(runtime_settings, "context", None),
        ROLE_RISK_VECTOR_FILTER_KEY: getattr(runtime_settings, "risk_vector_filter", None),
        ROLE_MAX_FINDINGS_KEY: getattr(runtime_settings, "max_findings", None),
        RUNTIME_DEBUG_KEY: getattr(runtime_settings, "debug", None),
        RUNTIME_SKIP_STARTUP_CHECKS_KEY: getattr(runtime_settings, "skip_startup_checks", None),
        RUNTIME_ALLOW_INSECURE_TLS_KEY: getattr(runtime_settings, "allow_insecure_tls", None),
        RUNTIME_CA_BUNDLE_PATH_KEY: getattr(runtime_settings, "ca_bundle_path", None),
        LOGGING_LEVEL_KEY: logging.getLevelName(getattr(logging_settings, "level", logging.INFO)),
        LOGGING_FORMAT_KEY: getattr(logging_settings, "format", None),
        LOGGING_FILE_KEY: getattr(logging_settings, "file_path", None),
        LOGGING_MAX_BYTES_KEY: getattr(logging_settings, "max_bytes", None),
        LOGGING_BACKUP_COUNT_KEY: getattr(logging_settings, "backup_count", None),
    }
    return values


def _determine_source_label(
    key: str,
    cli_labels: Mapping[str, str],
    env_labels: Mapping[str, str],
    config_entries: Mapping[str, tuple[Any, str]],
) -> str:
    if key in cli_labels:
        return cli_labels[key]
    if key in env_labels:
        return env_labels[key]
    if key in config_entries:
        return f"Config File ({config_entries[key][1]})"
    return "Default"


def _print_config_table(title: str, rows: Sequence[tuple[str, str, str]]) -> None:
    table = Table(title=title, box=box.SIMPLE_HEAVY)
    table.add_column("Config Key", style=_RichStyles.ACCENT, no_wrap=True)
    table.add_column("Resolved Value", overflow="fold")
    table.add_column("Source", style=_RichStyles.SECONDARY)
    for key, value, source in rows:
        table.add_row(key, value, source)
    stdout_console.print(table)


def _banner() -> Text:
    return Text.from_markup(
        "\n"
        "╭────────────────────────────────────────────────────────────────╮\n"
        "│[yellow]                                                                [/yellow]│\n"
        "│[yellow]     ███████████   ███  ███████████   ███████████               [/yellow]│\n"
        "│[yellow]    ░░███░░░░░███ ░░░  ░░███░░░░░███ ░░███░░░░░███              [/yellow]│\n"
        "│[yellow]     ░███    ░███ ████  ░███    ░███  ░███    ░███   ██████     [/yellow]│\n"
        "│[yellow]     ░██████████ ░░███  ░██████████   ░██████████   ███░░███    [/yellow]│\n"
        "│[yellow]     ░███░░░░░███ ░███  ░███░░░░░███  ░███░░░░░███ ░███████     [/yellow]│\n"
        "│[yellow]     ░███    ░███ ░███  ░███    ░███  ░███    ░███ ░███░░░      [/yellow]│\n"
        "│[yellow]     ███████████  █████ █████   █████ █████   █████░░██████     [/yellow]│\n"
        "│[yellow]    ░░░░░░░░░░░  ░░░░░ ░░░░░   ░░░░░ ░░░░░   ░░░░░  ░░░░░░      [/yellow]│\n"
        "│[yellow]                                                                [/yellow]│\n"
        "│[dim]                   "
        "[bold]Bi[/bold]tsight [bold]R[/bold]ating [bold]Re[/bold]triever"
        "                    [/dim]│\n"
        "│[yellow]                 Model Context Protocol Server                  [/yellow]│\n"
        "│[yellow]                https://github.com/boecht/birre                 [/yellow]│\n"
        "╰────────────────────────────────────────────────────────────────╯\n"
    )


def _keyboard_interrupt_banner() -> Text:
    return Text.from_markup(
        "\n"
        "╭───────────────────────────────╮\n"
        "│[red]  Keyboard interrupt received  [/red]│\n"
        "│[red]         BiRRe stopping        [/red]│\n"
        "╰───────────────────────────────╯\n"

    )


run_command.register(
    app,
    stderr_console=stderr_console,
    banner_factory=_banner,
    keyboard_interrupt_banner=_keyboard_interrupt_banner,
)


def _run_company_search_diagnostics(
    *,
    context: str,
    logger: BoundLogger,
    tool: Any,
    failures: list[DiagnosticFailure | None] | None = None,
    summary: dict[str, Any | None] | None = None,
    **kwargs,
) -> bool:
    return invoke_with_optional_run_sync(
        run_company_search_diagnostics,
        context=context,
        logger=logger,
        tool=tool,
        failures=failures,
        summary=summary,
        **kwargs,
    )


def _run_company_search_interactive_diagnostics(
    *,
    context: str,
    logger: BoundLogger,
    tool: Any,
    failures: list[DiagnosticFailure | None] | None = None,
    summary: dict[str, Any | None] | None = None,
    **kwargs,
) -> bool:
    return invoke_with_optional_run_sync(
        run_company_search_interactive_diagnostics,
        context=context,
        logger=logger,
        tool=tool,
        failures=failures,
        summary=summary,
        **kwargs,
    )


def _run_manage_subscriptions_diagnostics(
    *,
    context: str,
    logger: BoundLogger,
    tool: Any,
    failures: list[DiagnosticFailure | None] | None = None,
    summary: dict[str, Any | None] | None = None,
    **kwargs,
) -> bool:
    return invoke_with_optional_run_sync(
        run_manage_subscriptions_diagnostics,
        context=context,
        logger=logger,
        tool=tool,
        failures=failures,
        summary=summary,
        **kwargs,
    )


def _run_request_company_diagnostics(
    *,
    context: str,
    logger: BoundLogger,
    tool: Any,
    failures: list[DiagnosticFailure | None] | None = None,
    summary: dict[str, Any | None] | None = None,
    **kwargs,
) -> bool:
    return invoke_with_optional_run_sync(
        run_request_company_diagnostics,
        context=context,
        logger=logger,
        tool=tool,
        failures=failures,
        summary=summary,
        **kwargs,
    )


def _run_rating_diagnostics(
    *,
    context: str,
    logger: BoundLogger,
    tool: Any,
    failures: list[DiagnosticFailure | None] | None = None,
    summary: dict[str, Any | None] | None = None,
    **kwargs,
) -> bool:
    return invoke_with_optional_run_sync(
        run_rating_diagnostics,
        context=context,
        logger=logger,
        tool=tool,
        failures=failures,
        summary=summary,
        **kwargs,
    )


def _run_context_tool_diagnostics(
    *,
    context: str,
    logger: BoundLogger,
    server_instance: Any,
    expected_tools: frozenset[str],
    summary: dict[str, dict[str, Any | None]] | None = None,
    failures: list[DiagnosticFailure | None] | None = None,
    **kwargs,
) -> bool:
    return invoke_with_optional_run_sync(
        run_context_tool_diagnostics,
        context=context,
        logger=logger,
        server_instance=server_instance,
        expected_tools=expected_tools,
        summary=summary,
        failures=failures,
        **kwargs,
    )


_aggregate_tool_outcomes = aggregate_tool_outcomes
_record_failure = record_failure
_summarize_failure = summarize_failure
_classify_failure = classify_failure


def _discover_context_tools(server_instance: Any, **kwargs) -> set[str]:
    return invoke_with_optional_run_sync(
        discover_context_tools,
        server_instance,
        **kwargs,
    )




# Ensure the diagnostics module uses the CLI-specific wrappers so that
# monkeypatching the CLI names also affects HealthcheckRunner execution.

def _delegate_collect_tool_map(server_instance: Any, **kwargs) -> dict[str, Any]:
    kwargs.pop("run_sync", None)
    return collect_tool_map(server_instance, **kwargs)


def _delegate_prepare_server(runtime_settings, logger, **create_kwargs):
    return prepare_server(runtime_settings, logger, **create_kwargs)


def _delegate_run_company_search_diagnostics(**kwargs) -> bool:
    kwargs.pop("run_sync", None)
    return _run_company_search_diagnostics(**kwargs)


def _delegate_run_company_search_interactive_diagnostics(**kwargs) -> bool:
    kwargs.pop("run_sync", None)
    return _run_company_search_interactive_diagnostics(**kwargs)


def _delegate_run_manage_subscriptions_diagnostics(**kwargs) -> bool:
    kwargs.pop("run_sync", None)
    return _run_manage_subscriptions_diagnostics(**kwargs)


def _delegate_run_request_company_diagnostics(**kwargs) -> bool:
    kwargs.pop("run_sync", None)
    return _run_request_company_diagnostics(**kwargs)


def _delegate_run_rating_diagnostics(**kwargs) -> bool:
    kwargs.pop("run_sync", None)
    return _run_rating_diagnostics(**kwargs)


def _delegate_run_context_tool_diagnostics(**kwargs) -> bool:
    kwargs.pop("run_sync", None)
    return _run_context_tool_diagnostics(**kwargs)


def _delegate_run_offline_checks(*args, **kwargs) -> bool:
    kwargs.pop("run_sync", None)
    return run_offline_checks(*args, **kwargs)


def _delegate_run_online_checks(*args, **kwargs) -> bool:
    kwargs.pop("run_sync", None)
    return run_online_checks(*args, **kwargs)


diagnostics_module.collect_tool_map = _delegate_collect_tool_map
diagnostics_module.prepare_server = _delegate_prepare_server
diagnostics_module.discover_context_tools = (
    lambda server_instance, **kwargs: (
        kwargs.pop("run_sync", None),
        _discover_context_tools(server_instance, **kwargs)
    )[1]
)
diagnostics_module.run_offline_checks = _delegate_run_offline_checks
diagnostics_module.run_online_checks = _delegate_run_online_checks
diagnostics_module.run_company_search_diagnostics = (
    _delegate_run_company_search_diagnostics
)
diagnostics_module.run_company_search_interactive_diagnostics = (
    _delegate_run_company_search_interactive_diagnostics
)
diagnostics_module.run_manage_subscriptions_diagnostics = (
    _delegate_run_manage_subscriptions_diagnostics
)
diagnostics_module.run_request_company_diagnostics = (
    _delegate_run_request_company_diagnostics
)
diagnostics_module.run_rating_diagnostics = _delegate_run_rating_diagnostics
diagnostics_module.run_context_tool_diagnostics = (
    _delegate_run_context_tool_diagnostics
)


def _create_offline_tool_status(tool_name: str, missing_set: set[str | None]) -> dict[str, Any]:
    """Create tool status entry for offline mode."""
    if tool_name in missing_set:
        return {
            "status": "fail",
            "details": {"reason": MSG_TOOL_NOT_REGISTERED},
        }
    return {
        "status": "warning",
        "details": {"reason": "offline mode"},
    }


def _collect_tool_attempts(
    tool_name: str, attempts: Sequence[dict[str, Any]]
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Collect all attempt details and statuses for a specific tool."""
    attempt_details: dict[str, dict[str, Any]] = {}
    statuses: list[str] = []
    for attempt in attempts:
        tool_entry = attempt.get("tools", {}).get(tool_name)
        if tool_entry is None:
            continue
        attempt_details[attempt["label"]] = tool_entry
        status = tool_entry.get("status")
        if isinstance(status, str):
            statuses.append(status)
    return attempt_details, statuses


def _determine_final_status(statuses: list[str]) -> str:
    """Determine final tool status from multiple attempt statuses."""
    if any(status == "pass" for status in statuses):
        return "pass"
    if any(status == "fail" for status in statuses):
        return "fail"
    return statuses[0]


def _aggregate_tool_outcomes(
    expected_tools: frozenset[str],
    attempts: Sequence[dict[str, Any]],
    *,
    offline_mode: bool = False,
    offline_missing: Sequence[str | None] = None,
) -> dict[str, dict[str, Any]]:
    aggregated: dict[str, dict[str, Any]] = {}
    if offline_mode:
        missing_set = set(offline_missing or ())
        for tool_name in sorted(expected_tools):
            aggregated[tool_name] = _create_offline_tool_status(tool_name, missing_set)
        return aggregated

    for tool_name in sorted(expected_tools):
        attempt_details, statuses = _collect_tool_attempts(tool_name, attempts)
        
        if not statuses:
            aggregated[tool_name] = {
                "status": "warning",
                "attempts": attempt_details or None,
            }
            continue
        
        final_status = _determine_final_status(statuses)
        entry: dict[str, Any] = {"status": final_status}
        if attempt_details:
            entry["attempts"] = attempt_details
        aggregated[tool_name] = entry
    return aggregated


def _healthcheck_status_label(value: str | None) -> str:
    """Convert status value to uppercase label."""
    mapping = {"pass": "PASS", "fail": "FAIL", "warning": "WARNING"}
    if not value:
        return "WARNING"
    return mapping.get(value.lower(), value.upper())


def _stringify_healthcheck_detail(value: Any) -> str:
    """Convert any value to a string representation for healthcheck display."""
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        items = [f"{key}={value[key]}" for key in sorted(value)]
        return ", ".join(items) if items else "-"
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        items = [_stringify_healthcheck_detail(item) for item in value]
        return ", ".join(item for item in items if item and item != "-") or "-"
    return str(value)


def _format_healthcheck_context_detail(context_data: Mapping[str, Any]) -> str:
    """Format context diagnostic details into a summary string."""
    parts: list[str] = []
    if context_data.get("fallback_attempted"):
        resolved = context_data.get("fallback_success")
        parts.append("fallback=" + ("resolved" if resolved else "failed"))
    recoverable = context_data.get("recoverable_categories") or []
    if recoverable:
        parts.append("recoverable=" + ",".join(sorted(recoverable)))
    unrecoverable = context_data.get("unrecoverable_categories") or []
    if unrecoverable:
        parts.append("unrecoverable=" + ",".join(sorted(unrecoverable)))
    notes = context_data.get("notes") or []
    if notes:
        parts.append("notes=" + ",".join(notes))
    return "; ".join(parts) if parts else "-"


def _format_healthcheck_online_detail(online_data: Mapping[str, Any]) -> str:
    """Format online diagnostic details into a summary string."""
    attempts = online_data.get("attempts") if isinstance(online_data, Mapping) else None
    if isinstance(attempts, Mapping) and attempts:
        attempt_parts = [
            f"{label}:{_healthcheck_status_label(status)}"
            for label, status in sorted(attempts.items())
        ]
        return ", ".join(attempt_parts)
    details = online_data.get("details") if isinstance(online_data, Mapping) else None
    return _stringify_healthcheck_detail(details)


def _process_tool_attempt_entry(
    label: str,
    entry: Mapping[str, Any],
    parts: list[str],
) -> str:
    """Process a single tool attempt entry and return its status label."""
    attempt_status = _healthcheck_status_label(entry.get("status"))
    
    modes = entry.get("modes")
    if isinstance(modes, Mapping) and modes:
        mode_parts = [
            f"{mode}:{_healthcheck_status_label(mode_entry.get('status'))}"
            for mode, mode_entry in sorted(modes.items())
        ]
        if mode_parts:
            parts.append(f"{label} modes=" + ", ".join(mode_parts))
    
    detail = entry.get("details")
    if detail:
        parts.append(f"{label} detail=" + _stringify_healthcheck_detail(detail))
    
    return f"{label}:{attempt_status}"


def _format_healthcheck_tool_detail(tool_summary: Mapping[str, Any]) -> str:
    """Format tool diagnostic details into a summary string."""
    parts: list[str] = []
    attempts = tool_summary.get("attempts")
    if isinstance(attempts, Mapping) and attempts:
        attempt_parts = []
        for label, entry in sorted(attempts.items()):
            attempt_label = _process_tool_attempt_entry(label, entry, parts)
            attempt_parts.append(attempt_label)
        if attempt_parts:
            parts.insert(0, "attempts=" + ", ".join(attempt_parts))
    
    details = tool_summary.get("details")
    if details:
        parts.append(_stringify_healthcheck_detail(details))
    
    return "; ".join(parts) if parts else "-"


def _create_healthcheck_table() -> Table:
    """Create the healthcheck summary table with columns."""
    table = Table(title="Healthcheck Summary", box=box.SIMPLE_HEAVY)
    table.add_column("Check", style=_RichStyles.ACCENT)
    table.add_column("Context", style=_RichStyles.SECONDARY)
    table.add_column("Tool", style=_RichStyles.SUCCESS)
    table.add_column("Status", style=_RichStyles.EMPHASIS)
    table.add_column("Details", style=_RichStyles.DETAIL)
    return table


def _add_healthcheck_offline_row(table: Table, report: dict[str, Any]) -> None:
    """Add the offline check row to the healthcheck table."""
    offline_entry = report.get("offline_check", {})
    offline_status = _healthcheck_status_label(offline_entry.get("status"))
    offline_detail = _stringify_healthcheck_detail(offline_entry.get("details"))
    table.add_row("Offline checks", "-", "-", offline_status, offline_detail)


def _determine_context_status(context_data: Mapping[str, Any]) -> str:
    """Determine the status label for a context."""
    context_success = context_data.get("success")
    offline_mode = context_data.get("offline_mode")
    if offline_mode and context_success:
        return "warning"
    elif context_success:
        return "pass"
    else:
        return "fail"


def _add_healthcheck_context_rows(
    table: Table,
    context_name: str,
    context_data: Mapping[str, Any],
) -> None:
    """Add context, online, and tool rows for a single context."""
    context_status = _determine_context_status(context_data)
    context_detail = _format_healthcheck_context_detail(context_data)
    context_status_label = _healthcheck_status_label(context_status)
    table.add_row("Context", context_name, "-", context_status_label, context_detail)

    online_summary = context_data.get("online", {})
    online_status_label = _healthcheck_status_label(online_summary.get("status"))
    online_detail = _format_healthcheck_online_detail(online_summary)
    table.add_row("Online", context_name, "-", online_status_label, online_detail or "-")

    tools = context_data.get("tools", {})
    for tool_name, tool_summary in sorted(tools.items()):
        tool_status_label = _healthcheck_status_label(tool_summary.get("status"))
        detail_text = _format_healthcheck_tool_detail(tool_summary)
        table.add_row("Tool", context_name, tool_name, tool_status_label, detail_text)


def _collect_healthcheck_critical_failures(
    context_name: str,
    context_data: Mapping[str, Any],
) -> list[str]:
    """Collect critical failure messages for a context."""
    failures: list[str] = []
    context_status = _determine_context_status(context_data)
    context_status_label = _healthcheck_status_label(context_status)
    
    if context_status_label == "FAIL":
        failures.append(f"{context_name}: context failure")
    
    unrecoverable = context_data.get("unrecoverable_categories") or []
    if unrecoverable:
        failures.append(
            f"{context_name}: unrecoverable={','.join(sorted(unrecoverable))}"
        )
    
    return failures


def _render_healthcheck_summary(report: dict[str, Any]) -> None:
    """Render a comprehensive healthcheck summary table and JSON report."""
    table = _create_healthcheck_table()
    _add_healthcheck_offline_row(table, report)

    critical_failures: list[str] = []
    for context_name, context_data in sorted(report.get("contexts", {}).items()):
        _add_healthcheck_context_rows(table, context_name, context_data)
        critical_failures.extend(
            _collect_healthcheck_critical_failures(context_name, context_data)
        )

    if critical_failures:
        table.add_row(
            "Critical failures",
            "-",
            "-",
            "FAIL",
            "; ".join(critical_failures),
        )

    stdout_console.print()
    stdout_console.print(table)
    stdout_console.print()
    stdout_console.print("Machine-readable summary:")
    stdout_console.print(json.dumps(report, indent=2, sort_keys=True))


def _format_exception_message(exc: BaseException) -> str:
    return str(exc)


def _validate_company_entry(entry: Any, logger: BoundLogger) -> bool:
    """Validate a single company entry in search results."""
    if not isinstance(entry, dict):
        logger.critical("healthcheck.company_search.invalid_company", reason="entry not dict")
        return False
    if not entry.get("guid") or not entry.get("name"):
        logger.critical(
            "healthcheck.company_search.invalid_company",
            reason="missing guid/name",
            company=entry,
        )
        return False
    return True


def _check_domain_match(companies: list, expected_domain: str, logger: BoundLogger) -> bool:
    """Check if expected domain is present in company list."""
    for entry in companies:
        domain_value = str(entry.get("domain") or "")
        if domain_value.lower() == expected_domain.lower():
            return True
    logger.critical("healthcheck.company_search.domain_missing", expected=expected_domain)
    return False


def _validate_company_search_payload(
    payload: Any,
    *,
    logger: BoundLogger,
    expected_domain: str | None = None,
) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.company_search.invalid_response", reason=MSG_NOT_A_DICT)
        return False

    if payload.get("error"):
        logger.critical("healthcheck.company_search.api_error", error=str(payload["error"]))
        return False

    companies = payload.get("companies")
    if not isinstance(companies, list) or not companies:
        logger.critical("healthcheck.company_search.empty", reason="no companies returned")
        return False

    for entry in companies:
        if not _validate_company_entry(entry, logger):
            return False

    count_value = payload.get("count")
    if not isinstance(count_value, int) or count_value <= 0:
        logger.critical("healthcheck.company_search.invalid_count", count=count_value)
        return False

    if expected_domain and not _check_domain_match(companies, expected_domain, logger):
        return False

    return True


def _validate_rating_payload(payload: Any, *, logger: BoundLogger) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.rating.invalid_response", reason=MSG_NOT_A_DICT)
        return False

    if payload.get("error"):
        logger.critical("healthcheck.rating.api_error", error=str(payload["error"]))
        return False

    required_fields = ("name", "domain", "current_rating", "top_findings", "legend")
    for field in required_fields:
        if payload.get(field) in (None, {}):
            logger.critical("healthcheck.rating.missing_field", field=field)
            return False

    current_rating = payload.get("current_rating")
    if not isinstance(current_rating, dict) or current_rating.get("value") is None:
        logger.critical("healthcheck.rating.invalid_current_rating", payload=current_rating)
        return False

    findings = payload.get("top_findings")
    if not isinstance(findings, dict):
        logger.critical("healthcheck.rating.invalid_findings", payload=findings)
        return False

    finding_count = findings.get("count")
    finding_entries = findings.get("findings")
    if not isinstance(finding_count, int) or finding_count <= 0:
        logger.critical("healthcheck.rating.no_findings", count=finding_count)
        return False
    if not isinstance(finding_entries, list) or not finding_entries:
        logger.critical("healthcheck.rating.empty_findings", payload=findings)
        return False

    legend = payload.get("legend")
    if not isinstance(legend, dict) or not legend.get("rating"):
        logger.critical("healthcheck.rating.missing_legend", payload=legend)
        return False

    return True


def _validate_company_search_interactive_payload(payload: Any, *, logger: BoundLogger) -> bool:
    if not isinstance(payload, dict):
        logger.critical(
            "healthcheck.company_search_interactive.invalid_response", reason=MSG_NOT_A_DICT
        )
        return False

    if payload.get("error"):
        logger.critical(
            "healthcheck.company_search_interactive.api_error",
            error=str(payload["error"]),
        )
        return False

    results = payload.get("results")
    if not isinstance(results, list) or not results:
        logger.critical(
            "healthcheck.company_search_interactive.empty_results",
            reason="no interactive results",
        )
        return False

    for entry in results:
        if not isinstance(entry, dict):
            logger.critical(
                "healthcheck.company_search_interactive.invalid_entry",
                reason="entry not dict",
            )
            return False
        required_keys = ("guid", "name", "primary_domain", "subscription")
        if any(not entry.get(key) for key in required_keys):
            logger.critical(
                "healthcheck.company_search_interactive.missing_fields",
                entry=entry,
            )
            return False
        subscription = entry.get("subscription")
        if not isinstance(subscription, dict) or "active" not in subscription:
            logger.critical(
                "healthcheck.company_search_interactive.invalid_subscription",
                subscription=subscription,
            )
            return False

    count_value = payload.get("count")
    if not isinstance(count_value, int) or count_value <= 0:
        logger.critical(
            "healthcheck.company_search_interactive.invalid_count",
            count=count_value,
        )
        return False

    guidance = payload.get("guidance")
    if not isinstance(guidance, dict):
        logger.critical("healthcheck.company_search_interactive.missing_guidance")
        return False

    return True


def _validate_manage_subscriptions_payload(
    payload: Any, *, logger: BoundLogger, expected_guid: str
) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.manage_subscriptions.invalid_response", reason=MSG_NOT_A_DICT)
        return False

    if payload.get("error"):
        logger.critical("healthcheck.manage_subscriptions.api_error", error=str(payload["error"]))
        return False

    status = payload.get("status")
    if status not in {"dry_run", "applied"}:
        logger.critical("healthcheck.manage_subscriptions.unexpected_status", status=status)
        return False

    guids = payload.get("guids")
    if not isinstance(guids, list) or expected_guid not in guids:
        logger.critical(
            "healthcheck.manage_subscriptions.guid_missing",
            guids=guids,
            expected=expected_guid,
        )
        return False

    if status == "dry_run":
        dry_payload = payload.get("payload")
        if not isinstance(dry_payload, dict) or "add" not in dry_payload:
            logger.critical(
                "healthcheck.manage_subscriptions.invalid_payload",
                payload=dry_payload,
            )
            return False

    return True


def _healthcheck_status_label(value: str | None) -> str:
    """Convert status value to uppercase label."""
    mapping = {"pass": "PASS", "fail": "FAIL", "warning": "WARNING"}
    if not value:
        return "WARNING"
    return mapping.get(value.lower(), value.upper())


def _stringify_healthcheck_detail(value: Any) -> str:
    """Convert any value to a string representation for healthcheck display."""
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        items = [f"{key}={value[key]}" for key in sorted(value)]
        return ", ".join(items) if items else "-"
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        items = [_stringify_healthcheck_detail(item) for item in value]
        return ", ".join(item for item in items if item and item != "-") or "-"
    return str(value)


def _format_healthcheck_context_detail(context_data: Mapping[str, Any]) -> str:
    """Format context diagnostic details into a summary string."""
    parts: list[str] = []
    if context_data.get("fallback_attempted"):
        resolved = context_data.get("fallback_success")
        parts.append("fallback=" + ("resolved" if resolved else "failed"))
    recoverable = context_data.get("recoverable_categories") or []
    if recoverable:
        parts.append("recoverable=" + ",".join(sorted(recoverable)))
    unrecoverable = context_data.get("unrecoverable_categories") or []
    if unrecoverable:
        parts.append("unrecoverable=" + ",".join(sorted(unrecoverable)))
    notes = context_data.get("notes") or []
    if notes:
        parts.append("notes=" + ",".join(notes))
    return "; ".join(parts) if parts else "-"


def _format_healthcheck_online_detail(online_data: Mapping[str, Any]) -> str:
    """Format online diagnostic details into a summary string."""
    attempts = online_data.get("attempts") if isinstance(online_data, Mapping) else None
    if isinstance(attempts, Mapping) and attempts:
        attempt_parts = [
            f"{label}:{_healthcheck_status_label(status)}"
            for label, status in sorted(attempts.items())
        ]
        return ", ".join(attempt_parts)
    details = online_data.get("details") if isinstance(online_data, Mapping) else None
    return _stringify_healthcheck_detail(details)


def _process_tool_attempt_entry(
    label: str,
    entry: Mapping[str, Any],
    parts: list[str],
) -> str:
    """Process a single tool attempt entry and return its status label."""
    attempt_status = _healthcheck_status_label(entry.get("status"))
    
    modes = entry.get("modes")
    if isinstance(modes, Mapping) and modes:
        mode_parts = [
            f"{mode}:{_healthcheck_status_label(mode_entry.get('status'))}"
            for mode, mode_entry in sorted(modes.items())
        ]
        if mode_parts:
            parts.append(f"{label} modes=" + ", ".join(mode_parts))
    
    detail = entry.get("details")
    if detail:
        parts.append(f"{label} detail=" + _stringify_healthcheck_detail(detail))
    
    return f"{label}:{attempt_status}"


def _format_healthcheck_tool_detail(tool_summary: Mapping[str, Any]) -> str:
    """Format tool diagnostic details into a summary string."""
    parts: list[str] = []
    attempts = tool_summary.get("attempts")
    if isinstance(attempts, Mapping) and attempts:
        attempt_parts = []
        for label, entry in sorted(attempts.items()):
            attempt_label = _process_tool_attempt_entry(label, entry, parts)
            attempt_parts.append(attempt_label)
        if attempt_parts:
            parts.insert(0, "attempts=" + ", ".join(attempt_parts))
    
    details = tool_summary.get("details")
    if details:
        parts.append(_stringify_healthcheck_detail(details))
    
    return "; ".join(parts) if parts else "-"


def _create_healthcheck_table() -> Table:
    """Create the healthcheck summary table with columns."""
    table = Table(title="Healthcheck Summary", box=box.SIMPLE_HEAVY)
    table.add_column("Check", style=_RichStyles.ACCENT)
    table.add_column("Context", style=_RichStyles.SECONDARY)
    table.add_column("Tool", style=_RichStyles.SUCCESS)
    table.add_column("Status", style=_RichStyles.EMPHASIS)
    table.add_column("Details", style=_RichStyles.DETAIL)
    return table


def _add_healthcheck_offline_row(table: Table, report: dict[str, Any]) -> None:
    """Add the offline check row to the healthcheck table."""
    offline_entry = report.get("offline_check", {})
    offline_status = _healthcheck_status_label(offline_entry.get("status"))
    offline_detail = _stringify_healthcheck_detail(offline_entry.get("details"))
    table.add_row("Offline checks", "-", "-", offline_status, offline_detail)


def _determine_context_status(context_data: Mapping[str, Any]) -> str:
    """Determine the status label for a context."""
    context_success = context_data.get("success")
    offline_mode = context_data.get("offline_mode")
    if offline_mode and context_success:
        return "warning"
    elif context_success:
        return "pass"
    else:
        return "fail"


def _add_healthcheck_context_rows(
    table: Table,
    context_name: str,
    context_data: Mapping[str, Any],
) -> None:
    """Add context, online, and tool rows for a single context."""
    context_status = _determine_context_status(context_data)
    context_detail = _format_healthcheck_context_detail(context_data)
    context_status_label = _healthcheck_status_label(context_status)
    table.add_row("Context", context_name, "-", context_status_label, context_detail)

    online_summary = context_data.get("online", {})
    online_status_label = _healthcheck_status_label(online_summary.get("status"))
    online_detail = _format_healthcheck_online_detail(online_summary)
    table.add_row("Online", context_name, "-", online_status_label, online_detail or "-")

    tools = context_data.get("tools", {})
    for tool_name, tool_summary in sorted(tools.items()):
        tool_status_label = _healthcheck_status_label(tool_summary.get("status"))
        detail_text = _format_healthcheck_tool_detail(tool_summary)
        table.add_row("Tool", context_name, tool_name, tool_status_label, detail_text)


def _collect_healthcheck_critical_failures(
    context_name: str,
    context_data: Mapping[str, Any],
) -> list[str]:
    """Collect critical failure messages for a context."""
    failures: list[str] = []
    context_status = _determine_context_status(context_data)
    context_status_label = _healthcheck_status_label(context_status)
    
    if context_status_label == "FAIL":
        failures.append(f"{context_name}: context failure")
    
    unrecoverable = context_data.get("unrecoverable_categories") or []
    if unrecoverable:
        failures.append(
            f"{context_name}: unrecoverable={','.join(sorted(unrecoverable))}"
        )
    
    return failures


def _render_healthcheck_summary(report: dict[str, Any]) -> None:
    """Render a comprehensive healthcheck summary table and JSON report."""
    table = _create_healthcheck_table()
    _add_healthcheck_offline_row(table, report)

    critical_failures: list[str] = []
    for context_name, context_data in sorted(report.get("contexts", {}).items()):
        _add_healthcheck_context_rows(table, context_name, context_data)
        critical_failures.extend(
            _collect_healthcheck_critical_failures(context_name, context_data)
        )

    if critical_failures:
        table.add_row(
            "Critical failures",
            "-",
            "-",
            "FAIL",
            "; ".join(critical_failures),
        )

    stdout_console.print()
    stdout_console.print(table)
    stdout_console.print()
    stdout_console.print("Machine-readable summary:")
    stdout_console.print(json.dumps(report, indent=2, sort_keys=True))


def _format_exception_message(exc: BaseException) -> str:
    return str(exc)


def _validate_company_entry(entry: Any, logger: BoundLogger) -> bool:
    """Validate a single company entry in search results."""
    if not isinstance(entry, dict):
        logger.critical("healthcheck.company_search.invalid_company", reason="entry not dict")
        return False
    if not entry.get("guid") or not entry.get("name"):
        logger.critical(
            "healthcheck.company_search.invalid_company",
            reason="missing guid/name",
            company=entry,
        )
        return False
    return True


def _check_domain_match(companies: list, expected_domain: str, logger: BoundLogger) -> bool:
    """Check if expected domain is present in company list."""
    for entry in companies:
        domain_value = str(entry.get("domain") or "")
        if domain_value.lower() == expected_domain.lower():
            return True
    logger.critical("healthcheck.company_search.domain_missing", expected=expected_domain)
    return False


def _validate_company_search_payload(
    payload: Any,
    *,
    logger: BoundLogger,
    expected_domain: str | None = None,
) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.company_search.invalid_response", reason=MSG_NOT_A_DICT)
        return False

    if payload.get("error"):
        logger.critical("healthcheck.company_search.api_error", error=str(payload["error"]))
        return False

    companies = payload.get("companies")
    if not isinstance(companies, list) or not companies:
        logger.critical("healthcheck.company_search.empty", reason="no companies returned")
        return False

    for entry in companies:
        if not _validate_company_entry(entry, logger):
            return False

    count_value = payload.get("count")
    if not isinstance(count_value, int) or count_value <= 0:
        logger.critical("healthcheck.company_search.invalid_count", count=count_value)
        return False

    if expected_domain and not _check_domain_match(companies, expected_domain, logger):
        return False

    return True


def _validate_rating_payload(payload: Any, *, logger: BoundLogger) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.rating.invalid_response", reason=MSG_NOT_A_DICT)
        return False

    if payload.get("error"):
        logger.critical("healthcheck.rating.api_error", error=str(payload["error"]))
        return False

    required_fields = ("name", "domain", "current_rating", "top_findings", "legend")
    for field in required_fields:
        if payload.get(field) in (None, {}):
            logger.critical("healthcheck.rating.missing_field", field=field)
            return False

    current_rating = payload.get("current_rating")
    if not isinstance(current_rating, dict) or current_rating.get("value") is None:
        logger.critical("healthcheck.rating.invalid_current_rating", payload=current_rating)
        return False

    findings = payload.get("top_findings")
    if not isinstance(findings, dict):
        logger.critical("healthcheck.rating.invalid_findings", payload=findings)
        return False

    finding_count = findings.get("count")
    finding_entries = findings.get("findings")
    if not isinstance(finding_count, int) or finding_count <= 0:
        logger.critical("healthcheck.rating.no_findings", count=finding_count)
        return False
    if not isinstance(finding_entries, list) or not finding_entries:
        logger.critical("healthcheck.rating.empty_findings", payload=findings)
        return False

    legend = payload.get("legend")
    if not isinstance(legend, dict) or not legend.get("rating"):
        logger.critical("healthcheck.rating.missing_legend", payload=legend)
        return False

    return True


def _validate_company_search_interactive_payload(payload: Any, *, logger: BoundLogger) -> bool:
    if not isinstance(payload, dict):
        logger.critical(
            "healthcheck.company_search_interactive.invalid_response", reason=MSG_NOT_A_DICT
        )
        return False

    if payload.get("error"):
        logger.critical(
            "healthcheck.company_search_interactive.api_error",
            error=str(payload["error"]),
        )
        return False

    results = payload.get("results")
    if not isinstance(results, list) or not results:
        logger.critical(
            "healthcheck.company_search_interactive.empty_results",
            reason="no interactive results",
        )
        return False

    for entry in results:
        if not isinstance(entry, dict):
            logger.critical(
                "healthcheck.company_search_interactive.invalid_entry",
                reason="entry not dict",
            )
            return False
        required_keys = ("guid", "name", "primary_domain", "subscription")
        if any(not entry.get(key) for key in required_keys):
            logger.critical(
                "healthcheck.company_search_interactive.missing_fields",
                entry=entry,
            )
            return False
        subscription = entry.get("subscription")
        if not isinstance(subscription, dict) or "active" not in subscription:
            logger.critical(
                "healthcheck.company_search_interactive.invalid_subscription",
                subscription=subscription,
            )
            return False

    count_value = payload.get("count")
    if not isinstance(count_value, int) or count_value <= 0:
        logger.critical(
            "healthcheck.company_search_interactive.invalid_count",
            count=count_value,
        )
        return False

    guidance = payload.get("guidance")
    if not isinstance(guidance, dict):
        logger.critical("healthcheck.company_search_interactive.missing_guidance")
        return False

    return True


def _validate_manage_subscriptions_payload(
    payload: Any, *, logger: BoundLogger, expected_guid: str
) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.manage_subscriptions.invalid_response", reason=MSG_NOT_A_DICT)
        return False

    if payload.get("error"):
        logger.critical("healthcheck.manage_subscriptions.api_error", error=str(payload["error"]))
        return False

    status = payload.get("status")
    if status not in {"dry_run", "applied"}:
        logger.critical("healthcheck.manage_subscriptions.unexpected_status", status=status)
        return False

    guids = payload.get("guids")
    if not isinstance(guids, list) or expected_guid not in guids:
        logger.critical(
            "healthcheck.manage_subscriptions.guid_missing",
            guids=guids,
            expected=expected_guid,
        )
        return False

    if status == "dry_run":
        dry_payload = payload.get("payload")
        if not isinstance(dry_payload, dict) or "add" not in dry_payload:
            logger.critical(
                "healthcheck.manage_subscriptions.invalid_payload",
                payload=dry_payload,
            )
            return False

    return True


def _validate_request_company_payload(
    payload: Any, *, logger: BoundLogger, expected_domain: str
) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.request_company.invalid_response", reason=MSG_NOT_A_DICT)
        return False

    if payload.get("error"):
        logger.critical("healthcheck.request_company.api_error", error=str(payload["error"]))
        return False

    status = payload.get("status")
    if status not in {"dry_run", "already_requested"}:
        logger.critical("healthcheck.request_company.unexpected_status", status=status)
        return False

    domain_value = payload.get("domain")
    if not isinstance(domain_value, str) or domain_value.lower() != expected_domain.lower():
        logger.critical(
            "healthcheck.request_company.domain_mismatch",
            domain=domain_value,
            expected=expected_domain,
        )
        return False

    if status == "dry_run":
        dry_payload = payload.get("payload")
        if not isinstance(dry_payload, dict) or "file" not in dry_payload:
            logger.critical("healthcheck.request_company.invalid_payload", payload=dry_payload)
            return False
    else:
        requests = payload.get("requests")
        if not isinstance(requests, list):
            logger.critical(
                "healthcheck.request_company.invalid_requests",
                requests=requests,
            )
            return False

    return True


def _healthcheck_status_label(value: str | None) -> str:
    """Convert status value to uppercase label."""
    mapping = {"pass": "PASS", "fail": "FAIL", "warning": "WARNING"}
    if not value:
        return "WARNING"
    return mapping.get(value.lower(), value.upper())


def _stringify_healthcheck_detail(value: Any) -> str:
    """Convert any value to a string representation for healthcheck display."""
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        items = [f"{key}={value[key]}" for key in sorted(value)]
        return ", ".join(items) if items else "-"
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        items = [_stringify_healthcheck_detail(item) for item in value]
        return ", ".join(item for item in items if item and item != "-") or "-"
    return str(value)


def _format_healthcheck_context_detail(context_data: Mapping[str, Any]) -> str:
    """Format context diagnostic details into a summary string."""
    parts: list[str] = []
    if context_data.get("fallback_attempted"):
        resolved = context_data.get("fallback_success")
        parts.append("fallback=" + ("resolved" if resolved else "failed"))
    recoverable = context_data.get("recoverable_categories") or []
    if recoverable:
        parts.append("recoverable=" + ",".join(sorted(recoverable)))
    unrecoverable = context_data.get("unrecoverable_categories") or []
    if unrecoverable:
        parts.append("unrecoverable=" + ",".join(sorted(unrecoverable)))
    notes = context_data.get("notes") or []
    if notes:
        parts.append("notes=" + ",".join(notes))
    return "; ".join(parts) if parts else "-"


def _format_healthcheck_online_detail(online_data: Mapping[str, Any]) -> str:
    """Format online diagnostic details into a summary string."""
    attempts = online_data.get("attempts") if isinstance(online_data, Mapping) else None
    if isinstance(attempts, Mapping) and attempts:
        attempt_parts = [
            f"{label}:{_healthcheck_status_label(status)}"
            for label, status in sorted(attempts.items())
        ]
        return ", ".join(attempt_parts)
    details = online_data.get("details") if isinstance(online_data, Mapping) else None
    return _stringify_healthcheck_detail(details)


def _process_tool_attempt_entry(
    label: str,
    entry: Mapping[str, Any],
    parts: list[str],
) -> str:
    """Process a single tool attempt entry and return its status label."""
    attempt_status = _healthcheck_status_label(entry.get("status"))
    
    modes = entry.get("modes")
    if isinstance(modes, Mapping) and modes:
        mode_parts = [
            f"{mode}:{_healthcheck_status_label(mode_entry.get('status'))}"
            for mode, mode_entry in sorted(modes.items())
        ]
        if mode_parts:
            parts.append(f"{label} modes=" + ", ".join(mode_parts))
    
    detail = entry.get("details")
    if detail:
        parts.append(f"{label} detail=" + _stringify_healthcheck_detail(detail))
    
    return f"{label}:{attempt_status}"


def _format_healthcheck_tool_detail(tool_summary: Mapping[str, Any]) -> str:
    """Format tool diagnostic details into a summary string."""
    parts: list[str] = []
    attempts = tool_summary.get("attempts")
    if isinstance(attempts, Mapping) and attempts:
        attempt_parts = []
        for label, entry in sorted(attempts.items()):
            attempt_label = _process_tool_attempt_entry(label, entry, parts)
            attempt_parts.append(attempt_label)
        if attempt_parts:
            parts.insert(0, "attempts=" + ", ".join(attempt_parts))
    
    details = tool_summary.get("details")
    if details:
        parts.append(_stringify_healthcheck_detail(details))
    
    return "; ".join(parts) if parts else "-"


def _create_healthcheck_table() -> Table:
    """Create the healthcheck summary table with columns."""
    table = Table(title="Healthcheck Summary", box=box.SIMPLE_HEAVY)
    table.add_column("Check", style=_RichStyles.ACCENT)
    table.add_column("Context", style=_RichStyles.SECONDARY)
    table.add_column("Tool", style=_RichStyles.SUCCESS)
    table.add_column("Status", style=_RichStyles.EMPHASIS)
    table.add_column("Details", style=_RichStyles.DETAIL)
    return table


def _add_healthcheck_offline_row(table: Table, report: dict[str, Any]) -> None:
    """Add the offline check row to the healthcheck table."""
    offline_entry = report.get("offline_check", {})
    offline_status = _healthcheck_status_label(offline_entry.get("status"))
    offline_detail = _stringify_healthcheck_detail(offline_entry.get("details"))
    table.add_row("Offline checks", "-", "-", offline_status, offline_detail)


def _determine_context_status(context_data: Mapping[str, Any]) -> str:
    """Determine the status label for a context."""
    context_success = context_data.get("success")
    offline_mode = context_data.get("offline_mode")
    if offline_mode and context_success:
        return "warning"
    elif context_success:
        return "pass"
    else:
        return "fail"


def _add_healthcheck_context_rows(
    table: Table,
    context_name: str,
    context_data: Mapping[str, Any],
) -> None:
    """Add context, online, and tool rows for a single context."""
    context_status = _determine_context_status(context_data)
    context_detail = _format_healthcheck_context_detail(context_data)
    context_status_label = _healthcheck_status_label(context_status)
    table.add_row("Context", context_name, "-", context_status_label, context_detail)

    online_summary = context_data.get("online", {})
    online_status_label = _healthcheck_status_label(online_summary.get("status"))
    online_detail = _format_healthcheck_online_detail(online_summary)
    table.add_row("Online", context_name, "-", online_status_label, online_detail or "-")

    tools = context_data.get("tools", {})
    for tool_name, tool_summary in sorted(tools.items()):
        tool_status_label = _healthcheck_status_label(tool_summary.get("status"))
        detail_text = _format_healthcheck_tool_detail(tool_summary)
        table.add_row("Tool", context_name, tool_name, tool_status_label, detail_text)


def _collect_healthcheck_critical_failures(
    context_name: str,
    context_data: Mapping[str, Any],
) -> list[str]:
    """Collect critical failure messages for a context."""
    failures: list[str] = []
    context_status = _determine_context_status(context_data)
    context_status_label = _healthcheck_status_label(context_status)
    
    if context_status_label == "FAIL":
        failures.append(f"{context_name}: context failure")
    
    unrecoverable = context_data.get("unrecoverable_categories") or []
    if unrecoverable:
        failures.append(
            f"{context_name}: unrecoverable={','.join(sorted(unrecoverable))}"
        )
    
    return failures


def _render_healthcheck_summary(report: dict[str, Any]) -> None:
    """Render a comprehensive healthcheck summary table and JSON report."""
    table = _create_healthcheck_table()
    _add_healthcheck_offline_row(table, report)

    critical_failures: list[str] = []
    for context_name, context_data in sorted(report.get("contexts", {}).items()):
        _add_healthcheck_context_rows(table, context_name, context_data)
        critical_failures.extend(
            _collect_healthcheck_critical_failures(context_name, context_data)
        )

    if critical_failures:
        table.add_row(
            "Critical failures",
            "-",
            "-",
            "FAIL",
            "; ".join(critical_failures),
        )

    stdout_console.print()
    stdout_console.print(table)
    stdout_console.print()
    stdout_console.print("Machine-readable summary:")
    stdout_console.print(json.dumps(report, indent=2, sort_keys=True))


def _format_exception_message(exc: BaseException) -> str:
    return str(exc)


def _validate_company_entry(entry: Any, logger: BoundLogger) -> bool:
    """Validate a single company entry in search results."""
    if not isinstance(entry, dict):
        logger.critical("healthcheck.company_search.invalid_company", reason="entry not dict")
        return False
    if not entry.get("guid") or not entry.get("name"):
        logger.critical(
            "healthcheck.company_search.invalid_company",
            reason="missing guid/name",
            company=entry,
        )
        return False
    return True


def _check_domain_match(companies: list, expected_domain: str, logger: BoundLogger) -> bool:
    """Check if expected domain is present in company list."""
    for entry in companies:
        domain_value = str(entry.get("domain") or "")
        if domain_value.lower() == expected_domain.lower():
            return True
    logger.critical("healthcheck.company_search.domain_missing", expected=expected_domain)
    return False


def _validate_company_search_payload(
    payload: Any,
    *,
    logger: BoundLogger,
    expected_domain: str | None = None,
) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.company_search.invalid_response", reason=MSG_NOT_A_DICT)
        return False

    if payload.get("error"):
        logger.critical("healthcheck.company_search.api_error", error=str(payload["error"]))
        return False

    companies = payload.get("companies")
    if not isinstance(companies, list) or not companies:
        logger.critical("healthcheck.company_search.empty", reason="no companies returned")
        return False

    for entry in companies:
        if not _validate_company_entry(entry, logger):
            return False

    count_value = payload.get("count")
    if not isinstance(count_value, int) or count_value <= 0:
        logger.critical("healthcheck.company_search.invalid_count", count=count_value)
        return False

    if expected_domain and not _check_domain_match(companies, expected_domain, logger):
        return False

    return True


def _validate_rating_payload(payload: Any, *, logger: BoundLogger) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.rating.invalid_response", reason=MSG_NOT_A_DICT)
        return False

    if payload.get("error"):
        logger.critical("healthcheck.rating.api_error", error=str(payload["error"]))
        return False

    required_fields = ("name", "domain", "current_rating", "top_findings", "legend")
    for field in required_fields:
        if payload.get(field) in (None, {}):
            logger.critical("healthcheck.rating.missing_field", field=field)
            return False

    current_rating = payload.get("current_rating")
    if not isinstance(current_rating, dict) or current_rating.get("value") is None:
        logger.critical("healthcheck.rating.invalid_current_rating", payload=current_rating)
        return False

    findings = payload.get("top_findings")
    if not isinstance(findings, dict):
        logger.critical("healthcheck.rating.invalid_findings", payload=findings)
        return False

    finding_count = findings.get("count")
    finding_entries = findings.get("findings")
    if not isinstance(finding_count, int) or finding_count <= 0:
        logger.critical("healthcheck.rating.no_findings", count=finding_count)
        return False
    if not isinstance(finding_entries, list) or not finding_entries:
        logger.critical("healthcheck.rating.empty_findings", payload=findings)
        return False

    legend = payload.get("legend")
    if not isinstance(legend, dict) or not legend.get("rating"):
        logger.critical("healthcheck.rating.missing_legend", payload=legend)
        return False

    return True


def _validate_company_search_interactive_payload(payload: Any, *, logger: BoundLogger) -> bool:
    if not isinstance(payload, dict):
        logger.critical(
            "healthcheck.company_search_interactive.invalid_response", reason=MSG_NOT_A_DICT
        )
        return False

    if payload.get("error"):
        logger.critical(
            "healthcheck.company_search_interactive.api_error",
            error=str(payload["error"]),
        )
        return False

    results = payload.get("results")
    if not isinstance(results, list) or not results:
        logger.critical(
            "healthcheck.company_search_interactive.empty_results",
            reason="no interactive results",
        )
        return False

    for entry in results:
        if not isinstance(entry, dict):
            logger.critical(
                "healthcheck.company_search_interactive.invalid_entry",
                reason="entry not dict",
            )
            return False
        required_keys = ("guid", "name", "primary_domain", "subscription")
        if any(not entry.get(key) for key in required_keys):
            logger.critical(
                "healthcheck.company_search_interactive.missing_fields",
                entry=entry,
            )
            return False
        subscription = entry.get("subscription")
        if not isinstance(subscription, dict) or "active" not in subscription:
            logger.critical(
                "healthcheck.company_search_interactive.invalid_subscription",
                subscription=subscription,
            )
            return False

    count_value = payload.get("count")
    if not isinstance(count_value, int) or count_value <= 0:
        logger.critical(
            "healthcheck.company_search_interactive.invalid_count",
            count=count_value,
        )
        return False

    guidance = payload.get("guidance")
    if not isinstance(guidance, dict):
        logger.critical("healthcheck.company_search_interactive.missing_guidance")
        return False

    return True


def _validate_manage_subscriptions_payload(
    payload: Any, *, logger: BoundLogger, expected_guid: str
) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.manage_subscriptions.invalid_response", reason=MSG_NOT_A_DICT)
        return False

    if payload.get("error"):
        logger.critical("healthcheck.manage_subscriptions.api_error", error=str(payload["error"]))
        return False

    status = payload.get("status")
    if status not in {"dry_run", "applied"}:
        logger.critical("healthcheck.manage_subscriptions.unexpected_status", status=status)
        return False

    guids = payload.get("guids")
    if not isinstance(guids, list) or expected_guid not in guids:
        logger.critical(
            "healthcheck.manage_subscriptions.guid_missing",
            guids=guids,
            expected=expected_guid,
        )
        return False

    if status == "dry_run":
        dry_payload = payload.get("payload")
        if not isinstance(dry_payload, dict) or "add" not in dry_payload:
            logger.critical(
                "healthcheck.manage_subscriptions.invalid_payload",
                payload=dry_payload,
            )
            return False

    return True


def _healthcheck_status_label(value: str | None) -> str:
    """Convert status value to uppercase label."""
    mapping = {"pass": "PASS", "fail": "FAIL", "warning": "WARNING"}
    if not value:
        return "WARNING"
    return mapping.get(value.lower(), value.upper())


def _stringify_healthcheck_detail(value: Any) -> str:
    """Convert any value to a string representation for healthcheck display."""
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        items = [f"{key}={value[key]}" for key in sorted(value)]
        return ", ".join(items) if items else "-"
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        items = [_stringify_healthcheck_detail(item) for item in value]
        return ", ".join(item for item in items if item and item != "-") or "-"
    return str(value)


def _format_healthcheck_context_detail(context_data: Mapping[str, Any]) -> str:
    """Format context diagnostic details into a summary string."""
    parts: list[str] = []
    if context_data.get("fallback_attempted"):
        resolved = context_data.get("fallback_success")
        parts.append("fallback=" + ("resolved" if resolved else "failed"))
    recoverable = context_data.get("recoverable_categories") or []
    if recoverable:
        parts.append("recoverable=" + ",".join(sorted(recoverable)))
    unrecoverable = context_data.get("unrecoverable_categories") or []
    if unrecoverable:
        parts.append("unrecoverable=" + ",".join(sorted(unrecoverable)))
    notes = context_data.get("notes") or []
    if notes:
        parts.append("notes=" + ",".join(notes))
    return "; ".join(parts) if parts else "-"


def _format_healthcheck_online_detail(online_data: Mapping[str, Any]) -> str:
    """Format online diagnostic details into a summary string."""
    attempts = online_data.get("attempts") if isinstance(online_data, Mapping) else None
    if isinstance(attempts, Mapping) and attempts:
        attempt_parts = [
            f"{label}:{_healthcheck_status_label(status)}"
            for label, status in sorted(attempts.items())
        ]
        return ", ".join(attempt_parts)
    details = online_data.get("details") if isinstance(online_data, Mapping) else None
    return _stringify_healthcheck_detail(details)


def _process_tool_attempt_entry(
    label: str,
    entry: Mapping[str, Any],
    parts: list[str],
) -> str:
    """Process a single tool attempt entry and return its status label."""
    attempt_status = _healthcheck_status_label(entry.get("status"))
    
    modes = entry.get("modes")
    if isinstance(modes, Mapping) and modes:
        mode_parts = [
            f"{mode}:{_healthcheck_status_label(mode_entry.get('status'))}"
            for mode, mode_entry in sorted(modes.items())
        ]
        if mode_parts:
            parts.append(f"{label} modes=" + ", ".join(mode_parts))
    
    detail = entry.get("details")
    if detail:
        parts.append(f"{label} detail=" + _stringify_healthcheck_detail(detail))
    
    return f"{label}:{attempt_status}"


def _format_healthcheck_tool_detail(tool_summary: Mapping[str, Any]) -> str:
    """Format tool diagnostic details into a summary string."""
    parts: list[str] = []
    attempts = tool_summary.get("attempts")
    if isinstance(attempts, Mapping) and attempts:
        attempt_parts = []
        for label, entry in sorted(attempts.items()):
            attempt_label = _process_tool_attempt_entry(label, entry, parts)
            attempt_parts.append(attempt_label)
        if attempt_parts:
            parts.insert(0, "attempts=" + ", ".join(attempt_parts))
    
    details = tool_summary.get("details")
    if details:
        parts.append(_stringify_healthcheck_detail(details))
    
    return "; ".join(parts) if parts else "-"


def _create_healthcheck_table() -> Table:
    """Create the healthcheck summary table with columns."""
    table = Table(title="Healthcheck Summary", box=box.SIMPLE_HEAVY)
    table.add_column("Check", style=_RichStyles.ACCENT)
    table.add_column("Context", style=_RichStyles.SECONDARY)
    table.add_column("Tool", style=_RichStyles.SUCCESS)
    table.add_column("Status", style=_RichStyles.EMPHASIS)
    table.add_column("Details", style=_RichStyles.DETAIL)
    return table


def _add_healthcheck_offline_row(table: Table, report: dict[str, Any]) -> None:
    """Add the offline check row to the healthcheck table."""
    offline_entry = report.get("offline_check", {})
    offline_status = _healthcheck_status_label(offline_entry.get("status"))
    offline_detail = _stringify_healthcheck_detail(offline_entry.get("details"))
    table.add_row("Offline checks", "-", "-", offline_status, offline_detail)


def _determine_context_status(context_data: Mapping[str, Any]) -> str:
    """Determine the status label for a context."""
    context_success = context_data.get("success")
    offline_mode = context_data.get("offline_mode")
    if offline_mode and context_success:
        return "warning"
    elif context_success:
        return "pass"
    else:
        return "fail"


def _add_healthcheck_context_rows(
    table: Table,
    context_name: str,
    context_data: Mapping[str, Any],
) -> None:
    """Add context, online, and tool rows for a single context."""
    context_status = _determine_context_status(context_data)
    context_detail = _format_healthcheck_context_detail(context_data)
    context_status_label = _healthcheck_status_label(context_status)
    table.add_row("Context", context_name, "-", context_status_label, context_detail)

    online_summary = context_data.get("online", {})
    online_status_label = _healthcheck_status_label(online_summary.get("status"))
    online_detail = _format_healthcheck_online_detail(online_summary)
    table.add_row("Online", context_name, "-", online_status_label, online_detail or "-")

    tools = context_data.get("tools", {})
    for tool_name, tool_summary in sorted(tools.items()):
        tool_status_label = _healthcheck_status_label(tool_summary.get("status"))
        detail_text = _format_healthcheck_tool_detail(tool_summary)
        table.add_row("Tool", context_name, tool_name, tool_status_label, detail_text)


def _collect_healthcheck_critical_failures(
    context_name: str,
    context_data: Mapping[str, Any],
) -> list[str]:
    """Collect critical failure messages for a context."""
    failures: list[str] = []
    context_status = _determine_context_status(context_data)
    context_status_label = _healthcheck_status_label(context_status)
    
    if context_status_label == "FAIL":
        failures.append(f"{context_name}: context failure")
    
    unrecoverable = context_data.get("unrecoverable_categories") or []
    if unrecoverable:
        failures.append(
            f"{context_name}: unrecoverable={','.join(sorted(unrecoverable))}"
        )
    
    return failures


def _render_healthcheck_summary(report: dict[str, Any]) -> None:
    """Render a comprehensive healthcheck summary table and JSON report."""
    table = _create_healthcheck_table()
    _add_healthcheck_offline_row(table, report)

    critical_failures: list[str] = []
    for context_name, context_data in sorted(report.get("contexts", {}).items()):
        _add_healthcheck_context_rows(table, context_name, context_data)
        critical_failures.extend(
            _collect_healthcheck_critical_failures(context_name, context_data)
        )

    if critical_failures:
        table.add_row(
            "Critical failures",
            "-",
            "-",
            "FAIL",
            "; ".join(critical_failures),
        )

    stdout_console.print()
    stdout_console.print(table)
    stdout_console.print()
    stdout_console.print("Machine-readable summary:")
    stdout_console.print(json.dumps(report, indent=2, sort_keys=True))


def _format_exception_message(exc: BaseException) -> str:
    return str(exc)


def _validate_company_entry(entry: Any, logger: BoundLogger) -> bool:
    """Validate a single company entry in search results."""
    if not isinstance(entry, dict):
        logger.critical("healthcheck.company_search.invalid_company", reason="entry not dict")
        return False
    if not entry.get("guid") or not entry.get("name"):
        logger.critical(
            "healthcheck.company_search.invalid_company",
            reason="missing guid/name",
            company=entry,
        )
        return False
    return True


def _check_domain_match(companies: list, expected_domain: str, logger: BoundLogger) -> bool:
    """Check if expected domain is present in company list."""
    for entry in companies:
        domain_value = str(entry.get("domain") or "")
        if domain_value.lower() == expected_domain.lower():
            return True
    logger.critical("healthcheck.company_search.domain_missing", expected=expected_domain)
    return False


def _validate_company_search_payload(
    payload: Any,
    *,
    logger: BoundLogger,
    expected_domain: str | None = None,
) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.company_search.invalid_response", reason=MSG_NOT_A_DICT)
        return False

    if payload.get("error"):
        logger.critical("healthcheck.company_search.api_error", error=str(payload["error"]))
        return False

    companies = payload.get("companies")
    if not isinstance(companies, list) or not companies:
        logger.critical("healthcheck.company_search.empty", reason="no companies returned")
        return False

    for entry in companies:
        if not _validate_company_entry(entry, logger):
            return False

    count_value = payload.get("count")
    if not isinstance(count_value, int) or count_value <= 0:
        logger.critical("healthcheck.company_search.invalid_count", count=count_value)
        return False

    if expected_domain and not _check_domain_match(companies, expected_domain, logger):
        return False

    return True


def _validate_rating_payload(payload: Any, *, logger: BoundLogger) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.rating.invalid_response", reason=MSG_NOT_A_DICT)
        return False

    if payload.get("error"):
        logger.critical("healthcheck.rating.api_error", error=str(payload["error"]))
        return False

    required_fields = ("name", "domain", "current_rating", "top_findings", "legend")
    for field in required_fields:
        if payload.get(field) in (None, {}):
            logger.critical("healthcheck.rating.missing_field", field=field)
            return False

    current_rating = payload.get("current_rating")
    if not isinstance(current_rating, dict) or current_rating.get("value") is None:
        logger.critical("healthcheck.rating.invalid_current_rating", payload=current_rating)
        return False

    findings = payload.get("top_findings")
    if not isinstance(findings, dict):
        logger.critical("healthcheck.rating.invalid_findings", payload=findings)
        return False

    finding_count = findings.get("count")
    finding_entries = findings.get("findings")
    if not isinstance(finding_count, int) or finding_count <= 0:
        logger.critical("healthcheck.rating.no_findings", count=finding_count)
        return False
    if not isinstance(finding_entries, list) or not finding_entries:
        logger.critical("healthcheck.rating.empty_findings", payload=findings)
        return False

    legend = payload.get("legend")
    if not isinstance(legend, dict) or not legend.get("rating"):
        logger.critical("healthcheck.rating.missing_legend", payload=legend)
        return False

    return True


def _validate_company_search_interactive_payload(payload: Any, *, logger: BoundLogger) -> bool:
    if not isinstance(payload, dict):
        logger.critical(
            "healthcheck.company_search_interactive.invalid_response", reason=MSG_NOT_A_DICT
        )
        return False

    if payload.get("error"):
        logger.critical(
            "healthcheck.company_search_interactive.api_error",
            error=str(payload["error"]),
        )
        return False

    results = payload.get("results")
    if not isinstance(results, list) or not results:
        logger.critical(
            "healthcheck.company_search_interactive.empty_results",
            reason="no interactive results",
        )
        return False

    for entry in results:
        if not isinstance(entry, dict):
            logger.critical(
                "healthcheck.company_search_interactive.invalid_entry",
                reason="entry not dict",
            )
            return False
        required_keys = ("guid", "name", "primary_domain", "subscription")
        if any(not entry.get(key) for key in required_keys):
            logger.critical(
                "healthcheck.company_search_interactive.missing_fields",
                entry=entry,
            )
            return False
        subscription = entry.get("subscription")
        if not isinstance(subscription, dict) or "active" not in subscription:
            logger.critical(
                "healthcheck.company_search_interactive.invalid_subscription",
                subscription=subscription,
            )
            return False

    count_value = payload.get("count")
    if not isinstance(count_value, int) or count_value <= 0:
        logger.critical(
            "healthcheck.company_search_interactive.invalid_count",
            count=count_value,
        )
        return False

    guidance = payload.get("guidance")
    if not isinstance(guidance, dict):
        logger.critical("healthcheck.company_search_interactive.missing_guidance")
        return False

    return True


def _validate_manage_subscriptions_payload(
    payload: Any, *, logger: BoundLogger, expected_guid: str
) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.manage_subscriptions.invalid_response", reason=MSG_NOT_A_DICT)
        return False

    if payload.get("error"):
        logger.critical("healthcheck.manage_subscriptions.api_error", error=str(payload["error"]))
        return False

    status = payload.get("status")
    if status not in {"dry_run", "applied"}:
        logger.critical("healthcheck.manage_subscriptions.unexpected_status", status=status)
        return False

    guids = payload.get("guids")
    if not isinstance(guids, list) or expected_guid not in guids:
        logger.critical(
            "healthcheck.manage_subscriptions.guid_missing",
            guids=guids,
            expected=expected_guid,
        )
        return False

    if status == "dry_run":
        dry_payload = payload.get("payload")
        if not isinstance(dry_payload, dict) or "add" not in dry_payload:
            logger.critical(
                "healthcheck.manage_subscriptions.invalid_payload",
                payload=dry_payload,
            )
            return False

    return True


def _validate_request_company_payload(
    payload: Any, *, logger: BoundLogger, expected_domain: str
) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.request_company.invalid_response", reason=MSG_NOT_A_DICT)
        return False

    if payload.get("error"):
        logger.critical("healthcheck.request_company.api_error", error=str(payload["error"]))
        return False

    status = payload.get("status")
    if status not in {"dry_run", "already_requested"}:
        logger.critical("healthcheck.request_company.unexpected_status", status=status)
        return False

    domain_value = payload.get("domain")
    if not isinstance(domain_value, str) or domain_value.lower() != expected_domain.lower():
        logger.critical(
            "healthcheck.request_company.domain_mismatch",
            domain=domain_value,
            expected=expected_domain,
        )
        return False

    if status == "dry_run":
        dry_payload = payload.get("payload")
        if not isinstance(dry_payload, dict) or "file" not in dry_payload:
            logger.critical("healthcheck.request_company.invalid_payload", payload=dry_payload)
            return False
    else:
        requests = payload.get("requests")
        if not isinstance(requests, list):
            logger.critical(
                "healthcheck.request_company.invalid_requests",
                requests=requests,
            )
            return False

    return True





@app.command(help="Run BiRRe self tests without starting the FastMCP server.")
def selftest(  # NOSONAR python:S107
    config: cli_options.ConfigPathOption = Path(DEFAULT_CONFIG_FILENAME),  # NOSONAR
    bitsight_api_key: cli_options.BitsightApiKeyOption = None,
    subscription_folder: cli_options.SubscriptionFolderOption = None,
    subscription_type: cli_options.SubscriptionTypeOption = None,
    debug: cli_options.DebugOption = None,
    allow_insecure_tls: cli_options.AllowInsecureTlsOption = None,
    ca_bundle: cli_options.CaBundleOption = None,
    risk_vector_filter: cli_options.RiskVectorFilterOption = None,
    max_findings: cli_options.MaxFindingsOption = None,
    log_level: cli_options.LogLevelOption = None,
    log_format: cli_options.LogFormatOption = None,
    log_file: cli_options.LogFileOption = None,
    log_max_bytes: cli_options.LogMaxBytesOption = None,
    log_backup_count: cli_options.LogBackupCountOption = None,
    offline: cli_options.OfflineFlagOption = False,
    production: cli_options.ProductionFlagOption = False,
) -> None:
    """Execute BiRRe diagnostics and optional online checks."""

    invocation = build_invocation(
        config_path=str(config) if config is not None else None,
        api_key=bitsight_api_key,
        subscription_folder=subscription_folder,
        subscription_type=subscription_type,
        context=None,
        debug=debug,
        risk_vector_filter=risk_vector_filter,
        max_findings=max_findings,
        skip_startup_checks=True if offline else False,
        allow_insecure_tls=allow_insecure_tls,
        ca_bundle=ca_bundle,
        log_level=log_level,
        log_format=log_format,
        log_file=log_file,
        log_max_bytes=log_max_bytes,
        log_backup_count=log_backup_count,
    )

    runtime_settings, logging_settings, _ = resolve_runtime_and_logging(invocation)
    logger = initialize_logging(
        runtime_settings,
        logging_settings,
        show_banner=False,
        banner_printer=lambda: stderr_console.print(_banner()),
    )

    target_base_url = (
        HEALTHCHECK_PRODUCTION_V1_BASE_URL
        if production
        else HEALTHCHECK_TESTING_V1_BASE_URL
    )
    environment_label = "production" if production else "testing"
    logger.info(
        "Configured BitSight API environment",
        environment=environment_label,
        base_url=target_base_url,
    )
    if environment_label == "testing" and not offline:
        stdout_console.print(
            "[yellow]Note:[/yellow] BitSight's testing environment often returns "
            "[bold]HTTP 403[/bold] for subscription management tools even with valid credentials. "
            "This is expected for accounts without sandbox write access. "
            "Re-run with [green]--production[/green] to validate against the live API."
        )
    if offline:
        logger.info("Offline mode enabled; skipping online diagnostics")

    runner = HealthcheckRunner(
        runtime_settings=runtime_settings,
        logger=logger,
        offline=bool(offline),
        target_base_url=target_base_url,
        environment_label=environment_label,
        run_sync=await_sync,
        expected_tools_by_context=_EXPECTED_TOOLS_BY_CONTEXT,
    )
    result = runner.run()

    if ErrorCode.TLS_CERT_CHAIN_INTERCEPTED.value in result.alerts:
        stderr_console.print("[red]TLS interception detected.[/red]")
        stderr_console.print(
            "Set BIRRE_CA_BUNDLE or use --allow-insecure-tls"
        )

    _render_healthcheck_summary(result.summary)

    exit_code = result.exit_code()
    if exit_code == 1:
        logger.critical("Health checks failed")
        raise typer.Exit(code=1)
    if exit_code == 2:
        logger.warning(
            "Health checks completed with warnings",
            contexts=list(result.contexts),
            environment=environment_label,
        )
        raise typer.Exit(code=2)

    logger.info(
        "Health checks completed successfully",
        contexts=list(result.contexts),
        environment=environment_label,
    )


def _prompt_bool(prompt: str, default: bool) -> bool:
    return typer.confirm(prompt, default=default)


def _prompt_str(prompt: str, default: str | None, secret: bool = False) -> str | None:
    value = typer.prompt(prompt, default=default or "", hide_input=secret).strip()
    return value or None


def _validate_and_apply_normalizer(
    response: str | None, *, required: bool, normalizer: Callable[[str | None, str | None]] | None
) -> str | None:
    """Apply normalizer and validate the result."""
    def _apply(value: str | None) -> str | None:
        cleaned = cli_options.clean_string(value)
        if cleaned is None:
            return None
        if normalizer is None:
            return cleaned
        return normalizer(cleaned)

    try:
        normalized = _apply(response)
    except typer.BadParameter as exc:  # pragma: no cover - defensive; normalizer raises
        stdout_console.print(f"[red]{exc}[/red]")
        return None

    if normalized is None and required:
        stdout_console.print("[red]A value is required.[/red]")
        return None

    return normalized


def _collect_or_prompt_string(
    provided: str | None,
    *,
    prompt: str,
    default: str | None,
    secret: bool = False,
    required: bool = False,
    normalizer: Callable[[str | None, str | None]] | None = None,
) -> str | None:
    """Return a CLI-provided string or interactively prompt for one."""

    def _apply(value: str | None) -> str | None:
        cleaned = cli_options.clean_string(value)
        if cleaned is None:
            return None
        if normalizer is None:
            return cleaned
        return normalizer(cleaned)

    if provided is not None:
        return _apply(provided)

    while True:
        response = _prompt_str(prompt, default, secret=secret)
        if response is None:
            if required:
                stdout_console.print("[red]A value is required.[/red]")
                continue
            return None

        normalized = _validate_and_apply_normalizer(
            response, required=required, normalizer=normalizer
        )
        if normalized is not None or not required:
            return normalized


def _format_config_value(value: Any) -> str:
    """Format a single config value for TOML."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        formatted = ", ".join(_format_config_value(item) for item in value)
        return f"[{formatted}]"
    if value is None:
        return ""  # Should not be serialized
    escaped = str(value).replace("\\", "\\\\").replace("\"", "\\\"")
    return f'"{escaped}"'


def _format_config_section(section: str, section_values: dict[str, Any]) -> list[str]:
    """Format a single config section."""
    if not isinstance(section_values, dict) or not section_values:
        return []
    
    lines = ["", f"[{section}]"]
    for key, entry in sorted(section_values.items()):
        if entry is None:
            continue
        if isinstance(entry, str) and not entry.strip():
            continue
        lines.append(f"{key} = {_format_config_value(entry)}")
    return lines


def _generate_local_config_content(values: dict[str, Any], *, include_header: bool = True) -> str:
    lines: list[str] = []
    if include_header:
        lines.append("## Generated local configuration")

    for section, section_values in sorted(values.items()):
        lines.extend(_format_config_section(section, section_values))
    
    lines.append("")
    return "\n".join(lines)


def _determine_value_source(value, default_value, normalizer):
    """Determine the source of a prompted value (Default vs User Input)."""
    if default_value and value == default_value:
        return "Default"
    
    normalized_default = (
        normalizer(default_value) if normalizer and default_value else None
    )
    normalized_value = normalizer(value) if normalizer else value
    
    if normalized_default and normalized_value == normalized_default:
        return "Default"
    return SOURCE_USER_INPUT


def _prompt_and_record_string(
    cli_value,
    prompt_text,
    default_value,
    summary_rows,
    config_key,
    *,
    normalizer=None,
    secret=False,
    required=False,
    cli_source="CLI Option",
):
    """Prompt for a string value and add to summary if provided."""
    if cli_value is not None:
        value = cli_value
        source = cli_source
    else:
        value = _collect_or_prompt_string(
            None,
            prompt=prompt_text,
            default=default_value,
            secret=secret,
            required=required,
            normalizer=normalizer,
        )
        if value is not None:
            source = _determine_value_source(value, default_value, normalizer)
        else:
            return None
    
    if value and value not in (None, ""):
        display_value = _format_display_value(config_key, value)
        summary_rows.append((config_key, display_value, source))
    return value


def _prompt_and_record_bool(
    cli_value,
    prompt_text,
    default_value,
    summary_rows,
    config_key,
):
    """Prompt for a boolean value and add to summary."""
    if cli_value is not None:
        value = cli_value
        source = "CLI Option"
    else:
        value = _prompt_bool(prompt_text, default=default_value)
        source = "Default" if value == default_value else SOURCE_USER_INPUT
    
    display_value = _format_display_value(config_key, value)
    summary_rows.append((config_key, display_value, source))
    return value


def _check_overwrite_destination(destination, overwrite):
    """Check if destination exists and handle overwrite logic."""
    if not destination.exists():
        return
    
    if overwrite:
        stdout_console.print(
            f"[yellow]Overwriting existing configuration at[/yellow] {destination}"
        )
    else:
        stdout_console.print(f"[yellow]{destination} already exists.[/yellow]")
        if not typer.confirm("Overwrite this file?", default=False):
            stdout_console.print(
                "[red]Aborted without changing the existing configuration.[/red]"
            )
            raise typer.Exit(code=1)


def _display_config_preview(summary_rows):
    """Display configuration preview table."""
    if not summary_rows:
        return
    
    summary_rows.sort(key=lambda entry: entry[0])
    preview = Table(title="Local configuration preview")
    preview.add_column("Config Key", style=_RichStyles.ACCENT)
    preview.add_column("Value", style=_RichStyles.SECONDARY)
    preview.add_column("Source", style=_RichStyles.SUCCESS)
    for dotted_key, display_value, source in summary_rows:
        preview.add_row(dotted_key, display_value, source)
    stdout_console.print()
    stdout_console.print(preview)


@config_app.command(
    "init",
    help="Interactively create or update a local BiRRe configuration file.",
)
def config_init(
    output: cli_options.LocalConfOutputOption = Path(LOCAL_CONFIG_FILENAME),
    config_path: cli_options.ConfigPathOption = Path(LOCAL_CONFIG_FILENAME),
    subscription_type: cli_options.SubscriptionTypeOption = None,
    debug: cli_options.DebugOption = None,
    overwrite: cli_options.OverwriteOption = False,
) -> None:
    """Guide the user through generating a configuration file."""

    ctx = click.get_current_context()
    config_source = ctx.get_parameter_source("config_path")
    destination = Path(config_path if config_source is ParameterSource.COMMANDLINE else output)

    _check_overwrite_destination(destination, overwrite)

    defaults_settings = load_settings(
        str(config_path) if config_source is ParameterSource.COMMANDLINE else None
    )
    default_subscription_folder = defaults_settings.get(BITSIGHT_SUBSCRIPTION_FOLDER_KEY)
    default_subscription_type = defaults_settings.get(BITSIGHT_SUBSCRIPTION_TYPE_KEY)
    default_context = defaults_settings.get(ROLE_CONTEXT_KEY, "standard")
    default_debug = bool(defaults_settings.get(RUNTIME_DEBUG_KEY, False))

    summary_rows: list[tuple[str, str, str]] = []

    stdout_console.print("[bold]BiRRe local configuration generator[/bold]")

    api_key = _collect_or_prompt_string(
        None,
        prompt="BitSight API key",
        default=None,
        secret=True,
        required=True,
    )
    if api_key:
        display_value = _format_display_value(BITSIGHT_API_KEY_KEY, api_key)
        summary_rows.append((BITSIGHT_API_KEY_KEY, display_value, SOURCE_USER_INPUT))

    subscription_folder = _prompt_and_record_string(
        None,
        "Default subscription folder",
        str(default_subscription_folder) if default_subscription_folder else "",
        summary_rows,
        BITSIGHT_SUBSCRIPTION_FOLDER_KEY,
    )

    subscription_type_value = _prompt_and_record_string(
        subscription_type,
        "Default subscription type",
        str(default_subscription_type) if default_subscription_type else "",
        summary_rows,
        BITSIGHT_SUBSCRIPTION_TYPE_KEY,
    )

    context_value = _prompt_and_record_string(
        None,
        "Default persona (standard or risk_manager)",
        str(default_context or "standard"),
        summary_rows,
        ROLE_CONTEXT_KEY,
        normalizer=lambda value: cli_options.normalize_context(value, choices=CONTEXT_CHOICES),
    )

    debug_value = _prompt_and_record_bool(
        debug,
        "Enable debug mode?",
        default_debug,
        summary_rows,
        RUNTIME_DEBUG_KEY,
    )

    generated = {
        "bitsight": {
            "api_key": api_key,
            "subscription_folder": subscription_folder,
            "subscription_type": subscription_type_value,
        },
        "runtime": {
            "debug": debug_value,
        },
        "roles": {
            "context": context_value,
        },
    }

    serializable: dict[str, dict[str, Any]] = {}
    for section, section_values in generated.items():
        filtered = {k: v for k, v in section_values.items() if v not in (None, "")}
        if filtered:
            serializable[section] = filtered

    if not serializable:
        stdout_console.print(
            "[red]No values provided; aborting local configuration generation.[/red]"
        )
        raise typer.Exit(code=1)

    _display_config_preview(summary_rows)

    content = _generate_local_config_content(serializable)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        destination.write_text(content, encoding="utf-8")
    except OSError as error:
        stdout_console.print(
            f"[red]Failed to write configuration:[/red] {error}"
        )
        raise typer.Exit(code=1) from error

    stdout_console.print(f"[green]Local configuration saved to[/green] {destination}")


def _resolve_settings_files(config_path: str | None) -> tuple[Path, ...]:
    return resolve_config_file_candidates(config_path)


def _resolve_logging_settings_from_cli(
    *,
    config_path: Path | None,
    log_level: str | None,
    log_format: str | None,
    log_file: str | None,
    log_max_bytes: int | None,
    log_backup_count: int | None,
) -> tuple[CliInvocation, Any]:
    invocation = build_invocation(
        config_path=str(config_path) if config_path is not None else None,
        api_key=None,
        subscription_folder=None,
        subscription_type=None,
        context=None,
        debug=None,
        risk_vector_filter=None,
        max_findings=None,
        skip_startup_checks=None,
        allow_insecure_tls=None,
        ca_bundle=None,
        log_level=log_level,
        log_format=log_format,
        log_file=log_file,
        log_max_bytes=log_max_bytes,
        log_backup_count=log_backup_count,
    )
    _, logging_settings, _ = resolve_runtime_and_logging(invocation)
    return invocation, logging_settings


_RELATIVE_DURATION_PATTERN = re.compile(r"^\s*(\d+)([smhd])\s*$", re.IGNORECASE)


def _parse_iso_timestamp_to_epoch(value: str) -> float | None:
    if value is None:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.timestamp()


def _parse_relative_duration(value: str) -> timedelta | None:
    if value is None:
        return None
    match = _RELATIVE_DURATION_PATTERN.match(value)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2).lower()
    multiplier = {
        "s": timedelta(seconds=1),
        "m": timedelta(minutes=1),
        "h": timedelta(hours=1),
        "d": timedelta(days=1),
    }.get(unit)
    if multiplier is None:
        return None
    return multiplier * amount


def _parse_json_log_line(stripped: str) -> LogViewLine:
    """Parse a JSON-formatted log line."""
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return LogViewLine(raw=stripped, level=None, timestamp=None, json_data=None)

    timestamp = None
    for key in ("timestamp", "time", "@timestamp", "ts"):
        value = data.get(key)
        if isinstance(value, str):
            timestamp = _parse_iso_timestamp_to_epoch(value)
            if timestamp is not None:
                break

    level_value = data.get("level") or data.get("levelname") or data.get("severity")
    if isinstance(level_value, str):
        level = cli_options.LOG_LEVEL_MAP.get(level_value.strip().upper())
    elif isinstance(level_value, int):
        level = level_value
    else:
        level = None

    return LogViewLine(raw=stripped, level=level, timestamp=timestamp, json_data=data)


def _parse_text_log_line(stripped: str) -> LogViewLine:
    """Parse a text-formatted log line."""
    timestamp = None
    level = None
    tokens = stripped.split()
    
    if tokens:
        timestamp = _parse_iso_timestamp_to_epoch(tokens[0].strip("[]"))
        for token in tokens[:3]:
            candidate = cli_options.LOG_LEVEL_MAP.get(token.strip("[]:,").upper())
            if candidate is not None:
                level = candidate
                break
    
    return LogViewLine(raw=stripped, level=level, timestamp=timestamp, json_data=None)


def _parse_log_line(line: str, format_hint: str) -> LogViewLine:
    stripped = line.rstrip("\n")
    if format_hint == "json":
        return _parse_json_log_line(stripped)
    return _parse_text_log_line(stripped)


@config_app.command(
    "show",
    help=(
        "Inspect configuration sources and resolved settings.\n\n"
        "Example: uv run birre config show --config custom.toml"
    ),
)
def config_show(  # NOSONAR python:S107
    config: cli_options.ConfigPathOption = Path(DEFAULT_CONFIG_FILENAME),  # NOSONAR
    bitsight_api_key: cli_options.BitsightApiKeyOption = None,
    subscription_folder: cli_options.SubscriptionFolderOption = None,
    subscription_type: cli_options.SubscriptionTypeOption = None,
    context: cli_options.ContextOption = None,
    debug: cli_options.DebugOption = None,
    allow_insecure_tls: cli_options.AllowInsecureTlsOption = None,
    ca_bundle: cli_options.CaBundleOption = None,
    risk_vector_filter: cli_options.RiskVectorFilterOption = None,
    max_findings: cli_options.MaxFindingsOption = None,
    log_level: cli_options.LogLevelOption = None,
    log_format: cli_options.LogFormatOption = None,
    log_file: cli_options.LogFileOption = None,
    log_max_bytes: cli_options.LogMaxBytesOption = None,
    log_backup_count: cli_options.LogBackupCountOption = None,
) -> None:
    """Display configuration files, overrides, and effective values as Rich tables."""
    invocation = build_invocation(
        config_path=str(config) if config is not None else None,
        api_key=bitsight_api_key,
        subscription_folder=subscription_folder,
        subscription_type=subscription_type,
        context=context,
        debug=debug,
        risk_vector_filter=risk_vector_filter,
        max_findings=max_findings,
        skip_startup_checks=None,
        allow_insecure_tls=allow_insecure_tls,
        ca_bundle=ca_bundle,
        log_level=log_level,
        log_format=log_format,
        log_file=log_file,
        log_max_bytes=log_max_bytes,
        log_backup_count=log_backup_count,
    )

    runtime_settings, logging_settings, _ = resolve_runtime_and_logging(invocation)
    files = _resolve_settings_files(invocation.config_path)

    config_entries = _collect_config_file_entries(files)

    files_table = Table(title="Configuration files", box=box.SIMPLE_HEAVY)
    files_table.add_column("File", style=_RichStyles.ACCENT)
    files_table.add_column("Status", style=_RichStyles.SECONDARY)
    for file in files:
        status = "exists" if file.exists() else "missing"
        files_table.add_row(str(file), status)
    stdout_console.print(files_table)

    env_overrides = {
        name: os.getenv(name)
        for name in (
            "BIRRE_CONFIG",
            "BITSIGHT_API_KEY",
            "BIRRE_SUBSCRIPTION_FOLDER",
            "BIRRE_SUBSCRIPTION_TYPE",
            "BIRRE_CONTEXT",
            "BIRRE_RISK_VECTOR_FILTER",
            "BIRRE_MAX_FINDINGS",
            "BIRRE_SKIP_STARTUP_CHECKS",
            "BIRRE_DEBUG",
            "BIRRE_ALLOW_INSECURE_TLS",
            "BIRRE_CA_BUNDLE",
            "BIRRE_LOG_LEVEL",
            "BIRRE_LOG_FORMAT",
            "BIRRE_LOG_FILE",
            "BIRRE_LOG_MAX_BYTES",
            "BIRRE_LOG_BACKUP_COUNT",
        )
        if os.getenv(name) is not None
    }
    env_labels = _build_env_source_labels(env_overrides)
    env_rows = list(_build_env_override_rows(env_overrides))
    if env_rows:
        stdout_console.print()
        _print_config_table("Environment overrides", env_rows)

    cli_labels = {
        key: label
        for key, label in _build_cli_source_labels(invocation).items()
        if key not in env_labels
    }
    cli_rows = [row for row in _build_cli_override_rows(invocation) if row[0] not in env_labels]
    if cli_rows:
        stdout_console.print()
        _print_config_table("CLI overrides", cli_rows)

    effective_values = _effective_configuration_values(runtime_settings, logging_settings)
    effective_rows: list[tuple[str, str, str]] = []
    for key in _EFFECTIVE_CONFIG_KEY_ORDER:
        display_value = _format_display_value(key, effective_values.get(key))
        source_label = _determine_source_label(key, cli_labels, env_labels, config_entries)
        effective_rows.append((key, display_value, source_label))

    stdout_console.print()
    _print_config_table("Effective configuration", effective_rows)


@config_app.command(
    "validate",
    help="Validate or minimize a BiRRe configuration file before use.",
)
def config_validate(
    config: Path | None = typer.Option(
        None,
        "--config",
        help="Configuration TOML file to validate",
        envvar="BIRRE_CONFIG",
        show_envvar=True,
        rich_help_panel="Configuration",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
    debug: cli_options.DebugOption = None,
    minimize: cli_options.MinimizeOption = False,
) -> None:
    """Validate configuration syntax and optionally rewrite it in minimal form."""
    ctx = click.get_current_context()
    config_source = ctx.get_parameter_source("config")
    if config is None and config_source is ParameterSource.DEFAULT:
        typer.echo(ctx.get_help())
        raise typer.Exit()
    if config is None:
        raise typer.BadParameter(
            "Configuration path could not be determined.", param_hint="--config"
        )

    if not config.exists():
        raise typer.BadParameter(f"{config} does not exist", param_hint="--config")

    import tomllib

    try:
        with config.open("rb") as handle:
            parsed = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise typer.BadParameter(f"Invalid TOML: {exc}") from exc

    allowed_sections = {"bitsight", "runtime", "roles", "logging"}
    warnings: list[str] = []
    for section in parsed:
        if section not in allowed_sections:
            warnings.append(f"Unknown section '{section}' will be ignored by BiRRe")

    stdout_console.print(f"[green]TOML parsing succeeded[/green] for {config}")
    if warnings:
        stdout_console.print("[yellow]Warnings:[/yellow]")
        for warning in warnings:
            stdout_console.print(f"- {warning}")

    if debug:
        stdout_console.print("\n[bold]Parsed data[/bold]")
        stdout_console.print(parsed)

    if minimize:
        minimized = _generate_local_config_content(parsed, include_header=False)
        backup_path = config.with_suffix(f"{config.suffix}.bak")
        shutil.copy2(config, backup_path)
        config.write_text(minimized, encoding="utf-8")
        stdout_console.print(
            f"[green]Minimized configuration written to[/green] {config} "
            f"[dim](backup: {backup_path})[/dim]"
        )


def _rotate_logs(base_path: Path, backup_count: int) -> None:
    if backup_count <= 0:
        base_path.write_text("", encoding="utf-8")
        return

    for index in range(backup_count, 0, -1):
        source = base_path.with_name(f"{base_path.name}.{index}")
        target = base_path.with_name(f"{base_path.name}.{index + 1}")
        if source.exists():
            source.replace(target)

    if base_path.exists():
        base_path.replace(base_path.with_name(f"{base_path.name}.1"))
    base_path.touch()


@logs_app.command(
    "clear",
    help="Truncate the active BiRRe log file while leaving rotated archives untouched.",
)
def logs_clear(
    config: cli_options.ConfigPathOption = Path(DEFAULT_CONFIG_FILENAME),
    log_file: cli_options.LogFileOption = None,
) -> None:
    """Truncate the resolved log file."""
    _, logging_settings = _resolve_logging_settings_from_cli(
        config_path=config,
        log_level=None,
        log_format=None,
        log_file=log_file,
        log_max_bytes=None,
        log_backup_count=None,
    )
    file_path = getattr(logging_settings, "file_path", None)
    if not file_path:
        stdout_console.print("[yellow]File logging is disabled; nothing to clear[/yellow]")
        return

    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text("", encoding="utf-8")
    except OSError as exc:
        raise typer.BadParameter(f"Failed to clear log file: {exc}") from exc
    stdout_console.print(f"[green]Log file cleared at[/green] {path}")


@logs_app.command(
    "rotate",
    help="Perform a manual log rotation using the configured backup count.",
)
def logs_rotate(
    config: cli_options.ConfigPathOption = Path(DEFAULT_CONFIG_FILENAME),
    log_file: cli_options.LogFileOption = None,
    log_backup_count: cli_options.LogBackupCountOption = None,
) -> None:
    """Rotate the active log file into numbered archives."""
    _, logging_settings = _resolve_logging_settings_from_cli(
        config_path=config,
        log_level=None,
        log_format=None,
        log_file=log_file,
        log_max_bytes=None,
        log_backup_count=log_backup_count,
    )
    file_path = getattr(logging_settings, "file_path", None)
    if not file_path:
        stdout_console.print("[yellow]File logging is disabled; nothing to rotate[/yellow]")
        return

    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_count = (
        log_backup_count
        if log_backup_count is not None
        else getattr(logging_settings, "backup_count", 0) or 0
    )
    _rotate_logs(path, backup_count)
    stdout_console.print(f"[green]Log files rotated at[/green] {path}")


@logs_app.command(
    "path",
    help="Show the resolved BiRRe log file path after applying configuration overrides.",
)
def logs_path(
    config: cli_options.ConfigPathOption = Path(DEFAULT_CONFIG_FILENAME),
    log_file: cli_options.LogFileOption = None,
) -> None:
    """Print the effective log file path."""
    _, logging_settings = _resolve_logging_settings_from_cli(
        config_path=config,
        log_level=None,
        log_format=None,
        log_file=log_file,
        log_max_bytes=None,
        log_backup_count=None,
    )
    file_path = getattr(logging_settings, "file_path", None)
    if not file_path:
        stdout_console.print("[yellow]File logging is disabled[/yellow]")
        return
    resolved = Path(file_path)
    absolute = resolved.expanduser()
    try:
        absolute = absolute.resolve(strict=False)
    except OSError:
        absolute = absolute.absolute()

    stdout_console.print(f"[green]Log file (relative)[/green]: {resolved}")
    stdout_console.print(f"[green]Log file (absolute)[/green]: {absolute}")




def _validate_logs_show_params(
    tail: int,
    since: str | None,
    last: str | None,
    format_override: str | None,
) -> str | None:
    """Validate logs_show parameters. Returns normalized format or None."""
    if tail < 0:
        raise typer.BadParameter(
            "Tail must be greater than or equal to zero.", param_hint="--tail"
        )
    if since and last:
        raise typer.BadParameter(
            "Only one of --since or --last can be provided.", param_hint="--since"
        )
    
    if format_override is not None:
        normalized = format_override.strip().lower()
        if normalized not in cli_options.LOG_FORMAT_CHOICES:
            raise typer.BadParameter(
                "Format must be either 'text' or 'json'.", param_hint="--format"
            )
        return normalized
    return None


def _resolve_start_timestamp(since: str | None, last: str | None) -> float | None:
    """Calculate start timestamp from --since or --last options."""
    if since:
        timestamp = _parse_iso_timestamp_to_epoch(since)
        if timestamp is None:
            raise typer.BadParameter(
                "Invalid ISO 8601 timestamp.", param_hint="--since"
            )
        return timestamp
    
    if last:
        duration = _parse_relative_duration(last)
        if duration is None:
            raise typer.BadParameter(
                "Invalid relative duration; use values like 30m, 1h, or 2d.",
                param_hint="--last",
            )
        return (datetime.now(timezone.utc) - duration).timestamp()
    
    return None


def _should_include_log_entry(
    parsed: LogViewLine,
    level_threshold: int | None,
    normalized_level: str | None,
    start_timestamp: float | None,
) -> bool:
    """Check if log entry passes level and timestamp filters."""
    if level_threshold is not None:
        if parsed.level is not None:
            if parsed.level < level_threshold:
                return False
        else:
            if normalized_level not in parsed.raw.upper():
                return False
    
    if start_timestamp is not None:
        if parsed.timestamp is None or parsed.timestamp < start_timestamp:
            return False
    
    return True


def _display_log_entries(
    matched: list[LogViewLine],
    resolved_format: str,
) -> None:
    """Display filtered log entries to stdout."""
    if not matched:
        stdout_console.print(
            "[yellow]No log entries matched the supplied filters[/yellow]"
        )
        return
    
    for entry in matched:
        if resolved_format == "json" and entry.json_data is not None:
            stdout_console.print_json(data=entry.json_data)
        else:
            stdout_console.print(entry.raw, markup=False, highlight=False)


@logs_app.command(
    "show",
    help="Display recent log entries with optional level and time filtering.",
)
def logs_show(
    config: cli_options.ConfigPathOption = Path(DEFAULT_CONFIG_FILENAME),
    log_file: cli_options.LogFileOption = None,
    level: str | None = typer.Option(
        None,
        "--level",
        help="Minimum log level to include (e.g. INFO, WARNING).",
        rich_help_panel="Filtering",
    ),
    tail: int = typer.Option(
        100,
        "--tail",
        help="Number of lines from the end of the log to display (0 to show all).",
        rich_help_panel="Filtering",
    ),
    since: str | None = typer.Option(
        None,
        "--since",
        help="Only include entries at or after the given ISO 8601 timestamp.",
        rich_help_panel="Filtering",
    ),
    last: str | None = typer.Option(
        None,
        "--last",
        help="Only include entries from the relative window (e.g. 1h, 30m).",
        rich_help_panel="Filtering",
    ),
    format_override: str | None = typer.Option(
        None,
        "--format",
        case_sensitive=False,
        help="Treat log entries as 'json' or 'text'. Defaults to the configured format.",
        rich_help_panel="Presentation",
    ),
) -> None:
    """Render log entries to stdout."""
    normalized_format = _validate_logs_show_params(tail, since, last, format_override)
    
    normalized_level = cli_options.normalize_log_level(level) if level is not None else None
    level_threshold = cli_options.LOG_LEVEL_MAP.get(normalized_level) if normalized_level else None

    _, logging_settings = _resolve_logging_settings_from_cli(
        config_path=config,
        log_level=None,
        log_format=None,
        log_file=log_file,
        log_max_bytes=None,
        log_backup_count=None,
    )
    file_path = getattr(logging_settings, "file_path", None)
    resolved_format = normalized_format or getattr(logging_settings, "format", None) or "text"

    if not file_path:
        stdout_console.print("[yellow]File logging is disabled; nothing to show[/yellow]")
        return

    path = Path(file_path)
    if not path.exists():
        stdout_console.print(f"[yellow]Log file not found at[/yellow] {path}")
        return

    start_timestamp = _resolve_start_timestamp(since, last)

    matched: list[LogViewLine] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            parsed = _parse_log_line(line, resolved_format)
            if _should_include_log_entry(
                parsed, level_threshold, normalized_level, start_timestamp
            ):
                matched.append(parsed)

    if tail and tail > 0:
        matched = matched[-tail:]

    _display_log_entries(matched, resolved_format)


@app.command(help="Show the installed BiRRe package version.")
def version() -> None:
    """Print the BiRRe version discovered from the package metadata."""
    from importlib import metadata

    try:
        resolved_version = metadata.version("BiRRe")
    except metadata.PackageNotFoundError:
        pyproject = PROJECT_ROOT / "pyproject.toml"
        if not pyproject.exists():
            stdout_console.print("Version information unavailable")
            return
        import tomllib

        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        resolved_version = data.get("project", {}).get("version", "unknown")
    stdout_console.print(resolved_version)


@app.command(help="Print the BiRRe README to standard output.")
def readme() -> None:
    """Display the project README for quick reference."""
    readme_path = PROJECT_ROOT / "README.md"
    if not readme_path.exists():
        raise typer.BadParameter("README.md not found in project root")
    stdout_console.print(readme_path.read_text(encoding="utf-8"))


def main(argv: Sequence[str | None] = None) -> None:
    """Main entry point for BiRRe MCP server."""

    args = list(sys.argv[1:] if argv is None else argv)
    command = get_command(app)
    if not args:
        command.main(args=["run"], prog_name=_CLI_PROG_NAME)
        return

    if args[0] in {"-h", "--help"}:
        command.main(args=args, prog_name=_CLI_PROG_NAME)
        return

    if args[0].startswith("-"):
        command.main(args=["run", *args], prog_name=_CLI_PROG_NAME)
    else:
        command.main(args=args, prog_name=_CLI_PROG_NAME)


if __name__ == "__main__":
    main()
