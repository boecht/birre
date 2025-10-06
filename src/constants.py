"""Common boolean coercion helpers and constants."""

from __future__ import annotations

from typing import Optional

TRUTHY_STRINGS = {"1", "true", "yes", "on"}
FALSY_STRINGS = {"0", "false", "no", "off"}


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


__all__ = ["coerce_bool", "TRUTHY_STRINGS", "FALSY_STRINGS"]
