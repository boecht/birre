"""Request and configuration contract for the alert workflow."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

DEFAULT_PAGE_SIZE = 50
DEFAULT_MAX_PAGES = 10
DEFAULT_MAX_COMPANIES = 100
DEFAULT_MAX_RETURNED_PRIORITY = 4
DEFAULT_HUMAN_FACTOR = 1
DEFAULT_SUPPLIER_CRITICALITY = 1


@dataclass(frozen=True)
class AlertWorkflowRequest:
    """Deterministic inputs and caps for one alert workflow run."""

    alert_date_gte: str | None
    page_size: int
    max_pages: int
    max_companies: int
    max_returned_priority: int
    human_factor: int
    supplier_criticality: Mapping[str, int]


def build_alert_workflow_request(
    *,
    alert_date_gte: str | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_companies: int = DEFAULT_MAX_COMPANIES,
    max_returned_priority: int = DEFAULT_MAX_RETURNED_PRIORITY,
    human_factor: int = DEFAULT_HUMAN_FACTOR,
    supplier_criticality: Mapping[str, int] | None = None,
) -> AlertWorkflowRequest:
    """Build and validate the request used by the alert workflow."""
    for name, value in (
        ("page_size", page_size),
        ("max_pages", max_pages),
        ("max_companies", max_companies),
    ):
        if value <= 0:
            raise ValueError(f"{name} must be greater than zero")

    if max_returned_priority < 0:
        raise ValueError("max_returned_priority must not be negative")
    if human_factor < 0:
        raise ValueError("human_factor must not be negative")

    criticality = dict(supplier_criticality or {})
    return AlertWorkflowRequest(
        alert_date_gte=alert_date_gte,
        page_size=page_size,
        max_pages=max_pages,
        max_companies=max_companies,
        max_returned_priority=max_returned_priority,
        human_factor=human_factor,
        supplier_criticality=MappingProxyType(criticality),
    )


def resolve_supplier_criticality(supplier_criticality: Mapping[str, int], company_guid: str) -> int:
    """Return the configured criticality for a GUID, or the neutral default."""
    return supplier_criticality.get(company_guid, DEFAULT_SUPPLIER_CRITICALITY)
