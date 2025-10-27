"""BiRRe FastMCP server Typer CLI entrypoint."""

from __future__ import annotations

import asyncio
import atexit
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
import threading
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from datetime import datetime, timedelta, timezone
from contextlib import suppress
from typing import (
    Annotated,
    Any,
    Awaitable,
    Callable,
    Dict,
    Final,
    FrozenSet,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
)

import click
import httpx
from uuid import uuid4
from click.core import ParameterSource

import typer
from rich.console import Console
from rich import box
from rich.table import Table
from rich.text import Text
from typer.main import get_command

# FastMCP checks this flag during import time, so ensure it is enabled before
# importing any modules that depend on FastMCP.
os.environ["FASTMCP_EXPERIMENTAL_ENABLE_NEW_OPENAPI_PARSER"] = "true"

from src.apis.clients import DEFAULT_V1_API_BASE_URL, create_v1_api_server
from src.apis.v1_bridge import call_v1_openapi_tool
from src.birre import create_birre_server, _resolve_tls_verification
from src.constants import DEFAULT_CONFIG_FILENAME, LOCAL_CONFIG_FILENAME
from src.errors import BirreError, ErrorCode, TlsCertificateChainInterceptedError
from src.logging import BoundLogger, configure_logging, get_logger
from src.settings import (
    BITSIGHT_API_KEY_KEY,
    BITSIGHT_SUBSCRIPTION_FOLDER_KEY,
    BITSIGHT_SUBSCRIPTION_TYPE_KEY,
    LOGGING_BACKUP_COUNT_KEY,
    LOGGING_FILE_KEY,
    LOGGING_FORMAT_KEY,
    LOGGING_LEVEL_KEY,
    LOGGING_MAX_BYTES_KEY,
    LoggingInputs,
    ROLE_CONTEXT_KEY,
    ROLE_MAX_FINDINGS_KEY,
    ROLE_RISK_VECTOR_FILTER_KEY,
    RuntimeInputs,
    RUNTIME_ALLOW_INSECURE_TLS_KEY,
    RUNTIME_CA_BUNDLE_PATH_KEY,
    RUNTIME_DEBUG_KEY,
    RUNTIME_SKIP_STARTUP_CHECKS_KEY,
    SubscriptionInputs,
    TlsInputs,
    apply_cli_overrides,
    is_logfile_disabled_value,
    load_settings,
    logging_from_settings,
    resolve_config_file_candidates,
    runtime_from_settings,
)
from src.startup_checks import run_offline_startup_checks, run_online_startup_checks

PROJECT_ROOT = Path(__file__).resolve().parent

stderr_console = Console(stderr=True)
stdout_console = Console(stderr=False)

_loop_logger = logging.getLogger("birre.loop")

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
_CONTEXT_CHOICES = {"standard", "risk_manager"}
_LOG_FORMAT_CHOICES = {"text", "json"}
_LOG_LEVEL_CHOICES = sorted(
    name
    for name, value in logging.getLevelNamesMapping().items()
    if isinstance(name, str) and not name.isdigit()
)
_LOG_LEVEL_SET = {choice.upper() for choice in _LOG_LEVEL_CHOICES}
_LOG_LEVEL_MAP = {
    name.upper(): value
    for name, value in logging.getLevelNamesMapping().items()
    if isinstance(name, str) and not name.isdigit()
}

_SENSITIVE_KEY_PATTERNS = ("api_key", "secret", "token", "password")

SOURCE_USER_INPUT: Final = "User Input"

HEALTHCHECK_TESTING_V1_BASE_URL = "https://service.bitsighttech.com/customer-api/v1/"
HEALTHCHECK_PRODUCTION_V1_BASE_URL = DEFAULT_V1_API_BASE_URL

_HEALTHCHECK_COMPANY_NAME: Final = "GitHub"
_HEALTHCHECK_COMPANY_DOMAIN: Final = "github.com"
_HEALTHCHECK_COMPANY_GUID: Final = "6ca077e2-b5a7-42c2-ae1e-a974c3a91dc1"
_HEALTHCHECK_REQUEST_DOMAIN: Final = "healthcheck-birre-example.com"

_EXPECTED_TOOLS_BY_CONTEXT: Dict[str, FrozenSet[str]] = {
    "standard": frozenset({"company_search", "get_company_rating"}),
    "risk_manager": frozenset(
        {
            "company_search",
            "company_search_interactive",
            "get_company_rating",
            "manage_subscriptions",
            "request_company",
        }
    ),
}


# Reusable option annotations -------------------------------------------------

ConfigPathOption = Annotated[
    Path,
    typer.Option(
        "--config",
        help="Path to a configuration TOML file to load",
        envvar="BIRRE_CONFIG",
        show_envvar=True,
        rich_help_panel="Configuration",
    ),
]

BitsightApiKeyOption = Annotated[
    Optional[str],
    typer.Option(
        "--bitsight-api-key",
        help="BitSight API key (overrides BITSIGHT_API_KEY env var)",
        envvar="BITSIGHT_API_KEY",
        show_envvar=True,
        rich_help_panel="Authentication",
    ),
]

SubscriptionFolderOption = Annotated[
    Optional[str],
    typer.Option(
        "--subscription-folder",
        help="BitSight subscription folder override",
        envvar="BIRRE_SUBSCRIPTION_FOLDER",
        show_envvar=True,
        rich_help_panel="Runtime",
    ),
]

SubscriptionTypeOption = Annotated[
    Optional[str],
    typer.Option(
        "--subscription-type",
        help="BitSight subscription type override",
        envvar="BIRRE_SUBSCRIPTION_TYPE",
        show_envvar=True,
        rich_help_panel="Runtime",
    ),
]

SkipStartupChecksOption = Annotated[
    Optional[bool],
    typer.Option(
        "--skip-startup-checks/--require-startup-checks",
        help="Skip BitSight online startup checks (use --require-startup-checks to override any configured skip)",
        envvar="BIRRE_SKIP_STARTUP_CHECKS",
        show_envvar=True,
        rich_help_panel="Runtime",
    ),
]

DebugOption = Annotated[
    Optional[bool],
    typer.Option(
        "--debug/--no-debug",
        help="Enable verbose diagnostics",
        envvar="BIRRE_DEBUG",
        show_envvar=True,
        rich_help_panel="Diagnostics",
    ),
]

AllowInsecureTlsOption = Annotated[
    Optional[bool],
    typer.Option(
        "--allow-insecure-tls/--enforce-tls",
        help="Disable TLS verification when contacting BitSight",
        envvar="BIRRE_ALLOW_INSECURE_TLS",
        show_envvar=True,
        rich_help_panel="TLS",
    ),
]

CaBundleOption = Annotated[
    Optional[str],
    typer.Option(
        "--ca-bundle",
        help="Path to a custom certificate authority bundle",
        envvar="BIRRE_CA_BUNDLE",
        show_envvar=True,
        rich_help_panel="TLS",
    ),
]

ContextOption = Annotated[
    Optional[str],
    typer.Option(
        "--context",
        help="Tool persona to expose (standard or risk_manager)",
        envvar="BIRRE_CONTEXT",
        show_envvar=True,
        rich_help_panel="Runtime",
    ),
]

RiskVectorFilterOption = Annotated[
    Optional[str],
    typer.Option(
        "--risk-vector-filter",
        help="Comma separated list of BitSight risk vectors",
        envvar="BIRRE_RISK_VECTOR_FILTER",
        show_envvar=True,
        rich_help_panel="Runtime",
    ),
]

MaxFindingsOption = Annotated[
    Optional[int],
    typer.Option(
        "--max-findings",
        min=1,
        help="Maximum number of findings to surface per company",
        envvar="BIRRE_MAX_FINDINGS",
        show_envvar=True,
        rich_help_panel="Runtime",
    ),
]

LogLevelOption = Annotated[
    Optional[str],
    typer.Option(
        "--log-level",
        help="Logging level (e.g. INFO, DEBUG)",
        envvar="BIRRE_LOG_LEVEL",
        show_envvar=True,
        rich_help_panel="Logging",
    ),
]

LogFormatOption = Annotated[
    Optional[str],
    typer.Option(
        "--log-format",
        help="Logging format (text or json)",
        envvar="BIRRE_LOG_FORMAT",
        show_envvar=True,
        rich_help_panel="Logging",
    ),
]

LogFileOption = Annotated[
    Optional[str],
    typer.Option(
        "--log-file",
        help="Path to a log file (use '-', none, stderr, or stdout to disable)",
        envvar="BIRRE_LOG_FILE",
        show_envvar=True,
        rich_help_panel="Logging",
    ),
]

LogMaxBytesOption = Annotated[
    Optional[int],
    typer.Option(
        "--log-max-bytes",
        min=1,
        help="Maximum size in bytes for rotating log files",
        envvar="BIRRE_LOG_MAX_BYTES",
        show_envvar=True,
        rich_help_panel="Logging",
    ),
]

LogBackupCountOption = Annotated[
    Optional[int],
    typer.Option(
        "--log-backup-count",
        min=1,
        help="Number of rotating log file backups to retain",
        envvar="BIRRE_LOG_BACKUP_COUNT",
        show_envvar=True,
        rich_help_panel="Logging",
    ),
]

ProfilePathOption = Annotated[
    Optional[Path],
    typer.Option(
        "--profile",
        help="Write Python profiling data to the provided path",
        rich_help_panel="Diagnostics",
    ),
]

OfflineFlagOption = Annotated[
    bool,
    typer.Option(
        "--offline/--online",
        help="Skip BitSight network checks and run offline validation only",
        rich_help_panel="Diagnostics",
    ),
]

ProductionFlagOption = Annotated[
    bool,
    typer.Option(
        "--production/--testing",
        help="Use the BitSight production API for online validation",
        rich_help_panel="Diagnostics",
    ),
]

LocalConfOutputOption = Annotated[
    Path,
    typer.Option(
        "--output",
        help="Destination local config file",
    ),
]

OverwriteOption = Annotated[
    bool,
    typer.Option(
        "--overwrite/--no-overwrite",
        help="Allow overwriting an existing local configuration file",
    ),
]

MinimizeOption = Annotated[
    bool,
    typer.Option(
        "--minimize/--no-minimize",
        help="Rewrite the configuration file with a minimal canonical layout",
    ),
]
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
    elif isinstance(value, (int, float)):
        text = str(value)
    elif isinstance(value, Path):
        text = str(value)
    else:
        text = str(value)

    if any(pattern in lowered_key for pattern in _SENSITIVE_KEY_PATTERNS):
        original = value if isinstance(value, str) else text
        return _mask_sensitive_string(original)
    return text


def _flatten_to_dotted(mapping: Mapping[str, Any], prefix: str = "") -> Dict[str, Any]:
    flattened: Dict[str, Any] = {}
    for key, value in mapping.items():
        dotted = f"{prefix}.{key}" if prefix else key
        if isinstance(value, Mapping):
            flattened.update(_flatten_to_dotted(value, dotted))
        else:
            flattened[dotted] = value
    return flattened


def _collect_config_file_entries(files: Sequence[Path]) -> Dict[str, Tuple[Any, str]]:
    import tomllib

    entries: Dict[str, Tuple[Any, str]] = {}
    for file in files:
        if not file.exists():
            continue
        with file.open("rb") as handle:
            parsed = tomllib.load(handle)
        flattened = _flatten_to_dotted(parsed)
        for key, value in flattened.items():
            entries[key] = (value, file.name)
    return entries


def _build_cli_source_labels(invocation: "_CliInvocation") -> Dict[str, str]:
    labels: Dict[str, str] = {}
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


def _build_env_source_labels(env_overrides: Mapping[str, str]) -> Dict[str, str]:
    from src.settings import ENVVAR_TO_SETTINGS_KEY

    labels: Dict[str, str] = {}
    for env_var in env_overrides:
        config_key = ENVVAR_TO_SETTINGS_KEY.get(env_var)
        if config_key:
            labels[config_key] = f"ENV ({env_var})"
    return labels


def _build_cli_override_rows(invocation: "_CliInvocation") -> Sequence[Tuple[str, str, str]]:
    rows: list[Tuple[str, str, str]] = []
    for key, value in invocation.describe_cli_overrides().items():
        rows.append((key, _format_display_value(key, value), "CLI"))
    return rows


def _build_env_override_rows(env_overrides: Mapping[str, str]) -> Sequence[Tuple[str, str, str]]:
    from src.settings import ENVVAR_TO_SETTINGS_KEY

    rows: list[Tuple[str, str, str]] = []
    for env_var, value in env_overrides.items():
        config_key = ENVVAR_TO_SETTINGS_KEY.get(env_var)
        if not config_key:
            continue
        rows.append((config_key, _format_display_value(config_key, value), f"ENV ({env_var})"))
    return rows


_EFFECTIVE_CONFIG_KEY_ORDER: Tuple[str, ...] = (
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


def _effective_configuration_values(runtime_settings, logging_settings) -> Dict[str, Any]:
    values: Dict[str, Any] = {
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
    config_entries: Mapping[str, Tuple[Any, str]],
) -> str:
    if key in cli_labels:
        return cli_labels[key]
    if key in env_labels:
        return env_labels[key]
    if key in config_entries:
        return f"Config File ({config_entries[key][1]})"
    return "Default"


def _print_config_table(title: str, rows: Sequence[Tuple[str, str, str]]) -> None:
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
        "│[dim]                   Bitsight Rating Retriever                    [/dim]│\n"
        "│[yellow]                 Model Context Protocol Server                  [/yellow]│\n"
        "│[yellow]                https://github.com/boecht/birre                 [/yellow]│\n"
        "╰────────────────────────────────────────────────────────────────╯\n"
    )


def _keyboard_interrupt_banner() -> Text:
    return Text.from_markup(
        "\n"
        "╭───────────────────────────────────────╮\n"
        "│[red]  Keyboard interrupt received — stopping  [/red]│\n"
        "│[red]          BiRRe FastMCP server            [/red]│\n"
        "╰────────────────────────────────────────╯\n"
    )


def _normalize_context(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    candidate = value.strip().lower().replace("-", "_")
    if not candidate:
        return None
    if candidate not in _CONTEXT_CHOICES:
        raise typer.BadParameter(
            f"Context must be one of: {', '.join(sorted(_CONTEXT_CHOICES))}",
            param_hint="--context",
        )
    return candidate


def _normalize_log_format(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    candidate = value.strip().lower()
    if not candidate:
        return None
    if candidate not in _LOG_FORMAT_CHOICES:
        raise typer.BadParameter(
            "Log format must be either 'text' or 'json'",
            param_hint="--log-format",
        )
    return candidate


def _normalize_log_level(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    candidate = value.strip().upper()
    if not candidate:
        return None
    if candidate not in _LOG_LEVEL_SET:
        raise typer.BadParameter(
            f"Log level must be one of: {', '.join(_LOG_LEVEL_CHOICES)}",
            param_hint="--log-level",
        )
    return candidate


def _clean_string(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    candidate = value.strip()
    return candidate or None


def _validate_positive(name: str, value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    if value <= 0:
        raise typer.BadParameter(f"{name} must be a positive integer", param_hint=f"--{name.replace('_', '-')}")
    return value


@dataclass(frozen=True)
class _AuthCliOverrides:
    api_key: Optional[str] = None


@dataclass(frozen=True)
class _SubscriptionCliOverrides:
    folder: Optional[str] = None
    type: Optional[str] = None


@dataclass(frozen=True)
class _RuntimeCliOverrides:
    context: Optional[str] = None
    debug: Optional[bool] = None
    risk_vector_filter: Optional[str] = None
    max_findings: Optional[int] = None
    skip_startup_checks: Optional[bool] = None


@dataclass(frozen=True)
class _TlsCliOverrides:
    allow_insecure: Optional[bool] = None
    ca_bundle_path: Optional[str] = None


@dataclass(frozen=True)
class _LoggingCliOverrides:
    level: Optional[str] = None
    format: Optional[str] = None
    file_path: Optional[str] = None
    max_bytes: Optional[int] = None
    backup_count: Optional[int] = None


@dataclass
class _LogViewLine:
    raw: str
    level: Optional[int]
    timestamp: Optional[float]
    json_data: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class _CliInvocation:
    config_path: Optional[str]
    auth: _AuthCliOverrides
    subscription: _SubscriptionCliOverrides
    runtime: _RuntimeCliOverrides
    tls: _TlsCliOverrides
    logging: _LoggingCliOverrides
    profile_path: Optional[Path] = None

    def describe_cli_overrides(self) -> Dict[str, str]:
        details: Dict[str, str] = {}
        if self.auth.api_key:
            details[BITSIGHT_API_KEY_KEY] = _format_display_value(BITSIGHT_API_KEY_KEY, self.auth.api_key)
        if self.subscription.folder:
            details[BITSIGHT_SUBSCRIPTION_FOLDER_KEY] = _format_display_value(
                BITSIGHT_SUBSCRIPTION_FOLDER_KEY, self.subscription.folder
            )
        if self.subscription.type:
            details[BITSIGHT_SUBSCRIPTION_TYPE_KEY] = _format_display_value(
                BITSIGHT_SUBSCRIPTION_TYPE_KEY, self.subscription.type
            )
        if self.runtime.context:
            details[ROLE_CONTEXT_KEY] = _format_display_value(ROLE_CONTEXT_KEY, self.runtime.context)
        if self.runtime.risk_vector_filter:
            details[ROLE_RISK_VECTOR_FILTER_KEY] = _format_display_value(
                ROLE_RISK_VECTOR_FILTER_KEY, self.runtime.risk_vector_filter
            )
        if self.runtime.max_findings is not None:
            details[ROLE_MAX_FINDINGS_KEY] = _format_display_value(
                ROLE_MAX_FINDINGS_KEY, self.runtime.max_findings
            )
        if self.runtime.debug is not None:
            details[RUNTIME_DEBUG_KEY] = _format_display_value(RUNTIME_DEBUG_KEY, self.runtime.debug)
        if self.runtime.skip_startup_checks is not None:
            details[RUNTIME_SKIP_STARTUP_CHECKS_KEY] = _format_display_value(
                RUNTIME_SKIP_STARTUP_CHECKS_KEY, self.runtime.skip_startup_checks
            )
        if self.tls.allow_insecure is not None:
            details[RUNTIME_ALLOW_INSECURE_TLS_KEY] = _format_display_value(
                RUNTIME_ALLOW_INSECURE_TLS_KEY, self.tls.allow_insecure
            )
        if self.tls.ca_bundle_path:
            details[RUNTIME_CA_BUNDLE_PATH_KEY] = _format_display_value(
                RUNTIME_CA_BUNDLE_PATH_KEY, self.tls.ca_bundle_path
            )
        if self.logging.level:
            details[LOGGING_LEVEL_KEY] = _format_display_value(LOGGING_LEVEL_KEY, self.logging.level)
        if self.logging.format:
            details[LOGGING_FORMAT_KEY] = _format_display_value(LOGGING_FORMAT_KEY, self.logging.format)
        if self.logging.file_path is not None:
            details[LOGGING_FILE_KEY] = _format_display_value(LOGGING_FILE_KEY, self.logging.file_path)
        if self.logging.max_bytes is not None:
            details[LOGGING_MAX_BYTES_KEY] = _format_display_value(
                LOGGING_MAX_BYTES_KEY, self.logging.max_bytes
            )
        if self.logging.backup_count is not None:
            details[LOGGING_BACKUP_COUNT_KEY] = _format_display_value(
                LOGGING_BACKUP_COUNT_KEY, self.logging.backup_count
            )
        return details


def _build_invocation(
    *,
    config_path: Optional[Path | str],
    api_key: Optional[str],
    subscription_folder: Optional[str],
    subscription_type: Optional[str],
    context: Optional[str],
    debug: Optional[bool],
    risk_vector_filter: Optional[str],
    max_findings: Optional[int],
    skip_startup_checks: Optional[bool],
    allow_insecure_tls: Optional[bool],
    ca_bundle: Optional[str],
    log_level: Optional[str],
    log_format: Optional[str],
    log_file: Optional[str],
    log_max_bytes: Optional[int],
    log_backup_count: Optional[int],
    profile_path: Optional[Path] = None,
) -> _CliInvocation:
    normalized_context = _normalize_context(context)
    normalized_log_format = _normalize_log_format(log_format)
    normalized_log_level = _normalize_log_level(log_level)
    normalized_max_findings = _validate_positive("max_findings", max_findings)
    normalized_log_max_bytes = _validate_positive("log_max_bytes", log_max_bytes)
    normalized_log_backup_count = _validate_positive("log_backup_count", log_backup_count)

    clean_log_file = _clean_string(log_file)

    return _CliInvocation(
        config_path=str(config_path) if config_path is not None else None,
        auth=_AuthCliOverrides(api_key=_clean_string(api_key)),
        subscription=_SubscriptionCliOverrides(
            folder=_clean_string(subscription_folder),
            type=_clean_string(subscription_type),
        ),
        runtime=_RuntimeCliOverrides(
            context=normalized_context,
            debug=debug,
            risk_vector_filter=_clean_string(risk_vector_filter),
            max_findings=normalized_max_findings,
            skip_startup_checks=skip_startup_checks,
        ),
        tls=_TlsCliOverrides(
            allow_insecure=allow_insecure_tls,
            ca_bundle_path=_clean_string(ca_bundle),
        ),
        logging=_LoggingCliOverrides(
            level=normalized_log_level,
            format=normalized_log_format,
            file_path=clean_log_file,
            max_bytes=normalized_log_max_bytes,
            backup_count=normalized_log_backup_count,
        ),
        profile_path=profile_path,
    )


def _subscription_inputs(overrides: _SubscriptionCliOverrides) -> Optional[SubscriptionInputs]:
    if overrides.folder is None and overrides.type is None:
        return None
    return SubscriptionInputs(folder=overrides.folder, type=overrides.type)


def _runtime_inputs(overrides: _RuntimeCliOverrides) -> Optional[RuntimeInputs]:
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


def _tls_inputs(overrides: _TlsCliOverrides) -> Optional[TlsInputs]:
    if overrides.allow_insecure is None and overrides.ca_bundle_path is None:
        return None
    return TlsInputs(
        allow_insecure=overrides.allow_insecure,
        ca_bundle_path=overrides.ca_bundle_path,
    )


def _logging_inputs(overrides: _LoggingCliOverrides) -> Optional[LoggingInputs]:
    if (
        overrides.level is None
        and overrides.format is None
        and overrides.file_path is None
        and overrides.max_bytes is None
        and overrides.backup_count is None
    ):
        return None

    file_override: Optional[str]
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


def _load_settings_from_invocation(invocation: _CliInvocation):
    settings = load_settings(invocation.config_path)
    apply_cli_overrides(
        settings,
        api_key_input=invocation.auth.api_key,
        subscription_inputs=_subscription_inputs(invocation.subscription),
        runtime_inputs=_runtime_inputs(invocation.runtime),
        tls_inputs=_tls_inputs(invocation.tls),
        logging_inputs=_logging_inputs(invocation.logging),
    )
    return settings


def _resolve_runtime_and_logging(invocation: _CliInvocation):
    settings = _load_settings_from_invocation(invocation)
    runtime_settings = runtime_from_settings(settings)
    logging_settings = logging_from_settings(settings)
    if runtime_settings.debug and logging_settings.level > logging.DEBUG:
        logging_settings = replace(logging_settings, level=logging.DEBUG)
    return runtime_settings, logging_settings, settings


def _emit_runtime_messages(runtime_settings, logger) -> None:
    for message in getattr(runtime_settings, "overrides", ()):  # type: ignore[attr-defined]
        logger.info(message)
    for message in getattr(runtime_settings, "warnings", ()):  # type: ignore[attr-defined]
        logger.warning(message)


def _run_offline_checks(runtime_settings, logger) -> bool:
    logger.info("Running offline startup checks")
    offline_ok = run_offline_startup_checks(
        has_api_key=bool(runtime_settings.api_key),
        subscription_folder=runtime_settings.subscription_folder,
        subscription_type=runtime_settings.subscription_type,
        logger=logger,
    )
    if not offline_ok:
        logger.critical("Offline startup checks failed")
    return offline_ok


def _run_online_checks(
    runtime_settings,
    logger,
    *,
    v1_base_url: Optional[str] = None,
) -> bool:
    logger.info("Running online startup checks")

    verify_option = _resolve_tls_verification(runtime_settings, logger)
    base_url = v1_base_url or DEFAULT_V1_API_BASE_URL

    async def _execute_checks() -> bool:
        api_server = create_v1_api_server(
            runtime_settings.api_key,
            verify=verify_option,
            base_url=base_url,
        )

        async def call_v1_tool(tool_name: str, ctx, params: Dict[str, Any]) -> Any:
            return await call_v1_openapi_tool(
                api_server,
                tool_name,
                ctx,
                params,
                logger=logger,
            )

        try:
            return await run_online_startup_checks(
                call_v1_tool=call_v1_tool,
                subscription_folder=runtime_settings.subscription_folder,
                subscription_type=runtime_settings.subscription_type,
                logger=logger,
                skip_startup_checks=getattr(runtime_settings, "skip_startup_checks", False),
            )
        finally:
            client = getattr(api_server, "_client", None)
            close = getattr(client, "aclose", None)
            if callable(close):
                try:
                    await close()
                except Exception as exc:  # pragma: no cover - defensive logging
                    _loop_logger.warning(
                        "online_checks.client_close_failed",
                        error=str(exc),
                    )
            shutdown = getattr(api_server, "shutdown", None)
            if callable(shutdown):
                with suppress(Exception):
                    await shutdown()  # type: ignore[func-returns-value]

    return _await_sync(_execute_checks())


def _initialize_logging(runtime_settings, logging_settings, *, show_banner: bool = True):
    if show_banner:
        stderr_console.print(_banner())
    configure_logging(logging_settings)
    logger = get_logger("birre")
    _emit_runtime_messages(runtime_settings, logger)
    return logger


_SYNC_BRIDGE_LOOP: asyncio.AbstractEventLoop | None = None
_SYNC_BRIDGE_LOCK = threading.Lock()


def _close_sync_bridge_loop() -> None:
    """Best-effort shutdown for the shared synchronous event loop."""
    global _SYNC_BRIDGE_LOOP
    loop = _SYNC_BRIDGE_LOOP
    if loop is None or loop.is_closed():
        return
    _loop_logger.debug("sync_bridge.loop_close")
    pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
    for task in pending:
        task.cancel()
    with suppress(Exception):
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    loop.close()
    _SYNC_BRIDGE_LOOP = None


atexit.register(_close_sync_bridge_loop)


def _await_sync(coro: Awaitable[Any]) -> Any:
    """Execute an awaitable from sync code using a reusable event loop.

    The loop lives for the process lifetime, is guarded by a lock to prevent
    concurrent access, and cleans up any pending tasks before returning.
    """
    global _SYNC_BRIDGE_LOOP
    with _SYNC_BRIDGE_LOCK:
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop is not None:
            raise RuntimeError("_await_sync cannot be used inside a running event loop")

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


def _discover_context_tools(server) -> Set[str]:
    names: Set[str] = set()
    tools_attr = getattr(server, "tools", None)
    if isinstance(tools_attr, dict):
        names.update(str(name) for name in tools_attr.keys() if isinstance(name, str))

    get_tools = getattr(server, "get_tools", None)
    if callable(get_tools):
        try:
            result = get_tools()
        except TypeError:  # pragma: no cover - defensive
            result = None
        if asyncio.iscoroutine(result):
            resolved = _await_sync(result)
        else:
            resolved = result
        if isinstance(resolved, dict):
            names.update(str(name) for name in resolved.keys() if isinstance(name, str))

    return names


class _HealthcheckContext:
    def __init__(self, *, context: str, tool_name: str, logger: BoundLogger):
        self._context = context
        self._tool_name = tool_name
        self._logger = logger
        self._request_id = f"healthcheck-{context}-{tool_name}-{uuid4().hex}"
        self.metadata: Dict[str, Any] = {"healthcheck": True, "context": context, "tool": tool_name}
        self.tool = tool_name

    async def info(self, message: str) -> None:
        self._logger.info(
            "healthcheck.ctx.info",
            message=message,
            request_id=self._request_id,
            tool=self._tool_name,
        )

    async def warning(self, message: str) -> None:
        self._logger.warning(
            "healthcheck.ctx.warning",
            message=message,
            request_id=self._request_id,
            tool=self._tool_name,
        )

    async def error(self, message: str) -> None:
        self._logger.error(
            "healthcheck.ctx.error",
            message=message,
            request_id=self._request_id,
            tool=self._tool_name,
        )

    @property
    def request_id(self) -> str:
        return self._request_id

    @property
    def call_id(self) -> str:
        return self._request_id


@dataclass
class DiagnosticFailure:
    tool: str
    stage: str
    message: str
    mode: Optional[str] = None
    exception: Optional[BaseException] = None
    category: Optional[str] = None


@dataclass
class AttemptReport:
    label: str
    success: bool
    failures: list[DiagnosticFailure]
    notes: list[str]
    allow_insecure_tls: bool
    ca_bundle: Optional[str]
    online_success: Optional[bool]
    discovered_tools: list[str]
    missing_tools: list[str]
    tools: Dict[str, Dict[str, Any]]


@dataclass
class ContextDiagnosticsResult:
    """Captured diagnostics outcome for a single FastMCP context."""

    name: str
    success: bool
    degraded: bool
    report: Dict[str, Any]


@dataclass
class HealthcheckResult:
    """Aggregate result returned by :class:`HealthcheckRunner`."""

    success: bool
    degraded: bool
    summary: Dict[str, Any]
    contexts: Tuple[str, ...]
    alerts: Tuple[str, ...] = ()

    def exit_code(self) -> int:
        """Return the CLI exit code representing this result."""

        if ErrorCode.TLS_CERT_CHAIN_INTERCEPTED.value in self.alerts:
            return 2
        if not self.success:
            return 1
        if self.degraded:
            return 2
        return 0


class HealthcheckRunner:
    """Execute BiRRe health checks in a structured, testable manner."""

    def __init__(
        self,
        *,
        runtime_settings,
        logger: BoundLogger,
        offline: bool,
        target_base_url: str,
        environment_label: str,
    ) -> None:
        self._base_runtime_settings = runtime_settings
        self._logger = logger
        self._offline = offline
        self._target_base_url = target_base_url
        self._environment_label = environment_label
        self._contexts: Tuple[str, ...] = tuple(sorted(_CONTEXT_CHOICES))
        self._alerts: set[str] = set()

    def run(self) -> HealthcheckResult:
        """Run offline and per-context diagnostics and collect a summary."""

        self._alerts.clear()
        offline_ok = _run_offline_checks(self._base_runtime_settings, self._logger)
        summary: Dict[str, Any] = {
            "environment": self._environment_label,
            "offline_check": {"status": "pass" if offline_ok else "fail"},
            "contexts": {},
            "overall_success": None,
        }

        if not offline_ok:
            summary["overall_success"] = False
            return HealthcheckResult(
                success=False,
                degraded=False,
                summary=summary,
                contexts=self._contexts,
                alerts=tuple(sorted(self._alerts)),
            )

        overall_success = True
        degraded = self._offline
        context_reports: Dict[str, Dict[str, Any]] = summary["contexts"]

        for context_name in self._contexts:
            result = self._evaluate_context(context_name)
            context_reports[context_name] = result.report
            if not result.success:
                overall_success = False
            if result.degraded:
                degraded = True

        summary["overall_success"] = overall_success
        return HealthcheckResult(
            success=overall_success,
            degraded=degraded,
            summary=summary,
            contexts=self._contexts,
            alerts=tuple(sorted(self._alerts)),
        )

    # ------------------------------------------------------------------
    # Context evaluation helpers
    # ------------------------------------------------------------------

    def _evaluate_context(self, context_name: str) -> ContextDiagnosticsResult:
        logger = self._logger.bind(context=context_name)
        logger.info("Preparing context diagnostics")

        expected_tools = _EXPECTED_TOOLS_BY_CONTEXT.get(context_name)
        report: Dict[str, Any] = {
            "offline_mode": bool(self._offline),
            "attempts": [],
            "encountered_categories": [],
            "fallback_attempted": False,
            "fallback_success": None,
            "failure_categories": [],
            "recoverable_categories": [],
            "unrecoverable_categories": [],
            "notes": [],
        }

        if expected_tools is None:
            logger.critical("No expected tool inventory defined for context")
            report["success"] = False
            report["online"] = {
                "status": "fail",
                "details": {"reason": "missing expected tool inventory"},
            }
            report["tools"] = {}
            return ContextDiagnosticsResult(
                name=context_name,
                success=False,
                degraded=False,
                report=report,
            )

        context_settings = replace(self._base_runtime_settings, context=context_name)
        effective_settings, notes, degraded = self._resolve_ca_bundle(logger, context_settings)
        report["notes"] = list(notes)

        if self._offline:
            return self._evaluate_offline_context(
                context_name,
                logger,
                expected_tools,
                report,
                effective_settings,
                degraded,
            )

        return self._evaluate_online_context(
            context_name,
            logger,
            expected_tools,
            report,
            effective_settings,
            degraded,
        )

    def _resolve_ca_bundle(
        self,
        logger: BoundLogger,
        context_settings,
    ) -> tuple[Any, list[str], bool]:
        notes: list[str] = []
        degraded = False
        effective_settings = context_settings

        ca_bundle_path = getattr(context_settings, "ca_bundle_path", None)
        if ca_bundle_path:
            resolved_ca_path = Path(str(ca_bundle_path)).expanduser()
            if not resolved_ca_path.exists():
                logger.warning(
                    "Configured CA bundle missing; falling back to system defaults",
                    ca_bundle=str(resolved_ca_path),
                )
                effective_settings = replace(effective_settings, ca_bundle_path=None)
                notes.append("ca-bundle-defaulted")
                degraded = True

        return effective_settings, notes, degraded

    def _evaluate_offline_context(
        self,
        context_name: str,
        logger: BoundLogger,
        expected_tools: FrozenSet[str],
        report: Dict[str, Any],
        effective_settings,
        degraded: bool,
    ) -> ContextDiagnosticsResult:
        server_instance = _prepare_server(
            effective_settings,
            logger,
            v1_base_url=self._target_base_url,
        )
        discovered_tools = _discover_context_tools(server_instance)
        missing_tools = sorted(expected_tools - discovered_tools)
        report["discovery"] = {
            "discovered": sorted(discovered_tools),
            "missing": missing_tools,
        }
        report["tools"] = _aggregate_tool_outcomes(
            expected_tools,
            [],
            offline_mode=True,
            offline_missing=missing_tools,
        )
        report["online"] = {
            "status": "warning",
            "details": {"reason": "offline mode"},
        }
        report["encountered_categories"] = []
        report["failure_categories"] = []
        report["recoverable_categories"] = []
        report["unrecoverable_categories"] = []

        if missing_tools:
            logger.critical(
                "Tool discovery failed",
                missing_tools=missing_tools,
                discovered=sorted(discovered_tools),
                attempt="offline",
            )
            report["success"] = False
            return ContextDiagnosticsResult(
                name=context_name,
                success=False,
                degraded=degraded,
                report=report,
            )

        logger.info(
            "Tool discovery succeeded",
            tools=sorted(discovered_tools),
            attempt="offline",
        )
        report["success"] = True
        # Skipping online diagnostics inherently limits coverage.
        degraded = True
        return ContextDiagnosticsResult(
            name=context_name,
            success=True,
            degraded=degraded,
            report=report,
        )

    def _evaluate_online_context(
        self,
        context_name: str,
        logger: BoundLogger,
        expected_tools: FrozenSet[str],
        report: Dict[str, Any],
        effective_settings,
        degraded: bool,
    ) -> ContextDiagnosticsResult:
        attempt_reports: list[AttemptReport] = []
        encountered_categories: set[str] = set()
        failure_categories: set[str] = set()
        fallback_attempted = False
        fallback_success_value: Optional[bool] = None

        primary_report = self._run_diagnostic_attempt(
            context_name=context_name,
            settings=effective_settings,
            context_logger=logger,
            expected_tools=expected_tools,
            label="primary",
            notes=report.get("notes", ()),
        )
        attempt_reports.append(primary_report)
        self._update_failure_categories(
            primary_report, encountered_categories, failure_categories
        )
        context_success = primary_report.success

        if not context_success:
            tls_failures = [
                failure
                for failure in primary_report.failures
                if failure.category == "tls"
            ]
            if tls_failures and not effective_settings.allow_insecure_tls:
                logger.warning(
                    "TLS errors detected; retrying diagnostics with allow_insecure_tls enabled",
                    attempt="tls-fallback",
                    original_errors=[
                        _summarize_failure(failure) for failure in tls_failures
                    ],
                )
                fallback_settings = replace(
                    effective_settings,
                    allow_insecure_tls=True,
                    ca_bundle_path=None,
                )
                fallback_report = self._run_diagnostic_attempt(
                    context_name=context_name,
                    settings=fallback_settings,
                    context_logger=logger,
                    expected_tools=expected_tools,
                    label="tls-fallback",
                    notes=None,
                )
                attempt_reports.append(fallback_report)
                fallback_attempted = True
                fallback_success_value = fallback_report.success
                self._update_failure_categories(
                    fallback_report, encountered_categories, failure_categories
                )
                context_success = fallback_report.success
                if fallback_report.success:
                    logger.warning(
                        "TLS fallback resolved diagnostics failure",
                        attempt="tls-fallback",
                        original_errors=[
                            _summarize_failure(failure) for failure in tls_failures
                        ],
                    )
                else:
                    logger.error(
                        "TLS fallback failed to resolve diagnostics",
                        attempt="tls-fallback",
                        original_errors=[
                            _summarize_failure(failure) for failure in tls_failures
                        ],
                    )
            else:
                context_success = False

        if not context_success:
            recoverable = sorted(
                (failure_categories | encountered_categories)
                & {"tls", "config.ca_bundle"}
            )
            unrecoverable = sorted(
                (failure_categories | encountered_categories)
                - {"tls", "config.ca_bundle"}
            )
            logger.error(
                "Context diagnostics failed",
                attempts=[
                    {"label": report.label, "success": report.success}
                    for report in attempt_reports
                ],
                recoverable_categories=recoverable or None,
                unrecoverable_categories=unrecoverable or None,
            )
        else:
            recoverable = []
            unrecoverable = []
            if any(not report.success for report in attempt_reports):
                logger.info(
                    "Context diagnostics completed with recoveries",
                    attempts=[
                        {"label": report.label, "success": report.success}
                        for report in attempt_reports
                    ],
                )
            else:
                logger.info(
                    "Context diagnostics completed successfully",
                    attempt="primary",
                )

        report["success"] = context_success
        report["fallback_attempted"] = fallback_attempted
        report["fallback_success"] = fallback_success_value
        report["encountered_categories"] = sorted(encountered_categories)
        report["failure_categories"] = sorted(
            category for category in failure_categories if category
        )
        report["recoverable_categories"] = recoverable
        report["unrecoverable_categories"] = unrecoverable

        attempt_summaries = [
            {
                "label": attempt.label,
                "success": attempt.success,
                "notes": attempt.notes,
                "allow_insecure_tls": attempt.allow_insecure_tls,
                "ca_bundle": attempt.ca_bundle,
                "online_success": attempt.online_success,
                "discovered_tools": attempt.discovered_tools,
                "missing_tools": attempt.missing_tools,
                "tools": attempt.tools,
                "failures": [
                    _summarize_failure(failure) for failure in attempt.failures
                ],
            }
            for attempt in attempt_reports
        ]
        report["attempts"] = attempt_summaries

        online_attempts: Dict[str, str] = {}
        for attempt in attempt_summaries:
            result = attempt.get("online_success")
            if result is None:
                continue
            online_attempts[attempt["label"]] = "pass" if result else "fail"
        if any(status == "pass" for status in online_attempts.values()):
            online_status = "pass"
        elif any(status == "fail" for status in online_attempts.values()):
            online_status = "fail"
        else:
            online_status = "warning"
        online_summary: Dict[str, Any] = {"status": online_status}
        if online_attempts:
            online_summary["attempts"] = online_attempts
        report["online"] = online_summary

        report["tools"] = _aggregate_tool_outcomes(
            expected_tools,
            attempt_summaries,
            offline_mode=False,
        )

        tls_failure_present = any(
            failure.category == "tls"
            for attempt in attempt_reports
            for failure in attempt.failures
        )
        if tls_failure_present:
            report.setdefault("notes", []).append("tls-cert-chain-intercepted")
            report["tls_cert_chain_intercepted"] = True

        context_degraded = degraded
        if tls_failure_present and not context_success:
            context_degraded = True

        if context_success:
            context_degraded = context_degraded or self._has_degraded_outcomes(
                report, attempt_reports
            )

        return ContextDiagnosticsResult(
            name=context_name,
            success=context_success,
            degraded=context_degraded,
            report=report,
        )

    def _run_diagnostic_attempt(
        self,
        *,
        context_name: str,
        settings,
        context_logger: BoundLogger,
        expected_tools: FrozenSet[str],
        label: str,
        notes: Optional[Sequence[str]],
    ) -> AttemptReport:
        attempt_notes = list(notes or ())
        context_logger.info(
            "Starting diagnostics attempt",
            attempt=label,
            allow_insecure_tls=settings.allow_insecure_tls,
            ca_bundle=settings.ca_bundle_path,
            notes=attempt_notes,
        )

        server_instance = _prepare_server(
            settings,
            context_logger,
            v1_base_url=self._target_base_url,
        )

        discovered_tools = _discover_context_tools(server_instance)
        missing_tools = sorted(expected_tools - discovered_tools)
        failure_records: list[DiagnosticFailure] = []
        attempt_success = True
        tool_report: Dict[str, Dict[str, Any]] = {}
        online_success: Optional[bool] = None
        skip_tool_checks = False

        if missing_tools:
            context_logger.critical(
                "Tool discovery failed",
                missing_tools=missing_tools,
                discovered=sorted(discovered_tools),
                attempt=label,
            )
            for tool_name in missing_tools:
                _record_failure(
                    failure_records,
                    tool=tool_name,
                    stage="discovery",
                    message="expected tool not registered",
                )
                attempt_success = False
            for tool_name in sorted(expected_tools):
                if tool_name in missing_tools:
                    tool_report[tool_name] = {
                        "status": "fail",
                        "details": {"reason": "tool not registered"},
                    }
                else:
                    tool_report[tool_name] = {
                        "status": "warning",
                        "details": {"reason": "not evaluated"},
                    }
        else:
            context_logger.info(
                "Tool discovery succeeded",
                tools=sorted(discovered_tools),
                attempt=label,
            )

            try:
                online_ok = _run_online_checks(
                    settings,
                    context_logger,
                    v1_base_url=self._target_base_url,
                )
            except BirreError as exc:
                online_success = False
                attempt_success = False
                skip_tool_checks = True
                self._alerts.add(exc.code)
                _record_failure(
                    failure_records,
                    tool="startup_checks",
                    stage="online",
                    message="online startup checks failed",
                    exception=exc,
                )
                context_logger.error(
                    "Online startup checks failed",
                    reason=exc.user_message,
                    **exc.log_fields(),
                )
                attempt_notes.append(exc.context.code)
            else:
                online_success = online_ok
                if not online_ok:
                    _record_failure(
                        failure_records,
                        tool="startup_checks",
                        stage="online",
                        message="online startup checks failed",
                    )
                    attempt_success = False

            if not skip_tool_checks and not _run_context_tool_diagnostics(
                context=context_name,
                logger=context_logger,
                server_instance=server_instance,
                expected_tools=expected_tools,
                summary=tool_report,
                failures=failure_records,
            ):
                attempt_success = False

        attempt_report = AttemptReport(
            label=label,
            success=attempt_success,
            failures=failure_records,
            notes=attempt_notes,
            allow_insecure_tls=bool(settings.allow_insecure_tls),
            ca_bundle=str(settings.ca_bundle_path) if settings.ca_bundle_path else None,
            online_success=online_success,
            discovered_tools=sorted(discovered_tools),
            missing_tools=missing_tools,
            tools=tool_report,
        )

        log_method = context_logger.info if attempt_success else context_logger.warning
        log_method(
            "Diagnostics attempt completed",
            attempt=label,
            success=attempt_success,
            allow_insecure_tls=settings.allow_insecure_tls,
            ca_bundle=settings.ca_bundle_path,
            failure_count=len(failure_records),
            notes=attempt_notes,
            failures=[_summarize_failure(failure) for failure in failure_records],
        )

        return attempt_report

    def _update_failure_categories(
        self,
        attempt_report: AttemptReport,
        encountered_categories: set[str],
        failure_categories: set[str],
    ) -> None:
        for failure in attempt_report.failures:
            category = _classify_failure(failure)
            if category:
                encountered_categories.add(category)
        failure_categories.update(
            failure.category
            for failure in attempt_report.failures
            if failure.category
        )

    def _has_degraded_outcomes(
        self,
        report: Mapping[str, Any],
        attempts: Sequence[AttemptReport],
    ) -> bool:
        if report.get("offline_mode"):
            return True
        if report.get("notes"):
            return True
        if report.get("encountered_categories"):
            return True
        if report.get("recoverable_categories"):
            return True
        if report.get("fallback_attempted"):
            return True
        if any(not attempt.success for attempt in attempts):
            return True

        online_status = None
        online_section = report.get("online")
        if isinstance(online_section, Mapping):
            online_status = online_section.get("status")
        if online_status == "warning":
            return True

        tools_section = report.get("tools")
        if isinstance(tools_section, Mapping):
            for entry in tools_section.values():
                if not isinstance(entry, Mapping):
                    continue
                status = entry.get("status")
                if status == "warning":
                    return True
                attempts_map = entry.get("attempts")
                if isinstance(attempts_map, Mapping) and any(
                    value == "warning" for value in attempts_map.values()
                ):
                    return True

        return False

def _record_failure(
    failures: Optional[list[DiagnosticFailure]],
    *,
    tool: str,
    stage: str,
    message: str,
    mode: Optional[str] = None,
    exception: Optional[BaseException] = None,
) -> None:
    if failures is None:
        return
    failures.append(
        DiagnosticFailure(
            tool=tool,
            stage=stage,
            message=message,
            mode=mode,
            exception=exception,
        )
    )


def _is_tls_exception(exc: BaseException) -> bool:
    if isinstance(exc, TlsCertificateChainInterceptedError):
        return True
    if isinstance(exc, ssl.SSLError):
        return True
    if isinstance(exc, httpx.HTTPError):
        cause = exc.__cause__
        if isinstance(cause, ssl.SSLError):
            return True
        message = str(exc).lower()
        if any(token in message for token in ("ssl", "tls", "certificate")):
            return True
    message = str(exc).lower()
    if any(token in message for token in ("ssl", "tls", "certificate verify failed")):
        return True
    return False


def _is_missing_ca_bundle_exception(exc: BaseException) -> bool:
    if isinstance(exc, FileNotFoundError):
        return True
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == errno.ENOENT:
        return True
    message = str(exc).lower()
    if "could not find a suitable tls ca certificate bundle" in message:
        return True
    if "no such file or directory" in message and "ca" in message:
        return True
    return False


def _classify_failure(failure: DiagnosticFailure) -> Optional[str]:
    if failure.exception is None:
        message = failure.message.lower()
        if any(token in message for token in ("ssl", "tls", "certificate")):
            failure.category = "tls"
        return failure.category
    if _is_tls_exception(failure.exception):
        failure.category = "tls"
    elif _is_missing_ca_bundle_exception(failure.exception):
        failure.category = "config.ca_bundle"
    return failure.category


def _summarize_failure(failure: DiagnosticFailure) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "tool": failure.tool,
        "stage": failure.stage,
    }
    if failure.mode:
        summary["mode"] = failure.mode
    if failure.category:
        summary["category"] = failure.category
    if failure.exception is not None:
        summary["error"] = str(failure.exception)
    else:
        summary["message"] = failure.message
    return summary


def _aggregate_tool_outcomes(
    expected_tools: FrozenSet[str],
    attempts: Sequence[Dict[str, Any]],
    *,
    offline_mode: bool = False,
    offline_missing: Optional[Sequence[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    aggregated: Dict[str, Dict[str, Any]] = {}
    if offline_mode:
        missing_set = set(offline_missing or ())
        for tool_name in sorted(expected_tools):
            if tool_name in missing_set:
                aggregated[tool_name] = {
                    "status": "fail",
                    "details": {"reason": "tool not registered"},
                }
            else:
                aggregated[tool_name] = {
                    "status": "warning",
                    "details": {"reason": "offline mode"},
                }
        return aggregated

    for tool_name in sorted(expected_tools):
        attempt_details: Dict[str, Dict[str, Any]] = {}
        statuses: list[str] = []
        for attempt in attempts:
            tool_entry = attempt.get("tools", {}).get(tool_name)
            if tool_entry is None:
                continue
            attempt_details[attempt["label"]] = tool_entry
            status = tool_entry.get("status")
            if isinstance(status, str):
                statuses.append(status)
        if not statuses:
            aggregated[tool_name] = {
                "status": "warning",
                "attempts": attempt_details or None,
            }
            continue
        if any(status == "pass" for status in statuses):
            final_status = "pass"
        elif any(status == "fail" for status in statuses):
            final_status = "fail"
        else:
            final_status = statuses[0]
        entry: Dict[str, Any] = {"status": final_status}
        if attempt_details:
            entry["attempts"] = attempt_details
        aggregated[tool_name] = entry
    return aggregated


def _render_healthcheck_summary(report: Dict[str, Any]) -> None:
    def status_label(value: Optional[str]) -> str:
        mapping = {"pass": "PASS", "fail": "FAIL", "warning": "WARNING"}
        if not value:
            return "WARNING"
        return mapping.get(value.lower(), value.upper())

    def stringify_detail(value: Any) -> str:
        if value is None:
            return "-"
        if isinstance(value, str):
            return value
        if isinstance(value, Mapping):
            items = [f"{key}={value[key]}" for key in sorted(value)]
            return ", ".join(items) if items else "-"
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            items = [stringify_detail(item) for item in value]
            return ", ".join(item for item in items if item and item != "-") or "-"
        return str(value)

    def format_context_detail(context_data: Mapping[str, Any]) -> str:
        parts: list[str] = []
        if context_data.get("fallback_attempted"):
            resolved = context_data.get("fallback_success")
            parts.append(
                "fallback=" + ("resolved" if resolved else "failed")
            )
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

    def format_online_detail(online_data: Mapping[str, Any]) -> str:
        attempts = online_data.get("attempts") if isinstance(online_data, Mapping) else None
        if isinstance(attempts, Mapping) and attempts:
            attempt_parts = [
                f"{label}:{status_label(status)}"
                for label, status in sorted(attempts.items())
            ]
            return ", ".join(attempt_parts)
        details = online_data.get("details") if isinstance(online_data, Mapping) else None
        return stringify_detail(details)

    def format_tool_detail(tool_summary: Mapping[str, Any]) -> str:
        parts: list[str] = []
        attempts = tool_summary.get("attempts")
        if isinstance(attempts, Mapping) and attempts:
            attempt_parts = []
            for label, entry in sorted(attempts.items()):
                attempt_status = status_label(entry.get("status"))
                attempt_parts.append(f"{label}:{attempt_status}")
                modes = entry.get("modes")
                if isinstance(modes, Mapping) and modes:
                    mode_parts = [
                        f"{mode}:{status_label(mode_entry.get('status'))}"
                        for mode, mode_entry in sorted(modes.items())
                    ]
                    if mode_parts:
                        parts.append(f"{label} modes=" + ", ".join(mode_parts))
                detail = entry.get("details")
                if detail:
                    parts.append(f"{label} detail=" + stringify_detail(detail))
            if attempt_parts:
                parts.insert(0, "attempts=" + ", ".join(attempt_parts))
        details = tool_summary.get("details")
        if details:
            parts.append(stringify_detail(details))
        return "; ".join(parts) if parts else "-"

    table = Table(title="Healthcheck Summary", box=box.SIMPLE_HEAVY)
    table.add_column("Check", style=_RichStyles.ACCENT)
    table.add_column("Context", style=_RichStyles.SECONDARY)
    table.add_column("Tool", style=_RichStyles.SUCCESS)
    table.add_column("Status", style=_RichStyles.EMPHASIS)
    table.add_column("Details", style=_RichStyles.DETAIL)

    offline_entry = report.get("offline_check", {})
    offline_status = status_label(offline_entry.get("status"))
    offline_detail = stringify_detail(offline_entry.get("details"))
    table.add_row("Offline checks", "-", "-", offline_status, offline_detail)

    critical_failures: list[str] = []
    for context_name, context_data in sorted(report.get("contexts", {}).items()):
        context_success = context_data.get("success")
        offline_mode = context_data.get("offline_mode")
        if offline_mode and context_success:
            context_status = "warning"
        elif context_success:
            context_status = "pass"
        else:
            context_status = "fail"
        context_detail = format_context_detail(context_data)
        context_status_label = status_label(context_status)
        table.add_row("Context", context_name, "-", context_status_label, context_detail)

        online_summary = context_data.get("online", {})
        online_status_label = status_label(online_summary.get("status"))
        online_detail = format_online_detail(online_summary)
        table.add_row("Online", context_name, "-", online_status_label, online_detail or "-")

        tools = context_data.get("tools", {})
        for tool_name, tool_summary in sorted(tools.items()):
            tool_status_label = status_label(tool_summary.get("status"))
            detail_text = format_tool_detail(tool_summary)
            table.add_row("Tool", context_name, tool_name, tool_status_label, detail_text)

        if context_status_label == "FAIL":
            critical_failures.append(f"{context_name}: context failure")
        unrecoverable = context_data.get("unrecoverable_categories") or []
        if unrecoverable:
            critical_failures.append(
                f"{context_name}: unrecoverable={','.join(sorted(unrecoverable))}"
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


def _collect_tool_map(server_instance: Any) -> Dict[str, Any]:
    tools: Dict[str, Any] = {}

    tools_attr = getattr(server_instance, "tools", None)
    if isinstance(tools_attr, dict):
        tools.update({str(name): tool for name, tool in tools_attr.items() if isinstance(name, str)})

    get_tools = getattr(server_instance, "get_tools", None)
    if callable(get_tools):
        try:
            result = get_tools()
        except TypeError:  # pragma: no cover - defensive
            result = None
        if asyncio.iscoroutine(result):
            resolved = _await_sync(result)
        else:
            resolved = result
        if isinstance(resolved, dict):
            tools.update({str(name): tool for name, tool in resolved.items() if isinstance(name, str)})

    return tools


def _resolve_tool_callable(tool: Any) -> Optional[Callable[..., Any]]:
    if tool is None:
        return None
    if hasattr(tool, "fn") and callable(getattr(tool, "fn")):
        return getattr(tool, "fn")
    if callable(tool):
        return tool
    return None


def _invoke_tool(tool: Any, ctx: _HealthcheckContext, **params: Any) -> Any:
    callable_fn = _resolve_tool_callable(tool)
    if callable_fn is None:
        raise TypeError(f"Tool object {tool!r} is not callable")

    result = callable_fn(ctx, **params)
    if inspect.isawaitable(result):
        return _await_sync(result)
    return result


def _validate_company_search_payload(
    payload: Any,
    *,
    logger: BoundLogger,
    expected_domain: Optional[str] = None,
) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.company_search.invalid_response", reason="not a dict")
        return False

    if payload.get("error"):
        logger.critical("healthcheck.company_search.api_error", error=str(payload["error"]))
        return False

    companies = payload.get("companies")
    if not isinstance(companies, list) or not companies:
        logger.critical("healthcheck.company_search.empty", reason="no companies returned")
        return False

    matched_domain = False
    for entry in companies:
        if not isinstance(entry, dict):
            logger.critical("healthcheck.company_search.invalid_company", reason="entry not dict")
            return False
        if not entry.get("guid") or not entry.get("name"):
            logger.critical("healthcheck.company_search.invalid_company", reason="missing guid/name", company=entry)
            return False
        domain_value = str(entry.get("domain") or "")
        if expected_domain and domain_value.lower() == expected_domain.lower():
            matched_domain = True

    count_value = payload.get("count")
    if not isinstance(count_value, int) or count_value <= 0:
        logger.critical("healthcheck.company_search.invalid_count", count=count_value)
        return False

    if expected_domain and not matched_domain:
        logger.critical(
            "healthcheck.company_search.domain_missing",
            expected=expected_domain,
        )
        return False

    return True


def _validate_rating_payload(payload: Any, *, logger: BoundLogger) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.rating.invalid_response", reason="not a dict")
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
        logger.critical("healthcheck.company_search_interactive.invalid_response", reason="not a dict")
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


def _validate_manage_subscriptions_payload(payload: Any, *, logger: BoundLogger, expected_guid: str) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.manage_subscriptions.invalid_response", reason="not a dict")
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


def _validate_request_company_payload(payload: Any, *, logger: BoundLogger, expected_domain: str) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.request_company.invalid_response", reason="not a dict")
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


def _run_company_search_diagnostics(
    *,
    context: str,
    logger: BoundLogger,
    tool: Any,
    failures: Optional[list[DiagnosticFailure]] = None,
    summary: Optional[Dict[str, Any]] = None,
) -> bool:
    tool_logger = logger.bind(tool="company_search")
    ctx = _HealthcheckContext(context=context, tool_name="company_search", logger=tool_logger)
    if summary is not None:
        summary.clear()
        summary["status"] = "pass"
        summary["modes"] = {}
    try:
        by_name = _invoke_tool(tool, ctx, name=_HEALTHCHECK_COMPANY_NAME)
    except Exception as exc:  # pragma: no cover - network failures
        tool_logger.critical("healthcheck.company_search.call_failed", error=str(exc))
        _record_failure(
            failures,
            tool="company_search",
            stage="call",
            mode="name",
            message="tool invocation failed",
            exception=exc,
        )
        if summary is not None:
            summary["status"] = "fail"
            summary["details"] = {
                "reason": "tool invocation failed",
                "mode": "name",
                "error": str(exc),
            }
            summary.setdefault("modes", {})["name"] = {
                "status": "fail",
                "error": str(exc),
            }
        return False

    if not _validate_company_search_payload(by_name, logger=tool_logger):
        _record_failure(
            failures,
            tool="company_search",
            stage="validation",
            mode="name",
            message="unexpected payload structure",
        )
        if summary is not None:
            summary["status"] = "fail"
            summary["details"] = {
                "reason": "unexpected payload structure",
                "mode": "name",
            }
            summary.setdefault("modes", {})["name"] = {
                "status": "fail",
                "detail": "unexpected payload structure",
            }
        return False

    if summary is not None:
        summary.setdefault("modes", {})["name"] = {"status": "pass"}

    try:
        by_domain = _invoke_tool(tool, ctx, domain=_HEALTHCHECK_COMPANY_DOMAIN)
    except Exception as exc:  # pragma: no cover - network failures
        tool_logger.critical("healthcheck.company_search.call_failed", mode="domain", error=str(exc))
        _record_failure(
            failures,
            tool="company_search",
            stage="call",
            mode="domain",
            message="tool invocation failed",
            exception=exc,
        )
        if summary is not None:
            summary["status"] = "fail"
            summary["details"] = {
                "reason": "tool invocation failed",
                "mode": "domain",
                "error": str(exc),
            }
            summary.setdefault("modes", {})["domain"] = {
                "status": "fail",
                "error": str(exc),
            }
        return False

    if not _validate_company_search_payload(
        by_domain,
        logger=tool_logger,
        expected_domain=_HEALTHCHECK_COMPANY_DOMAIN,
    ):
        _record_failure(
            failures,
            tool="company_search",
            stage="validation",
            mode="domain",
            message="unexpected payload structure",
        )
        if summary is not None:
            summary["status"] = "fail"
            summary["details"] = {
                "reason": "unexpected payload structure",
                "mode": "domain",
            }
            summary.setdefault("modes", {})["domain"] = {
                "status": "fail",
                "detail": "unexpected payload structure",
            }
        return False

    if summary is not None:
        summary.setdefault("modes", {})["domain"] = {"status": "pass"}

    tool_logger.info("healthcheck.company_search.success")
    return True


def _run_rating_diagnostics(
    *,
    context: str,
    logger: BoundLogger,
    tool: Any,
    failures: Optional[list[DiagnosticFailure]] = None,
    summary: Optional[Dict[str, Any]] = None,
) -> bool:
    tool_logger = logger.bind(tool="get_company_rating")
    ctx = _HealthcheckContext(context=context, tool_name="get_company_rating", logger=tool_logger)
    if summary is not None:
        summary.clear()
        summary["status"] = "pass"
    try:
        payload = _invoke_tool(tool, ctx, guid=_HEALTHCHECK_COMPANY_GUID)
    except Exception as exc:  # pragma: no cover - network failures
        tool_logger.critical("healthcheck.rating.call_failed", error=str(exc))
        _record_failure(
            failures,
            tool="get_company_rating",
            stage="call",
            message="tool invocation failed",
            exception=exc,
        )
        if summary is not None:
            summary["status"] = "fail"
            summary["details"] = {
                "reason": "tool invocation failed",
                "error": str(exc),
            }
        return False

    if not _validate_rating_payload(payload, logger=tool_logger):
        _record_failure(
            failures,
            tool="get_company_rating",
            stage="validation",
            message="unexpected payload structure",
        )
        if summary is not None:
            summary["status"] = "fail"
            summary["details"] = {"reason": "unexpected payload structure"}
        return False

    domain_value = payload.get("domain")
    if isinstance(domain_value, str) and domain_value.lower() != _HEALTHCHECK_COMPANY_DOMAIN:
        tool_logger.critical(
            "healthcheck.rating.domain_mismatch",
            domain=domain_value,
            expected=_HEALTHCHECK_COMPANY_DOMAIN,
        )
        _record_failure(
            failures,
            tool="get_company_rating",
            stage="validation",
            message="domain mismatch",
        )
        if summary is not None:
            summary["status"] = "fail"
            summary["details"] = {
                "reason": "domain mismatch",
                "domain": domain_value,
            }
        return False

    tool_logger.info("healthcheck.rating.success")
    return True


def _run_company_search_interactive_diagnostics(
    *,
    context: str,
    logger: BoundLogger,
    tool: Any,
    failures: Optional[list[DiagnosticFailure]] = None,
    summary: Optional[Dict[str, Any]] = None,
) -> bool:
    tool_logger = logger.bind(tool="company_search_interactive")
    ctx = _HealthcheckContext(
        context=context,
        tool_name="company_search_interactive",
        logger=tool_logger,
    )
    if summary is not None:
        summary.clear()
        summary["status"] = "pass"
    try:
        payload = _invoke_tool(tool, ctx, name=_HEALTHCHECK_COMPANY_NAME)
    except Exception as exc:  # pragma: no cover - network failures
        tool_logger.critical("healthcheck.company_search_interactive.call_failed", error=str(exc))
        _record_failure(
            failures,
            tool="company_search_interactive",
            stage="call",
            message="tool invocation failed",
            exception=exc,
        )
        if summary is not None:
            summary["status"] = "fail"
            summary["details"] = {
                "reason": "tool invocation failed",
                "error": str(exc),
            }
        return False

    if not _validate_company_search_interactive_payload(payload, logger=tool_logger):
        _record_failure(
            failures,
            tool="company_search_interactive",
            stage="validation",
            message="unexpected payload structure",
        )
        if summary is not None:
            summary["status"] = "fail"
            summary["details"] = {"reason": "unexpected payload structure"}
        return False

    tool_logger.info("healthcheck.company_search_interactive.success")
    return True


def _run_manage_subscriptions_diagnostics(
    *,
    context: str,
    logger: BoundLogger,
    tool: Any,
    failures: Optional[list[DiagnosticFailure]] = None,
    summary: Optional[Dict[str, Any]] = None,
) -> bool:
    tool_logger = logger.bind(tool="manage_subscriptions")
    ctx = _HealthcheckContext(context=context, tool_name="manage_subscriptions", logger=tool_logger)
    if summary is not None:
        summary.clear()
        summary["status"] = "pass"
    try:
        payload = _invoke_tool(
            tool,
            ctx,
            action="add",
            guids=[_HEALTHCHECK_COMPANY_GUID],
            dry_run=True,
        )
    except Exception as exc:  # pragma: no cover - network failures
        tool_logger.critical("healthcheck.manage_subscriptions.call_failed", error=str(exc))
        _record_failure(
            failures,
            tool="manage_subscriptions",
            stage="call",
            message="tool invocation failed",
            exception=exc,
        )
        if summary is not None:
            summary["status"] = "fail"
            summary["details"] = {
                "reason": "tool invocation failed",
                "error": str(exc),
            }
        return False

    if not _validate_manage_subscriptions_payload(
        payload,
        logger=tool_logger,
        expected_guid=_HEALTHCHECK_COMPANY_GUID,
    ):
        _record_failure(
            failures,
            tool="manage_subscriptions",
            stage="validation",
            message="unexpected payload structure",
        )
        if summary is not None:
            summary["status"] = "fail"
            summary["details"] = {"reason": "unexpected payload structure"}
        return False

    tool_logger.info("healthcheck.manage_subscriptions.success")
    return True


def _run_request_company_diagnostics(
    *,
    context: str,
    logger: BoundLogger,
    tool: Any,
    failures: Optional[list[DiagnosticFailure]] = None,
    summary: Optional[Dict[str, Any]] = None,
) -> bool:
    tool_logger = logger.bind(tool="request_company")
    ctx = _HealthcheckContext(context=context, tool_name="request_company", logger=tool_logger)
    if summary is not None:
        summary.clear()
        summary["status"] = "pass"
    try:
        payload = _invoke_tool(
            tool,
            ctx,
            domain=_HEALTHCHECK_REQUEST_DOMAIN,
            dry_run=True,
        )
    except Exception as exc:  # pragma: no cover - network failures
        tool_logger.critical("healthcheck.request_company.call_failed", error=str(exc))
        _record_failure(
            failures,
            tool="request_company",
            stage="call",
            message="tool invocation failed",
            exception=exc,
        )
        if summary is not None:
            summary["status"] = "fail"
            summary["details"] = {
                "reason": "tool invocation failed",
                "error": str(exc),
            }
        return False

    if not _validate_request_company_payload(
        payload,
        logger=tool_logger,
        expected_domain=_HEALTHCHECK_REQUEST_DOMAIN,
    ):
        _record_failure(
            failures,
            tool="request_company",
            stage="validation",
            message="unexpected payload structure",
        )
        if summary is not None:
            summary["status"] = "fail"
            summary["details"] = {"reason": "unexpected payload structure"}
        return False

    tool_logger.info("healthcheck.request_company.success")
    return True


def _run_context_tool_diagnostics(
    *,
    context: str,
    logger: BoundLogger,
    server_instance: Any,
    expected_tools: FrozenSet[str],
    summary: Optional[Dict[str, Dict[str, Any]]] = None,
    failures: Optional[list[DiagnosticFailure]] = None,
) -> bool:
    tools = _collect_tool_map(server_instance)
    success = True

    if summary is not None:
        for tool_name in expected_tools:
            summary.setdefault(
                tool_name,
                {
                    "status": "warning",
                    "details": {"reason": "not evaluated"},
                },
            )

    def _summary_entry(name: str) -> Optional[Dict[str, Any]]:
        if summary is None:
            return None
        return summary.setdefault(name, {})

    company_search_tool = tools.get("company_search")
    company_summary = _summary_entry("company_search")
    if company_search_tool is None:
        logger.critical("healthcheck.tool_missing", tool="company_search")
        _record_failure(
            failures,
            tool="company_search",
            stage="discovery",
            message="expected tool not registered",
        )
        if company_summary is not None:
            company_summary.clear()
            company_summary["status"] = "fail"
            company_summary["details"] = {"reason": "tool not registered"}
        success = False
    else:
        if company_summary is not None:
            company_summary.clear()
        if not _run_company_search_diagnostics(
            context=context,
            logger=logger,
            tool=company_search_tool,
            failures=failures,
            summary=company_summary,
        ):
            success = False

    rating_tool = tools.get("get_company_rating")
    rating_summary = _summary_entry("get_company_rating")
    if rating_tool is None:
        logger.critical("healthcheck.tool_missing", tool="get_company_rating")
        _record_failure(
            failures,
            tool="get_company_rating",
            stage="discovery",
            message="expected tool not registered",
        )
        if rating_summary is not None:
            rating_summary.clear()
            rating_summary["status"] = "fail"
            rating_summary["details"] = {"reason": "tool not registered"}
        success = False
    else:
        if rating_summary is not None:
            rating_summary.clear()
        if not _run_rating_diagnostics(
            context=context,
            logger=logger,
            tool=rating_tool,
            failures=failures,
            summary=rating_summary,
        ):
            success = False

    interactive_tool = tools.get("company_search_interactive")
    if interactive_tool is not None:
        interactive_summary = _summary_entry("company_search_interactive")
        if interactive_summary is not None:
            interactive_summary.clear()
        if not _run_company_search_interactive_diagnostics(
            context=context,
            logger=logger,
            tool=interactive_tool,
            failures=failures,
            summary=interactive_summary,
        ):
            success = False
    else:
        interactive_summary = _summary_entry("company_search_interactive")
        if interactive_summary is not None:
            interactive_summary.clear()
            interactive_summary["status"] = "warning"
            interactive_summary["details"] = {"reason": "tool not registered"}

    manage_tool = tools.get("manage_subscriptions")
    if manage_tool is not None:
        manage_summary = _summary_entry("manage_subscriptions")
        if manage_summary is not None:
            manage_summary.clear()
        if not _run_manage_subscriptions_diagnostics(
            context=context,
            logger=logger,
            tool=manage_tool,
            failures=failures,
            summary=manage_summary,
        ):
            success = False
    else:
        manage_summary = _summary_entry("manage_subscriptions")
        if manage_summary is not None:
            manage_summary.clear()
            manage_summary["status"] = "warning"
            manage_summary["details"] = {"reason": "tool not registered"}

    request_tool = tools.get("request_company")
    if request_tool is not None:
        request_summary = _summary_entry("request_company")
        if request_summary is not None:
            request_summary.clear()
        if not _run_request_company_diagnostics(
            context=context,
            logger=logger,
            tool=request_tool,
            failures=failures,
            summary=request_summary,
        ):
            success = False
    else:
        request_summary = _summary_entry("request_company")
        if request_summary is not None:
            request_summary.clear()
            request_summary["status"] = "warning"
            request_summary["details"] = {"reason": "tool not registered"}

    return success


def _prepare_server(runtime_settings, logger, **create_kwargs):
    logger.info("Preparing BiRRe FastMCP server")
    return create_birre_server(
        settings=runtime_settings,
        logger=logger,
        **create_kwargs,
    )


@app.command(
    help="Start the BiRRe FastMCP server with BitSight connectivity."
)
def run(
    config: ConfigPathOption = Path(DEFAULT_CONFIG_FILENAME),
    bitsight_api_key: BitsightApiKeyOption = None,
    subscription_folder: SubscriptionFolderOption = None,
    subscription_type: SubscriptionTypeOption = None,
    skip_startup_checks: SkipStartupChecksOption = None,
    debug: DebugOption = None,
    allow_insecure_tls: AllowInsecureTlsOption = None,
    ca_bundle: CaBundleOption = None,
    context: ContextOption = None,
    risk_vector_filter: RiskVectorFilterOption = None,
    max_findings: MaxFindingsOption = None,
    log_level: LogLevelOption = None,
    log_format: LogFormatOption = None,
    log_file: LogFileOption = None,
    log_max_bytes: LogMaxBytesOption = None,
    log_backup_count: LogBackupCountOption = None,
    profile: ProfilePathOption = None,
) -> None:
    """Start the BiRRe FastMCP server with the configured runtime options."""
    invocation = _build_invocation(
        config_path=str(config) if config is not None else None,
        api_key=bitsight_api_key,
        subscription_folder=subscription_folder,
        subscription_type=subscription_type,
        context=context,
        debug=debug,
        risk_vector_filter=risk_vector_filter,
        max_findings=max_findings,
        skip_startup_checks=skip_startup_checks,
        allow_insecure_tls=allow_insecure_tls,
        ca_bundle=ca_bundle,
        log_level=log_level,
        log_format=log_format,
        log_file=log_file,
        log_max_bytes=log_max_bytes,
        log_backup_count=log_backup_count,
        profile_path=profile,
    )

    runtime_settings, logging_settings, _ = _resolve_runtime_and_logging(invocation)
    logger = _initialize_logging(runtime_settings, logging_settings, show_banner=True)

    if not _run_offline_checks(runtime_settings, logger):
        raise typer.Exit(code=1)

    try:
        online_ok = _run_online_checks(runtime_settings, logger)
    except BirreError as exc:
        logger.critical(
            "Online startup checks failed; aborting startup",
            **exc.log_fields(),
        )
        raise typer.Exit(code=1) from exc
    if not online_ok:
        logger.critical("Online startup checks failed; aborting startup")
        raise typer.Exit(code=1)

    server = _prepare_server(runtime_settings, logger)

    logger.info("Starting BiRRe FastMCP server")
    try:
        if invocation.profile_path is not None:
            invocation.profile_path.parent.mkdir(parents=True, exist_ok=True)
            profiler = cProfile.Profile()
            profiler.enable()
            try:
                server.run()
            finally:
                profiler.disable()
                profiler.dump_stats(str(invocation.profile_path))
                logger.info("Profiling data written", profile=str(invocation.profile_path))
        else:
            server.run()
    except KeyboardInterrupt:
        stderr_console.print(_keyboard_interrupt_banner())
        logger.info("BiRRe FastMCP server stopped via KeyboardInterrupt")


@app.command(help="Run BiRRe self tests without starting the FastMCP server.")
def selftest(
    config: ConfigPathOption = Path(DEFAULT_CONFIG_FILENAME),
    bitsight_api_key: BitsightApiKeyOption = None,
    subscription_folder: SubscriptionFolderOption = None,
    subscription_type: SubscriptionTypeOption = None,
    debug: DebugOption = None,
    allow_insecure_tls: AllowInsecureTlsOption = None,
    ca_bundle: CaBundleOption = None,
    risk_vector_filter: RiskVectorFilterOption = None,
    max_findings: MaxFindingsOption = None,
    log_level: LogLevelOption = None,
    log_format: LogFormatOption = None,
    log_file: LogFileOption = None,
    log_max_bytes: LogMaxBytesOption = None,
    log_backup_count: LogBackupCountOption = None,
    offline: OfflineFlagOption = False,
    production: ProductionFlagOption = False,
) -> None:
    """Execute BiRRe diagnostics and optional online checks."""

    invocation = _build_invocation(
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

    runtime_settings, logging_settings, _ = _resolve_runtime_and_logging(invocation)
    logger = _initialize_logging(runtime_settings, logging_settings, show_banner=False)

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
    if offline:
        logger.info("Offline mode enabled; skipping online diagnostics")

    runner = HealthcheckRunner(
        runtime_settings=runtime_settings,
        logger=logger,
        offline=bool(offline),
        target_base_url=target_base_url,
        environment_label=environment_label,
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


def _prompt_str(prompt: str, default: Optional[str], secret: bool = False) -> Optional[str]:
    value = typer.prompt(prompt, default=default or "", hide_input=secret).strip()
    return value or None


def _collect_or_prompt_string(
    provided: Optional[str],
    *,
    prompt: str,
    default: Optional[str],
    secret: bool = False,
    required: bool = False,
    normalizer: Optional[Callable[[Optional[str]], Optional[str]]] = None,
) -> Optional[str]:
    """Return a CLI-provided string or interactively prompt for one."""

    def _apply(value: Optional[str]) -> Optional[str]:
        cleaned = _clean_string(value)
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
        try:
            normalized = _apply(response)
        except typer.BadParameter as exc:  # pragma: no cover - defensive; normalizer raises
            stdout_console.print(f"[red]{exc}[/red]")
            continue

        if normalized is None and required:
            stdout_console.print("[red]A value is required.[/red]")
            continue
        return normalized


def _generate_local_config_content(values: Dict[str, Any], *, include_header: bool = True) -> str:
    def format_value(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, (list, tuple)):
            formatted = ", ".join(format_value(item) for item in value)
            return f"[{formatted}]"
        if value is None:
            return ""  # Should not be serialized
        escaped = (
            str(value)
            .replace("\\", "\\\\")
            .replace("\"", "\\\"")
        )
        return f'"{escaped}"'

    lines: list[str] = []
    if include_header:
        lines.append("## Generated local configuration")

    for section, section_values in sorted(values.items()):
        if not isinstance(section_values, dict) or not section_values:
            continue
        lines.append("")
        lines.append(f"[{section}]")
        for key, entry in sorted(section_values.items()):
            if entry is None:
                continue
            if isinstance(entry, str) and not entry.strip():
                continue
            lines.append(f"{key} = {format_value(entry)}")
    lines.append("")
    return "\n".join(lines)


@config_app.command(
    "init",
    help="Interactively create or update a local BiRRe configuration file.",
)
def config_init(
    output: LocalConfOutputOption = Path(LOCAL_CONFIG_FILENAME),
    config_path: ConfigPathOption = Path(LOCAL_CONFIG_FILENAME),
    subscription_type: SubscriptionTypeOption = None,
    debug: DebugOption = None,
    overwrite: OverwriteOption = False,
) -> None:
    """Guide the user through generating a configuration file."""

    ctx = click.get_current_context()
    config_source = ctx.get_parameter_source("config_path")
    destination = Path(config_path if config_source is ParameterSource.COMMANDLINE else output)

    if destination.exists():
        if overwrite:
            stdout_console.print(
                f"[yellow]Overwriting existing configuration at[/yellow] {destination}"
            )
        else:
            stdout_console.print(
                f"[yellow]{destination} already exists.[/yellow]"
            )
            if not typer.confirm("Overwrite this file?", default=False):
                stdout_console.print(
                    "[red]Aborted without changing the existing configuration.[/red]"
                )
                raise typer.Exit(code=1)

    defaults_settings = load_settings(str(config_path) if config_source is ParameterSource.COMMANDLINE else None)
    default_subscription_folder = defaults_settings.get(BITSIGHT_SUBSCRIPTION_FOLDER_KEY)
    default_subscription_type = defaults_settings.get(BITSIGHT_SUBSCRIPTION_TYPE_KEY)
    default_context = defaults_settings.get(ROLE_CONTEXT_KEY, "standard")
    default_debug = bool(defaults_settings.get(RUNTIME_DEBUG_KEY, False))

    summary_rows: list[tuple[str, str, str]] = []

    def add_summary(dotted_key: str, value: Any, source: str) -> None:
        if value in (None, ""):
            return
        display_value = _format_display_value(dotted_key, value)
        summary_rows.append((dotted_key, display_value, source))

    stdout_console.print("[bold]BiRRe local configuration generator[/bold]")

    api_key = _collect_or_prompt_string(
        None,
        prompt="BitSight API key",
        default=None,
        secret=True,
        required=True,
    )
    add_summary(BITSIGHT_API_KEY_KEY, api_key, SOURCE_USER_INPUT)

    default_subscription_folder_str = (
        str(default_subscription_folder)
        if default_subscription_folder is not None
        else ""
    )
    subscription_folder = _collect_or_prompt_string(
        None,
        prompt="Default subscription folder",
        default=default_subscription_folder_str,
    )
    if subscription_folder is not None:
        folder_source = (
            "Default"
            if default_subscription_folder_str
            and subscription_folder == default_subscription_folder_str
            else SOURCE_USER_INPUT
        )
        add_summary(BITSIGHT_SUBSCRIPTION_FOLDER_KEY, subscription_folder, folder_source)

    default_subscription_type_str = (
        str(default_subscription_type)
        if default_subscription_type is not None
        else ""
    )
    subscription_type_value = _collect_or_prompt_string(
        subscription_type,
        prompt="Default subscription type",
        default=default_subscription_type_str,
    )
    if subscription_type_value is not None:
        if subscription_type is not None:
            type_source = "CLI Option"
        else:
            type_source = (
                "Default"
                if default_subscription_type_str
                and subscription_type_value == default_subscription_type_str
                else SOURCE_USER_INPUT
            )
        add_summary(BITSIGHT_SUBSCRIPTION_TYPE_KEY, subscription_type_value, type_source)

    default_context_str = str(default_context or "standard")
    default_context_normalized = (
        _normalize_context(default_context_str) or _clean_string(default_context_str)
    )
    context_value = _collect_or_prompt_string(
        None,
        prompt="Default persona (standard or risk_manager)",
        default=default_context_str,
        normalizer=_normalize_context,
    )
    if context_value is not None:
        context_source = (
            "Default"
            if default_context_normalized is not None
            and context_value == default_context_normalized
            else SOURCE_USER_INPUT
        )
        add_summary(ROLE_CONTEXT_KEY, context_value, context_source)

    if debug is not None:
        debug_value = debug
        add_summary(RUNTIME_DEBUG_KEY, debug_value, "CLI Option")
    else:
        debug_value = _prompt_bool("Enable debug mode?", default=default_debug)
        debug_source = "Default" if debug_value == default_debug else SOURCE_USER_INPUT
        add_summary(RUNTIME_DEBUG_KEY, debug_value, debug_source)

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

    serializable: Dict[str, Dict[str, Any]] = {}
    for section, section_values in generated.items():
        filtered = {k: v for k, v in section_values.items() if v not in (None, "")}
        if filtered:
            serializable[section] = filtered

    if not serializable:
        stdout_console.print(
            "[red]No values provided; aborting local configuration generation.[/red]"
        )
        raise typer.Exit(code=1)

    if summary_rows:
        summary_rows.sort(key=lambda entry: entry[0])
        preview = Table(title="Local configuration preview")
        preview.add_column("Config Key", style=_RichStyles.ACCENT)
        preview.add_column("Value", style=_RichStyles.SECONDARY)
        preview.add_column("Source", style=_RichStyles.SUCCESS)
        for dotted_key, display_value, source in summary_rows:
            preview.add_row(dotted_key, display_value, source)
        stdout_console.print()
        stdout_console.print(preview)

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


def _resolve_settings_files(config_path: Optional[str]) -> Tuple[Path, ...]:
    return resolve_config_file_candidates(config_path)


def _resolve_logging_settings_from_cli(
    *,
    config_path: Optional[Path],
    log_level: Optional[str],
    log_format: Optional[str],
    log_file: Optional[str],
    log_max_bytes: Optional[int],
    log_backup_count: Optional[int],
) -> Tuple[_CliInvocation, Any]:
    invocation = _build_invocation(
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
    _, logging_settings, _ = _resolve_runtime_and_logging(invocation)
    return invocation, logging_settings


_RELATIVE_DURATION_PATTERN = re.compile(r"^\s*(\d+)([smhd])\s*$", re.IGNORECASE)


def _parse_iso_timestamp_to_epoch(value: str) -> Optional[float]:
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


def _parse_relative_duration(value: str) -> Optional[timedelta]:
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


def _parse_log_line(line: str, format_hint: str) -> _LogViewLine:
    stripped = line.rstrip("\n")
    if format_hint == "json":
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            return _LogViewLine(raw=stripped, level=None, timestamp=None, json_data=None)
        timestamp = None
        for key in ("timestamp", "time", "@timestamp", "ts"):
            value = data.get(key)
            if isinstance(value, str):
                timestamp = _parse_iso_timestamp_to_epoch(value)
                if timestamp is not None:
                    break
        level_value = data.get("level") or data.get("levelname") or data.get("severity")
        if isinstance(level_value, str):
            level = _LOG_LEVEL_MAP.get(level_value.strip().upper())
        elif isinstance(level_value, int):
            level = level_value
        else:
            level = None
        return _LogViewLine(raw=stripped, level=level, timestamp=timestamp, json_data=data)

    timestamp = None
    level = None
    tokens = stripped.split()
    if tokens:
        timestamp = _parse_iso_timestamp_to_epoch(tokens[0].strip("[]"))
        for token in tokens[:3]:
            candidate = _LOG_LEVEL_MAP.get(token.strip("[]:,").upper())
            if candidate is not None:
                level = candidate
                break
    return _LogViewLine(raw=stripped, level=level, timestamp=timestamp, json_data=None)


@config_app.command(
    "show",
    help=(
        "Inspect configuration sources and resolved settings.\n\n"
        "Example: python server.py config show --config custom.toml"
    ),
)
def config_show(
    config: ConfigPathOption = Path(DEFAULT_CONFIG_FILENAME),
    bitsight_api_key: BitsightApiKeyOption = None,
    subscription_folder: SubscriptionFolderOption = None,
    subscription_type: SubscriptionTypeOption = None,
    context: ContextOption = None,
    debug: DebugOption = None,
    allow_insecure_tls: AllowInsecureTlsOption = None,
    ca_bundle: CaBundleOption = None,
    risk_vector_filter: RiskVectorFilterOption = None,
    max_findings: MaxFindingsOption = None,
    log_level: LogLevelOption = None,
    log_format: LogFormatOption = None,
    log_file: LogFileOption = None,
    log_max_bytes: LogMaxBytesOption = None,
    log_backup_count: LogBackupCountOption = None,
) -> None:
    """Display configuration files, overrides, and effective values as Rich tables."""
    invocation = _build_invocation(
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

    runtime_settings, logging_settings, _ = _resolve_runtime_and_logging(invocation)
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
        key: label for key, label in _build_cli_source_labels(invocation).items() if key not in env_labels
    }
    cli_rows = [row for row in _build_cli_override_rows(invocation) if row[0] not in env_labels]
    if cli_rows:
        stdout_console.print()
        _print_config_table("CLI overrides", cli_rows)

    effective_values = _effective_configuration_values(runtime_settings, logging_settings)
    effective_rows: list[Tuple[str, str, str]] = []
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
    config: Optional[Path] = typer.Option(
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
    debug: DebugOption = None,
    minimize: MinimizeOption = False,
) -> None:
    """Validate configuration syntax and optionally rewrite it in minimal form."""
    ctx = click.get_current_context()
    config_source = ctx.get_parameter_source("config")
    if config is None and config_source is ParameterSource.DEFAULT:
        typer.echo(ctx.get_help())
        raise typer.Exit()
    if config is None:
        raise typer.BadParameter("Configuration path could not be determined.", param_hint="--config")

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
            f"[green]Minimized configuration written to[/green] {config} [dim](backup: {backup_path})[/dim]"
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
    config: ConfigPathOption = Path(DEFAULT_CONFIG_FILENAME),
    log_file: LogFileOption = None,
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
    config: ConfigPathOption = Path(DEFAULT_CONFIG_FILENAME),
    log_file: LogFileOption = None,
    log_backup_count: LogBackupCountOption = None,
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
    config: ConfigPathOption = Path(DEFAULT_CONFIG_FILENAME),
    log_file: LogFileOption = None,
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


@logs_app.command(
    "show",
    help="Display recent log entries with optional level and time filtering.",
)
def logs_show(
    config: ConfigPathOption = Path(DEFAULT_CONFIG_FILENAME),
    log_file: LogFileOption = None,
    level: Optional[str] = typer.Option(
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
    since: Optional[str] = typer.Option(
        None,
        "--since",
        help="Only include entries at or after the given ISO 8601 timestamp.",
        rich_help_panel="Filtering",
    ),
    last: Optional[str] = typer.Option(
        None,
        "--last",
        help="Only include entries from the relative window (e.g. 1h, 30m).",
        rich_help_panel="Filtering",
    ),
    format_override: Optional[str] = typer.Option(
        None,
        "--format",
        case_sensitive=False,
        help="Treat log entries as 'json' or 'text'. Defaults to the configured format.",
        rich_help_panel="Presentation",
    ),
) -> None:
    """Render log entries to stdout."""
    if tail < 0:
        raise typer.BadParameter("Tail must be greater than or equal to zero.", param_hint="--tail")
    if since and last:
        raise typer.BadParameter("Only one of --since or --last can be provided.", param_hint="--since")

    normalized_level = _normalize_log_level(level) if level is not None else None
    level_threshold = _LOG_LEVEL_MAP.get(normalized_level) if normalized_level else None

    if format_override is not None:
        normalized_format = format_override.strip().lower()
        if normalized_format not in _LOG_FORMAT_CHOICES:
            raise typer.BadParameter("Format must be either 'text' or 'json'.", param_hint="--format")
    else:
        normalized_format = None

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

    start_timestamp: Optional[float] = None
    if since:
        start_timestamp = _parse_iso_timestamp_to_epoch(since)
        if start_timestamp is None:
            raise typer.BadParameter("Invalid ISO 8601 timestamp.", param_hint="--since")
    elif last:
        duration = _parse_relative_duration(last)
        if duration is None:
            raise typer.BadParameter("Invalid relative duration; use values like 30m, 1h, or 2d.", param_hint="--last")
        start_timestamp = (datetime.now(timezone.utc) - duration).timestamp()

    matched: List[_LogViewLine] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            parsed = _parse_log_line(line, resolved_format)
            if level_threshold is not None:
                if parsed.level is not None:
                    if parsed.level < level_threshold:
                        continue
                else:
                    if normalized_level not in parsed.raw.upper():
                        continue
            if start_timestamp is not None:
                if parsed.timestamp is None or parsed.timestamp < start_timestamp:
                    continue
            matched.append(parsed)

    if tail and tail > 0:
        matched = matched[-tail:]

    if not matched:
        stdout_console.print("[yellow]No log entries matched the supplied filters[/yellow]")
        return

    for entry in matched:
        if resolved_format == "json" and entry.json_data is not None:
            stdout_console.print_json(data=entry.json_data)
        else:
            stdout_console.print(entry.raw, markup=False, highlight=False)


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


def main(argv: Optional[Sequence[str]] = None) -> None:
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
