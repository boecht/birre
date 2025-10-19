from __future__ import annotations

import csv
import io
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from fastmcp import Context, FastMCP
from fastmcp.tools.tool import FunctionTool

from pydantic import BaseModel, Field, field_validator, model_validator

from src.config import DEFAULT_MAX_FINDINGS
from src.constants import DEFAULT_CONFIG_FILENAME

from .helpers import CallV1Tool, CallV2Tool
from ..logging import log_event, log_search_event


class SubscriptionSnapshot(BaseModel):
    active: bool
    subscription_type: Optional[str] = None
    folders: List[str] = Field(default_factory=list)
    subscription_end_date: Optional[str] = None


class CompanyInteractiveResult(BaseModel):
    label: str
    guid: str
    name: str
    primary_domain: str
    website: str
    description: str
    employee_count: Optional[int] = None
    subscription: SubscriptionSnapshot

    @model_validator(mode="before")
    @classmethod
    def _coerce_input(cls, value: Any) -> Dict[str, Any]:
        if not isinstance(value, dict):
            return {
                "label": "",
                "guid": "",
                "name": "",
                "primary_domain": "",
                "website": "",
                "description": "",
                "employee_count": None,
                "subscription": {},
            }
        return {
            "label": str(value.get("label") or ""),
            "guid": str(value.get("guid") or ""),
            "name": str(value.get("name") or ""),
            "primary_domain": str(value.get("primary_domain") or ""),
            "website": str(value.get("website") or ""),
            "description": str(value.get("description") or ""),
            "employee_count": value.get("employee_count"),
            "subscription": value.get("subscription") or {},
        }

    @field_validator("employee_count", mode="before")
    @classmethod
    def _normalize_employee_count(cls, value: Any) -> Optional[int]:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


class RiskManagerGuidance(BaseModel):
    selection: Optional[str] = None
    if_missing: Optional[str] = None
    default_folder: Optional[str] = None
    default_subscription_type: Optional[str] = None


class CompanySearchInteractiveResponse(BaseModel):
    error: Optional[str] = None
    count: int = Field(default=0, ge=0)
    results: List[CompanyInteractiveResult] = Field(default_factory=list)
    search_term: Optional[str] = None
    guidance: Optional[RiskManagerGuidance] = None
    truncated: bool = False

    def to_payload(self) -> Dict[str, Any]:
        if self.error:
            return {"error": self.error}
        data = self.model_dump(exclude_unset=True)
        data.pop("error", None)
        return data


class RequestGuidance(BaseModel):
    next_steps: Optional[str] = None
    confirmation: Optional[str] = None


class RequestCompanyResponse(BaseModel):
    error: Optional[str] = None
    status: Optional[str] = None
    domain: Optional[str] = None
    requests: Optional[List[Dict[str, Any]]] = None
    guidance: Optional[RequestGuidance] = None
    folder: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    subscription_type: Optional[str] = None
    result: Optional[Any] = None
    warning: Optional[str] = None

    def to_payload(self) -> Dict[str, Any]:
        if self.error:
            return {"error": self.error}
        data = self.model_dump(exclude_unset=True)
        data.pop("error", None)
        return data


class ManageSubscriptionsGuidance(BaseModel):
    confirmation: Optional[str] = None
    next_steps: Optional[str] = None


class ManageSubscriptionsSummary(BaseModel):
    added: List[Any] = Field(default_factory=list)
    deleted: List[Any] = Field(default_factory=list)
    modified: List[Any] = Field(default_factory=list)
    errors: List[Any] = Field(default_factory=list)


class ManageSubscriptionsResponse(BaseModel):
    error: Optional[str] = None
    status: Optional[str] = None
    action: Optional[str] = None
    guids: Optional[List[str]] = None
    folder: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    guidance: Optional[ManageSubscriptionsGuidance] = None
    summary: Optional[ManageSubscriptionsSummary] = None

    def to_payload(self) -> Dict[str, Any]:
        if self.error:
            return {"error": self.error}
        data = self.model_dump(exclude_unset=True)
        data.pop("error", None)
        return data


COMPANY_SEARCH_INTERACTIVE_OUTPUT_SCHEMA: Dict[str, Any] = (
    CompanySearchInteractiveResponse.model_json_schema()
)

REQUEST_COMPANY_OUTPUT_SCHEMA: Dict[str, Any] = (
    RequestCompanyResponse.model_json_schema()
)

MANAGE_SUBSCRIPTIONS_OUTPUT_SCHEMA: Dict[str, Any] = (
    ManageSubscriptionsResponse.model_json_schema()
)


@dataclass(frozen=True)
class CompanySearchInputs:
    name: Optional[str]
    domain: Optional[str]
    term: str


@dataclass(frozen=True)
class CompanySearchDefaults:
    folder: Optional[str]
    subscription_type: Optional[str]
    limit: int


def _coerce_guid_list(guids: Any) -> List[str]:
    if isinstance(guids, str):
        return [guid.strip() for guid in guids.split(",") if guid.strip()]
    if isinstance(guids, Sequence):
        return [str(item).strip() for item in guids if str(item).strip()]
    return []


def _normalize_action(value: str) -> Optional[str]:
    mapping = {
        "add": "add",
        "create": "add",
        "subscribe": "add",
        "subscription": "add",
        "remove": "delete",
        "delete": "delete",
        "unsubscribe": "delete",
    }
    key = value.strip().lower()
    return mapping.get(key)


async def _fetch_company_details(
    call_v1_tool: CallV1Tool,
    ctx: Context,
    guids: Sequence[str],
    *,
    logger: logging.Logger,
    limit: int,
) -> Dict[str, Dict[str, Any]]:
    """Retrieve detailed company records for the provided GUIDs."""

    effective_limit = (
        limit if isinstance(limit, int) and limit > 0 else DEFAULT_MAX_FINDINGS
    )

    details: Dict[str, Dict[str, Any]] = {}
    for guid in list(guids)[:effective_limit]:
        if not guid:
            continue
        guid_str = str(guid).strip()
        if not guid_str:
            continue
        params = {
            "guid": guid_str,
            "fields": "name,primary_domain,display_url,homepage,description,people_count,subscription_type,in_spm_portfolio,subscription_end_date",
        }
        try:
            result = await call_v1_tool("getCompany", ctx, params)
            if isinstance(result, dict):
                details[guid_str] = result
        except Exception as exc:  # pragma: no cover - defensive
            await ctx.warning(f"Failed to fetch company details for {guid_str}: {exc}")
            logger.warning(
                "company_detail.fetch_failed", extra={"company_guid": guid_str}
            )
    return details


def _extract_folder_name(folder: Any) -> Optional[str]:
    if not isinstance(folder, dict):
        return None
    folder_name = folder.get("name") or folder.get("description")
    if not folder_name:
        return None
    return folder_name


def _iter_folder_guids(folder: Dict[str, Any]) -> Iterable[str]:
    company_ids = folder.get("companies")
    if not isinstance(company_ids, list):
        return ()
    return (str(guid) for guid in company_ids if guid)


def _iter_folder_memberships(
    folders: Iterable[Any], guid_set: set[str]
) -> Iterable[tuple[str, str]]:
    for folder in folders:
        folder_name = _extract_folder_name(folder)
        if not folder_name:
            continue
        for guid in _iter_folder_guids(folder):
            if guid in guid_set:
                yield str(guid), folder_name


async def _fetch_folder_memberships(
    call_v1_tool: CallV1Tool,
    ctx: Context,
    target_guids: Iterable[str],
    *,
    logger: logging.Logger,
) -> Dict[str, List[str]]:
    """Build a mapping of company GUID to folder names."""

    guid_set = {str(guid) for guid in target_guids if guid}
    if not guid_set:
        return {}

    try:
        folders = await call_v1_tool("getFolders", ctx, {})
    except Exception as exc:  # pragma: no cover - defensive
        await ctx.warning(f"Unable to fetch folder list: {exc}")
        logger.warning("folders.fetch_failed", exc_info=True)
        return {}

    if not isinstance(folders, list):
        return {}

    membership: defaultdict[str, List[str]] = defaultdict(list)
    for guid, folder_name in _iter_folder_memberships(folders, guid_set):
        membership[guid].append(folder_name)
    return dict(membership)


def _normalize_candidate_results(raw_result: Any) -> List[Any]:
    if isinstance(raw_result, dict):
        for key in ("results", "companies"):
            value = raw_result.get(key)
            if isinstance(value, list):
                return value
        return [raw_result]
    if isinstance(raw_result, list):
        return raw_result
    return []


def _build_candidate(entry: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(entry, dict):
        return None

    details = entry.get("details") if isinstance(entry.get("details"), dict) else {}
    primary_domain = (
        entry.get("primary_domain")
        or entry.get("domain")
        or entry.get("display_url")
        or ""
    )
    website = (
        entry.get("company_url")
        or entry.get("homepage")
        or entry.get("website")
        or primary_domain
    )

    return {
        "guid": entry.get("guid"),
        "name": entry.get("name") or entry.get("display_name"),
        "primary_domain": primary_domain,
        "website": website,
        "description": entry.get("description")
        or entry.get("business_description"),
        "employee_count": details.get("employee_count")
        or entry.get("people_count"),
        "in_portfolio": entry.get("in_portfolio"),
        "subscription_type": entry.get("subscription_type"),
    }


def _extract_search_candidates(raw_result: Any) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for entry in _normalize_candidate_results(raw_result):
        candidate = _build_candidate(entry)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def _build_subscription_snapshot(
    detail: Dict[str, Any],
    folders: Sequence[str],
) -> Dict[str, Any]:
    active = bool(detail.get("in_spm_portfolio")) or bool(folders)
    return {
        "active": active,
        "subscription_type": detail.get("subscription_type"),
        "folders": list(folders),
        "subscription_end_date": detail.get("subscription_end_date"),
    }


def _format_result_entry(
    candidate: Dict[str, Any],
    detail: Dict[str, Any],
    folders: Sequence[str],
) -> Dict[str, Any]:
    guid = candidate.get("guid") or detail.get("guid") or ""
    name = candidate.get("name") or detail.get("name") or ""
    label = f"{name} ({guid})" if guid else name
    description = (
        candidate.get("description")
        or detail.get("description")
        or detail.get("shortname")
    )
    employee_count = candidate.get("employee_count") or detail.get("people_count")
    return {
        "label": label,
        "guid": guid,
        "name": name,
        "primary_domain": candidate.get("primary_domain")
        or detail.get("primary_domain")
        or "",
        "website": candidate.get("website") or detail.get("homepage") or "",
        "description": description or "",
        "employee_count": employee_count,
        "subscription": _build_subscription_snapshot(detail, folders),
    }


def _validate_company_search_inputs(
    name: Optional[str], domain: Optional[str]
) -> Optional[Dict[str, Any]]:
    if name or domain:
        return None
    return {
        "error": "Provide at least 'name' or 'domain' for the search",
    }


def _build_company_search_params(
    name: Optional[str], domain: Optional[str]
) -> tuple[Dict[str, Any], str]:
    params: Dict[str, Any] = {"expand": "details.employee_count"}
    if domain:
        params["domain"] = domain
        if name:
            params["name"] = name
    elif name:
        params["name"] = name
    search_term = domain or name or ""
    return params, search_term


async def _perform_company_search(
    call_v1_tool: CallV1Tool,
    ctx: Context,
    search_params: Dict[str, Any],
    logger: logging.Logger,
    *,
    name: Optional[str],
    domain: Optional[str],
) -> tuple[Optional[Any], Optional[Dict[str, Any]]]:
    try:
        result = await call_v1_tool("companySearch", ctx, search_params)
    except Exception as exc:
        await ctx.error(f"Company search failed: {exc}")
        log_search_event(
            logger,
            "failure",
            ctx=ctx,
            company_name=name,
            company_domain=domain,
            error=str(exc),
        )
        return None, {"error": f"FastMCP company search failed: {exc}"}
    return result, None


def _build_empty_search_response(
    search_term: str,
    *,
    default_folder: Optional[str],
    default_type: Optional[str],
) -> CompanySearchInteractiveResponse:
    return CompanySearchInteractiveResponse(
        count=0,
        results=[],
        search_term=search_term,
        guidance=RiskManagerGuidance(
            selection="No matches were returned. Confirm the organization name or domain with the operator.",
            if_missing="Invoke `request_company` to submit an onboarding request when the entity is absent.",
            default_folder=default_folder,
            default_subscription_type=default_type,
        ),
        truncated=False,
    )


def _build_guid_order(candidates: Iterable[Dict[str, Any]]) -> List[str]:
    guid_order: List[str] = []
    for candidate in candidates:
        guid_value = candidate.get("guid")
        if isinstance(guid_value, str):
            guid_str = guid_value.strip()
            if guid_str:
                guid_order.append(guid_str)
    return guid_order


def _enrich_candidates(
    candidates: Iterable[Dict[str, Any]],
    details: Dict[str, Dict[str, Any]],
    memberships: Dict[str, List[str]],
) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    for candidate in candidates:
        guid_any = candidate.get("guid")
        if not isinstance(guid_any, str) or not guid_any:
            continue
        detail = details.get(guid_any) or {}
        folders = memberships.get(guid_any) or []
        enriched.append(_format_result_entry(candidate, detail, folders))
    return enriched


async def _build_company_search_response(
    call_v1_tool: CallV1Tool,
    ctx: Context,
    *,
    logger: logging.Logger,
    raw_result: Any,
    search: CompanySearchInputs,
    defaults: CompanySearchDefaults,
) -> CompanySearchInteractiveResponse:
    candidates = _extract_search_candidates(raw_result)
    guid_order = _build_guid_order(candidates)

    if not guid_order:
        log_search_event(
            logger,
            "success",
            ctx=ctx,
            company_name=search.name,
            company_domain=search.domain,
            result_count=0,
        )
        return _build_empty_search_response(
            search.term,
            default_folder=defaults.folder,
            default_type=defaults.subscription_type,
        )

    details = await _fetch_company_details(
        call_v1_tool,
        ctx,
        guid_order,
        logger=logger,
        limit=defaults.limit,
    )
    memberships = await _fetch_folder_memberships(
        call_v1_tool,
        ctx,
        guid_order,
        logger=logger,
    )

    enriched = _enrich_candidates(candidates, details, memberships)
    result_count = len(enriched)

    log_search_event(
        logger,
        "success",
        ctx=ctx,
        company_name=search.name,
        company_domain=search.domain,
        result_count=result_count,
    )

    truncated = len(guid_order) > defaults.limit

    result_models = [
        CompanyInteractiveResult.model_validate(entry) for entry in enriched
    ]

    return CompanySearchInteractiveResponse(
        count=result_count,
        results=result_models,
        search_term=search.term,
        guidance=RiskManagerGuidance(
            selection="Present the results to the human risk manager and collect the desired GUID before calling subscription or rating tools.",
            if_missing="If the correct organization is absent, call `request_company` with the validated domain and optional folder.",
            default_folder=defaults.folder,
            default_subscription_type=defaults.subscription_type,
        ),
        truncated=truncated,
    )


def register_company_search_interactive_tool(
    business_server: FastMCP,
    call_v1_tool: CallV1Tool,
    *,
    logger: logging.Logger,
    default_folder: Optional[str],
    default_type: Optional[str],
    max_findings: int = DEFAULT_MAX_FINDINGS,
) -> FunctionTool:
    effective_limit = max_findings if max_findings > 0 else DEFAULT_MAX_FINDINGS

    async def company_search_interactive(
        ctx: Context,
        name: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return enriched search results for human-in-the-loop selection."""

        validation_error = _validate_company_search_inputs(name, domain)
        if validation_error:
            return CompanySearchInteractiveResponse(**validation_error).to_payload()

        search_params, search_term = _build_company_search_params(name, domain)

        await ctx.info(f"risk-manager search for: {search_term}")
        log_search_event(
            logger,
            "start",
            ctx=ctx,
            company_name=name,
            company_domain=domain,
            persona="risk_manager",
        )

        raw_result, failure_response = await _perform_company_search(
            call_v1_tool,
            ctx,
            search_params,
            logger,
            name=name,
            domain=domain,
        )
        if failure_response is not None:
            return CompanySearchInteractiveResponse(**failure_response).to_payload()

        search = CompanySearchInputs(name=name, domain=domain, term=search_term)
        defaults = CompanySearchDefaults(
            folder=default_folder,
            subscription_type=default_type,
            limit=effective_limit,
        )
        response_model = await _build_company_search_response(
            call_v1_tool,
            ctx,
            logger=logger,
            raw_result=raw_result,
            search=search,
            defaults=defaults,
        )
        return response_model.to_payload()

    return business_server.tool(
        output_schema=COMPANY_SEARCH_INTERACTIVE_OUTPUT_SCHEMA
    )(company_search_interactive)


async def _resolve_folder_guid(
    call_v1_tool: CallV1Tool,
    ctx: Context,
    folder_name: Optional[str],
) -> Optional[str]:
    if not folder_name:
        return None
    folders = await call_v1_tool("getFolders", ctx, {})
    if not isinstance(folders, list):
        return None
    normalized = folder_name.strip().lower()
    for folder in folders:
        if not isinstance(folder, dict):
            continue
        name = folder.get("name")
        guid = folder.get("guid")
        if not name or not guid:
            continue
        if name.strip().lower() == normalized:
            return guid
    return None


async def _list_company_requests(
    call_v2_tool: CallV2Tool,
    ctx: Context,
    domain: str,
) -> List[Dict[str, Any]]:
    params = {"domain": domain, "limit": 5}
    try:
        result = await call_v2_tool("getCompanyRequests", ctx, params)
    except Exception:
        return []
    if isinstance(result, dict):
        if isinstance(result.get("results"), list):
            return result["results"]
        if isinstance(result.get("company_requests"), list):
            return result["company_requests"]
    return []


def _serialize_bulk_csv(domain: str, company_name: Optional[str]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["domain", "company_name"])
    writer.writerow([domain, company_name or ""])
    return buffer.getvalue()


def _normalize_domain(
    domain: str,
    *,
    logger: logging.Logger,
    ctx: Context,
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    domain_value = (domain or "").strip().lower()
    if domain_value:
        return domain_value, None

    log_event(
        logger,
        "company_request.invalid_domain",
        level=logging.WARNING,
        ctx=ctx,
        domain=domain,
    )
    return None, {"error": "Domain is required to request a company"}


async def _resolve_folder_selection(
    call_v1_tool: CallV1Tool,
    ctx: Context,
    *,
    logger: logging.Logger,
    domain_value: str,
    selected_folder: Optional[str],
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    if not selected_folder:
        return None, None

    folder_guid = await _resolve_folder_guid(call_v1_tool, ctx, selected_folder)
    if folder_guid is not None:
        return folder_guid, None

    log_event(
        logger,
        "company_request.folder_unknown",
        level=logging.WARNING,
        ctx=ctx,
        domain=domain_value,
        folder=selected_folder,
    )
    return None, {
        "error": (
            f"Unknown folder '{selected_folder}'. Call `company_search_interactive` "
            "to inspect available folders first."
        ),
    }


def _existing_requests_response(
    *,
    logger: logging.Logger,
    ctx: Context,
    domain_value: str,
    existing: List[Dict[str, Any]],
) -> RequestCompanyResponse:
    log_event(
        logger,
        "company_request.already_requested",
        ctx=ctx,
        domain=domain_value,
        existing_count=len(existing),
    )
    return RequestCompanyResponse(
        status="already_requested",
        domain=domain_value,
        requests=existing,
        guidance=RequestGuidance(
            next_steps="Monitor the existing request in BitSight or wait for fulfillment before retrying."
        ),
    )


def _build_bulk_payload(
    domain_value: str,
    company_name: Optional[str],
    folder_guid: Optional[str],
    subscription_type: Optional[str],
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "file": _serialize_bulk_csv(domain_value, company_name),
    }
    if folder_guid:
        payload["folder_guid"] = folder_guid
    if subscription_type:
        payload["subscription_type"] = subscription_type
    return payload


def _dry_run_response(
    *,
    logger: logging.Logger,
    ctx: Context,
    domain_value: str,
    selected_folder: Optional[str],
    subscription_type: Optional[str],
    bulk_payload: Dict[str, Any],
) -> RequestCompanyResponse:
    log_event(
        logger,
        "company_request.dry_run",
        ctx=ctx,
        domain=domain_value,
        folder=selected_folder,
        subscription_type=subscription_type,
    )
    return RequestCompanyResponse(
        status="dry_run",
        domain=domain_value,
        folder=selected_folder,
        payload=bulk_payload,
        guidance=RequestGuidance(
            confirmation="Share the preview with the human operator before submitting the real request."
        ),
    )


async def _submit_company_request(
    call_v2_tool: CallV2Tool,
    ctx: Context,
    *,
    logger: logging.Logger,
    domain_value: str,
    selected_folder: Optional[str],
    subscription_type: Optional[str],
    bulk_payload: Dict[str, Any],
) -> RequestCompanyResponse:
    try:
        result = await call_v2_tool("createCompanyRequestBulk", ctx, bulk_payload)
        log_event(
            logger,
            "company_request.submitted_bulk",
            ctx=ctx,
            domain=domain_value,
            folder=selected_folder,
            subscription_type=subscription_type,
        )
        return RequestCompanyResponse(
            status="submitted_v2_bulk",
            domain=domain_value,
            folder=selected_folder,
            subscription_type=subscription_type,
            result=result,
        )
    except Exception as exc:
        log_event(
            logger,
            "company_request.bulk_failed",
            level=logging.WARNING,
            ctx=ctx,
            domain=domain_value,
            folder=selected_folder,
            subscription_type=subscription_type,
            error=str(exc),
        )
        payload = {"company_request": {"domain": domain_value}}
        if subscription_type:
            payload["company_request"]["subscription_type"] = subscription_type
        result = await call_v2_tool("createCompanyRequest", ctx, payload)
        log_event(
            logger,
            "company_request.submitted_single",
            ctx=ctx,
            domain=domain_value,
            folder=selected_folder,
            subscription_type=subscription_type,
        )
        return RequestCompanyResponse(
            status="submitted_v2_single",
            domain=domain_value,
            folder=selected_folder,
            subscription_type=subscription_type,
            result=result,
            warning="The folder could not be specified via bulk API; adjust subscriptions once the request is approved.",
        )


def register_request_company_tool(
    business_server: FastMCP,
    call_v1_tool: CallV1Tool,
    call_v2_tool: CallV2Tool,
    *,
    logger: logging.Logger,
    default_folder: Optional[str],
    default_type: Optional[str],
) -> FunctionTool:
    async def request_company(
        ctx: Context,
        domain: str,
        *,
        company_name: Optional[str] = None,
        folder: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Submit a BitSight company onboarding request when an entity is missing."""

        domain_value, error = _normalize_domain(domain, logger=logger, ctx=ctx)
        if error:
            return RequestCompanyResponse(**error).to_payload()
        selected_folder = folder or default_folder
        folder_guid = None
        log_event(
            logger,
            "company_request.start",
            ctx=ctx,
            domain=domain_value,
            folder=selected_folder,
            dry_run=dry_run,
        )
        folder_guid, error = await _resolve_folder_selection(
            call_v1_tool,
            ctx,
            logger=logger,
            domain_value=domain_value,
            selected_folder=selected_folder,
        )
        if error:
            return RequestCompanyResponse(**error).to_payload()

        existing = await _list_company_requests(call_v2_tool, ctx, domain_value)
        if existing:
            return _existing_requests_response(
                logger=logger,
                ctx=ctx,
                domain_value=domain_value,
                existing=existing,
            ).to_payload()

        subscription_type = default_type

        bulk_payload = _build_bulk_payload(
            domain_value,
            company_name,
            folder_guid,
            subscription_type,
        )

        if dry_run:
            return _dry_run_response(
                logger=logger,
                ctx=ctx,
                domain_value=domain_value,
                selected_folder=selected_folder,
                subscription_type=subscription_type,
                bulk_payload=bulk_payload,
            ).to_payload()

        response_model = await _submit_company_request(
            call_v2_tool,
            ctx,
            logger=logger,
            domain_value=domain_value,
            selected_folder=selected_folder,
            subscription_type=subscription_type,
            bulk_payload=bulk_payload,
        )
        return response_model.to_payload()

    return business_server.tool(output_schema=REQUEST_COMPANY_OUTPUT_SCHEMA)(
        request_company
    )


def _build_subscription_payload(
    action: str,
    guids: Sequence[str],
    *,
    folder: Optional[str],
    subscription_type: Optional[str],
) -> Dict[str, Any]:
    if action == "add":
        entries: List[Dict[str, Any]] = []
        for guid in guids:
            entry: Dict[str, Any] = {"guid": guid}
            if subscription_type:
                entry["type"] = subscription_type
            if folder:
                entry["folder"] = [folder]
            entries.append(entry)
        return {"add": entries}
    if action == "delete":
        return {"delete": [{"guid": guid} for guid in guids]}
    raise ValueError(f"Unsupported action: {action}")


def _summarize_bulk_result(result: Any) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return {"raw": result}
    return {
        "added": result.get("added", []),
        "deleted": result.get("deleted", []),
        "modified": result.get("modified", []),
        "errors": result.get("errors", []),
    }


def register_manage_subscriptions_tool(
    business_server: FastMCP,
    call_v1_tool: CallV1Tool,
    *,
    logger: logging.Logger,
    default_folder: Optional[str],
    default_type: Optional[str],
) -> FunctionTool:
    async def manage_subscriptions(
        ctx: Context,
        action: str,
        guids: Sequence[str],
        *,
        folder: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Bulk subscribe or unsubscribe companies using BitSight's v1 API."""

        normalized_action = _normalize_action(action)
        if normalized_action is None:
            return ManageSubscriptionsResponse(
                error="Unsupported action. Use one of: add, subscribe, remove, delete, unsubscribe"
            ).to_payload()

        guid_list = _coerce_guid_list(guids)
        if not guid_list:
            return ManageSubscriptionsResponse(
                error="At least one company GUID must be supplied"
            ).to_payload()

        target_folder = folder or default_folder
        if normalized_action == "add" and not default_type:
            return ManageSubscriptionsResponse(
                error=(
                    "Subscription type is not configured. Provide a subscription_type via CLI "
                    "arguments, set BIRRE_SUBSCRIPTION_TYPE in the environment, or update "
                    f"{DEFAULT_CONFIG_FILENAME}."
                )
            ).to_payload()

        payload = _build_subscription_payload(
            normalized_action,
            guid_list,
            folder=target_folder,
            subscription_type=default_type,
        )

        if dry_run:
            return ManageSubscriptionsResponse(
                status="dry_run",
                action=normalized_action,
                guids=guid_list,
                folder=target_folder,
                payload=payload,
                guidance=ManageSubscriptionsGuidance(
                    confirmation="Review the payload with the human operator. Re-run with dry_run=false to apply changes."
                ),
            ).to_payload()

        await ctx.info(
            f"Executing manageSubscriptionsBulk action={normalized_action} for {len(guid_list)} companies"
        )

        try:
            result = await call_v1_tool("manageSubscriptionsBulk", ctx, payload)
        except Exception as exc:
            await ctx.error(f"Subscription management failed: {exc}")
            logger.error(
                "manage_subscriptions.failed",
                extra={"action": normalized_action, "count": len(guid_list)},
                exc_info=True,
            )
            return ManageSubscriptionsResponse(
                error=f"manageSubscriptionsBulk failed: {exc}"
            ).to_payload()

        summary = _summarize_bulk_result(result)
        summary_model = ManageSubscriptionsSummary.model_validate(summary)
        return ManageSubscriptionsResponse(
            status="applied",
            action=normalized_action,
            guids=guid_list,
            folder=target_folder,
            summary=summary_model,
            guidance=ManageSubscriptionsGuidance(
                next_steps="Run `get_company_rating` for a sample GUID to verify post-change access."
            ),
        ).to_payload()

    return business_server.tool(output_schema=MANAGE_SUBSCRIPTIONS_OUTPUT_SCHEMA)(
        manage_subscriptions
    )


__all__ = [
    "register_company_search_interactive_tool",
    "register_manage_subscriptions_tool",
    "register_request_company_tool",
]
