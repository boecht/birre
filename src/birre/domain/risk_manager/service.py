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


def _build_guid_order(candidates: Iterable[dict[str, Any]]) -> list[str]:
    guid_order: list[str] = []
    for candidate in candidates:
        guid_value = candidate.get("guid")
        if isinstance(guid_value, str):
            guid_str = guid_value.strip()
            if guid_str:
                guid_order.append(guid_str)
    return guid_order


def _enrich_candidates(
    candidates: Iterable[dict[str, Any]],
    details: dict[str, dict[str, Any]],
    memberships: dict[str, list[str]],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for candidate in candidates:
        guid_any = candidate.get("guid")
        if not isinstance(guid_any, str) or not guid_any:
            continue
        detail = details.get(guid_any) or {}
        folders = memberships.get(guid_any) or []
        enriched.append(_format_result_entry(candidate, detail, folders))
    return enriched


def _identify_non_subscribed_companies(
    candidates: Iterable[dict[str, Any]],
) -> list[str]:
    """Extract GUIDs of companies not in portfolio (need ephemeral subscription)."""
    non_subscribed: list[str] = []
    for candidate in candidates:
        if not candidate.get("in_portfolio"):
            guid = candidate.get("guid")
            if isinstance(guid, str) and guid:
                non_subscribed.append(guid)
    return non_subscribed


async def _bulk_subscribe_companies(
    call_v1_tool: CallV1Tool,
    ctx: Context,
    guids: Sequence[str],
    *,
    logger: BoundLogger,
    folder: str | None,
    subscription_type: str | None,
) -> set[str]:
    """Subscribe to multiple companies at once. Returns set of subscribed GUIDs."""
    if not guids:
        return set()

    try:
        payload = {
            "add": [
                {
                    "guid": guid,
                    **({"type": subscription_type} if subscription_type else {}),
                    **({"folder": [folder]} if folder else {}),
                }
                for guid in guids
            ]
        }
        await call_v1_tool("manageSubscriptionsBulk", ctx, payload)
        logger.info(
            "bulk_subscribe.success",
            count=len(guids),
            folder=folder,
            subscription_type=subscription_type,
        )
        return set(guids)
    except Exception as exc:
        await ctx.warning(f"Bulk subscription failed: {exc}")
        logger.warning(
            "bulk_subscribe.failed",
            count=len(guids),
            error=str(exc),
        )
        return set()


async def _bulk_unsubscribe_companies(
    call_v1_tool: CallV1Tool,
    ctx: Context,
    guids: Iterable[str],
    *,
    logger: BoundLogger,
) -> None:
    """Unsubscribe from multiple companies at once (cleanup ephemeral subscriptions)."""
    guid_list = list(guids)
    if not guid_list:
        return

    try:
        payload = {"delete": [{"guid": guid} for guid in guid_list]}
        await call_v1_tool("manageSubscriptionsBulk", ctx, payload)
        logger.info("bulk_unsubscribe.success", count=len(guid_list))
    except Exception as exc:
        await ctx.warning(f"Bulk unsubscription failed: {exc}")
        logger.warning(
            "bulk_unsubscribe.failed",
            count=len(guid_list),
            error=str(exc),
        )


async def _build_company_search_response(
    call_v1_tool: CallV1Tool,
    ctx: Context,
    *,
    logger: BoundLogger,
    raw_result: Any,
    search: CompanySearchInputs,
    defaults: CompanySearchDefaults,
) -> CompanySearchInteractiveResponse:
    """Build comprehensive search response with company details, trees, and parents."""
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

    # Subscribe to non-portfolio companies
    non_subscribed_guids = _identify_non_subscribed_companies(candidates)
    ephemeral_subscriptions = await _bulk_subscribe_companies(
        call_v1_tool,
        ctx,
        non_subscribed_guids[: defaults.limit],
        logger=logger,
        folder=defaults.folder,
        subscription_type=defaults.subscription_type,
    )

    try:
        # Fetch company details and trees
        details = await _fetch_company_details(
            call_v1_tool,
            ctx,
            guid_order,
            logger=logger,
            limit=defaults.limit,
        )

        trees = await _fetch_company_trees(
            call_v1_tool,
            ctx,
            details,
            logger=logger,
        )

        # Process parent companies
        (
            parent_details,
            parent_to_children,
            parent_ephemeral,
        ) = await _process_parent_companies(
            call_v1_tool,
            ctx,
            trees=trees,
            details=details,
            logger=logger,
            defaults=defaults,
        )
        ephemeral_subscriptions.update(parent_ephemeral)

        # Fetch folder memberships for all companies
        all_guids = list(guid_order) + list(parent_details.keys())
        memberships = await _fetch_folder_memberships(
            call_v1_tool,
            ctx,
            all_guids,
            logger=logger,
        )

        # Build enriched results
        all_details = {**details, **parent_details}
        enriched = _enrich_candidates(candidates, all_details, memberships)
        enriched.extend(
            _build_parent_entries(
                parent_details,
                details,
                parent_to_children,
                memberships,
            )
        )

        result_count = len(enriched)
        log_search_event(
            logger,
            "success",
            ctx=ctx,
            company_name=search.name,
            company_domain=search.domain,
            result_count=result_count,
        )
    finally:
        await _bulk_unsubscribe_companies(
            call_v1_tool,
            ctx,
            ephemeral_subscriptions,
            logger=logger,
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
            selection=(
                "Present the results to the human risk manager and collect the "
                "desired GUID before calling subscription or rating tools."
            ),
            if_missing=(
                "If the correct organization is absent, call `request_company` "
                "with the validated domain and optional folder."
            ),
            default_folder=defaults.folder,
            default_subscription_type=defaults.subscription_type,
        ),
        truncated=truncated,
    )


async def _fetch_company_trees(
    call_v1_tool: CallV1Tool,
    ctx: Context,
    details: dict[str, dict[str, Any]],
    *,
    logger: BoundLogger,
) -> dict[str, dict[str, Any]]:
    """Fetch company trees for companies that have them."""
    trees: dict[str, dict[str, Any]] = {}
    for guid, detail in details.items():
        has_tree = detail.get("has_company_tree")
        if has_tree:
            tree_data = await _fetch_company_tree(
                call_v1_tool,
                ctx,
                guid,
                logger=logger,
            )
            if tree_data:
                trees[guid] = tree_data
    return trees


async def _process_parent_companies(
    call_v1_tool: CallV1Tool,
    ctx: Context,
    *,
    trees: dict[str, dict[str, Any]],
    details: dict[str, dict[str, Any]],
    logger: BoundLogger,
    defaults: CompanySearchDefaults,
) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]], set[str]]:
    """Process parent companies from trees: subscribe, fetch details, track relationships."""
    parent_details: dict[str, dict[str, Any]] = {}
    parent_to_children: dict[str, list[str]] = {}
    ephemeral_subscriptions: set[str] = set()

    for company_guid, tree_data in trees.items():
        parent_guids = _extract_parent_guids(tree_data, company_guid)

        for parent_guid in parent_guids:
            # Track parent-child relationship
            if parent_guid not in parent_to_children:
                parent_to_children[parent_guid] = []
            parent_to_children[parent_guid].append(company_guid)

            # Skip if already processed
            if parent_guid in details or parent_guid in parent_details:
                continue

            # Subscribe and fetch parent details
            parent_ephemeral, parent_data = await _subscribe_and_fetch_parent(
                call_v1_tool,
                ctx,
                parent_guid=parent_guid,
                tree_data=tree_data,
                logger=logger,
                defaults=defaults,
            )
            ephemeral_subscriptions.update(parent_ephemeral)
            if parent_data:
                parent_details[parent_guid] = parent_data

    return parent_details, parent_to_children, ephemeral_subscriptions


async def _subscribe_and_fetch_parent(
    call_v1_tool: CallV1Tool,
    ctx: Context,
    *,
    parent_guid: str,
    tree_data: dict[str, Any],
    logger: BoundLogger,
    defaults: CompanySearchDefaults,
) -> tuple[set[str], dict[str, Any] | None]:
    """Subscribe to parent company if needed and fetch its details."""
    ephemeral: set[str] = set()

    # Check if parent is already subscribed
    parent_node = _find_node_in_tree(tree_data, parent_guid)
    parent_is_subscribed = (
        parent_node.get("is_subscribed", False) if parent_node else False
    )

    # Subscribe if needed
    if not parent_is_subscribed:
        ephemeral = await _bulk_subscribe_companies(
            call_v1_tool,
            ctx,
            [parent_guid],
            logger=logger,
            folder=defaults.folder,
            subscription_type=defaults.subscription_type,
        )

    # Fetch parent details. Ensure we still return the ephemeral set even if
    # detail fetching fails so callers can clean up subscriptions.
    try:
        parent_data_map = await _fetch_company_details(
            call_v1_tool,
            ctx,
            [parent_guid],
            logger=logger,
            limit=DEFAULT_FINDINGS_LIMIT,
        )
        parent_data = parent_data_map.get(parent_guid)
        return ephemeral, parent_data
    except Exception as exc:  # pragma: no cover - defensive safety
        await ctx.warning(
            f"Failed to fetch parent company details for {parent_guid}: {exc}"
        )
        logger.warning(
            "parent_detail.fetch_failed",
            company_guid=parent_guid,
            error=str(exc),
        )
        # Return any ephemeral subscriptions so outer cleanup can proceed
        return ephemeral, None


def _build_parent_entries(
    parent_details: dict[str, dict[str, Any]],
    details: dict[str, dict[str, Any]],
    parent_to_children: dict[str, list[str]],
    memberships: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build result entries for parent companies."""
    parent_entries = []

    for parent_guid, parent_detail in parent_details.items():
        # Get first child for labeling
        child_guids = parent_to_children.get(parent_guid, [])
        if not child_guids:
            continue

        child_guid = child_guids[0]
        child_detail = details.get(child_guid, {})
        child_name = child_detail.get("name", "Unknown Company")

        # Build parent candidate structure
        parent_candidate = {
            "guid": parent_guid,
            "name": parent_detail.get("name", ""),
            "primary_domain": parent_detail.get("primary_domain", ""),
            "website": parent_detail.get("display_url", ""),
            "description": parent_detail.get("description", ""),
            "employee_count": parent_detail.get("people_count"),
            "in_portfolio": parent_detail.get("in_spm_portfolio", False),
            "subscription_type": parent_detail.get("subscription_type"),
            "is_parent_entry": True,
            "parent_of": child_name,
        }

        # Format and add to results
        parent_folders = memberships.get(parent_guid, [])
        parent_entry = _format_result_entry(
            parent_candidate,
            parent_detail,
            parent_folders,
        )
        # Override label to indicate parent relationship
        parent_entry["label"] = f"Parent of {child_name}"
        parent_entries.append(parent_entry)

    return parent_entries


def register_company_search_interactive_tool(
    business_server: FastMCP,
    call_v1_tool: CallV1Tool,
    *,
    logger: BoundLogger,
    default_folder: str | None,
    default_type: str | None,
    max_findings: int = DEFAULT_MAX_FINDINGS,
) -> FunctionTool:
    effective_limit = max_findings if max_findings > 0 else DEFAULT_MAX_FINDINGS

    async def company_search_interactive(
        ctx: Context,
        name: str | None = None,
        domain: str | None = None,
    ) -> dict[str, Any]:
        """Search for a single company with interactive guidance.

        Parameters
        - name: Optional company name (fuzzy match, best for human review).
        - domain: Optional primary domain (exact match preferred; overrides name).

        Returns
        - {"results": [<enriched company dict>], "count": int,
            "guidance": {...}, "defaults": {...}} or {"error": str}

        Output semantics
        - results: Ordered list of enriched candidates. Each entry includes
            BitSight GUID, display label, domain, subscription metadata, folders,
            ratings, and descriptive text for analyst decision-making.
        - count: Number of enriched candidates returned (bounded by max_findings).
        - guidance: Next-step recommendations (e.g., "run manage_subscriptions")
            plus context such as suggested folder or subscription type.
        - defaults: Echoes the implicit folder/subscription defaults that will be
            used by downstream actions.
        - error: Present when validation or BitSight calls fail; formatted message.

        Notes
        - Use this tool when the operator explicitly wants a human-in-the-loop,
            high-signal search for a *single* company.
        - Prefer `company_search` for automation and bulk enumeration.
        - Provide at least one of name or domain; domain wins when both exist.

        Example
        >>> company_search_interactive(name="Acme Security")
        {
            "results": [{"guid": "...", "label": "Acme Security", "folders": ["Ops"], ...}],
            "count": 3,
            "guidance": {"next": "Review candidates and run manage_subscriptions"},
            "defaults": {"folder": "Ops", "subscription_type": "managed"}
        }
        """

        validation_error = _validate_company_search_inputs(name, domain)
        if validation_error:
            # Pydantic models accept **kwargs, but pyright can't verify field names
            validation_payload = cast(dict[str, Any], validation_error)
            response = CompanySearchInteractiveResponse(**validation_payload)
            return response.to_payload()

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
            # Pydantic models accept **kwargs, but pyright can't verify field names
            failure_payload = cast(dict[str, Any], failure_response)
            response = CompanySearchInteractiveResponse(**failure_payload)
            return response.to_payload()

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

    return business_server.tool(output_schema=COMPANY_SEARCH_INTERACTIVE_OUTPUT_SCHEMA)(
        company_search_interactive
    )


async def _list_company_requests(
    call_v2_tool: CallV2Tool,
    ctx: Context,
    domain: str,
) -> list[dict[str, Any]]:
    params = {"domain": domain, "limit": 5}
    try:
        result = await call_v2_tool("getCompanyRequests", ctx, params)
    except Exception:
        return []
    if isinstance(result, dict):
        results = result.get("results")
        if isinstance(results, list):
            return results
        company_requests = result.get("company_requests")
        if isinstance(company_requests, list):
            return company_requests
    return []


def _serialize_bulk_csv(domains: Sequence[str]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["domain"])
    for domain in domains:
        writer.writerow([domain])
    return buffer.getvalue()


def _parse_domain_string(
    comma_separated_domains: str,
    *,
    logger: BoundLogger,
    ctx: Context,
) -> tuple[list[str], dict[str, Any | None] | None]:
    """Parse the CLI comma-separated domain list (not a CSV file)."""
    raw_value = (comma_separated_domains or "").strip()
    if not raw_value:
        log_event(
            logger,
            "company_request.invalid_domain_input",
            level=logging.WARNING,
            ctx=ctx,
            domains=comma_separated_domains,
        )
        return [], {"error": "Provide at least one domain"}

    tokens = [token.strip().lower() for token in raw_value.split(",") if token.strip()]
    if not tokens:
        log_event(
            logger,
            "company_request.invalid_domain_input",
            level=logging.WARNING,
            ctx=ctx,
            domains=comma_separated_domains,
        )
        return [], {"error": "Provide at least one valid domain"}

    if len(tokens) > MAX_REQUEST_COMPANY_DOMAINS:
        log_event(
            logger,
            "company_request.domain_limit_exceeded",
            level=logging.WARNING,
            ctx=ctx,
            count=len(tokens),
            limit=MAX_REQUEST_COMPANY_DOMAINS,
        )
        return [], {
            "error": f"Provide at most {MAX_REQUEST_COMPANY_DOMAINS} domains per request",
        }

    invalid = [token for token in tokens if " " in token or "." not in token]
    if invalid:
        log_event(
            logger,
            "company_request.invalid_domain_token",
            level=logging.WARNING,
            ctx=ctx,
            invalid=invalid[:5],
        )
        return [], {
            "error": f"Invalid domain entries: {', '.join(invalid[:5])}",
        }

    return tokens, None


def _deduplicate_domains(domains: Sequence[str]) -> tuple[list[str], list[str]]:
    seen: set[str] = set()
    unique: list[str] = []
    duplicates: list[str] = []
    for domain in domains:
        if domain in seen:
            duplicates.append(domain)
            continue
        seen.add(domain)
        unique.append(domain)
    return unique, duplicates


def _register_existing_domain(
    order: list[str],
    mapping: dict[str, str | None],
    domain: str,
    company_name: str | None,
) -> None:
    if domain not in mapping:
        order.append(domain)
        mapping[domain] = company_name
        return
    if company_name and not mapping[domain]:
        mapping[domain] = company_name


def _build_existing_entries(
    order: Sequence[str], mapping: dict[str, str | None]
) -> list[RequestCompanyExistingEntry]:
    entries: list[RequestCompanyExistingEntry] = []
    for domain in order:
        company_name = mapping.get(domain)
        if company_name:
            entries.append(
                RequestCompanyExistingEntry(domain=domain, company_name=company_name)
            )
        else:
            entries.append(RequestCompanyExistingEntry(domain=domain))
    return entries


async def _initialize_request_company_state(
    domains: str,
    *,
    folder: str | None,
    default_folder: str | None,
    default_folder_guid: str | None,
    call_v1_tool: CallV1Tool,
    ctx: Context,
    logger: BoundLogger,
) -> tuple[RequestCompanyState | None, dict[str, Any] | None]:
    submitted_domains, error = _parse_domain_string(domains, logger=logger, ctx=ctx)
    if error:
        return (
            None,
            RequestCompanyResponse(error=error["error"]).to_payload(),
        )

    unique_domains, duplicates = _deduplicate_domains(submitted_domains)
    existing_order: list[str] = []
    existing_mapping: dict[str, str | None] = {}
    for duplicate in duplicates:
        _register_existing_domain(existing_order, existing_mapping, duplicate, None)

    selected_folder = folder or default_folder
    folder_guid: str | None = None
    folder_created = False
    if (
        selected_folder
        and default_folder
        and selected_folder == default_folder
        and default_folder_guid
    ):
        folder_guid = default_folder_guid

    remaining_domains = await _partition_submitted_domains(
        unique_domains,
        call_v1_tool=call_v1_tool,
        ctx=ctx,
        logger=logger,
        existing_order=existing_order,
        existing_mapping=existing_mapping,
    )

    existing_entries = _build_existing_entries(existing_order, existing_mapping)
    csv_body = _serialize_bulk_csv(remaining_domains) if remaining_domains else ""

    state = RequestCompanyState(
        submitted_domains=list(submitted_domains),
        remaining_domains=remaining_domains,
        existing_entries=existing_entries,
        selected_folder=selected_folder,
        folder_guid=folder_guid,
        folder_created=folder_created,
        folder_pending_reason=None,
        csv_body=csv_body,
    )
    return state, None


async def _find_existing_company(
    call_v1_tool: CallV1Tool,
    ctx: Context,
    *,
    logger: BoundLogger,
    domain: str,
) -> str | None:
    params = {"domain": domain}
    try:
        result = await call_v1_tool("companySearch", ctx, params)
    except Exception as exc:  # pragma: no cover - diagnostics path
        await ctx.warning(f"Company search failed for {domain}: {exc}")
        log_event(
            logger,
            "company_request.company_search_failed",
            level=logging.WARNING,
            ctx=ctx,
            domain=domain,
            error=str(exc),
        )
        return None

    candidates: list[dict[str, Any]] = []
    if isinstance(result, dict):
        maybe_results = result.get("results")
        if isinstance(maybe_results, list):
            candidates = [cast(dict[str, Any], entry) for entry in maybe_results]

    target = domain.lower()
    for candidate in candidates:
        primary = str(candidate.get("primary_domain") or "").lower()
        if primary == target:
            return str(
                candidate.get("name") or candidate.get("primary_domain") or domain
            )
        candidate_domain = str(candidate.get("domain") or "").lower()
        if candidate_domain == target:
            return str(candidate.get("name") or candidate.get("domain") or domain)

    return None


async def _resolve_request_company_folder(
    call_v1_tool: CallV1Tool,
    ctx: Context,
    *,
    logger: BoundLogger,
    selected_folder: str | None,
    default_folder: str | None,
    default_folder_guid: str | None,
    submitted_domains: Sequence[str],
    existing_entries: list[RequestCompanyExistingEntry],
    allow_create: bool,
) -> tuple[str | None, bool, dict[str, Any] | None, str | None]:
    if not selected_folder:
        return None, False, None, None

    if default_folder and selected_folder == default_folder and default_folder_guid:
        return default_folder_guid, False, None, None

    folder_result = await resolve_or_create_folder(
        call_v1_tool,
        ctx,
        logger=logger,
        folder_name=selected_folder,
        tool_name="request_company",
        allow_create=allow_create,
    )
    if folder_result.error:
        if not allow_create:
            return None, False, None, folder_result.error
        return (
            None,
            False,
            RequestCompanyResponse(
                error=folder_result.error,
                status="folder_error",
                submitted=list(submitted_domains),
                already_existing=existing_entries,
                successfully_requested=[],
                failed=[],
                folder=selected_folder,
            ).to_payload(),
            None,
        )

    return folder_result.guid, folder_result.created, None, None


async def _partition_submitted_domains(
    unique_domains: Sequence[str],
    *,
    call_v1_tool: CallV1Tool,
    ctx: Context,
    logger: BoundLogger,
    existing_order: list[str],
    existing_mapping: dict[str, str | None],
) -> list[str]:
    remaining_domains: list[str] = []
    for domain_value in unique_domains:
        company_name = await _find_existing_company(
            call_v1_tool,
            ctx,
            logger=logger,
            domain=domain_value,
        )
        if company_name:
            log_event(
                logger,
                "company_request.domain_exists",
                ctx=ctx,
                domain=domain_value,
                company_name=company_name,
            )
            _register_existing_domain(
                existing_order,
                existing_mapping,
                domain_value,
                company_name,
            )
            continue
        remaining_domains.append(domain_value)
    return remaining_domains


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


def _request_company_all_existing_response(
    *,
    submitted_domains: Sequence[str],
    existing_entries: list[RequestCompanyExistingEntry],
    selected_folder: str | None,
    folder_guid: str | None,
    folder_created: bool,
) -> dict[str, Any]:
    return RequestCompanyResponse(
        status="already_existing",
        submitted=list(submitted_domains),
        already_existing=existing_entries,
        successfully_requested=[],
        failed=[],
        folder=selected_folder,
        folder_guid=folder_guid,
        folder_created=folder_created or None,
        guidance=RequestGuidance(
            next_steps=(
                "All provided domains already exist in BitSight or were duplicates."
            )
        ),
    ).to_payload()


def _short_circuit_request_company(
    *,
    dry_run: bool,
    submitted_domains: Sequence[str],
    existing_entries: list[RequestCompanyExistingEntry],
    remaining_domains: Sequence[str],
    selected_folder: str | None,
    folder_guid: str | None,
    folder_created: bool,
    csv_body: str,
    folder_pending_reason: str | None,
) -> dict[str, Any] | None:
    if dry_run:
        return _request_company_dry_run_response(
            submitted_domains=submitted_domains,
            existing_entries=existing_entries,
            remaining_domains=remaining_domains,
            selected_folder=selected_folder,
            folder_guid=folder_guid,
            folder_created=folder_created,
            csv_body=csv_body,
            pending_folder_reason=folder_pending_reason,
        )
    if not remaining_domains:
        return _request_company_all_existing_response(
            submitted_domains=submitted_domains,
            existing_entries=existing_entries,
            selected_folder=selected_folder,
            folder_guid=folder_guid,
            folder_created=folder_created,
        )
    return None


def _short_circuit_request_company_state(
    state: RequestCompanyState,
    *,
    dry_run: bool,
) -> dict[str, Any] | None:
    return _short_circuit_request_company(
        dry_run=dry_run,
        submitted_domains=state.submitted_domains,
        existing_entries=state.existing_entries,
        remaining_domains=state.remaining_domains,
        selected_folder=state.selected_folder,
        folder_guid=state.folder_guid,
        folder_created=state.folder_created,
        csv_body=state.csv_body,
        folder_pending_reason=state.folder_pending_reason,
    )


async def _submit_request_company_bulk(
    call_v2_tool: CallV2Tool,
    ctx: Context,
    *,
    logger: BoundLogger,
    remaining_domains: Sequence[str],
    selected_folder: str | None,
    folder_guid: str | None,
    submitted_domains: Sequence[str],
    existing_entries: list[RequestCompanyExistingEntry],
    folder_created: bool,
    csv_body: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    bulk_payload = _build_bulk_payload(csv_body, folder_guid)
    try:
        result = await call_v2_tool("createCompanyRequestBulk", ctx, bulk_payload)
    except Exception as exc:  # pragma: no cover - network failure
        log_event(
            logger,
            "company_request.bulk_failed",
            level=logging.WARNING,
            ctx=ctx,
            domains=remaining_domains,
            folder=selected_folder,
            error=str(exc),
        )
        failed_entries = [
            RequestCompanyFailedEntry(domain=domain, error=str(exc))
            for domain in remaining_domains
        ]
        return None, RequestCompanyResponse(
            error=str(exc),
            status="failed",
            submitted=list(submitted_domains),
            already_existing=existing_entries,
            successfully_requested=[],
            failed=failed_entries,
            folder=selected_folder,
            folder_guid=folder_guid,
            folder_created=folder_created or None,
        ).to_payload()

    log_event(
        logger,
        "company_request.submitted_bulk",
        ctx=ctx,
        domains=remaining_domains,
        folder=selected_folder,
    )
    return result, None


async def _prepare_manage_subscriptions_folder_state(
    *,
    normalized_action: str,
    target_folder: str | None,
    default_folder: str | None,
    default_folder_guid: str | None,
    call_v1_tool: CallV1Tool,
    ctx: Context,
    logger: BoundLogger,
    allow_create: bool,
) -> tuple[ManageSubscriptionsFolderState, dict[str, Any] | None]:
    state = ManageSubscriptionsFolderState(folder=target_folder)
    if normalized_action != "add" or not target_folder:
        return state, None

    (
        folder_guid,
        folder_created,
        folder_error,
        folder_pending_reason,
    ) = await _resolve_manage_subscriptions_folder(
        call_v1_tool,
        ctx,
        logger=logger,
        target_folder=target_folder,
        default_folder=default_folder,
        default_folder_guid=default_folder_guid,
        allow_create=allow_create,
    )
    if folder_error is not None:
        return state, folder_error

    state.folder_guid = folder_guid
    state.folder_created = folder_created
    state.folder_pending_reason = folder_pending_reason
    return state, None


async def _maybe_resolve_request_company_folder(
    state: RequestCompanyState,
    *,
    dry_run: bool,
    call_v1_tool: CallV1Tool,
    ctx: Context,
    logger: BoundLogger,
    default_folder: str | None,
    default_folder_guid: str | None,
) -> dict[str, Any] | None:
    needs_folder = (
        state.selected_folder
        and state.remaining_domains
        and not state.folder_guid
        and not (
            default_folder
            and state.selected_folder == default_folder
            and default_folder_guid
        )
    )
    if not needs_folder:
        return None

    (
        folder_guid,
        folder_created,
        folder_error,
        folder_pending_reason,
    ) = await _resolve_request_company_folder(
        call_v1_tool,
        ctx,
        logger=logger,
        selected_folder=state.selected_folder,
        default_folder=default_folder,
        default_folder_guid=default_folder_guid,
        submitted_domains=state.submitted_domains,
        existing_entries=state.existing_entries,
        allow_create=not dry_run,
    )
    if folder_error is not None:
        return folder_error

    state.folder_guid = folder_guid
    state.folder_created = folder_created
    state.folder_pending_reason = folder_pending_reason
    return None


async def _finalize_request_company_state(
    state: RequestCompanyState,
    *,
    dry_run: bool,
    call_v1_tool: CallV1Tool,
    ctx: Context,
    logger: BoundLogger,
    default_folder: str | None,
    default_folder_guid: str | None,
) -> dict[str, Any] | None:
    ready = _short_circuit_request_company_state(state, dry_run=dry_run)
    if ready is not None:
        return ready

    folder_error = await _maybe_resolve_request_company_folder(
        state,
        dry_run=dry_run,
        call_v1_tool=call_v1_tool,
        ctx=ctx,
        logger=logger,
        default_folder=default_folder,
        default_folder_guid=default_folder_guid,
    )
    if folder_error is not None:
        return folder_error

    return _short_circuit_request_company_state(state, dry_run=dry_run)


def _build_bulk_payload(csv_body: str, folder_guid: str | None) -> dict[str, Any]:
    payload: dict[str, Any] = {"file": csv_body}
    if folder_guid:
        payload["folder_guid"] = folder_guid
    return payload


def register_request_company_tool(
    business_server: FastMCP,
    call_v1_tool: CallV1Tool,
    call_v2_tool: CallV2Tool,
    *,
    logger: BoundLogger,
    default_folder: str | None,
    default_folder_guid: str | None = None,
) -> FunctionTool:
    async def request_company(
        ctx: Context,
        domains: str,
        *,
        folder: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        "Submit BitSight onboarding requests for one or more domains."

        state, error_response = await _initialize_request_company_state(
            domains,
            folder=folder,
            default_folder=default_folder,
            default_folder_guid=default_folder_guid,
            call_v1_tool=call_v1_tool,
            ctx=ctx,
            logger=logger,
        )
        if error_response is not None:
            return error_response
        assert state is not None, (
            "State must be available when no error response is returned."
        )

        log_event(
            logger,
            "company_request.start",
            ctx=ctx,
            domains=state.submitted_domains,
            folder=state.selected_folder,
            dry_run=dry_run,
        )

        needs_folder_for_dry_run = (
            dry_run
            and state.remaining_domains
            and state.selected_folder
            and not state.folder_guid
        )
        if needs_folder_for_dry_run:
            folder_error = await _maybe_resolve_request_company_folder(
                state,
                dry_run=dry_run,
                call_v1_tool=call_v1_tool,
                ctx=ctx,
                logger=logger,
                default_folder=default_folder,
                default_folder_guid=default_folder_guid,
            )
            if folder_error is not None:
                return folder_error

        short_circuit = await _finalize_request_company_state(
            state,
            dry_run=dry_run,
            call_v1_tool=call_v1_tool,
            ctx=ctx,
            logger=logger,
            default_folder=default_folder,
            default_folder_guid=default_folder_guid,
        )
        if short_circuit is not None:
            return short_circuit

        result, failure_payload = await _submit_request_company_bulk(
            call_v2_tool,
            ctx,
            logger=logger,
            remaining_domains=state.remaining_domains,
            selected_folder=state.selected_folder,
            folder_guid=state.folder_guid,
            submitted_domains=state.submitted_domains,
            existing_entries=state.existing_entries,
            folder_created=state.folder_created,
            csv_body=state.csv_body,
        )
        if failure_payload is not None:
            return failure_payload

        return RequestCompanyResponse(
            status="submitted_v2_bulk",
            submitted=list(state.submitted_domains),
            already_existing=state.existing_entries,
            successfully_requested=state.remaining_domains,
            failed=[],
            folder=state.selected_folder,
            folder_guid=state.folder_guid,
            folder_created=state.folder_created or None,
            result=result,
        ).to_payload()

    return business_server.tool(output_schema=REQUEST_COMPANY_OUTPUT_SCHEMA)(
        request_company
    )


def _build_subscription_payload(
    action: str,
    guids: Sequence[str],
    *,
    folder_guid: str | None,
    subscription_type: str | None,
) -> dict[str, Any]:
    if action == "add":
        entries: list[dict[str, Any]] = []
        for guid in guids:
            entry: dict[str, Any] = {"guid": guid}
            if subscription_type:
                entry["type"] = subscription_type
            if folder_guid:
                entry["folder"] = [folder_guid]
            entries.append(entry)
        return {"add": entries}
    if action == "delete":
        return {"delete": [{"guid": guid} for guid in guids]}
    raise ValueError(f"Unsupported action: {action}")


def _summarize_bulk_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {"raw": result}
    return {
        "added": result.get("added", []),
        "deleted": result.get("deleted", []),
        "modified": result.get("modified", []),
        "errors": result.get("errors", []),
    }


def _manage_subscriptions_error(message: str) -> dict[str, Any]:
    return ManageSubscriptionsResponse(error=message).to_payload()


def _build_manage_subscriptions_success_response(
    *,
    normalized_action: str,
    guid_list: Sequence[str],
    target_folder: str | None,
    folder_state: ManageSubscriptionsFolderState,
    result: Any,
) -> dict[str, Any]:
    summary = _summarize_bulk_result(result)
    summary_model = ManageSubscriptionsSummary.model_validate(summary)
    return ManageSubscriptionsResponse(
        status="applied",
        action=normalized_action,
        guids=list(guid_list),
        folder=target_folder,
        folder_guid=folder_state.folder_guid,
        folder_created=folder_state.folder_created or None,
        summary=summary_model,
        guidance=ManageSubscriptionsGuidance(
            next_steps=(
                "Run `get_company_rating` for a sample GUID to verify post-change access."
            )
        ),
    ).to_payload()


def _validate_manage_subscriptions_inputs(
    action: str,
    guids: Sequence[str],
    *,
    default_type: str | None,
) -> tuple[str | None, list[str], dict[str, Any | None] | None]:
    normalized_action = _normalize_action(action)
    if normalized_action is None:
        return (
            None,
            [],
            _manage_subscriptions_error(
                "Unsupported action. Use one of: add, subscribe, remove, delete, unsubscribe"
            ),
        )

    guid_list = _coerce_guid_list(guids)
    if not guid_list:
        return (
            None,
            [],
            _manage_subscriptions_error("At least one company GUID must be supplied"),
        )

    if normalized_action == "add" and not default_type:
        return (
            None,
            [],
            _manage_subscriptions_error(
                "Subscription type is not configured. Provide a subscription_type via CLI "
                "arguments, set BIRRE_SUBSCRIPTION_TYPE in the environment, or update "
                f"{DEFAULT_CONFIG_FILENAME}."
            ),
        )

    return normalized_action, guid_list, None


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


async def _resolve_manage_subscriptions_folder(
    call_v1_tool: CallV1Tool,
    ctx: Context,
    *,
    logger: BoundLogger,
    target_folder: str | None,
    default_folder: str | None,
    default_folder_guid: str | None,
    allow_create: bool,
) -> tuple[str | None, bool, dict[str, Any] | None, str | None]:
    if not target_folder:
        return None, False, None, None

    if default_folder and target_folder == default_folder and default_folder_guid:
        return default_folder_guid, False, None, None

    folder_result = await resolve_or_create_folder(
        call_v1_tool,
        ctx,
        logger=logger,
        folder_name=target_folder,
        tool_name="manage_subscriptions",
        allow_create=allow_create,
    )
    if folder_result.error:
        if not allow_create:
            return None, False, None, folder_result.error
        return None, False, _manage_subscriptions_error(folder_result.error), None
    return folder_result.guid, folder_result.created, None, None


async def _perform_manage_subscriptions_bulk(
    call_v1_tool: CallV1Tool,
    ctx: Context,
    payload: dict[str, Any],
    action: str,
    guids: Sequence[str],
    logger: BoundLogger,
) -> tuple[Any | None, dict[str, Any] | None]:
    try:
        result = await call_v1_tool("manageSubscriptionsBulk", ctx, payload)
    except Exception as exc:
        await ctx.error(f"Subscription management failed: {exc}")
        logger_obj = getattr(logger, "_logger", None)
        exc_info = (
            exc if logger_obj and logger_obj.isEnabledFor(logging.DEBUG) else False
        )
        logger.error(
            "manage_subscriptions.failed",
            action=action,
            count=len(guids),
            exc_info=exc_info,
        )
        return None, ManageSubscriptionsResponse(
            error=f"manageSubscriptionsBulk failed: {exc}"
        ).to_payload()

    return result, None


def _maybe_return_manage_subscriptions_dry_run(
    *,
    dry_run: bool,
    normalized_action: str,
    guid_list: Sequence[str],
    folder_state: ManageSubscriptionsFolderState,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    if not dry_run:
        return None
    return _manage_subscriptions_dry_run_response(
        action=normalized_action,
        guids=guid_list,
        folder=folder_state.folder if normalized_action == "add" else None,
        folder_guid=folder_state.folder_guid,
        folder_created=folder_state.folder_created,
        payload=payload,
        pending_folder_reason=folder_state.folder_pending_reason,
    )


async def _apply_manage_subscriptions_changes(
    *,
    call_v1_tool: CallV1Tool,
    ctx: Context,
    payload: dict[str, Any],
    normalized_action: str,
    guid_list: Sequence[str],
    logger: BoundLogger,
    target_folder: str | None,
    folder_state: ManageSubscriptionsFolderState,
) -> dict[str, Any]:
    await ctx.info(
        f"Executing manageSubscriptionsBulk action={normalized_action} "
        f"for {len(guid_list)} companies"
    )

    result, error_payload = await _perform_manage_subscriptions_bulk(
        call_v1_tool,
        ctx,
        payload,
        normalized_action,
        guid_list,
        logger,
    )
    if error_payload is not None:
        return error_payload

    return _build_manage_subscriptions_success_response(
        normalized_action=normalized_action,
        guid_list=guid_list,
        target_folder=target_folder,
        folder_state=folder_state,
        result=result,
    )


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
        guids: Sequence[str],
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
        >>> manage_subscriptions(action=\"add\", guids=[\"guid-1\"], folder=\"Ops\")
        {
            \"status\": \"applied\",
            \"action\": \"add\",
            \"summary\": {\"added\": [\"guid-1\"], \"deleted\": [], \"errors\": []},
            \"guidance\": {\"next_steps\": \"Run get_company_rating for guid-1\"}
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
