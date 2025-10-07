from __future__ import annotations

import asyncio
import logging
import os
from functools import partial
from typing import Optional, Dict, Any

from fastmcp import FastMCP

from src.config import DEFAULT_MAX_FINDINGS, DEFAULT_RISK_VECTOR_FILTER
from src.constants import coerce_bool

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


def create_birre_server(settings: Dict[str, Any], logger: logging.Logger) -> FastMCP:
    """Create and configure the BiRRe FastMCP business server using resolved settings."""

    settings = dict(settings)
    resolved_api_key = settings.get("api_key")
    if not resolved_api_key:
        raise ValueError("Resolved settings must include a non-empty 'api_key'")

    # Propagate resolved settings to environment for helpers.
    subscription_folder = settings.get("subscription_folder")
    if subscription_folder is not None:
        os.environ["BIRRE_SUBSCRIPTION_FOLDER"] = str(subscription_folder)
    subscription_type = settings.get("subscription_type")
    if subscription_type is not None:
        os.environ["BIRRE_SUBSCRIPTION_TYPE"] = str(subscription_type)

    active_context = settings.get("context", "standard")
    risk_vector_filter = str(
        settings.get("risk_vector_filter") or DEFAULT_RISK_VECTOR_FILTER
    )
    max_findings_value = settings.get("max_findings")
    if isinstance(max_findings_value, int) and max_findings_value > 0:
        max_findings = max_findings_value
    else:
        max_findings = DEFAULT_MAX_FINDINGS

    v1_api_server = create_v1_api_server(resolved_api_key)

    v2_api_server: Optional[FastMCP] = None
    if active_context == "risk_manager" or coerce_bool(os.getenv("BIRRE_ENABLE_V2")):
        v2_api_server = create_v2_api_server(resolved_api_key)

    instructions_map = {
        "standard": (
            "BitSight rating retriever. Use `company_search` to locate a company, "
            "then call `get_company_rating` with the chosen GUID."
        ),
        "risk_manager": (
            "Risk manager persona. Start with `company_search_interactive` to review "
            "matches, call `manage_subscriptions` to adjust coverage, and use "
            "`request_company` when an entity is missing."
        ),
    }

    business_server = FastMCP(
        name="io.github.boecht.birre",
        title="BiRRe",
        instructions=instructions_map.get(active_context, instructions_map["standard"]),
    )

    call_v1_tool = partial(call_v1_openapi_tool, v1_api_server, logger=logger)
    setattr(business_server, "call_v1_tool", call_v1_tool)
    if v2_api_server is not None:
        call_v2_tool = partial(call_v2_openapi_tool, v2_api_server, logger=logger)
        setattr(business_server, "call_v2_tool", call_v2_tool)

    async def _disable_unused_v1_tools() -> None:
        tools = await v1_api_server.get_tools()  # type: ignore[attr-defined]
        keep = {
            "companySearch",
            "manageSubscriptionsBulk",
            "getCompany",
            "getCompaniesFindings",
            "getFolders",
            "getCompanySubscriptions",
        }
        for name, tool in tools.items():
            if name not in keep:
                tool.disable()

    try:
        asyncio.run(_disable_unused_v1_tools())
    except RuntimeError:
        loop = asyncio.get_running_loop()
        loop.create_task(_disable_unused_v1_tools())

    if v2_api_server is not None:

        async def _disable_unused_v2_tools() -> None:
            tools = await v2_api_server.get_tools()  # type: ignore[attr-defined]
            keep = {
                "getCompanyRequests",
                "createCompanyRequest",
                "createCompanyRequestBulk",
            }
            for name, tool in tools.items():
                if name not in keep:
                    tool.disable()

        try:
            asyncio.run(_disable_unused_v2_tools())
        except RuntimeError:
            loop = asyncio.get_running_loop()
            loop.create_task(_disable_unused_v2_tools())

    register_company_rating_tool(
        business_server,
        call_v1_tool,
        logger=logger,
        risk_vector_filter=risk_vector_filter,
        max_findings=max_findings,
    )

    # Register context-specific tooling
    if active_context == "risk_manager":
        from src.business.risk_manager import (
            register_company_search_interactive_tool,
            register_manage_subscriptions_tool,
            register_request_company_tool,
        )

        register_company_search_tool(business_server, call_v1_tool, logger=logger)
        if v2_api_server is None:
            call_v2_tool = partial(
                call_v2_openapi_tool,
                create_v2_api_server(resolved_api_key),
                logger=logger,
            )
            setattr(business_server, "call_v2_tool", call_v2_tool)
        else:
            call_v2_tool = getattr(business_server, "call_v2_tool")

        default_folder = settings.get("subscription_folder")
        default_type = settings.get("subscription_type")

        register_company_search_interactive_tool(
            business_server,
            call_v1_tool,
            call_v2_tool,
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
    else:
        # Default persona keeps the lightweight search + rating flow.
        register_company_search_tool(business_server, call_v1_tool, logger=logger)
        # rating tool already registered above

    return business_server


__all__ = [
    "create_birre_server",
]
