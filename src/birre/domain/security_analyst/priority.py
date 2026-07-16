"""Priority scoring components for alert-driven workflows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_EVENT_CATEGORY_POINTS: Mapping[str, int] = {
    "public disclosure": -1,
    "security incident": -1,
    "botnet infection": 0,
    "malware": 0,
    "potentially exploited": 0,
    "open ports": 1,
    "patching cadence": 1,
    "server software": 1,
    "insecure systems": 1,
    "TLS certificates": 3,
    "TLS configuration": 3,
    "spam propagation": 3,
    "mobile app security": 3,
    "desktop software": 3,
    "mobile software": 3,
    "exposed credentials": 3,
    "web application headers": 3,
    "web application security": 3,
}
_OUT_OF_SCOPE_CATEGORIES = frozenset(
    {
        "DNSSEC",
        "DMARC",
        "DKIM",
        "SPF",
        "domain squatting",
        "unsolicited communication",
        "file sharing",
    }
)


def score_supplier_criticality(criticality: Any) -> int:
    """Return points for supplier criticality, defaulting missing values to one."""
    return {1: 0, 2: 1, 3: 3}.get(criticality, 1)


def score_event_category(category: str) -> dict[str, Any]:
    """Return event-category points and whether the category is out of scope."""
    if category in _OUT_OF_SCOPE_CATEGORIES:
        return {"points": 0, "out_of_scope": True}
    return {"points": _EVENT_CATEGORY_POINTS.get(category, 0), "out_of_scope": False}


def score_rating_change(drop: int | float) -> int:
    """Return points for the size of a positive rating drop."""
    if drop > 150:
        return -1
    if drop > 100:
        return 0
    if drop > 40:
        return 1
    return 3


def compute_priority_level(total_points: int | float) -> int:
    """Map total priority points to the initial priority level."""
    if total_points <= 1:
        return 0
    if total_points == 2:
        return 1
    if total_points == 3:
        return 2
    if total_points <= 5:
        return 3
    return 4


def score_human_factor(factor: str | None = None) -> int:
    """Return points for the human-factor classification."""
    factor_key = factor if isinstance(factor, str) else ""
    return {"many_events": 0, "normal": 1, "low_relevance": 3}.get(factor_key, 1)


def filter_action_candidates(
    candidates: Sequence[Mapping[str, Any]], *, max_returned_priority: int
) -> dict[str, Any]:
    """Return eligible action candidates and explain excluded candidates."""
    if max_returned_priority < 0:
        raise ValueError("max_returned_priority must not be negative")

    action_candidates: list[dict[str, Any]] = []
    filtered_candidates: list[dict[str, Any]] = []
    warnings: list[str] = []

    for candidate in candidates:
        record = dict(candidate)
        category = record.get("category")
        category_score = score_event_category(category) if isinstance(category, str) else None
        metadata = dict(record.get("metadata", {}))

        if category_score and category_score["out_of_scope"]:
            filtered_candidates.append(
                {
                    "company_guid": record.get("company_guid"),
                    "priority": record.get("priority"),
                    "eligible": False,
                    "action_item": None,
                    "filter_reason": "out_of_scope_category",
                }
            )
            continue

        if category == "web application security":
            metadata["warning"] = "category_ambiguous"
            record["metadata"] = metadata
            if "category_ambiguous" not in warnings:
                warnings.append("category_ambiguous")

        priority = record.get("priority")
        if not isinstance(priority, int):
            raise ValueError("candidate priority must be an integer")
        if priority > max_returned_priority:
            filtered_candidates.append(
                {
                    "company_guid": record.get("company_guid"),
                    "priority": priority,
                    "eligible": False,
                    "action_item": None,
                    "filter_reason": "priority_filtered",
                }
            )
            continue

        record["eligible"] = True
        action_candidates.append(record)

    return {
        "action_candidates": action_candidates,
        "filtered_candidates": filtered_candidates,
        "metadata": {"warnings": warnings},
    }
