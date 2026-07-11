"""Caller-facing Jira action payloads for alert-driven workflows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return list(value)
    return []


def _candidate_records(candidates: Any) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    if isinstance(candidates, Mapping):
        action_candidates = candidates.get("action_candidates", [])
        filtered_candidates = candidates.get("filtered_candidates", [])
    else:
        action_candidates = candidates
        filtered_candidates = []
    return (
        [record for record in _as_list(action_candidates) if isinstance(record, Mapping)],
        [record for record in _as_list(filtered_candidates) if isinstance(record, Mapping)],
    )


def _alert_provenance(trigger: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "alert_guid": trigger.get("alert_guid"),
        "event_date": trigger.get("event_date", trigger.get("alert_date")),
        "seen_at": trigger.get("seen_at", trigger.get("start_date")),
        "severity": trigger.get("severity"),
        "trigger": trigger.get("trigger"),
        "raw_evidence_reference": trigger.get(
            "raw_evidence_reference",
            trigger.get("raw_alert", trigger.get("source_metadata")),
        ),
    }


def _missing_data(item: Mapping[str, Any], group: Mapping[str, Any]) -> list[str]:
    flags = item.get("missing_data", item.get("missing_data_flags", []))
    if isinstance(flags, Mapping):
        missing = [key for key, present in flags.items() if not present]
    else:
        missing = [flag for flag in _as_list(flags) if isinstance(flag, str)]
    if not group.get("name"):
        missing.append("company_name")
    if group.get("current_rating") is None:
        missing.append("current_rating")
    return list(dict.fromkeys(missing))


def _warning_codes(candidate: Mapping[str, Any], group: Mapping[str, Any]) -> list[str]:
    warnings = list(candidate.get("warnings", []))
    warnings.extend(group.get("warnings", []))
    warnings.extend(group.get("enrichment_warnings", []))
    candidate_metadata = candidate.get("metadata", {})
    candidate_warning = (
        candidate_metadata.get("warning") if isinstance(candidate_metadata, Mapping) else None
    )
    if isinstance(candidate_warning, str):
        warnings.append(candidate_warning)
    elif isinstance(candidate_warning, list):
        warnings.extend(candidate_warning)
    return list(dict.fromkeys(warnings))


def build_jira_action_payload(
    grouped: Mapping[str, Any],
    candidates: Any,
    *,
    warnings: Sequence[str] = (),
    missing_data: Sequence[str] = (),
) -> dict[str, Any]:
    """Build Jira-ready action items without exposing internal grouped batches."""
    action_candidates, filtered_candidates = _candidate_records(candidates)
    groups = grouped.get("groups", grouped)
    if not isinstance(groups, Mapping):
        groups = {}

    grouped_metadata = grouped.get("metadata", {})
    metadata_warnings = (
        list(grouped_metadata.get("warnings", []))
        if isinstance(grouped_metadata, Mapping)
        else []
    )
    for warning in warnings:
        if warning not in metadata_warnings:
            metadata_warnings.append(warning)
    metadata_missing = list(dict.fromkeys(missing_data))
    action_items: list[dict[str, Any]] = []

    for candidate in action_candidates:
        company_guid = candidate.get("company_guid")
        group = groups.get(company_guid, {})
        if not isinstance(group, Mapping):
            group = {}
        triggers = [
            trigger
            for trigger in _as_list(group.get("triggers", []))
            if isinstance(trigger, Mapping)
        ]
        movement = candidate.get("rating_movement", candidate.get("movement", {}))
        if not isinstance(movement, Mapping):
            movement = {}
        rating_before = candidate.get("rating_before", movement.get("rating_before"))
        rating_after = candidate.get("rating_after", movement.get("rating_after"))
        rating_drop = candidate.get("rating_drop", movement.get("drop"))
        item_missing = _missing_data(candidate, group)
        for flag in item_missing:
            if flag not in metadata_missing:
                metadata_missing.append(flag)
        item_warnings = _warning_codes(candidate, group)

        action_items.append(
            {
                "company_guid": company_guid,
                "correlation_key": company_guid,
                "company_name": candidate.get("company_name", group.get("name")),
                "primary_domain": candidate.get("primary_domain", group.get("primary_domain")),
                "current_rating": candidate.get("current_rating", group.get("current_rating")),
                "alerts": [_alert_provenance(trigger) for trigger in triggers],
                "priority_score": candidate.get("priority_score", candidate.get("priority")),
                "priority_level": candidate.get("priority_level"),
                "eligible": candidate.get("eligible", True),
                "filtered_candidate_metadata": candidate.get("filtered_candidate_metadata", {}),
                "warning_codes": item_warnings,
                "missing_data_flags": item_missing,
                "proposed_jira_body": {
                    "rating_before": rating_before,
                    "rating_after": rating_after,
                    "rating_drop": rating_drop,
                    "movement_source": candidate.get(
                        "movement_source", movement.get("source")
                    ),
                    "current_rating": candidate.get(
                        "current_rating", group.get("current_rating")
                    ),
                },
            }
        )

    return {
        "action_items": action_items,
        "metadata": {
            "warnings": metadata_warnings,
            "missing_data_flags": metadata_missing,
            "filtered_candidates": filtered_candidates,
        },
    }
