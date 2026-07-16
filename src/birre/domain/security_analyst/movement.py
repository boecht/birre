"""Deterministic rating movement evidence for alert-driven workflows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def _numeric_drop(before: Any, after: Any) -> float | None:
    if not isinstance(before, int | float) or isinstance(before, bool):
        return None
    if not isinstance(after, int | float) or isinstance(after, bool):
        return None
    drop = float(before) - float(after)
    return drop if drop > 0 else None


def _alert_value(alert: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in alert:
            return alert[key]
    details = alert.get("details")
    if isinstance(details, Mapping):
        for key in keys:
            if key in details:
                return details[key]
    return None


def _history_drop(history: Any) -> float | None:
    if isinstance(history, Mapping):
        history = history.get("ratings")
    if not isinstance(history, Sequence) or isinstance(history, str):
        return None

    values = [
        float(entry["rating"])
        for entry in history
        if isinstance(entry, Mapping)
        and isinstance(entry.get("rating"), int | float)
        and not isinstance(entry.get("rating"), bool)
    ]
    drops = [before - after for before, after in zip(values, values[1:]) if before > after]
    return max(drops, default=None)


def _category_drop(
    category_before: Any,
    category_after: Any,
    category_rating_map: Mapping[str, int | float],
) -> float | None:
    if not isinstance(category_before, str) or not isinstance(category_after, str):
        return None
    before_rating = category_rating_map.get(category_before)
    after_rating = category_rating_map.get(category_after)
    if _numeric_drop(before_rating, after_rating) is None:
        return None
    if len(category_before) != 1 or len(category_after) != 1:
        return None
    return float(ord(category_after) - ord(category_before)) * 25


def derive_rating_movement(
    alert: Mapping[str, Any],
    company_history: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None = None,
    category_rating_map: Mapping[str, int | float] | None = None,
) -> dict[str, Any]:
    """Select the largest available rating drop and its evidence source."""
    numeric_drop = _numeric_drop(
        _alert_value(alert, "rating_before"),
        _alert_value(alert, "rating_after"),
    )
    category_drop = None
    category_before = _alert_value(alert, "category_before")
    category_after = _alert_value(alert, "category_after")
    if category_rating_map is not None:
        category_drop = _category_drop(
            category_before,
            category_after,
            category_rating_map,
        )

    candidates = [
        (numeric_drop, "alert_rating"),
        (category_drop, "alert_category"),
        (_history_drop(company_history), "company_history"),
    ]
    available = [(drop, source) for drop, source in candidates if drop is not None]
    if not available:
        return {"warning": "rating_movement_missing"}

    drop, source = max(available, key=lambda candidate: candidate[0])
    return {"drop": drop, "source": source}
