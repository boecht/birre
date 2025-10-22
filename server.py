"""BiRRe FastMCP server Typer CLI entrypoint."""

from __future__ import annotations

import asyncio
import cProfile
import logging
import os
import shutil
import sys
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Annotated, Any, Dict, Mapping, Optional, Sequence, Tuple

import typer
from rich.console import Console
from rich import box
from rich.table import Table
from typer.main import get_command

# FastMCP checks this flag during import time, so ensure it is enabled before
# importing any modules that depend on FastMCP.
os.environ["FASTMCP_EXPERIMENTAL_ENABLE_NEW_OPENAPI_PARSER"] = "true"

from src.birre import create_birre_server
from src.constants import DEFAULT_CONFIG_FILENAME, LOCAL_CONFIG_FILENAME
from src.logging import configure_logging, get_logger
from src.settings import (
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

OnlineFlagOption = Annotated[
    bool,
    typer.Option(
        "--online/--offline",
        help="Run BitSight network checks in addition to offline validation",
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
    if key == "logging.file":
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
        labels["bitsight.api_key"] = "CLI"
    if invocation.subscription.folder:
        labels["bitsight.subscription_folder"] = "CLI"
    if invocation.subscription.type:
        labels["bitsight.subscription_type"] = "CLI"
    if invocation.runtime.context:
        labels["roles.context"] = "CLI"
    if invocation.runtime.risk_vector_filter:
        labels["roles.risk_vector_filter"] = "CLI"
    if invocation.runtime.max_findings is not None:
        labels["roles.max_findings"] = "CLI"
    if invocation.runtime.debug is not None:
        labels["runtime.debug"] = "CLI"
    if invocation.runtime.skip_startup_checks is not None:
        labels["runtime.skip_startup_checks"] = "CLI"
    if invocation.tls.allow_insecure is not None:
        labels["runtime.allow_insecure_tls"] = "CLI"
    if invocation.tls.ca_bundle_path:
        labels["runtime.ca_bundle_path"] = "CLI"
    if invocation.logging.level:
        labels["logging.level"] = "CLI"
    if invocation.logging.format:
        labels["logging.format"] = "CLI"
    if invocation.logging.file_path is not None:
        labels["logging.file"] = "CLI"
    if invocation.logging.max_bytes is not None:
        labels["logging.max_bytes"] = "CLI"
    if invocation.logging.backup_count is not None:
        labels["logging.backup_count"] = "CLI"
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
    "bitsight.api_key",
    "bitsight.subscription_folder",
    "bitsight.subscription_type",
    "roles.context",
    "roles.risk_vector_filter",
    "roles.max_findings",
    "runtime.debug",
    "runtime.skip_startup_checks",
    "runtime.allow_insecure_tls",
    "runtime.ca_bundle_path",
    "logging.level",
    "logging.format",
    "logging.file",
    "logging.max_bytes",
    "logging.backup_count",
)


def _effective_configuration_values(runtime_settings, logging_settings) -> Dict[str, Any]:
    values: Dict[str, Any] = {
        "bitsight.api_key": getattr(runtime_settings, "api_key", None),
        "bitsight.subscription_folder": getattr(runtime_settings, "subscription_folder", None),
        "bitsight.subscription_type": getattr(runtime_settings, "subscription_type", None),
        "roles.context": getattr(runtime_settings, "context", None),
        "roles.risk_vector_filter": getattr(runtime_settings, "risk_vector_filter", None),
        "roles.max_findings": getattr(runtime_settings, "max_findings", None),
        "runtime.debug": getattr(runtime_settings, "debug", None),
        "runtime.skip_startup_checks": getattr(runtime_settings, "skip_startup_checks", None),
        "runtime.allow_insecure_tls": getattr(runtime_settings, "allow_insecure_tls", None),
        "runtime.ca_bundle_path": getattr(runtime_settings, "ca_bundle_path", None),
        "logging.level": logging.getLevelName(getattr(logging_settings, "level", logging.INFO)),
        "logging.format": getattr(logging_settings, "format", None),
        "logging.file": getattr(logging_settings, "file_path", None),
        "logging.max_bytes": getattr(logging_settings, "max_bytes", None),
        "logging.backup_count": getattr(logging_settings, "backup_count", None),
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


def _banner() -> str:
    return (
        "\n"
        "╭────────────────────────────────────────────────────────────────╮\n"
        "│\033[0;33m                                                                \033[0m│\n"
        "│\033[0;33m     ███████████   ███  ███████████   ███████████               \033[0m│\n"
        "│\033[0;33m    ░░███░░░░░███ ░░░  ░░███░░░░░███ ░░███░░░░░███              \033[0m│\n"
        "│\033[0;33m     ░███    ░███ ████  ░███    ░███  ░███    ░███   ██████     \033[0m│\n"
        "│\033[0;33m     ░██████████ ░░███  ░██████████   ░██████████   ███░░███    \033[0m│\n"
        "│\033[0;33m     ░███░░░░░███ ░███  ░███░░░░░███  ░███░░░░░███ ░███████     \033[0m│\n"
        "│\033[0;33m     ░███    ░███ ░███  ░███    ░███  ░███    ░███ ░███░░░      \033[0m│\n"
        "│\033[0;33m     ███████████  █████ █████   █████ █████   █████░░██████     \033[0m│\n"
        "│\033[0;33m    ░░░░░░░░░░░  ░░░░░ ░░░░░   ░░░░░ ░░░░░   ░░░░░  ░░░░░░      \033[0m│\n"
        "│\033[0;33m                                                                \033[0m│\n"
        "│\033[2m                   Bitsight Rating Retriever                    \033[0m│\n"
        "│\033[0;33m                 Model Context Protocol Server                  \033[0m│\n"
        "│\033[0;33m                https://github.com/boecht/birre                 \033[0m│\n"
        "╰────────────────────────────────────────────────────────────────╯\n\033[0m"
    )


def _keyboard_interrupt_banner() -> str:
    return (
        "\n"
        "╭───────────────────────────────────────╮\n"
        "│\033[0;31m  Keyboard interrupt received — stopping  \033[0m│\n"
        "│\033[0;31m          BiRRe FastMCP server            \033[0m│\n"
        "╰────────────────────────────────────────╯\n\033[0m"
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
            details["bitsight.api_key"] = _format_display_value("bitsight.api_key", self.auth.api_key)
        if self.subscription.folder:
            details["bitsight.subscription_folder"] = _format_display_value(
                "bitsight.subscription_folder", self.subscription.folder
            )
        if self.subscription.type:
            details["bitsight.subscription_type"] = _format_display_value(
                "bitsight.subscription_type", self.subscription.type
            )
        if self.runtime.context:
            details["roles.context"] = _format_display_value("roles.context", self.runtime.context)
        if self.runtime.risk_vector_filter:
            details["roles.risk_vector_filter"] = _format_display_value(
                "roles.risk_vector_filter", self.runtime.risk_vector_filter
            )
        if self.runtime.max_findings is not None:
            details["roles.max_findings"] = _format_display_value(
                "roles.max_findings", self.runtime.max_findings
            )
        if self.runtime.debug is not None:
            details["runtime.debug"] = _format_display_value("runtime.debug", self.runtime.debug)
        if self.runtime.skip_startup_checks is not None:
            details["runtime.skip_startup_checks"] = _format_display_value(
                "runtime.skip_startup_checks", self.runtime.skip_startup_checks
            )
        if self.tls.allow_insecure is not None:
            details["runtime.allow_insecure_tls"] = _format_display_value(
                "runtime.allow_insecure_tls", self.tls.allow_insecure
            )
        if self.tls.ca_bundle_path:
            details["runtime.ca_bundle_path"] = _format_display_value(
                "runtime.ca_bundle_path", self.tls.ca_bundle_path
            )
        if self.logging.level:
            details["logging.level"] = _format_display_value("logging.level", self.logging.level)
        if self.logging.format:
            details["logging.format"] = _format_display_value("logging.format", self.logging.format)
        if self.logging.file_path is not None:
            details["logging.file"] = _format_display_value("logging.file", self.logging.file_path)
        if self.logging.max_bytes is not None:
            details["logging.max_bytes"] = _format_display_value(
                "logging.max_bytes", self.logging.max_bytes
            )
        if self.logging.backup_count is not None:
            details["logging.backup_count"] = _format_display_value(
                "logging.backup_count", self.logging.backup_count
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

    clean_log_file = log_file.strip() if isinstance(log_file, str) else None
    if clean_log_file:
        clean_log_file = clean_log_file

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
        stderr_console.print(_banner(), markup=False)
    configure_logging(logging_settings)
    logger = get_logger("birre")
    _emit_runtime_messages(runtime_settings, logger)
    return logger


def _prepare_server(runtime_settings, logger):
    logger.info("Preparing BiRRe FastMCP server")
    return create_birre_server(settings=runtime_settings, logger=logger)


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
        stderr_console.print(_keyboard_interrupt_banner(), markup=False)
        logger.info("BiRRe FastMCP server stopped via KeyboardInterrupt")


@app.command(
    help="Run startup checks without launching the BiRRe FastMCP server."
)
def checks_only(
    config: ConfigPathOption = Path(DEFAULT_CONFIG_FILENAME),
    bitsight_api_key: BitsightApiKeyOption = None,
    subscription_folder: SubscriptionFolderOption = None,
    subscription_type: SubscriptionTypeOption = None,
    debug: DebugOption = None,
    allow_insecure_tls: AllowInsecureTlsOption = None,
    ca_bundle: CaBundleOption = None,
    log_level: LogLevelOption = None,
    log_format: LogFormatOption = None,
    log_file: LogFileOption = None,
    log_max_bytes: LogMaxBytesOption = None,
    log_backup_count: LogBackupCountOption = None,
    online: OnlineFlagOption = False,
) -> None:
    """Run BiRRe startup checks and exit with the resulting status."""
    invocation = _build_invocation(
        config_path=config,
        api_key=bitsight_api_key,
        subscription_folder=subscription_folder,
        subscription_type=subscription_type,
        context=None,
        debug=debug,
        risk_vector_filter=None,
        max_findings=None,
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
    logger = _initialize_logging(runtime_settings, logging_settings, show_banner=False)

    if not _run_offline_checks(runtime_settings, logger):
        raise typer.Exit(code=1)

    if online:
        server = _prepare_server(runtime_settings, logger)
        if not _run_online_checks(runtime_settings, logger, server):
            logger.critical("Online startup checks failed")
            raise typer.Exit(code=1)
    logger.info("Startup checks completed successfully")


def _prompt_bool(prompt: str, default: bool) -> bool:
    return typer.confirm(prompt, default=default)


def _prompt_str(prompt: str, default: Optional[str], secret: bool = False) -> Optional[str]:
    value = typer.prompt(prompt, default=default or "", hide_input=secret).strip()
    return value or None


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
    default_subscription_folder = defaults_settings.get("bitsight.subscription_folder")
    default_subscription_type = defaults_settings.get("bitsight.subscription_type")
    default_context = defaults_settings.get("roles.context", "standard")
    default_debug = bool(defaults_settings.get("runtime.debug", False))

    summary_rows: list[tuple[str, str, str]] = []

    def add_summary(section: str, key: str, value: Any, source: str) -> None:
        if value in (None, ""):
            return
        dotted_key = f"{section}.{key}" if section else key
        display_value = _format_display_value(dotted_key, value)
        summary_rows.append((dotted_key, display_value, source))

    stdout_console.print("[bold]BiRRe local configuration generator[/bold]")
    api_key = _prompt_str("BitSight API key", default=None, secret=True)
    if api_key:
        add_summary("bitsight", "api_key", api_key, "User Input")

    default_subscription_folder_str = (
        str(default_subscription_folder)
        if default_subscription_folder is not None
        else ""
    )
    subscription_folder = _prompt_str(
        "Default subscription folder",
        default_subscription_folder_str,
    )
    if subscription_folder is not None:
        folder_source = (
            "Default"
            if default_subscription_folder_str
            and subscription_folder == default_subscription_folder_str
            else "User Input"
        )
        add_summary("bitsight", "subscription_folder", subscription_folder, folder_source)

    subscription_type_value: Optional[str]
    if subscription_type is not None:
        subscription_type_value = subscription_type.strip() or None
        if subscription_type_value is not None:
            add_summary(
                "bitsight",
                "subscription_type",
                subscription_type_value,
                "CLI Option",
            )
    else:
        default_subscription_type_str = (
            str(default_subscription_type)
            if default_subscription_type is not None
            else ""
        )
        subscription_type_value = _prompt_str(
            "Default subscription type",
            default_subscription_type_str,
        )
        if subscription_type_value is not None:
            type_source = (
                "Default"
                if default_subscription_type_str
                and subscription_type_value == default_subscription_type_str
                else "User Input"
            )
            add_summary("bitsight", "subscription_type", subscription_type_value, type_source)

    default_context_str = str(default_context or "standard")
    context_value = _prompt_str(
        "Default persona (standard or risk_manager)",
        default_context_str,
    )
    if context_value is not None:
        context_source = (
            "Default"
            if context_value == default_context_str
            else "User Input"
        )
        add_summary("roles", "context", context_value, context_source)

    if debug is not None:
        debug_value = debug
        add_summary("runtime", "debug", debug_value, "CLI Option")
    else:
        debug_value = _prompt_bool("Enable debug mode?", default=default_debug)
        debug_source = "Default" if debug_value == default_debug else "User Input"
        add_summary("runtime", "debug", debug_value, debug_source)

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

    runtime_settings, logging_settings, settings = _resolve_runtime_and_logging(invocation)
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


@app.command(help="Run diagnostics without starting the BiRRe server.")
def test(
    config: ConfigPathOption = Path(DEFAULT_CONFIG_FILENAME),
    bitsight_api_key: BitsightApiKeyOption = None,
    subscription_folder: SubscriptionFolderOption = None,
    subscription_type: SubscriptionTypeOption = None,
    debug: DebugOption = None,
    allow_insecure_tls: AllowInsecureTlsOption = None,
    ca_bundle: CaBundleOption = None,
    risk_vector_filter: RiskVectorFilterOption = None,
    max_findings: MaxFindingsOption = None,
    online: OnlineFlagOption = False,
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
        skip_startup_checks=None,
        allow_insecure_tls=allow_insecure_tls,
        ca_bundle=ca_bundle,
        log_level=None,
        log_format=None,
        log_file=None,
        log_max_bytes=None,
        log_backup_count=None,
    )

    runtime_settings, logging_settings, _ = _resolve_runtime_and_logging(invocation)
    logger = _initialize_logging(runtime_settings, logging_settings, show_banner=False)

    if not _run_offline_checks(runtime_settings, logger):
        raise typer.Exit(code=1)

    server = _prepare_server(runtime_settings, logger)
    tools_attr = getattr(server, "tools", None)
    if isinstance(tools_attr, dict):
        logger.info("Business tools available", tools=list(tools_attr.keys()))

    if online:
        if not _run_online_checks(runtime_settings, logger, server):
            logger.critical("Online diagnostics failed")
            raise typer.Exit(code=1)
    logger.info("Diagnostics completed successfully")


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
