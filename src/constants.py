"""Common boolean coercion helpers and constants."""

from __future__ import annotations

from typing import Optional

TRUTHY_STRINGS = {"1", "true", "yes", "on"}
FALSY_STRINGS = {"0", "false", "no", "off"}


CONFIG_BASENAME = "config"
DEFAULT_CONFIG_FILENAME = f"{CONFIG_BASENAME}.toml"
LOCAL_CONFIG_FILENAME = f"{CONFIG_BASENAME}.local.toml"


def coerce_bool(value: Optional[object], *, default: bool = False) -> bool:
    """Convert common truthy/falsey string markers into booleans.

    Falls back to ``default`` when the value is ``None`` or ambiguous.
    Passing a non-string/non-bool value relies on Python's ``bool`` constructor.
    """

    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if not normalized:
            return default
        if normalized in TRUTHY_STRINGS:
            return True
        if normalized in FALSY_STRINGS:
            return False
        return default
    try:
        return bool(value)
    except Exception:
        return default


def coerce_positive_int(
    candidate: Optional[object], *, default: Optional[int] = None
) -> int:
    """Coerce ``candidate`` into a positive integer, enforcing strict validation."""

    if candidate is None:
        if default is None:
            raise ValueError("No integer value provided and no default specified")
        return default

    try:
        value = int(candidate)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid integer value: {candidate}") from exc

    if value <= 0:
        raise ValueError(f"Value must be positive: {candidate}")

    return value


__all__ = [
    "coerce_bool",
    "coerce_positive_int",
    "TRUTHY_STRINGS",
    "FALSY_STRINGS",
    "CONFIG_BASENAME",
    "DEFAULT_CONFIG_FILENAME",
    "LOCAL_CONFIG_FILENAME",
]
