"""BitSight v2 alert paging for the security analyst workflow."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from birre.domain.security_analyst.request import AlertWorkflowRequest

V2_ALERTS_ENDPOINT = "getAlerts"


async def enrich_company_groups(
    grouped: Mapping[str, Any],
    company_fetcher: Callable[[str], Awaitable[Any]],
) -> dict[str, Any]:
    """Attach v1 company profile data to grouped alert triggers."""
    enriched_groups: dict[str, dict[str, Any]] = {}
    warnings = list(grouped.get("metadata", {}).get("warnings", []))

    for company_guid, group in grouped.get("groups", {}).items():
        record = dict(group)
        record["company_guid"] = company_guid
        record["enrichment_status"] = "enriched"
        record["enrichment_warnings"] = []
        try:
            company = await company_fetcher(company_guid)
            if not isinstance(company, Mapping):
                raise ValueError("company fetcher returned a non-mapping response")
            for field in ("name", "primary_domain", "current_rating", "ratings"):
                if field in company:
                    record[field] = company[field]
        except Exception:
            record["enrichment_status"] = "failed"
            record["enrichment_warnings"] = ["company_enrichment_failed"]
            if "company_enrichment_failed" not in warnings:
                warnings.append("company_enrichment_failed")
        enriched_groups[company_guid] = record

    return {"groups": enriched_groups, "metadata": {"warnings": warnings}}


def group_alert_triggers_by_company(
    triggers: list[Mapping[str, Any]], *, max_companies: int
) -> dict[str, Any]:
    """Group enrichable trigger records by company GUID within the company cap."""
    if max_companies <= 0:
        raise ValueError("max_companies must be greater than zero")

    groups: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []

    for trigger in triggers:
        if not trigger.get("enrichable", False):
            for warning in trigger.get("warnings", []):
                if warning not in warnings:
                    warnings.append(warning)
            continue

        company_guid = trigger.get("company_guid")
        if not isinstance(company_guid, str) or not company_guid:
            continue
        if company_guid not in groups:
            if len(groups) >= max_companies:
                if "company_cap_reached" not in warnings:
                    warnings.append("company_cap_reached")
                continue
            groups[company_guid] = {
                "company_guid": company_guid,
                "triggers": [],
                "warnings": [],
            }
        groups[company_guid]["triggers"].append(dict(trigger))

    return {"groups": groups, "metadata": {"warnings": warnings}}


def normalize_alert_trigger(
    alert: Mapping[str, Any], page_metadata: Mapping[str, Any]
) -> dict[str, Any]:
    """Convert one v2 alert item into a loss-aware trigger record."""
    company_guid = alert.get("company_guid")
    record = {
        "alert_guid": alert.get("guid"),
        "company_guid": company_guid,
        "company_name": alert.get("company_name"),
        "alert_type": alert.get("alert_type"),
        "alert_date": alert.get("alert_date"),
        "start_date": alert.get("start_date"),
        "severity": alert.get("severity"),
        "trigger": alert.get("trigger"),
        "folder_context": {
            key: alert[key]
            for key in ("folder_guid", "folder_name", "alert_set_guid", "alert_set_name")
            if key in alert
        },
        "details": alert.get("details"),
        "raw_alert": dict(alert),
        "source_metadata": dict(page_metadata),
        "enrichable": bool(company_guid),
        "warnings": [],
    }
    if not company_guid:
        record["warnings"].append("company_guid_missing_anomaly")
    return record


def _next_page(response: Mapping[str, Any]) -> Any:
    links = response.get("links")
    if isinstance(links, Mapping) and links.get("next"):
        return links["next"]
    return response.get("next")


async def fetch_v2_alert_pages(
    call_v2_tool: Callable[[str, Any, dict[str, Any]], Awaitable[Any]],
    ctx: Any,
    request: AlertWorkflowRequest,
    *,
    severity: str | None = None,
    alert_type: str | None = None,
    folder_guid: str | None = None,
) -> dict[str, Any]:
    """Fetch alert pages while preserving source and truncation metadata."""
    pages: list[dict[str, Any]] = []
    warnings: list[str] = []
    offset = 0
    next_link: Any = True

    while next_link and len(pages) < request.max_pages:
        params = {
            "limit": request.page_size,
            "offset": offset,
            "expand": "details",
        }
        for key, value in (
            ("alert_date_gte", request.alert_date_gte),
            ("severity", severity),
            ("alert_type", alert_type),
            ("folder_guid", folder_guid),
        ):
            if value is not None:
                params[key] = value

        response = await call_v2_tool(V2_ALERTS_ENDPOINT, ctx, params)
        if not isinstance(response, Mapping) or not isinstance(response.get("results"), list):
            raise ValueError("v2 alert response must contain a list-valued results field")

        pages.append(
            {
                "results": response["results"],
                "raw_response": response,
                "metadata": {
                    "endpoint": V2_ALERTS_ENDPOINT,
                    "query": params,
                    "page_index": len(pages),
                    "offset": offset,
                },
            }
        )
        next_link = _next_page(response)
        offset += request.page_size

    if next_link:
        warnings.append("alert_page_cap_reached")

    return {
        "pages": pages,
        "metadata": {
            "endpoint": V2_ALERTS_ENDPOINT,
            "warnings": warnings,
            "page_count": len(pages),
        },
    }
