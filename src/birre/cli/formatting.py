"""Shared Rich console formatting utilities for BiRRe CLI commands."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from rich import box
from rich.console import Console
from rich.table import Table

__all__ = [
    "RichStyles",
    "mask_sensitive_value",
    "format_config_value",
    "flatten_to_dotted",
    "create_config_table",
    "stringify_value",
]


class RichStyles:
    """Rich console styling constants shared across CLI commands."""

    ACCENT = "bold cyan"
    SECONDARY = "magenta"
    SUCCESS = "green"
    EMPHASIS = "bold"
    DETAIL = "white"


# Sensitive value patterns
SENSITIVE_KEY_PATTERNS: Final[tuple[str, ...]] = (
    "api_key",
    "secret",
    "token",
    "password",
)


def mask_sensitive_value(value: str) -> str:
    """Mask sensitive values for display.

    Args:
        value: The string value to potentially mask

    Returns:
        Masked string showing first 2 and last 2 characters with asterisks in between

    Examples:
        >>> mask_sensitive_value("secret123")
        'se*****23'
        >>> mask_sensitive_value("abc")
        '***'
    """
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"


def is_sensitive_key(key: str) -> bool:
    """Check if a config key name indicates sensitive data.

    Args:
        key: The configuration key name to check

    Returns:
        True if the key name contains any sensitive pattern
    """
    lowered_key = key.lower()
    return any(pattern in lowered_key for pattern in SENSITIVE_KEY_PATTERNS)


def format_config_value(key: str, value: Any, log_file_key: str | None = None) -> str:
    """Format a config value for display, masking sensitive values.

    Args:
        key: The configuration key name
        value: The configuration value
        log_file_key: Optional key name that represents log file path

    Returns:
        Formatted string representation of the value
    """
    # Special handling for log file key
    if log_file_key and key == log_file_key:
        if value is None:
            return "<stderr>"
        if isinstance(value, str) and not value.strip():
            return "<stderr>"

    # Format the value
    if value is None:
        text = "<unset>"
    elif isinstance(value, bool):
        text = "true" if value else "false"
    else:
        text = str(value)

    # Mask sensitive values
    if is_sensitive_key(key):
        original = value if isinstance(value, str) else text
        return mask_sensitive_value(original)

    return text


def flatten_to_dotted(mapping: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten nested dictionary to dotted key notation.

    Args:
        mapping: Nested dictionary to flatten
        prefix: Key prefix for recursive calls

    Returns:
        Dictionary with dotted keys and flat values

    Examples:
        >>> flatten_to_dotted({"a": {"b": 1, "c": 2}})
        {'a.b': 1, 'a.c': 2}
    """
    flattened: dict[str, Any] = {}
    for key, value in mapping.items():
        dotted = f"{prefix}.{key}" if prefix else key
        if isinstance(value, Mapping):
            flattened.update(flatten_to_dotted(value, dotted))
        else:
            flattened[dotted] = value
    return flattened


def create_info_table(
    title: str,
    columns: Sequence[tuple[str, str | None]],
    *,
    box_style: box.Box = box.SIMPLE_HEAVY,
) -> Table:
    """Create a Rich Table with standard styling.

    Args:
        title: Table title
        columns: List of (column_name, style) tuples. Use None for default style
        box_style: Rich box style to use

    Returns:
        Configured Rich Table ready for rows
    """
    table = Table(title=title, box=box_style)
    for col_name, col_style in columns:
        if col_style:
            table.add_column(col_name, style=col_style, no_wrap=True)
        else:
            table.add_column(col_name)
    return table


def create_config_table(title: str) -> Table:
    """Create a standard config display table.

    Args:
        title: Table title

    Returns:
        Table configured for config key/value/source display
    """
    return create_info_table(
        title,
        [
            ("Config Key", RichStyles.ACCENT),
            ("Resolved Value", None),
            ("Source", RichStyles.SECONDARY),
        ],
    )


def stringify_value(value: Any) -> str:
    """Convert any value to a string representation for display.

    Args:
        value: Value to convert

    Returns:
        String representation suitable for console display
    """
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        items = [f"{key}={value[key]}" for key in sorted(value)]
        return ", ".join(items) if items else "-"
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        items = [stringify_value(item) for item in value]
        return ", ".join(item for item in items if item and item != "-") or "-"
    return str(value)


def print_table(table: Table, console: Console) -> None:
    """Print a Rich table to console with surrounding whitespace.

    Args:
        table: Rich Table to print
        console: Rich Console to print to
    """
    console.print()
    console.print(table)
    console.print()
