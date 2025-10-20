from __future__ import annotations

import asyncio
from functools import partial
from typing import Awaitable, Callable, Dict, Any, Optional, Iterable

from fastmcp import FastMCP

from src.settings import DEFAULT_MAX_FINDINGS, DEFAULT_RISK_VECTOR_FILTER
from src.logging import BoundLogger

from .apis import (
    call_v1_openapi_tool,
    call_v2_openapi_tool,
    create_v1_api_server,
    create_v2_api_server,
)
from .business import (
    register_company_rating_tool,
    register_company_search_tool,
)


INSTRUCTIONS_MAP: Dict[str, str] = {
    "standard": (
        "BitSight rating retriever. Use `company_search` to locate a company, "
        "then call `get_company_rating` with the chosen GUID."
    ),
    "risk_manager": (
        "Risk manager persona. Start with `company_search_interactive` to review matches, "
        "call `manage_subscriptions` to adjust coverage, and use `request_company` when an entity is missing."
    ),
}


def _require_api_key(settings: Dict[str, Any]) -> str:
    resolved_api_key = settings.get("api_key")
    if not resolved_api_key:
        raise ValueError("Resolved settings must include a non-empty 'api_key'")
    return str(resolved_api_key)

def _resolve_active_context(settings: Dict[str, Any]) -> str:
    return str(settings.get("context", "standard"))


def _resolve_risk_vector_filter(settings: Dict[str, Any]) -> str:
    return str(settings.get("risk_vector_filter") or DEFAULT_RISK_VECTOR_FILTER)


def _resolve_max_findings(settings: Dict[str, Any]) -> int:
    max_findings_value = settings.get("max_findings")
    if isinstance(max_findings_value, int) and max_findings_value > 0:
        return max_findings_value
    return DEFAULT_MAX_FINDINGS


def _resolve_tls_verification(settings: Dict[str, Any], logger: BoundLogger) -> bool | str:
    allow_insecure_tls = bool(settings.get("allow_insecure_tls"))
    ca_bundle_path = settings.get("ca_bundle_path")
    verify_option: bool | str = True
    if allow_insecure_tls:
        logger.warning(
            "tls.verify.disabled",
            reason="allow_insecure_tls flag set",
        )
        return False
    if ca_bundle_path:
        verify_option = str(ca_bundle_path)
        logger.info(
            "tls.verify.custom_ca_bundle",
            ca_bundle=verify_option,
        )
    return verify_option


def _maybe_create_v2_api_server(
    active_context: str,
    api_key: str,
    verify_option: bool | str,
) -> Optional[FastMCP]:
    if active_context == "risk_manager":
        return create_v2_api_server(api_key, verify=verify_option)
    return None


def _run_async(coro: Awaitable[None]) -> None:
    try:
        asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)


async def _disable_tools(api_server: FastMCP, keep: Iterable[str]) -> None:
    tools = await api_server.get_tools()  # type: ignore[attr-defined]
    keep_set = set(keep)
    for name, tool in tools.items():
        if name not in keep_set:
            tool.disable()


def _schedule_tool_disablement(api_server: FastMCP, keep: Iterable[str]) -> None:
    _run_async(_disable_tools(api_server, keep))


def _configure_risk_manager_tools(
    business_server: FastMCP,
    settings: Dict[str, Any],
    call_v1_tool: Callable[..., Any],
    logger: BoundLogger,
    resolved_api_key: str,
    verify_option: bool | str,
    max_findings: int,
) -> None:
    from src.business.risk_manager import (
        register_company_search_interactive_tool,
        register_manage_subscriptions_tool,
        register_request_company_tool,
    )

    register_company_search_tool(business_server, call_v1_tool, logger=logger)
    call_v2_tool = getattr(business_server, "call_v2_tool", None)
    if call_v2_tool is None:
        call_v2_tool = partial(
            call_v2_openapi_tool,
            create_v2_api_server(resolved_api_key, verify=verify_option),
            logger=logger,
        )
        setattr(business_server, "call_v2_tool", call_v2_tool)

    default_folder = settings.get("subscription_folder")
    default_type = settings.get("subscription_type")

    register_company_search_interactive_tool(
        business_server,
        call_v1_tool,
        logger=logger,
        default_folder=default_folder,
        default_type=default_type,
        max_findings=max_findings,
    )
    register_manage_subscriptions_tool(
        business_server,
        call_v1_tool,
        logger=logger,
        default_folder=default_folder,
        default_type=default_type,
    )
    register_request_company_tool(
        business_server,
        call_v1_tool,
        call_v2_tool,
        logger=logger,
        default_folder=default_folder,
        default_type=default_type,
    )


def _configure_standard_tools(
    business_server: FastMCP,
    call_v1_tool: Callable[..., Any],
    logger: BoundLogger,
) -> None:
    register_company_search_tool(business_server, call_v1_tool, logger=logger)


def create_birre_server(settings: Dict[str, Any], logger: BoundLogger) -> FastMCP:
    """Create and configure the BiRRe FastMCP business server using resolved settings."""

    settings = dict(settings)
    resolved_api_key = _require_api_key(settings)

    active_context = _resolve_active_context(settings)
    risk_vector_filter = _resolve_risk_vector_filter(settings)
    max_findings = _resolve_max_findings(settings)
    verify_option = _resolve_tls_verification(settings, logger)
    v1_api_server = create_v1_api_server(resolved_api_key, verify=verify_option)
    v2_api_server = _maybe_create_v2_api_server(
        active_context,
        resolved_api_key,
        verify_option,
    )

    business_server = FastMCP(
        name="io.github.boecht.birre",
        instructions=INSTRUCTIONS_MAP.get(active_context, INSTRUCTIONS_MAP["standard"]),
    )

    call_v1_tool = partial(call_v1_openapi_tool, v1_api_server, logger=logger)
    setattr(business_server, "call_v1_tool", call_v1_tool)
    if v2_api_server is not None:
        call_v2_tool = partial(call_v2_openapi_tool, v2_api_server, logger=logger)
        setattr(business_server, "call_v2_tool", call_v2_tool)

    _schedule_tool_disablement(
        v1_api_server,
        {
            "companySearch",
            "manageSubscriptionsBulk",
            "getCompany",
            "getCompaniesFindings",
            "getFolders",
            "getCompanySubscriptions",
        },
    )

    if v2_api_server is not None:
        _schedule_tool_disablement(
            v2_api_server,
            {
                "getCompanyRequests",
                "createCompanyRequest",
                "createCompanyRequestBulk",
            },
        )

    register_company_rating_tool(
        business_server,
        call_v1_tool,
        logger=logger,
        risk_vector_filter=risk_vector_filter,
        max_findings=max_findings,
        default_folder=settings.get("subscription_folder"),
        default_type=settings.get("subscription_type"),
        debug_enabled=bool(settings.get("debug")),
    )

    if active_context == "risk_manager":
        _configure_risk_manager_tools(
            business_server,
            settings,
            call_v1_tool,
            logger,
            resolved_api_key,
            verify_option,
            max_findings,
        )
    else:
        _configure_standard_tools(business_server, call_v1_tool, logger)

    return business_server


__all__ = [
    "create_birre_server",
]
