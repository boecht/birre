"""Risk manager tooling (interactive search, subscriptions, onboarding)."""

from __future__ import annotations

import csv
import io
import logging
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, cast

from fastmcp import Context, FastMCP
from fastmcp.tools.tool import FunctionTool
from pydantic import BaseModel, Field, field_validator, model_validator

from birre.config.constants import DEFAULT_CONFIG_FILENAME
from birre.config.settings import DEFAULT_MAX_FINDINGS
from birre.domain.common import CallV1Tool, CallV2Tool
from birre.domain.company_rating.constants import DEFAULT_FINDINGS_LIMIT
from birre.domain.company_rating.service import _rating_color
from birre.domain.folders.utils import resolve_or_create_folder
from birre.infrastructure.logging import BoundLogger, log_event, log_search_event

MAX_REQUEST_COMPANY_DOMAINS = 255


class SubscriptionSnapshot(BaseModel):
    active: bool
    subscription_type: str | None = None
    folders: list[str] = Field(default_factory=list)
    subscription_end_date: str | None = None


class CompanyInteractiveResult(BaseModel):
    label: str
    guid: str
    name: str
    primary_domain: str
    website: str
    description: str
    employee_count: int | None = None
    rating: int | None = None
    rating_color: str | None = None
    subscription: SubscriptionSnapshot

    @model_validator(mode="before")
    @classmethod
    def _coerce_input(cls, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {
                "label": "",
                "guid": "",
                "name": "",
                "primary_domain": "",
                "website": "",
                "description": "",
                "employee_count": None,
                "rating": None,
                "rating_color": None,
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
            "rating": value.get("rating"),
            "rating_color": value.get("rating_color"),
            "subscription": value.get("subscription") or {},
        }

    @field_validator("employee_count", mode="before")
    @classmethod
    def _normalize_employee_count(cls, value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


class RiskManagerGuidance(BaseModel):
    selection: str | None = None
    if_missing: str | None = None
    default_folder: str | None = None
    default_subscription_type: str | None = None


class CompanySearchInteractiveResponse(BaseModel):
    error: str | None = None
    count: int = Field(default=0, ge=0)
    results: list[CompanyInteractiveResult] = Field(default_factory=list)
    search_term: str | None = None
    guidance: RiskManagerGuidance | None = None
    truncated: bool = False

    def to_payload(self) -> dict[str, Any]:
        if self.error:
            return {"error": self.error}
        data = self.model_dump(exclude_unset=True, exclude_none=True)
        data.pop("error", None)
        return data


class RequestGuidance(BaseModel):
    next_steps: str | None = None
    confirmation: str | None = None


class RequestCompanyExistingEntry(BaseModel):
    domain: str
    company_name: str | None = None


class RequestCompanyFailedEntry(BaseModel):
    domain: str
    error: str


class RequestCompanyResponse(BaseModel):
    error: str | None = None
    status: str | None = None
    submitted: list[str] = Field(default_factory=list)
    already_existing: list[RequestCompanyExistingEntry] = Field(default_factory=list)
    successfully_requested: list[str] = Field(default_factory=list)
    failed: list[RequestCompanyFailedEntry] = Field(default_factory=list)
    dry_run: bool = False
    csv_preview: str | None = None
    guidance: RequestGuidance | None = None
    folder: str | None = None
    folder_guid: str | None = None
    folder_created: bool | None = None
    result: Any | None = None

    def to_payload(self) -> dict[str, Any]:
        if self.error:
            return {"error": self.error}
        data = self.model_dump(exclude_unset=True)
        data.pop("error", None)
        return data


class ManageSubscriptionsGuidance(BaseModel):
    confirmation: str | None = None
    next_steps: str | None = None


class ManageSubscriptionsSummary(BaseModel):
    added: list[Any] = Field(default_factory=list)
    deleted: list[Any] = Field(default_factory=list)
    modified: list[Any] = Field(default_factory=list)
    errors: list[Any] = Field(default_factory=list)


class ManageSubscriptionsResponse(BaseModel):
    error: str | None = None
    status: str | None = None
    action: str | None = None
    guids: list[str] | None = None
    folder: str | None = None
    folder_guid: str | None = None
    folder_created: bool | None = None
    payload: dict[str, Any] | None = None
    guidance: ManageSubscriptionsGuidance | None = None
    summary: ManageSubscriptionsSummary | None = None

    def to_payload(self) -> dict[str, Any]:
        if self.error:
            return {"error": self.error}
        data = self.model_dump(exclude_unset=True)
        data.pop("error", None)
        return data


@dataclass
class ManageSubscriptionsFolderState:
    folder: str | None
    folder_guid: str | None = None
    folder_created: bool = False
    folder_pending_reason: str | None = None


COMPANY_SEARCH_INTERACTIVE_OUTPUT_SCHEMA: dict[str, Any] = (
    CompanySearchInteractiveResponse.model_json_schema()
)

REQUEST_COMPANY_OUTPUT_SCHEMA: dict[str, Any] = (
    RequestCompanyResponse.model_json_schema()
)

MANAGE_SUBSCRIPTIONS_OUTPUT_SCHEMA: dict[str, Any] = (
    ManageSubscriptionsResponse.model_json_schema()
)


@dataclass
class RequestCompanyState:
    submitted_domains: list[str]
    remaining_domains: list[str]
    existing_entries: list[RequestCompanyExistingEntry]
    selected_folder: str | None
    folder_guid: str | None
    folder_created: bool
    folder_pending_reason: str | None
    csv_body: str


@dataclass(frozen=True)
class CompanySearchInputs:
    name: str | None
    domain: str | None
    term: str


@dataclass(frozen=True)
class CompanySearchDefaults:
    folder: str | None
    subscription_type: str | None
    limit: int


def _coerce_guid_list(guids: Any) -> list[str]:
    if isinstance(guids, str):
        return [guid.strip() for guid in guids.split(",") if guid.strip()]
    if isinstance(guids, Iterable):
        return [str(item).strip() for item in guids if str(item).strip()]
    return []


def _normalize_action(value: str) -> str | None:
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
    logger: BoundLogger,
    limit: int,
) -> dict[str, dict[str, Any]]:
    """Retrieve detailed company records for the provided GUIDs.

    Requires companies to be already subscribed (via bulk subscription).
    """

    effective_limit = (
        limit if isinstance(limit, int) and limit > 0 else DEFAULT_MAX_FINDINGS
    )

    details: dict[str, dict[str, Any]] = {}
    for guid in list(guids)[:effective_limit]:
        if not guid:
            continue
        guid_str = str(guid).strip()
        if not guid_str:
            continue

        params = {
            "guid": guid_str,
            "fields": (
                "guid,name,description,primary_domain,display_url,homepage,"
                "people_count,subscription_type,in_spm_portfolio,subscription_end_date,"
                "current_rating,has_company_tree"
            ),
        }
        try:
            result = await call_v1_tool("getCompany", ctx, params)
            if isinstance(result, dict):
                details[guid_str] = result
        except Exception as exc:  # pragma: no cover - defensive
            await ctx.warning(f"Failed to fetch company details for {guid_str}: {exc}")
            logger.warning(
                "company_detail.fetch_failed",
                company_guid=guid_str,
            )

    return details


async def _fetch_company_tree(
    call_v1_tool: CallV1Tool,
    ctx: Context,
    guid: str,
    *,
    logger: BoundLogger,
) -> dict[str, Any] | None:
    """
    Fetch company tree from BitSight API.

    Returns tree structure with parent-child relationships, or None if no tree exists.
    """
    try:
        params = {"guid": str(guid).strip()}
        tree_data = await call_v1_tool("getCompaniesTree", ctx, params)
        if isinstance(tree_data, dict):
            logger.debug(
                "company_tree.fetched",
                company_guid=guid,
                has_tree=True,
            )
            return tree_data
        return None
    except Exception as error:  # pragma: no cover - defensive
        await ctx.warning(f"Failed to fetch company tree for {guid}: {error}")
        logger.warning(
            "company_tree.fetch_failed",
            company_guid=guid,
            error=str(error),
        )
        return None


def _find_company_in_tree(
    tree_node: dict[str, Any], target_guid: str, path: list[str] | None = None
) -> list[str] | None:
    """
    Recursively find path from root to target company in tree.

    Returns list of GUIDs from root to target (excluding target itself),
    or None if target not found in this branch.
    """
    if path is None:
        path = []

    node_guid = tree_node.get("guid")
    if not node_guid:
        return None

    # Found the target - return path (excluding target)
    if str(node_guid) == str(target_guid):
        return path.copy()

    # Recurse into children
    children = tree_node.get("children", [])
    if not isinstance(children, list):
        return None

    new_path = path + [str(node_guid)]
    for child in children:
        if not isinstance(child, dict):
            continue
        result = _find_company_in_tree(child, target_guid, new_path)
        if result is not None:
            return result

    return None


def _find_node_in_tree(
    tree_node: dict[str, Any], target_guid: str
) -> dict[str, Any] | None:
    """
    Recursively find a node with the given GUID in the tree.

    Returns the node dict if found, None otherwise.
    """
    node_guid = tree_node.get("guid")
    if node_guid and str(node_guid) == str(target_guid):
        return tree_node

    children = tree_node.get("children", [])
    if not isinstance(children, list):
        return None

    for child in children:
        if not isinstance(child, dict):
            continue
        result = _find_node_in_tree(child, target_guid)
        if result is not None:
            return result

    return None


def _extract_parent_guids(tree_root: dict[str, Any], company_guid: str) -> list[str]:
    """
    Extract all parent GUIDs from root to company (excluding company itself).

    Returns list ordered from immediate parent to root.
    Example: If tree is Root -> Parent -> Company, returns [Parent, Root]
    """
    path = _find_company_in_tree(tree_root, company_guid)
    if not path:
        return []

    # Reverse to get immediate parent first, then grandparent, etc.
    return list(reversed(path))


def _extract_folder_name(folder: Any) -> str | None:
    if not isinstance(folder, dict):
        return None
    folder_name = folder.get("name") or folder.get("description")
    if not folder_name:
        return None
    if not isinstance(folder_name, str):
        return None
    return folder_name


def _iter_folder_guids(folder: dict[str, Any]) -> Iterable[str]:
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
    logger: BoundLogger,
) -> dict[str, list[str]]:
    """Build a mapping of company GUID to folder names."""

    guid_set = {str(guid) for guid in target_guids if guid}
    if not guid_set:
        return {}

    try:
        folders = await call_v1_tool("getFolders", ctx, {})
    except Exception as exc:  # pragma: no cover - defensive
        await ctx.warning(f"Unable to fetch folder list: {exc}")
        logger_obj = getattr(logger, "_logger", None)
        exc_info = (
            exc if logger_obj and logger_obj.isEnabledFor(logging.DEBUG) else False
        )
        logger.warning(
            "folders.fetch_failed",
            error=str(exc),
            exc_info=exc_info,
        )
        return {}

    if not isinstance(folders, list):
        return {}

    membership: defaultdict[str, list[str]] = defaultdict(list)
    for guid, folder_name in _iter_folder_memberships(folders, guid_set):
        membership[guid].append(folder_name)
    return dict(membership)


def _normalize_candidate_results(raw_result: Any) -> list[Any]:
    if isinstance(raw_result, dict):
        for key in ("results", "companies"):
            value = raw_result.get(key)
            if isinstance(value, list):
                return value
        return [raw_result]
    if isinstance(raw_result, list):
        return raw_result
    return []


def _build_candidate(entry: Any) -> dict[str, Any | None] | None:
    if not isinstance(entry, dict):
        return None

    details_raw = entry.get("details")
    details: dict[str, Any] = details_raw if isinstance(details_raw, dict) else {}
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
        "description": entry.get("description") or entry.get("business_description"),
        "employee_count": details.get("employee_count") or entry.get("people_count"),
        "in_portfolio": details.get("in_portfolio") or entry.get("in_portfolio"),
        "subscription_type": entry.get("subscription_type"),
    }


def _extract_search_candidates(raw_result: Any) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for entry in _normalize_candidate_results(raw_result):
        candidate = _build_candidate(entry)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def _build_subscription_snapshot(
    detail: dict[str, Any],
    folders: Sequence[str],
) -> dict[str, Any]:
    active = bool(detail.get("in_spm_portfolio")) or bool(folders)
    return {
        "active": active,
        "subscription_type": detail.get("subscription_type"),
        "folders": list(folders),
        "subscription_end_date": detail.get("subscription_end_date"),
    }


def _format_result_entry(
    candidate: dict[str, Any],
    detail: dict[str, Any],
    folders: Sequence[str],
) -> dict[str, Any]:
    guid = candidate.get("guid") or detail.get("guid") or ""
    name = candidate.get("name") or detail.get("name") or ""
    label = f"{name} ({guid})" if guid else name
    description = (
        candidate.get("description")
        or detail.get("description")
        or detail.get("shortname")
    )
    employee_count = candidate.get("employee_count") or detail.get("people_count")

    # Extract rating from detail (from getCompany call)
    current_rating = detail.get("current_rating")
    rating_value = None
    if current_rating is not None:
        try:
            rating_value = int(current_rating)
        except (TypeError, ValueError):
            pass

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
        "rating": rating_value,
        "rating_color": _rating_color(rating_value),
        "subscription": _build_subscription_snapshot(detail, folders),
    }


def _validate_company_search_inputs(
    name: str | None, domain: str | None
) -> dict[str, str] | None:
    if name or domain:
        return None
    return {
        "error": "Provide at least 'name' or 'domain' for the search",
    }


def _build_company_search_params(
    name: str | None, domain: str | None
) -> tuple[dict[str, Any], str]:
    params: dict[str, Any] = {"expand": "details.employee_count,details.in_portfolio"}
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
    search_params: dict[str, Any],
    logger: BoundLogger,
    *,
    name: str | None,
    domain: str | None,
) -> tuple[Any | None, dict[str, Any | None] | None]:
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
    default_folder: str | None,
    default_type: str | None,
) -> CompanySearchInteractiveResponse:
    return CompanySearchInteractiveResponse(
        count=0,
        results=[],
        search_term=search_term,
        guidance=RiskManagerGuidance(
            selection=(
                "No matches were returned. Confirm the organization name or "
                "domain with the operator."
            ),
            if_missing=(
                "Invoke `request_company` to submit an onboarding request "
                "when the entity is absent."
            ),
            default_folder=default_folder,
            default_subscription_type=default_type,
        ),
        truncated=False,
    )


# ... (content unchanged, truncated in commit payload generation)


def _request_company_dry_run_response(
    *,
    submitted_domains: Sequence[str],
    existing_entries: list[RequestCompanyExistingEntry],
    remaining_domains: Sequence[str],
    selected_folder: str | None,
    folder_guid: str | None,
    folder_created: bool,
    csv_body: str,
    pending_folder_reason: str | None,
) -> dict[str, Any]:
    guidance: RequestGuidance | None = None
    if pending_folder_reason:
        guidance = RequestGuidance(
            next_steps=pending_folder_reason,
            confirmation="Folder not created during dry run; \
                submission would create or require it.",
        )
    return RequestCompanyResponse(
        status="dry_run",
        submitted=list(submitted_domains),
        already_existing=existing_entries,
        successfully_requested=list(remaining_domains),
        failed=[],
        dry_run=True,
        folder=selected_folder,
        folder_guid=folder_guid,
        folder_created=folder_created or None,
        csv_preview=csv_body or None,
        guidance=guidance,
    ).to_payload()


def _manage_subscriptions_dry_run_response(
    *,
    action: str,
    guids: Sequence[str],
    folder: str | None,
    folder_guid: str | None,
    folder_created: bool,
    payload: dict[str, Any],
    pending_folder_reason: str | None,
) -> dict[str, Any]:
    guidance = ManageSubscriptionsGuidance(
        confirmation=(
            "Review the payload with the human operator. \
                Re-run with dry_run=false to apply changes."
        )
    )
    if pending_folder_reason:
        guidance.next_steps = pending_folder_reason

    return ManageSubscriptionsResponse(
        status="dry_run",
        action=action,
        guids=list(guids),
        folder=folder,
        folder_guid=folder_guid,
        folder_created=folder_created or None,
        payload=payload,
        guidance=guidance,
    ).to_payload()


def register_manage_subscriptions_tool(
    business_server: FastMCP,
    call_v1_tool: CallV1Tool,
    *,
    logger: BoundLogger,
    default_folder: str | None,
    default_folder_guid: str | None = None,
    default_type: str | None,
) -> FunctionTool:
    async def manage_subscriptions(
        ctx: Context,
        action: str,
        guids: str | list[str],
        *,
        folder: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Bulk subscribe or unsubscribe BitSight companies.

        Parameters
        - action: Desired change; accepts add/subscribe or delete/unsubscribe.
        - guids: Iterable of BitSight company GUIDs to modify.
        - folder: Optional folder to apply when subscribing (defaults to context).
        - dry_run: When True, return the planned payload instead of executing.

        Returns
        - ManageSubscriptionsResponse payload:
            {"status": str, "action": str, "guids": [...], "folder": str | None,
            "folder_guid": str | None, "folder_created": bool | None,
            "summary": {...}, "guidance": {...}} or {"error": str}

        Output semantics
        - status: "dry_run" or "applied".
        - action: Normalized action ("add" or "delete").
        - guids: Normalized GUID list targeted by the operation.
        - folder / folder_guid / folder_created: Folder context used for adds.
        - summary: Aggregated BitSight response (added / deleted / modified / errors).
        - guidance: Follow-up instruction (e.g., run get_company_rating to verify).
        - error: Present when validation fails or BitSight rejects the call.

        Notes
        - `dry_run=True` returns the computed payload so operators can audit
            the exact GUID/folder/type combination before executing.
        - Folder names are resolved (and created if necessary) when subscribing.
        - Only call this tool when the user explicitly asks to change
            subscriptions; discover GUIDs first via company_search or
            company_search_interactive.

        Example
        >>> manage_subscriptions(action="add", guids=["guid-1"], folder="Ops")
        {
            "status": "applied",
            "action": "add",
            "summary": {"added": ["guid-1"], "deleted": [], "errors": []},
            "guidance": {"next_steps": "Run get_company_rating for guid-1"}
        }
        """

        normalized_action, guid_list, error_payload = (
            _validate_manage_subscriptions_inputs(
                action,
                guids,
                default_type=default_type,
            )
        )
        if error_payload is not None or normalized_action is None:
            return (
                error_payload
                if error_payload is not None
                else _manage_subscriptions_error("Unknown subscription error")
            )

        target_folder = folder or default_folder
        folder_state, folder_error = await _prepare_manage_subscriptions_folder_state(
            normalized_action=normalized_action,
            target_folder=target_folder,
            default_folder=default_folder,
            default_folder_guid=default_folder_guid,
            call_v1_tool=call_v1_tool,
            ctx=ctx,
            logger=logger,
            allow_create=not dry_run,
        )
        if folder_error is not None:
            return folder_error

        payload = _build_subscription_payload(
            normalized_action,
            guid_list,
            folder_guid=folder_state.folder_guid,
            subscription_type=default_type,
        )

        dry_run_payload = _maybe_return_manage_subscriptions_dry_run(
            dry_run=dry_run,
            normalized_action=normalized_action,
            guid_list=guid_list,
            folder_state=folder_state,
            payload=payload,
        )
        if dry_run_payload is not None:
            return dry_run_payload

        return await _apply_manage_subscriptions_changes(
            call_v1_tool=call_v1_tool,
            ctx=ctx,
            payload=payload,
            normalized_action=normalized_action,
            guid_list=guid_list,
            logger=logger,
            target_folder=target_folder,
            folder_state=folder_state,
        )

    return business_server.tool(output_schema=MANAGE_SUBSCRIPTIONS_OUTPUT_SCHEMA)(
        manage_subscriptions
    )


__all__ = [
    "register_company_search_interactive_tool",
    "register_manage_subscriptions_tool",
    "register_request_company_tool",
]
