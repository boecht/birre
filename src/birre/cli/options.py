"""Typer option declarations and normalization helpers."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Final

import typer

LOG_FORMAT_CHOICES: Final[set[str]] = {"text", "json"}
LOG_LEVEL_CHOICES: Final[list[str]] = sorted(
    name
    for name, value in logging.getLevelNamesMapping().items()
    if isinstance(name, str) and not name.isdigit()
)
LOG_LEVEL_SET: Final[set[str]] = {choice.upper() for choice in LOG_LEVEL_CHOICES}
LOG_LEVEL_MAP: Final[dict[str, int]] = {
    name.upper(): value
    for name, value in logging.getLevelNamesMapping().items()
    if isinstance(name, str) and not name.isdigit()
}

ConfigPathOption = Annotated[
    Path,
    typer.Option(
        "--config",
        help="Path to a BiRRe configuration TOML file to load",
        envvar="BIRRE_CONFIG",
        show_envvar=True,
        rich_help_panel="Configuration",
    ),
]

BitsightApiKeyOption = Annotated[
    str | None,
    typer.Option(
        "--bitsight-api-key",
        help="BitSight API key (overrides BITSIGHT_API_KEY env var)",
        envvar="BITSIGHT_API_KEY",
        show_envvar=True,
        rich_help_panel="Authentication",
    ),
]

SubscriptionFolderOption = Annotated[
    str | None,
    typer.Option(
        "--subscription-folder",
        help="BitSight subscription folder override",
        envvar="BIRRE_SUBSCRIPTION_FOLDER",
        show_envvar=True,
        rich_help_panel="Runtime",
    ),
]

SubscriptionTypeOption = Annotated[
    str | None,
    typer.Option(
        "--subscription-type",
        help="BitSight subscription type override",
        envvar="BIRRE_SUBSCRIPTION_TYPE",
        show_envvar=True,
        rich_help_panel="Runtime",
    ),
]

SkipStartupChecksOption = Annotated[
    bool | None,
    typer.Option(
        "--skip-startup-checks/--require-startup-checks",
        help=(
            "Skip online startup checks "
            "(use --require-startup-checks to override any configured skip)"
        ),
        envvar="BIRRE_SKIP_STARTUP_CHECKS",
        show_envvar=True,
        rich_help_panel="Runtime",
    ),
]

DebugOption = Annotated[
    bool | None,
    typer.Option(
        "--debug/--no-debug",
        help="Enable verbose diagnostics",
        envvar="BIRRE_DEBUG",
        show_envvar=True,
        rich_help_panel="Diagnostics",
    ),
]

AllowInsecureTlsOption = Annotated[
    bool | None,
    typer.Option(
        "--allow-insecure-tls/--enforce-tls",
        help="Disable TLS verification for API calls (not recommended)",
        envvar="BIRRE_ALLOW_INSECURE_TLS",
        show_envvar=True,
        rich_help_panel="TLS",
    ),
]

CaBundleOption = Annotated[
    str | None,
    typer.Option(
        "--ca-bundle",
        help="Path to a custom certificate authority bundle, e.g. for TLS interception",
        envvar="BIRRE_CA_BUNDLE",
        show_envvar=True,
        rich_help_panel="TLS",
    ),
]

ContextOption = Annotated[
    str | None,
    typer.Option(
        "--context",
        help="Tool persona to expose (standard or risk_manager)",
        envvar="BIRRE_CONTEXT",
        show_envvar=True,
        rich_help_panel="Runtime",
    ),
]

RiskVectorFilterOption = Annotated[
    str | None,
    typer.Option(
        "--risk-vector-filter",
        help="Comma separated list of BitSight risk vectors",
        envvar="BIRRE_RISK_VECTOR_FILTER",
        show_envvar=True,
        rich_help_panel="Runtime",
    ),
]

MaxFindingsOption = Annotated[
    int | None,
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
    str | None,
    typer.Option(
        "--log-level",
        help="Logging level (e.g. INFO, DEBUG)",
        envvar="BIRRE_LOG_LEVEL",
        show_envvar=True,
        rich_help_panel="Logging",
    ),
]

LogFormatOption = Annotated[
    str | None,
    typer.Option(
        "--log-format",
        help="Logging format (text or json)",
        envvar="BIRRE_LOG_FORMAT",
        show_envvar=True,
        rich_help_panel="Logging",
    ),
]

LogFileOption = Annotated[
    str | None,
    typer.Option(
        "--log-file",
        help="Path to a log file (use '-', none, stderr to disable)",
        envvar="BIRRE_LOG_FILE",
        show_envvar=True,
        rich_help_panel="Logging",
    ),
]

LogMaxBytesOption = Annotated[
    int | None,
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
    int | None,
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
    Path | None,
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
        help="Skip network checks and run offline validation only",
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


def clean_string(value: str | None) -> str | None:
    """Normalize optional string input."""

    if value is None:
        return None
    candidate = value.strip()
    return candidate or None


def validate_positive(name: str, value: int | None) -> int | None:
    """Validate that a numeric option is positive when provided."""

    if value is None:
        return None
    if value <= 0:
        raise typer.BadParameter(
            f"{name} must be a positive integer",
            param_hint=f"--{name.replace('_', '-')}",
        )
    return value


def normalize_context(value: str | None, *, choices: set[str]) -> str | None:
    """Normalize the context option, ensuring it is one of the allowed choices."""

    if value is None:
        return None
    candidate = value.strip().lower().replace("-", "_")
    if not candidate:
        return None
    if candidate not in choices:
        raise typer.BadParameter(
            f"Context must be one of: {', '.join(sorted(choices))}",
            param_hint="--context",
        )
    return candidate


def normalize_log_format(value: str | None) -> str | None:
    """Normalize the log format option."""

    if value is None:
        return None
    candidate = value.strip().lower()
    if not candidate:
        return None
    if candidate not in LOG_FORMAT_CHOICES:
        raise typer.BadParameter(
            "Log format must be either 'text' or 'json'",
            param_hint="--log-format",
        )
    return candidate


def normalize_log_level(value: str | None) -> str | None:
    """Normalize the log level option."""

    if value is None:
        return None
    candidate = value.strip().upper()
    if not candidate:
        return None
    if candidate not in LOG_LEVEL_SET:
        raise typer.BadParameter(
            f"Log level must be one of: {', '.join(LOG_LEVEL_CHOICES)}",
            param_hint="--log-level",
        )
    return candidate


__all__ = [
    "AllowInsecureTlsOption",
    "BitsightApiKeyOption",
    "CaBundleOption",
    "ConfigPathOption",
    "ContextOption",
    "DebugOption",
    "LocalConfOutputOption",
    "LOG_FORMAT_CHOICES",
    "LOG_LEVEL_CHOICES",
    "LOG_LEVEL_MAP",
    "LogBackupCountOption",
    "LogFileOption",
    "LogFormatOption",
    "LogLevelOption",
    "LogMaxBytesOption",
    "MaxFindingsOption",
    "MinimizeOption",
    "OfflineFlagOption",
    "OverwriteOption",
    "ProfilePathOption",
    "ProductionFlagOption",
    "RiskVectorFilterOption",
    "SkipStartupChecksOption",
    "SubscriptionFolderOption",
    "SubscriptionTypeOption",
    "clean_string",
    "normalize_context",
    "normalize_log_format",
    "normalize_log_level",
    "validate_positive",
]
