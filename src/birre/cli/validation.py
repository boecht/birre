"""Validation utilities and error handling helpers for BiRRe CLI."""

from __future__ import annotations

import tomllib
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import typer

# File and path validation


def require_file_exists(
    path: Path | None,
    *,
    param_hint: str | None = None,
    custom_message: str | None = None,
) -> Path:
    """Validate that a file exists, raising BadParameter if not.

    Args:
        path: Path to validate (or None to raise immediately)
        param_hint: Parameter name for error message (e.g., "--config")
        custom_message: Custom error message (overrides default)

    Returns:
        The validated Path if it exists

    Raises:
        typer.BadParameter: If path is None or doesn't exist

    Examples:
        >>> config = require_file_exists(config_path, param_hint="--config")
        >>> log_file = require_file_exists(
        ...     Path(log_path),
        ...     custom_message="Log file not found"
        ... )
    """
    if path is None:
        message = custom_message or "Path could not be determined"
        raise typer.BadParameter(message, param_hint=param_hint)

    if not path.exists():
        message = custom_message or f"{path} does not exist"
        raise typer.BadParameter(message, param_hint=param_hint)

    return path


def validate_path_exists(path: Path) -> bool:
    """Check if a path exists, returning boolean result.

    Args:
        path: Path to check

    Returns:
        True if path exists, False otherwise

    Examples:
        >>> if validate_path_exists(log_path):
        ...     print("Log file found")
    """
    return path.exists()


# TOML parsing


def parse_toml_file(
    path: Path,
    *,
    param_hint: str | None = None,
) -> dict[str, Any]:
    """Parse a TOML file, raising BadParameter on errors.

    Args:
        path: Path to TOML file
        param_hint: Parameter name for error message (e.g., "--config")

    Returns:
        Parsed TOML content as dictionary

    Raises:
        typer.BadParameter: If file cannot be parsed

    Examples:
        >>> config = parse_toml_file(config_path, param_hint="--config")
    """
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise typer.BadParameter(f"Invalid TOML: {exc}", param_hint=param_hint) from exc
    except OSError as exc:
        raise typer.BadParameter(
            f"Cannot read {path}: {exc}",
            param_hint=param_hint,
        ) from exc


@contextmanager
def toml_parse_context(param_hint: str | None = None) -> Any:
    """Context manager for TOML parsing with automatic error conversion.

    Args:
        param_hint: Parameter name for error message

    Yields:
        None (use within 'with' statement for parsing code)

    Raises:
        typer.BadParameter: If TOML parsing fails within context

    Examples:
        >>> with toml_parse_context(param_hint="--config"):
        ...     with path.open("rb") as f:
        ...         data = tomllib.load(f)
    """
    try:
        yield
    except tomllib.TOMLDecodeError as exc:
        raise typer.BadParameter(f"Invalid TOML: {exc}", param_hint=param_hint) from exc


# Error handling helpers


def abort_with_message(message: str, *, exit_code: int = 1) -> None:
    """Print error message and exit with specified code.

    Args:
        message: Error message to display
        exit_code: Exit code (default: 1)

    Examples:
        >>> if not api_key:
        ...     abort_with_message("API key required", exit_code=1)
    """
    typer.echo(message, err=True)
    raise typer.Exit(code=exit_code)


def require_parameter(
    value: Any,
    *,
    param_hint: str,
    message: str | None = None,
) -> Any:
    """Validate that a required parameter is provided.

    Args:
        value: Parameter value to validate
        param_hint: Parameter name for error message
        message: Custom error message

    Returns:
        The value if valid

    Raises:
        typer.BadParameter: If value is None or empty

    Examples:
        >>> api_key = require_parameter(
        ...     api_key_value,
        ...     param_hint="--api-key",
        ...     message="API key is required"
        ... )
    """
    if value is None:
        error_msg = message or "Required parameter not provided"
        raise typer.BadParameter(error_msg, param_hint=param_hint)

    # Handle empty strings
    if isinstance(value, str) and not value.strip():
        error_msg = message or "Parameter cannot be empty"
        raise typer.BadParameter(error_msg, param_hint=param_hint)

    return value


__all__ = [
    "require_file_exists",
    "validate_path_exists",
    "parse_toml_file",
    "toml_parse_context",
    "abort_with_message",
    "require_parameter",
]
