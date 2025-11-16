# ruff: noqa: I001  # Must import _fastmcp_env before third-party modules.
"""Assembly for the BiRRe FastMCP business server."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable, Iterable, Mapping
from functools import partial
from typing import Any, Protocol, TypeVar

from birre import _fastmcp_env  # noqa: F401

from fastmcp import FastMCP
from fastmcp.tools.tool import FunctionTool

from birre.config.settings import (
    DEFAULT_MAX_FINDINGS,
    DEFAULT_RISK_VECTOR_FILTER,
    RuntimeSettings,
)
from birre.domain import company_rating, company_search, risk_manager
from birre.infrastructure.logging import BoundLogger
from birre.integrations.bitsight import create_v1_api_server, create_v2_api_server
from birre.integrations.bitsight.v1_bridge import (
    call_v1_openapi_tool,
    call_v2_openapi_tool,
)


def register_company_rating_tool(*args: Any, **kwargs: Any) -> FunctionTool:
    """Register the company rating tool with a FastMCP server.

    Forwards to domain.company_rating.register_company_rating_tool.
    """
    return company_rating.register_company_rating_tool(*args, **kwargs)


def register_company_search_tool(*args: Any, **kwargs: Any) -> FunctionTool:
    """Register the company search tool with a FastMCP server.

    Forwards to domain.company_search.register_company_search_tool.
    """
    return company_search.register_company_search_tool(*args, **kwargs)


def register_company_search_interactive_tool(*args: Any, **kwargs: Any) -> FunctionTool:
    """Register the interactive company search tool with a FastMCP server.

    Forwards to domain.risk_manager.register_company_search_interactive_tool.
    """
    return risk_manager.register_company_search_interactive_tool(*args, **kwargs)


def register_manage_subscriptions_tool(*args: Any, **kwargs: Any) -> FunctionTool:
    """Register the subscription management tool with a FastMCP server.

    Forwards to domain.risk_manager.register_manage_subscriptions_tool.
    """
    return risk_manager.register_manage_subscriptions_tool(*args, **kwargs)


def register_request_company_tool(*args: Any, **kwargs: Any) -> FunctionTool:
    """Register the company request tool with a FastMCP server.

    Forwards to domain.risk_manager.register_request_company_tool.
    """
    return risk_manager.register_request_company_tool(*args, **kwargs)


_tool_logger = logging.getLogger("birre.tools")
T = TypeVar("T", covariant=True)


class _AnyCallable(Protocol[T]):
    def __call__(self, *args: Any, **kwargs: Any) -> T: ...


INSTRUCTIONS_MAP: dict[str, str] = {
    "standard": (
        "BitSight rating retriever. Use `company_search` to locate a company, "
        "then call `get_company_rating` with the chosen GUID."
    ),
    "risk_manager": (
        "Risk manager persona. Start with `company_search_interactive` to "
        "review matches, call `manage_subscriptions` to adjust coverage, and "
        "use `request_company` when an entity is missing."
    ),
}


def _require_api_key(settings: RuntimeSettings) -> str:
    resolved_api_key = settings.api_key
    if not resolved_api_key:
        raise ValueError("Resolved settings must include a non-empty 'api_key'")
    return str(resolved_api_key)


def _resolve_active_context(settings: RuntimeSettings) -> str:
    return str(settings.context or "standard")


def _resolve_risk_vector_filter(settings: RuntimeSettings) -> str:
    return str(settings.risk_vector_filter or DEFAULT_RISK_VECTOR_FILTER)


def _resolve_max_findings(settings: RuntimeSettings) -> int:
    max_findings_value = settings.max_findings
    if isinstance(max_findings_value, int) and max_findings_value > 0:
        return max_findings_value
    return DEFAULT_MAX_FINDINGS


def _resolve_tls_verification(
    settings: RuntimeSettings, logger: BoundLogger
) -> bool | str:
    allow_insecure_tls = bool(settings.allow_insecure_tls)
    ca_bundle_path = settings.ca_bundle_path
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
    *,
    base_url: str | None = None,
) -> FastMCP | None:
    if active_context == "risk_manager":
        kwargs: dict[str, Any] = {"verify": verify_option}
        if base_url is not None:
            kwargs["base_url"] = base_url
        return create_v2_api_server(api_key, **kwargs)
    return None


def _schedule_tool_disablement(api_server: FastMCP, keep: Iterable[str]) -> None:
    """Disable generated FastMCP tools not exposed by BiRRe.

    FastMCP exposes no synchronous API for pruning tools, so we prefer the
    manager's in-memory registry when available. If the internals are missing,
    we fall back to a no-op and emit diagnostics instead of risking loop
    teardown via ad-hoc asyncio usage.
    """
    tool_manager = getattr(api_server, "_tool_manager", None)
    if tool_manager is None:
        _tool_logger.debug("tool_manager.missing server=%r", api_server)
        return

    tools = getattr(tool_manager, "_tools", None)
    if not isinstance(tools, dict):
        _tool_logger.debug(
            "tool_registry.unexpected_shape registry_type=%s",
            type(tools).__name__,
        )
        return

    keep_set = set(keep)
    for name, tool in tools.items():
        if name in keep_set:
            continue
        try:
            tool.disable()
        except Exception as exc:  # pragma: no cover - defensive
            _tool_logger.debug(
                "tool.disable_failed tool=%s error=%s",
                name,
                exc,
            )
            continue


def _configure_risk_manager_tools(
    business_server: FastMCP,
    settings: RuntimeSettings,
    call_v1_tool: Callable[..., Any],
    logger: BoundLogger,
    resolved_api_key: str,
    verify_option: bool | str,
    max_findings: int,
) -> None:
    register_company_search_tool(
        business_server,
        call_v1_tool,
        logger=logger,
    )
    call_v2_tool = getattr(business_server, "call_v2_tool", None)
    if call_v2_tool is None:
        call_v2_tool = partial(
            call_v2_openapi_tool,
            create_v2_api_server(resolved_api_key, verify=verify_option),
            logger=logger,
        )
        setattr(business_server, "call_v2_tool", call_v2_tool)

    default_folder = settings.subscription_folder
    default_type = settings.subscription_type

    risk_manager.register_company_search_interactive_tool(
        business_server,
        call_v1_tool,
        logger=logger,
        default_folder=default_folder,
        default_type=default_type,
        max_findings=max_findings,
    )
    _call_with_supported_kwargs(
        risk_manager.register_manage_subscriptions_tool,
        business_server,
        call_v1_tool,
        logger=logger,
        default_folder=default_folder,
        default_folder_guid=settings.subscription_folder_guid,
        default_type=default_type,
    )
    _call_with_supported_kwargs(
        risk_manager.register_request_company_tool,
        business_server,
        call_v1_tool,
        call_v2_tool,
        logger=logger,
        default_folder=default_folder,
        default_folder_guid=settings.subscription_folder_guid,
    )


def _configure_standard_tools(
    business_server: FastMCP,
    call_v1_tool: Callable[..., Any],
    logger: BoundLogger,
) -> None:
    register_company_search_tool(
        business_server,
        call_v1_tool,
        logger=logger,
    )


def _coerce_runtime_settings(
    settings: RuntimeSettings | Mapping[str, Any],
) -> RuntimeSettings:
    if isinstance(settings, RuntimeSettings):
        return settings

    data = dict(settings)
    max_findings = data.get("max_findings")
    if not isinstance(max_findings, int) or max_findings <= 0:
        max_findings = DEFAULT_MAX_FINDINGS

    risk_vector_filter = data.get("risk_vector_filter") or DEFAULT_RISK_VECTOR_FILTER
    warnings_raw = data.get("warnings", ())
    if isinstance(warnings_raw, str):
        warnings_tuple = (warnings_raw,)
    else:
        warnings_tuple = tuple(warnings_raw)
    overrides_raw = data.get("overrides", ())
    if isinstance(overrides_raw, str):
        overrides_tuple = (overrides_raw,)
    else:
        overrides_tuple = tuple(overrides_raw)

    raw_api_key = data.get("api_key")
    if raw_api_key is None:
        api_key = ""
    elif isinstance(raw_api_key, str):
        api_key = raw_api_key
    else:
        api_key = str(raw_api_key)

    return RuntimeSettings(
        api_key=api_key,
        subscription_folder=data.get("subscription_folder"),
        subscription_type=data.get("subscription_type"),
        subscription_folder_guid=data.get("subscription_folder_guid"),
        context=data.get("context"),
        risk_vector_filter=risk_vector_filter,
        max_findings=max_findings,
        skip_startup_checks=bool(data.get("skip_startup_checks", False)),
        debug=bool(data.get("debug", False)),
        allow_insecure_tls=bool(data.get("allow_insecure_tls", False)),
        ca_bundle_path=data.get("ca_bundle_path"),
        warnings=warnings_tuple,
        overrides=overrides_tuple,
    )


def create_birre_server(
    settings: RuntimeSettings | Mapping[str, Any],
    logger: BoundLogger,
    *,
    v1_base_url: str | None = None,
    v2_base_url: str | None = None,
) -> FastMCP:
    """Create and configure the BiRRe FastMCP business server using resolved settings."""

    resolved_settings = _coerce_runtime_settings(settings)
    resolved_api_key = _require_api_key(resolved_settings)

    active_context = _resolve_active_context(resolved_settings)
    risk_vector_filter = _resolve_risk_vector_filter(resolved_settings)
    max_findings = _resolve_max_findings(resolved_settings)
    verify_option = _resolve_tls_verification(resolved_settings, logger)
    v1_kwargs: dict[str, Any] = {"verify": verify_option}
    if v1_base_url is not None:
        v1_kwargs["base_url"] = v1_base_url
    v1_api_server = create_v1_api_server(resolved_api_key, **v1_kwargs)
    v2_api_server = _maybe_create_v2_api_server(
        active_context,
        resolved_api_key,
        verify_option,
        base_url=v2_base_url,
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
            "getCompaniesTree",
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
        default_folder=resolved_settings.subscription_folder,
        default_type=resolved_settings.subscription_type,
        debug_enabled=bool(resolved_settings.debug),
    )

    if active_context == "risk_manager":
        _configure_risk_manager_tools(
            business_server,
            resolved_settings,
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


def _call_with_supported_kwargs(  # noqa: UP047 - ParamSpec rejected by pyright
    func: _AnyCallable[T], *args: Any, **kwargs: Any
) -> T:
    sig = inspect.signature(func)
    accepted: dict[str, Any] = {}
    for name, param in sig.parameters.items():
        if param.kind in (
            inspect.Parameter.VAR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        ):
            return func(*args, **kwargs)
    for key, value in kwargs.items():
        if key in sig.parameters:
            accepted[key] = value
    return func(*args, **accepted)
