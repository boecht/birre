"""Core option type definitions and utilities.

Provides base Typer option definitions, normalization functions,
and validation helpers used across all CLI options.
"""

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


def normalize_context(
    value: str | None, *, choices: set[str] | frozenset[str]
) -> str | None:
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
    "ConfigPathOption",
    "LOG_FORMAT_CHOICES",
    "LOG_LEVEL_CHOICES",
    "LOG_LEVEL_MAP",
    "clean_string",
    "normalize_context",
    "normalize_log_format",
    "normalize_log_level",
    "validate_positive",
]
