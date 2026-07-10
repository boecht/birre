"""Executable alert workflow for API and CLI callers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from birre.domain.common import CallV1Tool, CallV2Tool
from birre.domain.security_analyst.alerts import (
    enrich_company_groups,
    fetch_v2_alert_pages,
    group_alert_triggers_by_company,
    normalize_alert_trigger,
)
from birre.domain.security_analyst.movement import derive_rating_movement
from birre.domain.security_analyst.payload import build_jira_action_payload
from birre.domain.security_analyst.priority import (
    compute_priority_level,
    filter_action_candidates,
    score_event_category,
    score_human_factor,
    score_rating_change,
    score_supplier_criticality,
)
from birre.domain.security_analyst.request import (
    AlertWorkflowRequest,
    build_alert_workflow_request,
    resolve_supplier_criticality,
)

CompanyFetcher = Callable[[str], Awaitable[Any]]


def _trigger_candidate(
    trigger: Mapping[str, Any],
    group: Mapping[str, Any],
    request: AlertWorkflowRequest,
) -> dict[str, Any]:
    movement = derive_rating_movement(trigger, group.get("ratings"))
    category = trigger.get("alert_type", trigger.get("trigger"))
    category_score = score_event_category(category) if isinstance(category, str) else {"points": 0}
    drop = movement.get("drop")
    movement_points = score_rating_change(drop) if isinstance(drop, int | float) else 0
    event_count = len(group.get("triggers", []))
    human_factor = "many_events" if event_count > 1 else None
    total = (
        score_supplier_criticality(
            resolve_supplier_criticality(request.supplier_criticality, str(group["company_guid"]))
        )
        + int(category_score.get("points", 0))
        + movement_points
        + score_human_factor(human_factor)
    )
    result = dict(trigger)
    result.update(
        {
            "company_guid": group["company_guid"],
            "company_name": group.get("name"),
            "primary_domain": group.get("primary_domain"),
            "category": category,
            "current_rating": group.get("current_rating"),
            "rating_movement": movement,
            "rating_before": trigger.get("rating_before"),
            "rating_after": trigger.get("rating_after"),
            "priority_score": total,
            "priority": compute_priority_level(total),
            "priority_level": compute_priority_level(total),
            "warnings": [movement["warning"]] if "warning" in movement else [],
            "raw_evidence_reference": trigger.get("raw_alert"),
        }
    )
    return result


async def run_alert_workflow_action_payload(
    call_v2_tool: CallV2Tool,
    company_fetcher: CompanyFetcher | CallV1Tool,
    ctx: Any = None,
    *,
    request: AlertWorkflowRequest | None = None,
    alert_date_gte: str | None = None,
    page_size: int = 50,
    max_pages: int = 10,
    max_companies: int = 100,
    max_returned_priority: int = 4,
    human_factor: int = 1,
    supplier_criticality: Mapping[str, int] | None = None,
    severity: str | None = None,
    alert_type: str | None = None,
    folder_guid: str | None = None,
) -> dict[str, Any]:
    """Run the alert workflow and return the caller-facing Jira action payload."""
    workflow_request = request or build_alert_workflow_request(
        alert_date_gte=alert_date_gte,
        page_size=page_size,
        max_pages=max_pages,
        max_companies=max_companies,
        max_returned_priority=max_returned_priority,
        human_factor=human_factor,
        supplier_criticality=supplier_criticality,
    )
    fetched = await fetch_v2_alert_pages(
        call_v2_tool,
        ctx,
        workflow_request,
        severity=severity,
        alert_type=alert_type,
        folder_guid=folder_guid,
    )
    triggers = [
        normalize_alert_trigger(alert, page["metadata"])
        for page in fetched["pages"]
        for alert in page["results"]
        if isinstance(alert, Mapping)
    ]
    grouped = group_alert_triggers_by_company(
        triggers, max_companies=workflow_request.max_companies
    )
    enriched = await enrich_company_groups(grouped, company_fetcher)

    candidates: list[dict[str, Any]] = []
    warnings = list(fetched["metadata"].get("warnings", []))
    warnings.extend(enriched["metadata"].get("warnings", []))
    for company_guid, group in enriched["groups"].items():
        records = [
            _trigger_candidate(trigger, group, workflow_request) for trigger in group["triggers"]
        ]
        if not records:
            continue
        candidate = max(records, key=lambda record: record.get("priority_score", 0))
        candidate["warnings"] = list(
            dict.fromkeys(warning for record in records for warning in record.get("warnings", []))
        )
        candidate["metadata"] = {"trigger_count": len(records)}
        candidates.append(candidate)

    filtered = filter_action_candidates(
        candidates, max_returned_priority=workflow_request.max_returned_priority
    )
    warnings.extend(filtered["metadata"].get("warnings", []))
    warnings.extend(
        warning
        for candidate in candidates
        for warning in candidate.get("warnings", [])
        if isinstance(warning, str)
    )
    return build_jira_action_payload(enriched, filtered, warnings=list(dict.fromkeys(warnings)))


__all__ = ["run_alert_workflow_action_payload"]
