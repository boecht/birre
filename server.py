"""BiRRe FastMCP server Typer CLI entrypoint."""

from __future__ import annotations

import asyncio
import cProfile
import inspect
import logging
import os
import shutil
import sys
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import (
    Annotated,
    Any,
    Awaitable,
    Callable,
    Dict,
    FrozenSet,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    Final,
)
from uuid import uuid4

import typer
from rich.console import Console
from rich import box
from rich.table import Table
from rich.text import Text
from typer.main import get_command

# FastMCP checks this flag during import time, so ensure it is enabled before
# importing any modules that depend on FastMCP.
os.environ["FASTMCP_EXPERIMENTAL_ENABLE_NEW_OPENAPI_PARSER"] = "true"

from src.apis.clients import DEFAULT_V1_API_BASE_URL
from src.birre import create_birre_server
from src.constants import DEFAULT_CONFIG_FILENAME, LOCAL_CONFIG_FILENAME
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
    runtime_from_settings,
)
from src.startup_checks import run_offline_startup_checks, run_online_startup_checks

PROJECT_ROOT = Path(__file__).resolve().parent

stderr_console = Console(stderr=True)
stdout_console = Console(stderr=False)

app = typer.Typer(
    help="Model Context Protocol server for BitSight rating retrieval",
    rich_markup_mode="rich",
)

_CLI_PROG_NAME = Path(__file__).name
_CONTEXT_CHOICES = {"standard", "risk_manager"}
_LOG_FORMAT_CHOICES = {"text", "json"}
_LOG_LEVEL_CHOICES = sorted(
    name
    for name, value in logging.getLevelNamesMapping().items()
    if isinstance(name, str) and not name.isdigit()
)
_LOG_LEVEL_SET = {choice.upper() for choice in _LOG_LEVEL_CHOICES}

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
        "--skip-startup-checks/--no-skip-startup-checks",
        help="Skip BitSight online startup checks",
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
        help="Path to a log file (use '-', none, or stderr to disable)",
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
        "--offline",
        help="Skip BitSight network checks and run offline validation only",
        rich_help_panel="Diagnostics",
        is_flag=True,
    ),
]

ProductionFlagOption = Annotated[
    bool,
    typer.Option(
        "--production",
        help="Use the BitSight production API for online validation",
        rich_help_panel="Diagnostics",
        is_flag=True,
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
    table.add_column("Config Key", style="bold cyan")
    table.add_column("Resolved Value", overflow="fold")
    table.add_column("Source", style="magenta")
    for key, value, source in rows:
        table.add_row(key, value, source)
    stdout_console.print(table)


class LogResetMode(str, Enum):
    """Supported log reset strategies."""

    ROTATE = "rotate"
    CLEAR = "clear"

    def __str__(self) -> str:  # pragma: no cover - Typer uses __str__ for help text
        return self.value


LogResetModeOption = Annotated[
    LogResetMode,
    typer.Option(
        "--mode",
        case_sensitive=False,
        help="Log reset strategy: 'rotate' to perform log rotation or 'clear' to truncate the active log file",
        rich_help_panel="Logging",
    ),
]


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


def _run_online_checks(runtime_settings, logger, server) -> bool:
    logger.info("Running online startup checks")
    call_v1_tool = getattr(server, "call_v1_tool", None)
    return asyncio.run(
        run_online_startup_checks(
            call_v1_tool=call_v1_tool,
            subscription_folder=runtime_settings.subscription_folder,
            subscription_type=runtime_settings.subscription_type,
            logger=logger,
            skip_startup_checks=getattr(runtime_settings, "skip_startup_checks", False),
        )
    )


def _initialize_logging(runtime_settings, logging_settings, *, show_banner: bool = True):
    if show_banner:
        stderr_console.print(_banner())
    configure_logging(logging_settings)
    logger = get_logger("birre")
    _emit_runtime_messages(runtime_settings, logger)
    return logger


def _await_sync(coro: Awaitable[Any]) -> Any:
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)
        finally:
            asyncio.set_event_loop(None)
            loop.close()


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
) -> bool:
    tool_logger = logger.bind(tool="company_search")
    ctx = _HealthcheckContext(context=context, tool_name="company_search", logger=tool_logger)
    try:
        by_name = _invoke_tool(tool, ctx, name=_HEALTHCHECK_COMPANY_NAME)
    except Exception as exc:  # pragma: no cover - network failures
        tool_logger.critical("healthcheck.company_search.call_failed", error=str(exc))
        return False

    if not _validate_company_search_payload(by_name, logger=tool_logger):
        return False

    try:
        by_domain = _invoke_tool(tool, ctx, domain=_HEALTHCHECK_COMPANY_DOMAIN)
    except Exception as exc:  # pragma: no cover - network failures
        tool_logger.critical("healthcheck.company_search.call_failed", mode="domain", error=str(exc))
        return False

    if not _validate_company_search_payload(
        by_domain,
        logger=tool_logger,
        expected_domain=_HEALTHCHECK_COMPANY_DOMAIN,
    ):
        return False

    tool_logger.info("healthcheck.company_search.success")
    return True


def _run_rating_diagnostics(
    *,
    context: str,
    logger: BoundLogger,
    tool: Any,
) -> bool:
    tool_logger = logger.bind(tool="get_company_rating")
    ctx = _HealthcheckContext(context=context, tool_name="get_company_rating", logger=tool_logger)
    try:
        payload = _invoke_tool(tool, ctx, guid=_HEALTHCHECK_COMPANY_GUID)
    except Exception as exc:  # pragma: no cover - network failures
        tool_logger.critical("healthcheck.rating.call_failed", error=str(exc))
        return False

    if not _validate_rating_payload(payload, logger=tool_logger):
        return False

    domain_value = payload.get("domain")
    if isinstance(domain_value, str) and domain_value.lower() != _HEALTHCHECK_COMPANY_DOMAIN:
        tool_logger.critical(
            "healthcheck.rating.domain_mismatch",
            domain=domain_value,
            expected=_HEALTHCHECK_COMPANY_DOMAIN,
        )
        return False

    tool_logger.info("healthcheck.rating.success")
    return True


def _run_company_search_interactive_diagnostics(
    *,
    context: str,
    logger: BoundLogger,
    tool: Any,
) -> bool:
    tool_logger = logger.bind(tool="company_search_interactive")
    ctx = _HealthcheckContext(
        context=context,
        tool_name="company_search_interactive",
        logger=tool_logger,
    )
    try:
        payload = _invoke_tool(tool, ctx, name=_HEALTHCHECK_COMPANY_NAME)
    except Exception as exc:  # pragma: no cover - network failures
        tool_logger.critical("healthcheck.company_search_interactive.call_failed", error=str(exc))
        return False

    if not _validate_company_search_interactive_payload(payload, logger=tool_logger):
        return False

    tool_logger.info("healthcheck.company_search_interactive.success")
    return True


def _run_manage_subscriptions_diagnostics(
    *,
    context: str,
    logger: BoundLogger,
    tool: Any,
) -> bool:
    tool_logger = logger.bind(tool="manage_subscriptions")
    ctx = _HealthcheckContext(context=context, tool_name="manage_subscriptions", logger=tool_logger)
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
        return False

    if not _validate_manage_subscriptions_payload(
        payload,
        logger=tool_logger,
        expected_guid=_HEALTHCHECK_COMPANY_GUID,
    ):
        return False

    tool_logger.info("healthcheck.manage_subscriptions.success")
    return True


def _run_request_company_diagnostics(
    *,
    context: str,
    logger: BoundLogger,
    tool: Any,
) -> bool:
    tool_logger = logger.bind(tool="request_company")
    ctx = _HealthcheckContext(context=context, tool_name="request_company", logger=tool_logger)
    try:
        payload = _invoke_tool(
            tool,
            ctx,
            domain=_HEALTHCHECK_REQUEST_DOMAIN,
            dry_run=True,
        )
    except Exception as exc:  # pragma: no cover - network failures
        tool_logger.critical("healthcheck.request_company.call_failed", error=str(exc))
        return False

    if not _validate_request_company_payload(
        payload,
        logger=tool_logger,
        expected_domain=_HEALTHCHECK_REQUEST_DOMAIN,
    ):
        return False

    tool_logger.info("healthcheck.request_company.success")
    return True


def _run_context_tool_diagnostics(
    *,
    context: str,
    logger: BoundLogger,
    server_instance: Any,
) -> bool:
    tools = _collect_tool_map(server_instance)
    success = True

    company_search_tool = tools.get("company_search")
    if company_search_tool is None:
        logger.critical("healthcheck.tool_missing", tool="company_search")
        success = False
    else:
        if not _run_company_search_diagnostics(context=context, logger=logger, tool=company_search_tool):
            success = False

    rating_tool = tools.get("get_company_rating")
    if rating_tool is None:
        logger.critical("healthcheck.tool_missing", tool="get_company_rating")
        success = False
    else:
        if not _run_rating_diagnostics(context=context, logger=logger, tool=rating_tool):
            success = False

    interactive_tool = tools.get("company_search_interactive")
    if interactive_tool is not None:
        if not _run_company_search_interactive_diagnostics(
            context=context,
            logger=logger,
            tool=interactive_tool,
        ):
            success = False

    manage_tool = tools.get("manage_subscriptions")
    if manage_tool is not None:
        if not _run_manage_subscriptions_diagnostics(
            context=context,
            logger=logger,
            tool=manage_tool,
        ):
            success = False

    request_tool = tools.get("request_company")
    if request_tool is not None:
        if not _run_request_company_diagnostics(
            context=context,
            logger=logger,
            tool=request_tool,
        ):
            success = False

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
        config_path=config,
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

    server = _prepare_server(runtime_settings, logger)
    online_ok = _run_online_checks(runtime_settings, logger, server)
    if not online_ok:
        logger.critical("Online startup checks failed; aborting startup")
        raise typer.Exit(code=1)

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


@app.command(help="Run BiRRe health checks without starting the FastMCP server.")
def healthcheck(
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
        config_path=config,
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

    if not _run_offline_checks(runtime_settings, logger):
        raise typer.Exit(code=1)

    contexts = sorted(_CONTEXT_CHOICES)
    overall_success = True

    for context_name in contexts:
        context_logger = logger.bind(context=context_name)
        context_settings = replace(runtime_settings, context=context_name)

        context_logger.info("Preparing context diagnostics")
        server_instance = _prepare_server(
            context_settings,
            context_logger,
            v1_base_url=target_base_url,
        )

        expected_tools = _EXPECTED_TOOLS_BY_CONTEXT.get(context_name)
        if expected_tools is None:
            context_logger.critical("No expected tool inventory defined for context")
            overall_success = False
        else:
            discovered_tools = _discover_context_tools(server_instance)
            missing_tools = sorted(expected_tools - discovered_tools)
            if missing_tools:
                context_logger.critical(
                    "Tool discovery failed",
                    missing_tools=missing_tools,
                    discovered=sorted(discovered_tools),
                )
                overall_success = False
            else:
                context_logger.info(
                    "Tool discovery succeeded",
                    tools=sorted(discovered_tools),
                )

        if not offline:
            online_ok = _run_online_checks(context_settings, context_logger, server_instance)
            if not online_ok:
                overall_success = False
            else:
                if not _run_context_tool_diagnostics(
                    context=context_name,
                    logger=context_logger,
                    server_instance=server_instance,
                ):
                    overall_success = False
        else:
            context_logger.info("Online checks skipped", reason="offline flag")

    if not overall_success:
        logger.critical("Health checks failed")
        raise typer.Exit(code=1)

    logger.info(
        "Health checks completed successfully",
        contexts=contexts,
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


@app.command(
    help="Interactively create or update a local BiRRe configuration file."
)
def local_conf_create(
    output: LocalConfOutputOption = Path(LOCAL_CONFIG_FILENAME),
    subscription_type: SubscriptionTypeOption = None,
    debug: DebugOption = None,
    overwrite: OverwriteOption = False,
) -> None:
    """Guide the user through generating a config.local.toml file."""

    if output.exists():
        if overwrite:
            stdout_console.print(
                f"[yellow]Overwriting existing configuration at[/yellow] {output}"
            )
        else:
            stdout_console.print(
                f"[yellow]{output} already exists.[/yellow]"
            )
            if not typer.confirm("Overwrite this file?", default=False):
                stdout_console.print(
                    "[red]Aborted without changing the existing configuration.[/red]"
                )
                raise typer.Exit(code=1)

    defaults_settings = load_settings(DEFAULT_CONFIG_FILENAME)
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
        preview.add_column("Config Key", style="cyan")
        preview.add_column("Value", style="magenta")
        preview.add_column("Source", style="green")
        for dotted_key, display_value, source in summary_rows:
            preview.add_row(dotted_key, display_value, source)
        stdout_console.print()
        stdout_console.print(preview)

    content = _generate_local_config_content(serializable)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        output.write_text(content, encoding="utf-8")
    except OSError as error:
        stdout_console.print(
            f"[red]Failed to write configuration:[/red] {error}"
        )
        raise typer.Exit(code=1) from error

    stdout_console.print(f"[green]Local configuration saved to[/green] {output}")


def _resolve_settings_files(config_path: Optional[str]) -> Tuple[Path, ...]:
    if config_path:
        config_file = Path(config_path)
        local_file = config_file.with_name(f"{config_file.stem}.local{config_file.suffix}")
        files: list[Path] = []
        if config_file.exists():
            files.append(config_file)
        if local_file.exists():
            files.append(local_file)
        if not files:
            files.append(config_file)
        return tuple(files)
    return (
        Path(DEFAULT_CONFIG_FILENAME),
        Path(LOCAL_CONFIG_FILENAME),
    )


@app.command(
    help=(
        "Inspect configuration sources and resolved settings.\n\n"
        "Example: python server.py check-conf --config custom.toml"
    )
)
def check_conf(
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
        config_path=config,
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
    files_table.add_column("File", style="bold cyan")
    files_table.add_column("Status", style="magenta")
    for file in files:
        status = "exists" if file.exists() else "missing"
        files_table.add_row(str(file), status)
    stdout_console.print(files_table)

    env_overrides = {
        name: os.getenv(name)
        for name in (
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


@app.command(help="Validate or minimize a BiRRe configuration file before use.")
def lint_config(
    config_file: Path = typer.Argument(..., help="Configuration TOML file to validate"),
    debug: DebugOption = None,
    minimize: MinimizeOption = False,
) -> None:
    """Validate configuration syntax and optionally rewrite it in minimal form."""
    if not config_file.exists():
        raise typer.BadParameter(f"{config_file} does not exist", param_hint="config-file")

    import tomllib

    try:
        with config_file.open("rb") as handle:
            parsed = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise typer.BadParameter(f"Invalid TOML: {exc}") from exc

    allowed_sections = {"bitsight", "runtime", "roles", "logging"}
    warnings: list[str] = []
    for section in parsed:
        if section not in allowed_sections:
            warnings.append(f"Unknown section '{section}' will be ignored by BiRRe")

    stdout_console.print(f"[green]TOML parsing succeeded[/green] for {config_file}")
    if warnings:
        stdout_console.print("[yellow]Warnings:[/yellow]")
        for warning in warnings:
            stdout_console.print(f"- {warning}")

    if debug:
        stdout_console.print("\n[bold]Parsed data[/bold]")
        stdout_console.print(parsed)

    if minimize:
        minimized = _generate_local_config_content(parsed, include_header=False)
        backup_path = config_file.with_suffix(f"{config_file.suffix}.bak")
        shutil.copy2(config_file, backup_path)
        config_file.write_text(minimized, encoding="utf-8")
        stdout_console.print(
            f"[green]Minimized configuration written to[/green] {config_file} [dim](backup: {backup_path})[/dim]"
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


@app.command(
    help=(
        "Rotate or clear BiRRe log files based on the selected mode.\n\n"
        "Example: python server.py reset-logs --log-file server.log --mode rotate"
    )
)
def reset_logs(
    config: ConfigPathOption = Path(DEFAULT_CONFIG_FILENAME),
    mode: LogResetModeOption = ...,
    debug: DebugOption = None,
    log_level: LogLevelOption = None,
    log_format: LogFormatOption = None,
    log_file: LogFileOption = None,
    log_max_bytes: LogMaxBytesOption = None,
    log_backup_count: LogBackupCountOption = None,
) -> None:
    """Reset BiRRe log files by rotating archives or clearing the active file."""
    invocation = _build_invocation(
        config_path=config,
        api_key=None,
        subscription_folder=None,
        subscription_type=None,
        context=None,
        debug=debug,
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
    file_path = logging_settings.file_path
    if not file_path:
        stdout_console.print("[yellow]File logging is disabled; nothing to reset[/yellow]")
        return

    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if mode is LogResetMode.ROTATE:
        _rotate_logs(path, logging_settings.backup_count)
        stdout_console.print(f"[green]Log files rotated at[/green] {path}")
        return

    try:
        path.write_text("", encoding="utf-8")
    except OSError as exc:
        raise typer.BadParameter(f"Failed to clear log file: {exc}") from exc
    stdout_console.print(f"[green]Log file cleared at[/green] {path}")


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
