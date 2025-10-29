"""Diagnostic helpers for validating BiRRe tool availability and health.

This module hosts the shared business logic that previously lived in the CLI
entrypoint.  The CLI now imports from here so that diagnostics can be reused
without pulling Typer- or Rich-specific dependencies.
"""

from __future__ import annotations

import asyncio
import errno
import inspect
import logging
import ssl
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Final
from uuid import uuid4

import httpx

from birre import _resolve_tls_verification, create_birre_server
from birre.application.startup import run_offline_startup_checks, run_online_startup_checks
from birre.config.settings import RuntimeSettings
from birre.infrastructure.errors import (
    BirreError,
    ErrorCode,
    TlsCertificateChainInterceptedError,
)
from birre.infrastructure.logging import BoundLogger
from birre.integrations.bitsight import DEFAULT_V1_API_BASE_URL, create_v1_api_server
from birre.integrations.bitsight.v1_bridge import call_v1_openapi_tool

SyncRunner = Callable[[Awaitable[Any]], Any]

_LOOP_LOGGER = logging.getLogger("birre.loop")

CONTEXT_CHOICES: Final[frozenset[str]] = frozenset({"standard", "risk_manager"})
EXPECTED_TOOLS_BY_CONTEXT: dict[str, frozenset[str]] = {
    "standard": frozenset({"company_search", "get_company_rating"}),
    "risk_manager": frozenset(
        {
            "company_search",
            "company_search_interactive",
            "get_company_rating",
            "manage_subscriptions",
            "request_company",
        }
    ),
}

MSG_NOT_A_DICT: Final = "not a dict"
MSG_TOOL_INVOCATION_FAILED: Final = "tool invocation failed"
MSG_UNEXPECTED_PAYLOAD_STRUCTURE: Final = "unexpected payload structure"
MSG_EXPECTED_TOOL_NOT_REGISTERED: Final = "expected tool not registered"
MSG_TOOL_NOT_REGISTERED: Final = "tool not registered"
MSG_CONFIG_CA_BUNDLE: Final = "config.ca_bundle"

HEALTHCHECK_COMPANY_NAME: Final = "GitHub"
HEALTHCHECK_COMPANY_DOMAIN: Final = "github.com"
HEALTHCHECK_COMPANY_GUID: Final = "6ca077e2-b5a7-42c2-ae1e-a974c3a91dc1"
HEALTHCHECK_REQUEST_DOMAIN: Final = "healthcheck-birre-example.com"


def _default_run_sync(coro: Awaitable[Any]) -> Any:
    return asyncio.run(coro)


def _sync(coro: Awaitable[Any], run_sync: SyncRunner | None = None) -> Any:
    runner = run_sync or _default_run_sync
    return runner(coro)


@dataclass
class DiagnosticFailure:
    tool: str
    stage: str
    message: str
    mode: str | None = None
    exception: BaseException | None = None
    category: str | None = None


@dataclass
class AttemptReport:
    label: str
    success: bool
    failures: list[DiagnosticFailure]
    notes: list[str]
    allow_insecure_tls: bool
    ca_bundle: str | None
    online_success: bool | None
    discovered_tools: list[str]
    missing_tools: list[str]
    tools: dict[str, dict[str, Any]]


@dataclass
class ContextDiagnosticsResult:
    name: str
    success: bool
    degraded: bool
    report: dict[str, Any]


@dataclass
class SelfTestResult:
    """Result of running BiRRe self-tests/diagnostics."""
    success: bool
    degraded: bool
    summary: dict[str, Any]
    contexts: tuple[str, ...]
    alerts: tuple[str, ...] = ()

    def exit_code(self) -> int:
        if ErrorCode.TLS_CERT_CHAIN_INTERCEPTED.value in self.alerts:
            return 2
        if not self.success:
            return 1
        if self.degraded:
            return 2
        return 0


# Backward compatibility alias - remove after migration
HealthcheckResult = SelfTestResult


class _HealthcheckContext:
    def __init__(self, *, context: str, tool_name: str, logger: BoundLogger) -> None:
        self._context = context
        self._tool_name = tool_name
        self._logger = logger
        self._request_id = f"healthcheck-{context}-{tool_name}-{uuid4().hex}"
        self.metadata: dict[str, Any] = {
            "healthcheck": True,
            "context": context,
            "tool": tool_name,
        }
        self.tool = tool_name

    def info(self, message: str) -> None:
        self._logger.info(
            "healthcheck.ctx.info",
            message=message,
            request_id=self._request_id,
            tool=self._tool_name,
        )

    def warning(self, message: str) -> None:
        self._logger.warning(
            "healthcheck.ctx.warning",
            message=message,
            request_id=self._request_id,
            tool=self._tool_name,
        )

    def error(self, message: str) -> None:
        self._logger.error(
            "healthcheck.ctx.error",
            message=message,
            request_id=self._request_id,
            tool=self._tool_name,
        )

    @property
    def request_id(self) -> str:
        return self._request_id

    @property
    def call_id(self) -> str:
        return self._request_id


def record_failure(
    failures: list[DiagnosticFailure | None] | None,
    *,
    tool: str,
    stage: str,
    message: str,
    mode: str | None = None,
    exception: BaseException | None = None,
) -> None:
    if failures is None:
        return
    failures.append(
        DiagnosticFailure(
            tool=tool,
            stage=stage,
            message=message,
            mode=mode,
            exception=exception,
        )
    )


def _resolve_tool_callable(tool: Any) -> Callable[..., Any | None] | None:
    if tool is None:
        return None
    if hasattr(tool, "fn") and callable(getattr(tool, "fn")):
        return getattr(tool, "fn")
    if callable(tool):
        return tool
    return None


def _invoke_tool(
    tool: Any,
    ctx: _HealthcheckContext,
    *,
    run_sync: SyncRunner | None,
    **params: Any,
) -> Any:
    callable_fn = _resolve_tool_callable(tool)
    if callable_fn is None:
        raise TypeError(f"Tool object {tool!r} is not callable")
    try:
        result = callable_fn(ctx, **params)
    except TypeError as exc:
        if params:
            try:
                result = callable_fn(ctx, params)
            except TypeError:
                raise
        else:
            raise
    if inspect.isawaitable(result):
        return _sync(result, run_sync)
    return result


def discover_context_tools(
    server: Any,
    *,
    run_sync: SyncRunner | None = None,
) -> set[str]:
    names: set[str] = set()
    tools_attr = getattr(server, "tools", None)
    if isinstance(tools_attr, dict):
        names.update(str(name) for name in tools_attr.keys() if isinstance(name, str))

    get_tools = getattr(server, "get_tools", None)
    if callable(get_tools):
        try:
            result = get_tools()
        except TypeError:  # pragma: no cover - defensive
            result = None
        if inspect.isawaitable(result):
            resolved = _sync(result, run_sync)
        else:
            resolved = result
        if isinstance(resolved, dict):
            names.update(str(name) for name in resolved.keys() if isinstance(name, str))

    return names


def collect_tool_map(
    server: Any,
    *,
    run_sync: SyncRunner | None = None,
) -> dict[str, Any]:
    tools: dict[str, Any] = {}

    tools_attr = getattr(server, "tools", None)
    if isinstance(tools_attr, dict):
        tools.update(
            {str(name): tool for name, tool in tools_attr.items() if isinstance(name, str)}
        )

    get_tools = getattr(server, "get_tools", None)
    if callable(get_tools):
        try:
            result = get_tools()
        except TypeError:  # pragma: no cover - defensive
            result = None
        if inspect.isawaitable(result):
            resolved = _sync(result, run_sync)
        else:
            resolved = result
        if isinstance(resolved, dict):
            tools.update(
                {str(name): tool for name, tool in resolved.items() if isinstance(name, str)}
            )

    for candidate in (
        "company_search",
        "company_search_interactive",
        "get_company_rating",
        "manage_subscriptions",
        "request_company",
    ):
        tool = getattr(server, candidate, None)
        if tool is not None:
            tools.setdefault(candidate, tool)

    return tools


def prepare_server(
    runtime_settings: RuntimeSettings,
    logger: BoundLogger,
    *,
    v1_base_url: str = DEFAULT_V1_API_BASE_URL,
) -> Any:
    logger.info("Preparing BiRRe FastMCP server")
    return create_birre_server(
        settings=runtime_settings,
        logger=logger,
        v1_base_url=v1_base_url,
    )


def _validate_positive(name: str, value: int | None) -> int | None:
    if value is None:
        return None
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def check_required_tool(
    *,
    tool_name: str,
    tool: Any,
    context: str,
    logger: BoundLogger,
    diagnostic_fn: Callable[..., bool],
    failures: list[DiagnosticFailure | None] | None,
    summary: dict[str, Any] | None,
    run_sync: SyncRunner | None,
) -> bool:
    if tool is None:
        record_failure(
            failures,
            tool=tool_name,
            stage="discovery",
            message="required tool missing",
        )
        if summary is not None:
            summary.update(
                {
                    "status": "fail",
                    "details": {"reason": "required tool not registered"},
                }
            )
        logger.error("Required tool missing", tool=tool_name)
        return False

    try:
        ok = diagnostic_fn(
            context=context,
            logger=logger,
            tool=tool,
            failures=failures,
            summary=summary,
            run_sync=run_sync,
        )
    except Exception as exc:  # pragma: no cover - defensive
        record_failure(
            failures,
            tool=tool_name,
            stage="invoke",
            message="unexpected exception during diagnostic",
            exception=exc,
        )
        if summary is not None:
            summary.update(
                {
                    "status": "fail",
                    "details": {
                        "reason": "diagnostic invocation failed",
                        "error": str(exc),
                    },
                }
            )
        logger.exception("Diagnostic invocation failed", tool=tool_name)
        return False

    if summary is not None:
        summary.update(
            {
                "status": "pass" if ok else "fail",
                "details": {
                    "reason": "diagnostic succeeded" if ok else "diagnostic reported failure",
                },
            }
        )

    return ok


def check_optional_tool(
    *,
    tool: Any,
    context: str,
    logger: BoundLogger,
    diagnostic_fn: Callable[..., bool],
    failures: list[DiagnosticFailure | None] | None,
    summary: dict[str, Any] | None,
    run_sync: SyncRunner | None,
) -> bool:
    if tool is None:
        if summary is not None:
            summary.update(
                {
                    "status": "warning",
                    "details": {"reason": "tool not available in this configuration"},
                }
            )
        return True

    try:
        ok = diagnostic_fn(
            context=context,
            logger=logger,
            tool=tool,
            failures=failures,
            summary=summary,
            run_sync=run_sync,
        )
    except Exception as exc:  # pragma: no cover - defensive
        record_failure(
            failures,
            tool=getattr(tool, "name", "optional"),
            stage="invoke",
            message="optional tool diagnostic failed",
            exception=exc,
        )
        if summary is not None:
            summary.update(
                {
                    "status": "warning",
                    "details": {
                        "reason": "diagnostic invocation failed",
                        "error": str(exc),
                    },
                }
            )
        logger.warning("Optional tool diagnostic failed", error=str(exc))
        return False

    if summary is not None:
        summary.update(
            {
                "status": "pass" if ok else "warning",
                "details": {
                    "reason": "diagnostic succeeded"
                    if ok
                    else "diagnostic reported warnings",
                },
            }
        )

    return ok


def run_context_tool_diagnostics(
    *,
    context: str,
    logger: BoundLogger,
    server_instance: Any,
    expected_tools: frozenset[str],
    summary: dict[str, dict[str, Any | None]] | None = None,
    failures: list[DiagnosticFailure | None] | None = None,
    run_sync: SyncRunner | None = None,
) -> bool:
    tools = collect_tool_map(server_instance, run_sync=run_sync)
    success = True

    if summary is not None:
        for tool_name in expected_tools:
            summary.setdefault(
                tool_name,
                {
                    "status": "warning",
                    "details": {"reason": "not evaluated"},
                },
            )

    def summary_entry(name: str) -> dict[str, Any | None] | None:
        if summary is None:
            return None
        return summary.setdefault(name, {})

    if not check_required_tool(
        tool_name="company_search",
        tool=tools.get("company_search"),
        context=context,
        logger=logger,
        diagnostic_fn=run_company_search_diagnostics,
        failures=failures,
        summary=summary_entry("company_search"),
        run_sync=run_sync,
    ):
        success = False

    if not check_required_tool(
        tool_name="get_company_rating",
        tool=tools.get("get_company_rating"),
        context=context,
        logger=logger,
        diagnostic_fn=run_rating_diagnostics,
        failures=failures,
        summary=summary_entry("get_company_rating"),
        run_sync=run_sync,
    ):
        success = False

    if not check_optional_tool(
        tool=tools.get("company_search_interactive"),
        context=context,
        logger=logger,
        diagnostic_fn=run_company_search_interactive_diagnostics,
        failures=failures,
        summary=summary_entry("company_search_interactive"),
        run_sync=run_sync,
    ):
        success = False

    if not check_optional_tool(
        tool=tools.get("manage_subscriptions"),
        context=context,
        logger=logger,
        diagnostic_fn=run_manage_subscriptions_diagnostics,
        failures=failures,
        summary=summary_entry("manage_subscriptions"),
        run_sync=run_sync,
    ):
        success = False

    if not check_optional_tool(
        tool=tools.get("request_company"),
        context=context,
        logger=logger,
        diagnostic_fn=run_request_company_diagnostics,
        failures=failures,
        summary=summary_entry("request_company"),
        run_sync=run_sync,
    ):
        success = False

    return success


def run_company_search_diagnostics(
    *,
    context: str,
    logger: BoundLogger,
    tool: Any,
    failures: list[DiagnosticFailure | None] | None = None,
    summary: dict[str, Any | None] | None = None,
    run_sync: SyncRunner | None = None,
) -> bool:
    tool_logger = logger.bind(tool="company_search")
    ctx = _HealthcheckContext(context=context, tool_name="company_search", logger=tool_logger)
    if summary is not None:
        summary.clear()
        summary["status"] = "pass"
    try:
        by_name = _invoke_tool(
            tool,
            ctx,
            run_sync=run_sync,
            name=HEALTHCHECK_COMPANY_NAME,
        )
    except Exception as exc:  # pragma: no cover - network failures
        tool_logger.critical("healthcheck.company_search.call_failed", error=str(exc))
        record_failure(
            failures,
            tool="company_search",
            stage="call",
            mode="name",
            message=MSG_TOOL_INVOCATION_FAILED,
            exception=exc,
        )
        if summary is not None:
            summary["status"] = "fail"
            summary["details"] = {
                "reason": MSG_TOOL_INVOCATION_FAILED,
                "mode": "name",
                "error": str(exc),
            }
        return False

    if not _validate_company_search_payload(
        by_name,
        logger=tool_logger,
        expected_domain=None,
    ):
        record_failure(
            failures,
            tool="company_search",
            stage="validation",
            mode="name",
            message=MSG_UNEXPECTED_PAYLOAD_STRUCTURE,
        )
        if summary is not None:
            summary["status"] = "fail"
            summary["details"] = {
                "reason": MSG_UNEXPECTED_PAYLOAD_STRUCTURE,
                "mode": "name",
            }
        return False

    if summary is not None:
        summary.setdefault("modes", {})["name"] = {"status": "pass"}

    try:
        by_domain = _invoke_tool(
            tool,
            ctx,
            run_sync=run_sync,
            domain=HEALTHCHECK_COMPANY_DOMAIN,
        )
    except Exception as exc:  # pragma: no cover - network failures
        tool_logger.critical("healthcheck.company_search.domain_call_failed", error=str(exc))
        record_failure(
            failures,
            tool="company_search",
            stage="call",
            mode="domain",
            message=MSG_TOOL_INVOCATION_FAILED,
            exception=exc,
        )
        if summary is not None:
            summary["status"] = "fail"
            summary["details"] = {
                "reason": MSG_TOOL_INVOCATION_FAILED,
                "mode": "domain",
                "error": str(exc),
            }
            summary.setdefault("modes", {})["domain"] = {
                "status": "fail",
                "error": str(exc),
            }
        return False

    if not _validate_company_search_payload(
        by_domain,
        logger=tool_logger,
        expected_domain=HEALTHCHECK_COMPANY_DOMAIN,
    ):
        record_failure(
            failures,
            tool="company_search",
            stage="validation",
            mode="domain",
            message=MSG_UNEXPECTED_PAYLOAD_STRUCTURE,
        )
        if summary is not None:
            summary["status"] = "fail"
            summary["details"] = {
                "reason": MSG_UNEXPECTED_PAYLOAD_STRUCTURE,
                "mode": "domain",
            }
            summary.setdefault("modes", {})["domain"] = {
                "status": "fail",
                "detail": MSG_UNEXPECTED_PAYLOAD_STRUCTURE,
            }
        return False

    if summary is not None:
        summary.setdefault("modes", {})["domain"] = {"status": "pass"}

    tool_logger.info("healthcheck.company_search.success")
    return True


def run_rating_diagnostics(
    *,
    context: str,
    logger: BoundLogger,
    tool: Any,
    failures: list[DiagnosticFailure | None] | None = None,
    summary: dict[str, Any | None] | None = None,
    run_sync: SyncRunner | None = None,
) -> bool:
    tool_logger = logger.bind(tool="get_company_rating")
    ctx = _HealthcheckContext(context=context, tool_name="get_company_rating", logger=tool_logger)
    if summary is not None:
        summary.clear()
        summary["status"] = "pass"
    try:
        payload = _invoke_tool(
            tool,
            ctx,
            run_sync=run_sync,
            guid=HEALTHCHECK_COMPANY_GUID,
        )
    except Exception as exc:  # pragma: no cover - network failures
        tool_logger.critical("healthcheck.rating.call_failed", error=str(exc))
        record_failure(
            failures,
            tool="get_company_rating",
            stage="call",
            message=MSG_TOOL_INVOCATION_FAILED,
            exception=exc,
        )
        if summary is not None:
            summary["status"] = "fail"
            summary["details"] = {
                "reason": MSG_TOOL_INVOCATION_FAILED,
                "error": str(exc),
            }
        return False

    if not _validate_rating_payload(payload, logger=tool_logger):
        record_failure(
            failures,
            tool="get_company_rating",
            stage="validation",
            message=MSG_UNEXPECTED_PAYLOAD_STRUCTURE,
        )
        if summary is not None:
            summary["status"] = "fail"
            summary["details"] = {"reason": MSG_UNEXPECTED_PAYLOAD_STRUCTURE}
        return False

    domain_value = payload.get("domain")
    if isinstance(domain_value, str) and domain_value.lower() != HEALTHCHECK_COMPANY_DOMAIN:
        tool_logger.critical(
            "healthcheck.rating.domain_mismatch",
            domain=domain_value,
            expected=HEALTHCHECK_COMPANY_DOMAIN,
        )
        record_failure(
            failures,
            tool="get_company_rating",
            stage="validation",
            message="domain mismatch",
        )
        if summary is not None:
            summary["status"] = "fail"
            summary["details"] = {
                "reason": "domain mismatch",
                "domain": domain_value,
            }
        return False

    tool_logger.info("healthcheck.rating.success")
    return True


def run_company_search_interactive_diagnostics(
    *,
    context: str,
    logger: BoundLogger,
    tool: Any,
    failures: list[DiagnosticFailure | None] | None = None,
    summary: dict[str, Any | None] | None = None,
    run_sync: SyncRunner | None = None,
) -> bool:
    tool_logger = logger.bind(tool="company_search_interactive")
    ctx = _HealthcheckContext(
        context=context,
        tool_name="company_search_interactive",
        logger=tool_logger,
    )
    if summary is not None:
        summary.clear()
        summary["status"] = "pass"
    try:
        payload = _invoke_tool(
            tool,
            ctx,
            run_sync=run_sync,
            name=HEALTHCHECK_COMPANY_NAME,
        )
    except Exception as exc:  # pragma: no cover - network failures
        tool_logger.warning("healthcheck.company_search_interactive.call_failed", error=str(exc))
        record_failure(
            failures,
            tool="company_search_interactive",
            stage="call",
            message=MSG_TOOL_INVOCATION_FAILED,
            exception=exc,
        )
        if summary is not None:
            summary["status"] = "warning"
            summary["details"] = {
                "reason": MSG_TOOL_INVOCATION_FAILED,
                "error": str(exc),
            }
        return False

    if not _validate_company_search_interactive_payload(payload, logger=tool_logger):
        record_failure(
            failures,
            tool="company_search_interactive",
            stage="validation",
            message=MSG_UNEXPECTED_PAYLOAD_STRUCTURE,
        )
        if summary is not None:
            summary["status"] = "warning"
            summary["details"] = {"reason": MSG_UNEXPECTED_PAYLOAD_STRUCTURE}
        return False

    tool_logger.info("healthcheck.company_search_interactive.success")
    return True


def run_manage_subscriptions_diagnostics(
    *,
    context: str,
    logger: BoundLogger,
    tool: Any,
    failures: list[DiagnosticFailure | None] | None = None,
    summary: dict[str, Any | None] | None = None,
    run_sync: SyncRunner | None = None,
) -> bool:
    tool_logger = logger.bind(tool="manage_subscriptions")
    ctx = _HealthcheckContext(context=context, tool_name="manage_subscriptions", logger=tool_logger)
    if summary is not None:
        summary.clear()
        summary["status"] = "pass"
    try:
        payload = _invoke_tool(
            tool,
            ctx,
            run_sync=run_sync,
            name=HEALTHCHECK_COMPANY_NAME,
            guids=[HEALTHCHECK_COMPANY_GUID],
            dry_run=True,
        )
    except Exception as exc:  # pragma: no cover - network failures
        tool_logger.warning("healthcheck.manage_subscriptions.call_failed", error=str(exc))
        record_failure(
            failures,
            tool="manage_subscriptions",
            stage="call",
            message=MSG_TOOL_INVOCATION_FAILED,
            exception=exc,
        )
        if summary is not None:
            summary["status"] = "warning"
            summary["details"] = {
                "reason": MSG_TOOL_INVOCATION_FAILED,
                "error": str(exc),
            }
        return False

    if not _validate_manage_subscriptions_payload(
        payload,
        logger=tool_logger,
        expected_guid=HEALTHCHECK_COMPANY_GUID,
    ):
        record_failure(
            failures,
            tool="manage_subscriptions",
            stage="validation",
            message=MSG_UNEXPECTED_PAYLOAD_STRUCTURE,
        )
        if summary is not None:
            summary["status"] = "warning"
            summary["details"] = {"reason": MSG_UNEXPECTED_PAYLOAD_STRUCTURE}
        return False

    tool_logger.info("healthcheck.manage_subscriptions.success")
    return True


def run_request_company_diagnostics(
    *,
    context: str,
    logger: BoundLogger,
    tool: Any,
    failures: list[DiagnosticFailure | None] | None = None,
    summary: dict[str, Any | None] | None = None,
    run_sync: SyncRunner | None = None,
) -> bool:
    tool_logger = logger.bind(tool="request_company")
    ctx = _HealthcheckContext(context=context, tool_name="request_company", logger=tool_logger)
    if summary is not None:
        summary.clear()
        summary["status"] = "pass"
    try:
        payload = _invoke_tool(
            tool,
            ctx,
            run_sync=run_sync,
            name=HEALTHCHECK_COMPANY_NAME,
            domain=HEALTHCHECK_REQUEST_DOMAIN,
        )
    except Exception as exc:  # pragma: no cover - network failures
        tool_logger.warning("healthcheck.request_company.call_failed", error=str(exc))
        record_failure(
            failures,
            tool="request_company",
            stage="call",
            message=MSG_TOOL_INVOCATION_FAILED,
            exception=exc,
        )
        if summary is not None:
            summary["status"] = "warning"
            summary["details"] = {
                "reason": MSG_TOOL_INVOCATION_FAILED,
                "error": str(exc),
            }
        return False

    if not _validate_request_company_payload(
        payload,
        logger=tool_logger,
        expected_domain=HEALTHCHECK_REQUEST_DOMAIN,
    ):
        record_failure(
            failures,
            tool="request_company",
            stage="validation",
            message=MSG_UNEXPECTED_PAYLOAD_STRUCTURE,
        )
        if summary is not None:
            summary["status"] = "warning"
            summary["details"] = {"reason": MSG_UNEXPECTED_PAYLOAD_STRUCTURE}
        return False

    tool_logger.info("healthcheck.request_company.success")
    return True


def _validate_company_entry(entry: Any, logger: BoundLogger) -> bool:
    if not isinstance(entry, dict):
        logger.critical("healthcheck.company_search.invalid_company", reason="entry not dict")
        return False
    if not entry.get("guid") or not entry.get("name"):
        logger.critical(
            "healthcheck.company_search.invalid_company",
            reason="missing guid/name",
            company=entry,
        )
        return False
    return True


def _check_domain_match(companies: list, expected_domain: str, logger: BoundLogger) -> bool:
    for entry in companies:
        domain_value = str(entry.get("domain") or "")
        if domain_value.lower() == expected_domain.lower():
            return True
    logger.critical("healthcheck.company_search.domain_missing", expected=expected_domain)
    return False


def _validate_company_search_payload(
    payload: Any,
    *,
    logger: BoundLogger,
    expected_domain: str | None,
) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.company_search.invalid_response", reason=MSG_NOT_A_DICT)
        return False

    if payload.get("error"):
        logger.critical("healthcheck.company_search.api_error", error=str(payload["error"]))
        return False

    companies = payload.get("companies")
    if not isinstance(companies, list) or not companies:
        logger.critical("healthcheck.company_search.empty", reason="no companies returned")
        return False

    for entry in companies:
        if not _validate_company_entry(entry, logger):
            return False

    count_value = payload.get("count")
    if not isinstance(count_value, int) or count_value <= 0:
        logger.critical("healthcheck.company_search.invalid_count", count=count_value)
        return False

    if expected_domain and not _check_domain_match(companies, expected_domain, logger):
        return False

    return True


def _validate_company_search_interactive_payload(
    payload: Any,
    *,
    logger: BoundLogger,
) -> bool:
    if not isinstance(payload, dict):
        logger.critical(
            "healthcheck.company_search_interactive.invalid_response",
            reason=MSG_NOT_A_DICT,
        )
        return False

    if payload.get("error"):
        logger.critical(
            "healthcheck.company_search_interactive.api_error",
            error=str(payload["error"]),
        )
        return False

    results = payload.get("results")
    if not isinstance(results, list) or not results:
        logger.critical(
            "healthcheck.company_search_interactive.empty_results",
            reason="no interactive results",
        )
        return False

    for entry in results:
        if not isinstance(entry, dict):
            logger.critical(
                "healthcheck.company_search_interactive.invalid_entry",
                reason="entry not dict",
            )
            return False
        required_keys = ("guid", "name", "primary_domain", "subscription")
        if any(not entry.get(key) for key in required_keys):
            logger.critical(
                "healthcheck.company_search_interactive.missing_fields",
                entry=entry,
            )
            return False
        subscription = entry.get("subscription")
        if not isinstance(subscription, dict) or "active" not in subscription:
            logger.critical(
                "healthcheck.company_search_interactive.invalid_subscription",
                subscription=subscription,
            )
            return False

    count_value = payload.get("count")
    if not isinstance(count_value, int) or count_value <= 0:
        logger.critical(
            "healthcheck.company_search_interactive.invalid_count",
            count=count_value,
        )
        return False

    guidance = payload.get("guidance")
    if not isinstance(guidance, dict):
        logger.critical("healthcheck.company_search_interactive.missing_guidance")
        return False

    return True


def _validate_rating_payload(payload: Any, *, logger: BoundLogger) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.rating.invalid_response", reason=MSG_NOT_A_DICT)
        return False

    if payload.get("error"):
        logger.critical("healthcheck.rating.api_error", error=str(payload["error"]))
        return False

    required_fields = ("name", "domain", "current_rating", "top_findings", "legend")
    for field in required_fields:
        if payload.get(field) in (None, {}):
            logger.critical("healthcheck.rating.missing_field", field=field)
            return False

    current_rating = payload.get("current_rating")
    if not isinstance(current_rating, dict) or current_rating.get("value") is None:
        logger.critical("healthcheck.rating.invalid_current_rating", payload=current_rating)
        return False

    findings = payload.get("top_findings")
    if not isinstance(findings, dict):
        logger.critical("healthcheck.rating.invalid_findings", payload=findings)
        return False

    finding_count = findings.get("count")
    finding_entries = findings.get("findings")
    if not isinstance(finding_count, int) or finding_count <= 0:
        logger.critical("healthcheck.rating.no_findings", count=finding_count)
        return False
    if not isinstance(finding_entries, list) or not finding_entries:
        logger.critical("healthcheck.rating.empty_findings", payload=findings)
        return False

    legend = payload.get("legend")
    if not isinstance(legend, dict) or not legend.get("rating"):
        logger.critical("healthcheck.rating.missing_legend", payload=legend)
        return False

    return True


def _validate_manage_subscriptions_payload(
    payload: Any,
    *,
    logger: BoundLogger,
    expected_guid: str,
) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.manage_subscriptions.invalid_response", reason=MSG_NOT_A_DICT)
        return False

    if payload.get("error"):
        logger.critical("healthcheck.manage_subscriptions.api_error", error=str(payload["error"]))
        return False

    status = payload.get("status")
    if status not in {"dry_run", "applied"}:
        logger.critical("healthcheck.manage_subscriptions.unexpected_status", status=status)
        return False

    guids = payload.get("guids")
    if not isinstance(guids, list) or expected_guid not in guids:
        logger.critical(
            "healthcheck.manage_subscriptions.guid_missing",
            guids=guids,
            expected=expected_guid,
        )
        return False

    if status == "dry_run":
        dry_payload = payload.get("payload")
        if not isinstance(dry_payload, dict) or "add" not in dry_payload:
            logger.critical(
                "healthcheck.manage_subscriptions.invalid_payload",
                payload=dry_payload,
            )
            return False

    return True


def _validate_request_company_domains(domains: Any, *, logger: BoundLogger, expected: str) -> bool:
    if not isinstance(domains, list) or not domains:
        logger.critical("healthcheck.request_company.invalid_domains", domains=domains)
        return False
    for entry in domains:
        if not isinstance(entry, dict) or not entry.get("domain"):
            logger.critical("healthcheck.request_company.invalid_domain_entry", entry=entry)
            return False
        if entry.get("domain", "").lower() == expected.lower():
            return True
    logger.critical("healthcheck.request_company.domain_missing", expected=expected)
    return False


def _validate_request_company_payload(
    payload: Any,
    *,
    logger: BoundLogger,
    expected_domain: str,
) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.request_company.invalid_response", reason=MSG_NOT_A_DICT)
        return False

    if payload.get("error"):
        logger.critical("healthcheck.request_company.api_error", error=str(payload["error"]))
        return False

    status = payload.get("status")
    if status not in {"requested", "existing"}:
        logger.critical("healthcheck.request_company.unexpected_status", status=status)
        return False

    domains = payload.get("domains")
    if not _validate_request_company_domains(domains, logger=logger, expected=expected_domain):
        return False

    return True


def _is_tls_exception(exc: BaseException) -> bool:
    if isinstance(exc, TlsCertificateChainInterceptedError):
        return True
    if isinstance(exc, ssl.SSLError):
        return True
    if isinstance(exc, httpx.HTTPError):
        cause = exc.__cause__
        if isinstance(cause, ssl.SSLError):
            return True
        message = str(exc).lower()
        if any(token in message for token in ("ssl", "tls", "certificate")):
            return True
    message = str(exc).lower()
    if any(token in message for token in ("ssl", "tls", "certificate verify failed")):
        return True
    return False


def _is_missing_ca_bundle_exception(exc: BaseException) -> bool:
    if isinstance(exc, FileNotFoundError):
        return True
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == errno.ENOENT:
        return True
    message = str(exc).lower()
    if "could not find a suitable tls ca certificate bundle" in message:
        return True
    if "no such file or directory" in message and "ca" in message:
        return True
    return False


def classify_failure(failure: DiagnosticFailure) -> str | None:
    if failure.exception is None:
        message = failure.message.lower()
        if any(token in message for token in ("ssl", "tls", "certificate")):
            failure.category = "tls"
        return failure.category
    if _is_tls_exception(failure.exception):
        failure.category = "tls"
    elif _is_missing_ca_bundle_exception(failure.exception):
        failure.category = MSG_CONFIG_CA_BUNDLE
    return failure.category


def summarize_failure(failure: DiagnosticFailure) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "tool": failure.tool,
        "stage": failure.stage,
    }
    if failure.mode:
        summary["mode"] = failure.mode
    if failure.category:
        summary["category"] = failure.category
    if failure.exception is not None:
        summary["error"] = str(failure.exception)
    else:
        summary["message"] = failure.message
    return summary


def _create_offline_tool_status(tool_name: str, missing_set: set[str | None]) -> dict[str, Any]:
    if tool_name in missing_set:
        return {
            "status": "fail",
            "details": {"reason": MSG_TOOL_NOT_REGISTERED},
        }
    return {
        "status": "warning",
        "details": {"reason": "offline mode"},
    }


def _collect_tool_attempts(
    tool_name: str,
    attempts: Sequence[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    attempt_details: dict[str, dict[str, Any]] = {}
    statuses: list[str] = []
    for attempt in attempts:
        tool_entry = attempt.get("tools", {}).get(tool_name)
        if tool_entry is None:
            continue
        attempt_details[attempt["label"]] = tool_entry
        status = tool_entry.get("status")
        if isinstance(status, str):
            statuses.append(status)
    return attempt_details, statuses


def _determine_final_status(statuses: list[str]) -> str:
    if any(status == "pass" for status in statuses):
        return "pass"
    if any(status == "fail" for status in statuses):
        return "fail"
    return statuses[0]


def aggregate_tool_outcomes(
    expected_tools: frozenset[str],
    attempts: Sequence[dict[str, Any]],
    *,
    offline_mode: bool = False,
    offline_missing: Sequence[str | None] | None = None,
) -> dict[str, dict[str, Any]]:
    aggregated: dict[str, dict[str, Any]] = {}
    if offline_mode:
        missing_set = set(offline_missing or ())
        for tool_name in sorted(expected_tools):
            aggregated[tool_name] = _create_offline_tool_status(tool_name, missing_set)
        return aggregated

    for tool_name in sorted(expected_tools):
        attempt_details, statuses = _collect_tool_attempts(tool_name, attempts)

        if not statuses:
            aggregated[tool_name] = {
                "status": "warning",
                "attempts": attempt_details or None,
            }
            continue

        final_status = _determine_final_status(statuses)
        entry: dict[str, Any] = {"status": final_status}
        if attempt_details:
            entry["attempts"] = attempt_details
        aggregated[tool_name] = entry
    return aggregated


def run_offline_checks(runtime_settings: RuntimeSettings, logger: BoundLogger) -> bool:
    logger.info("Running offline startup checks")
    offline_ok = run_offline_startup_checks(
        has_api_key=bool(runtime_settings.api_key),
        subscription_folder=runtime_settings.subscription_folder,
        subscription_type=runtime_settings.subscription_type,
        logger=logger,
    )
    if not offline_ok:
        logger.critical("Offline startup checks failed")
    return offline_ok


def run_online_checks(
    runtime_settings: RuntimeSettings,
    logger: BoundLogger,
    *,
    run_sync: SyncRunner | None = None,
    v1_base_url: str | None = None,
) -> bool:
    logger.info("Running online startup checks")

    verify_option = _resolve_tls_verification(runtime_settings, logger)
    base_url = v1_base_url or DEFAULT_V1_API_BASE_URL

    async def _execute_checks() -> bool:
        api_server = create_v1_api_server(
            runtime_settings.api_key,
            verify=verify_option,
            base_url=base_url,
        )

        async def call_v1_tool(tool_name: str, ctx, params: dict[str, Any]) -> Any:
            return await call_v1_openapi_tool(
                api_server,
                tool_name,
                ctx,
                params,
                logger=logger,
            )

        try:
            return await run_online_startup_checks(
                call_v1_tool=call_v1_tool,
                subscription_folder=runtime_settings.subscription_folder,
                subscription_type=runtime_settings.subscription_type,
                logger=logger,
                skip_startup_checks=getattr(runtime_settings, "skip_startup_checks", False),
            )
        finally:
            client = getattr(api_server, "_client", None)
            close = getattr(client, "aclose", None)
            if callable(close):
                try:
                    await close()
                except Exception as exc:  # pragma: no cover - defensive logging
                    _LOOP_LOGGER.warning(
                        "online_checks.client_close_failed",
                        error=str(exc),
                    )
            shutdown = getattr(api_server, "shutdown", None)
            if callable(shutdown):
                with suppress(Exception):
                    await shutdown()  # type: ignore[func-returns-value]

    return _sync(_execute_checks(), run_sync=run_sync)


class SelfTestRunner:
    """Execute BiRRe self-tests and diagnostics in a structured, testable manner."""

    def __init__(
        self,
        *,
        runtime_settings: RuntimeSettings,
        logger: BoundLogger,
        offline: bool,
        target_base_url: str = DEFAULT_V1_API_BASE_URL,
        environment_label: str,
        run_sync: SyncRunner | None = None,
        expected_tools_by_context: Mapping[str, frozenset[str]] | None = None,
    ) -> None:
        self._base_runtime_settings = runtime_settings
        self._logger = logger
        self._offline = offline
        self._target_base_url = target_base_url
        self._environment_label = environment_label
        self._run_sync = run_sync or _default_run_sync
        self._expected_tools_by_context = dict(
            expected_tools_by_context or EXPECTED_TOOLS_BY_CONTEXT
        )
        self._contexts: tuple[str, ...] = tuple(sorted(self._expected_tools_by_context))
        self._alerts: set[str] = set()

    def run(self) -> HealthcheckResult:
        self._alerts.clear()
        offline_ok = run_offline_checks(self._base_runtime_settings, self._logger)
        summary: dict[str, Any] = {
            "environment": self._environment_label,
            "offline_check": {"status": "pass" if offline_ok else "fail"},
            "contexts": {},
            "overall_success": None,
        }

        if not offline_ok:
            summary["overall_success"] = False
            return HealthcheckResult(
                success=False,
                degraded=False,
                summary=summary,
                contexts=self._contexts,
                alerts=tuple(sorted(self._alerts)),
            )

        overall_success = True
        degraded = self._offline
        context_reports: dict[str, dict[str, Any]] = summary["contexts"]

        for context_name in self._contexts:
            result = self._evaluate_context(context_name)
            context_reports[context_name] = result.report
            if not result.success:
                overall_success = False
            if result.degraded:
                degraded = True

        summary["overall_success"] = overall_success
        return HealthcheckResult(
            success=overall_success,
            degraded=degraded,
            summary=summary,
            contexts=self._contexts,
            alerts=tuple(sorted(self._alerts)),
        )

    def _evaluate_context(self, context_name: str) -> ContextDiagnosticsResult:
        logger = self._logger.bind(context=context_name)
        logger.info("Preparing context diagnostics")

        expected_tools = self._expected_tools_by_context.get(context_name)
        report: dict[str, Any] = {
            "offline_mode": bool(self._offline),
            "attempts": [],
            "encountered_categories": [],
            "fallback_attempted": False,
            "fallback_success": None,
            "failure_categories": [],
            "recoverable_categories": [],
            "unrecoverable_categories": [],
            "notes": [],
        }

        if expected_tools is None:
            logger.critical("No expected tool inventory defined for context")
            report["success"] = False
            report["online"] = {
                "status": "fail",
                "details": {"reason": "missing expected tool inventory"},
            }
            report["tools"] = {}
            return ContextDiagnosticsResult(
                name=context_name,
                success=False,
                degraded=False,
                report=report,
            )

        context_settings = replace(self._base_runtime_settings, context=context_name)
        effective_settings, notes, degraded = self._resolve_ca_bundle(logger, context_settings)
        report["notes"] = list(notes)

        if self._offline:
            return self._evaluate_offline_context(
                context_name,
                logger,
                expected_tools,
                report,
                effective_settings,
                degraded,
            )

        return self._evaluate_online_context(
            context_name,
            logger,
            expected_tools,
            report,
            effective_settings,
            degraded,
        )

    def _resolve_ca_bundle(
        self,
        logger: BoundLogger,
        context_settings: RuntimeSettings,
    ) -> tuple[RuntimeSettings, list[str], bool]:
        notes: list[str] = []
        degraded = False
        effective_settings = context_settings

        ca_bundle_path = getattr(context_settings, "ca_bundle_path", None)
        if ca_bundle_path:
            resolved_ca_path = Path(str(ca_bundle_path)).expanduser()
            if not resolved_ca_path.exists():
                logger.warning(
                    "Configured CA bundle missing; falling back to system defaults",
                    ca_bundle=str(resolved_ca_path),
                )
                effective_settings = replace(effective_settings, ca_bundle_path=None)
                notes.append("ca-bundle-defaulted")
                degraded = True

        return effective_settings, notes, degraded

    def _evaluate_offline_context(
        self,
        context_name: str,
        logger: BoundLogger,
        expected_tools: frozenset[str],
        report: dict[str, Any],
        effective_settings: RuntimeSettings,
        degraded: bool,
    ) -> ContextDiagnosticsResult:
        server_instance = prepare_server(
            effective_settings,
            logger,
            v1_base_url=self._target_base_url,
        )
        discovered_tools = discover_context_tools(
            server_instance,
            run_sync=self._run_sync,
        )
        missing_tools = sorted(expected_tools - discovered_tools)
        report["discovery"] = {
            "discovered": sorted(discovered_tools),
            "missing": missing_tools,
        }
        report["tools"] = aggregate_tool_outcomes(
            expected_tools,
            [],
            offline_mode=True,
            offline_missing=missing_tools,
        )
        report["online"] = {
            "status": "warning",
            "details": {"reason": "offline mode"},
        }
        report["encountered_categories"] = []
        report["failure_categories"] = []
        report["recoverable_categories"] = []
        report["unrecoverable_categories"] = []

        if missing_tools:
            logger.critical(
                "Tool discovery failed",
                missing_tools=missing_tools,
                discovered=sorted(discovered_tools),
                attempt="offline",
            )
            report["success"] = False
            return ContextDiagnosticsResult(
                name=context_name,
                success=False,
                degraded=degraded,
                report=report,
            )

        logger.info(
            "Tool discovery succeeded",
            tools=sorted(discovered_tools),
            attempt="offline",
        )
        report["success"] = True
        degraded = True  # offline mode limits coverage
        return ContextDiagnosticsResult(
            name=context_name,
            success=True,
            degraded=degraded,
            report=report,
        )

    def _evaluate_online_context(
        self,
        context_name: str,
        logger: BoundLogger,
        expected_tools: frozenset[str],
        report: dict[str, Any],
        effective_settings: RuntimeSettings,
        degraded: bool,
    ) -> ContextDiagnosticsResult:
        attempt_reports: list[AttemptReport] = []
        encountered_categories: set[str] = set()
        failure_categories: set[str] = set()
        fallback_attempted = False
        fallback_success_value: bool | None = None

        primary_report = self._run_diagnostic_attempt(
            context_name=context_name,
            settings=effective_settings,
            context_logger=logger,
            expected_tools=expected_tools,
            label="primary",
            notes=report.get("notes", ()),
        )
        attempt_reports.append(primary_report)
        self._update_failure_categories(
            primary_report, encountered_categories, failure_categories
        )
        context_success = primary_report.success

        if not context_success:
            tls_failures = [
                failure
                for failure in primary_report.failures
                if failure.category == "tls"
            ]
            if tls_failures and not effective_settings.allow_insecure_tls:
                fallback_report = self._attempt_tls_fallback(
                    context_name,
                    effective_settings,
                    logger,
                    expected_tools,
                    tls_failures,
                )
                attempt_reports.append(fallback_report)
                fallback_attempted = True
                fallback_success_value = fallback_report.success
                self._update_failure_categories(
                    fallback_report,
                    encountered_categories,
                    failure_categories,
                )
                context_success = fallback_report.success
                self._log_fallback_result(logger, fallback_report.success, tls_failures)
            else:
                context_success = False

        recoverable, unrecoverable = self._categorize_failures(
            encountered_categories, failure_categories
        )
        self._log_context_result(
            logger, context_success, attempt_reports, recoverable, unrecoverable
        )

        report["success"] = context_success
        report["fallback_attempted"] = fallback_attempted
        report["fallback_success"] = fallback_success_value
        report["encountered_categories"] = sorted(encountered_categories)
        report["failure_categories"] = sorted(
            category for category in failure_categories if category
        )
        report["recoverable_categories"] = recoverable
        report["unrecoverable_categories"] = unrecoverable

        attempt_summaries = self._build_attempt_summaries(attempt_reports)
        report["attempts"] = attempt_summaries

        report["online"] = self._calculate_online_status(attempt_summaries)

        report["tools"] = aggregate_tool_outcomes(
            expected_tools,
            attempt_summaries,
            offline_mode=False,
        )

        tls_failure_present = any(
            failure.category == "tls"
            for attempt in attempt_reports
            for failure in attempt.failures
        )
        if tls_failure_present:
            report.setdefault("notes", []).append("tls-cert-chain-intercepted")
            report["tls_cert_chain_intercepted"] = True

        context_degraded = degraded
        if tls_failure_present and not context_success:
            context_degraded = True

        if context_success:
            context_degraded = context_degraded or self._has_degraded_outcomes(
                report, attempt_reports
            )

        return ContextDiagnosticsResult(
            name=context_name,
            success=context_success,
            degraded=context_degraded,
            report=report,
        )

    def _attempt_tls_fallback(
        self,
        context_name: str,
        effective_settings: RuntimeSettings,
        logger: BoundLogger,
        expected_tools: frozenset[str],
        tls_failures: list[Any],
    ) -> AttemptReport:
        logger.warning(
            "TLS errors detected; retrying diagnostics with allow_insecure_tls enabled",
            attempt="tls-fallback",
            original_errors=[summarize_failure(failure) for failure in tls_failures],
        )
        fallback_settings = replace(
            effective_settings,
            allow_insecure_tls=True,
            ca_bundle_path=None,
        )
        return self._run_diagnostic_attempt(
            context_name=context_name,
            settings=fallback_settings,
            context_logger=logger,
            expected_tools=expected_tools,
            label="tls-fallback",
            notes=(),
        )

    def _log_fallback_result(
        self, logger: BoundLogger, success: bool, tls_failures: list[Any]
    ) -> None:
        if success:
            logger.warning(
                "TLS fallback resolved diagnostics failure",
                attempt="tls-fallback",
                original_errors=[summarize_failure(failure) for failure in tls_failures],
            )
        else:
            logger.error(
                "TLS fallback failed to resolve diagnostics",
                attempt="tls-fallback",
                original_errors=[summarize_failure(failure) for failure in tls_failures],
            )

    def _run_diagnostic_attempt(
        self,
        *,
        context_name: str,
        settings: RuntimeSettings,
        context_logger: BoundLogger,
        expected_tools: frozenset[str],
        label: str,
        notes: Sequence[str | None],
    ) -> AttemptReport:
        attempt_notes = list(notes or ())
        context_logger.info(
            "Starting diagnostics attempt",
            attempt=label,
            allow_insecure_tls=settings.allow_insecure_tls,
            ca_bundle=settings.ca_bundle_path,
            notes=attempt_notes,
        )

        server_instance = prepare_server(
            settings,
            context_logger,
            v1_base_url=self._target_base_url,
        )

        discovered_tools = discover_context_tools(
            server_instance,
            run_sync=self._run_sync,
        )
        missing_tools = sorted(expected_tools - discovered_tools)
        failure_records: list[DiagnosticFailure] = []
        attempt_success = True
        online_success: bool | None = None
        skip_tool_checks = False

        if missing_tools:
            tool_report = self._handle_missing_tools(
                missing_tools,
                expected_tools,
                context_logger,
                label,
                failure_records,
            )
            attempt_success = False
        else:
            context_logger.info(
                "Tool discovery succeeded",
                tools=sorted(discovered_tools),
                attempt=label,
            )
            tool_report: dict[str, dict[str, Any]] = {}
            online_success, skip_tool_checks = self._run_online_diagnostics(
                settings,
                context_logger,
                attempt_notes,
                failure_records,
            )
            if not online_success:
                attempt_success = False

            if not skip_tool_checks and not run_context_tool_diagnostics(
                context=context_name,
                logger=context_logger,
                server_instance=server_instance,
                expected_tools=expected_tools,
                summary=tool_report,
                failures=failure_records,
                run_sync=self._run_sync,
            ):
                attempt_success = False

        attempt_report = AttemptReport(
            label=label,
            success=attempt_success,
            failures=failure_records,
            notes=attempt_notes,
            allow_insecure_tls=bool(settings.allow_insecure_tls),
            ca_bundle=str(settings.ca_bundle_path) if settings.ca_bundle_path else None,
            online_success=online_success,
            discovered_tools=sorted(discovered_tools),
            missing_tools=missing_tools,
            tools=tool_report,
        )

        log_method = context_logger.info if attempt_success else context_logger.warning
        log_method(
            "Diagnostics attempt completed",
            attempt=label,
            success=attempt_success,
            allow_insecure_tls=settings.allow_insecure_tls,
            ca_bundle=settings.ca_bundle_path,
            failure_count=len(failure_records),
            notes=attempt_notes,
            failures=[summarize_failure(failure) for failure in failure_records],
        )

        return attempt_report

    def _handle_missing_tools(
        self,
        missing_tools: list[str],
        expected_tools: frozenset[str],
        context_logger: BoundLogger,
        label: str,
        failure_records: list[DiagnosticFailure],
    ) -> dict[str, dict[str, Any]]:
        context_logger.critical(
            "Tool discovery failed",
            missing_tools=missing_tools,
            discovered=sorted(set(expected_tools) - set(missing_tools)),
            attempt=label,
        )
        for tool_name in missing_tools:
            record_failure(
                failure_records,
                tool=tool_name,
                stage="discovery",
                message=MSG_EXPECTED_TOOL_NOT_REGISTERED,
            )

        tool_report: dict[str, dict[str, Any]] = {}
        for tool_name in sorted(expected_tools):
            if tool_name in missing_tools:
                tool_report[tool_name] = {
                    "status": "fail",
                    "details": {"reason": MSG_TOOL_NOT_REGISTERED},
                }
            else:
                tool_report[tool_name] = {
                    "status": "warning",
                    "details": {"reason": "not evaluated"},
                }
        return tool_report

    def _run_online_diagnostics(
        self,
        settings: RuntimeSettings,
        context_logger: BoundLogger,
        attempt_notes: list[str | None],
        failure_records: list[DiagnosticFailure],
    ) -> tuple[bool | None, bool]:
        try:
            online_ok = run_online_checks(
                settings,
                context_logger,
                run_sync=self._run_sync,
                v1_base_url=self._target_base_url,
            )
        except BirreError as exc:
            self._alerts.add(exc.code)
            record_failure(
                failure_records,
                tool="startup_checks",
                stage="online",
                message="online startup checks failed",
                exception=exc,
            )
            context_logger.error(
                "Online startup checks failed",
                reason=exc.user_message,
                **exc.log_fields(),
            )
            attempt_notes.append(exc.context.code)
            return False, True
        else:
            if not online_ok:
                record_failure(
                    failure_records,
                    tool="startup_checks",
                    stage="online",
                    message="online startup checks failed",
                )
            return online_ok, False

    def _build_attempt_summaries(
        self, attempt_reports: list[AttemptReport]
    ) -> list[dict[str, Any]]:
        return [
            {
                "label": attempt.label,
                "success": attempt.success,
                "notes": attempt.notes,
                "allow_insecure_tls": attempt.allow_insecure_tls,
                "ca_bundle": attempt.ca_bundle,
                "online_success": attempt.online_success,
                "discovered_tools": attempt.discovered_tools,
                "missing_tools": attempt.missing_tools,
                "tools": attempt.tools,
                "failures": [summarize_failure(failure) for failure in attempt.failures],
            }
            for attempt in attempt_reports
        ]

    def _calculate_online_status(
        self, attempt_summaries: list[dict[str, Any]]
    ) -> dict[str, Any]:
        online_attempts: dict[str, str] = {}
        for attempt in attempt_summaries:
            result = attempt.get("online_success")
            if result is None:
                continue
            online_attempts[attempt["label"]] = "pass" if result else "fail"

        if any(status == "pass" for status in online_attempts.values()):
            online_status = "pass"
        elif any(status == "fail" for status in online_attempts.values()):
            online_status = "fail"
        else:
            online_status = "warning"

        online_summary: dict[str, Any] = {"status": online_status}
        if online_attempts:
            online_summary["attempts"] = online_attempts
        return online_summary

    def _update_failure_categories(
        self,
        attempt_report: AttemptReport,
        encountered_categories: set[str],
        failure_categories: set[str],
    ) -> None:
        for failure in attempt_report.failures:
            category = classify_failure(failure)
            if category:
                encountered_categories.add(category)
        failure_categories.update(
            failure.category
            for failure in attempt_report.failures
            if failure.category
        )

    def _categorize_failures(
        self,
        encountered_categories: set[str],
        failure_categories: set[str],
    ) -> tuple[list[str], list[str]]:
        recoverable = sorted(
            (failure_categories | encountered_categories) & {"tls", MSG_CONFIG_CA_BUNDLE}
        )
        unrecoverable = sorted(
            (failure_categories | encountered_categories) - {"tls", MSG_CONFIG_CA_BUNDLE}
        )
        return recoverable, unrecoverable

    def _log_context_result(
        self,
        logger: BoundLogger,
        context_success: bool,
        attempt_reports: list[AttemptReport],
        recoverable: list[str],
        unrecoverable: list[str],
    ) -> None:
        if not context_success:
            logger.error(
                "Context diagnostics failed",
                attempts=[
                    {"label": report.label, "success": report.success}
                    for report in attempt_reports
                ],
                recoverable_categories=recoverable or None,
                unrecoverable_categories=unrecoverable or None,
            )
        elif any(not report.success for report in attempt_reports):
            logger.info(
                "Context diagnostics completed with recoveries",
                attempts=[
                    {"label": report.label, "success": report.success}
                    for report in attempt_reports
                ],
            )
        else:
            logger.info(
                "Context diagnostics completed successfully",
                attempt="primary",
            )

    def _has_degraded_outcomes(
        self,
        report: Mapping[str, Any],
        attempts: Sequence[AttemptReport],
    ) -> bool:
        if report.get("offline_mode"):
            return True
        if report.get("notes"):
            return True
        if report.get("encountered_categories"):
            return True
        if report.get("recoverable_categories"):
            return True
        if report.get("fallback_attempted"):
            return True
        if any(not attempt.success for attempt in attempts):
            return True
        online_section = report.get("online")
        if isinstance(online_section, Mapping) and online_section.get("status") == "warning":
            return True
        tools_section = report.get("tools")
        if isinstance(tools_section, Mapping):
            for entry in tools_section.values():
                if not isinstance(entry, Mapping):
                    continue
                if entry.get("status") == "warning":
                    return True
                attempts_map = entry.get("attempts")
                if isinstance(attempts_map, Mapping) and any(
                    value == "warning" for value in attempts_map.values()
                ):
                    return True
        return False


# Backward compatibility aliases - remove after full migration
HealthcheckRunner = SelfTestRunner


__all__ = [
    "AttemptReport",
    "ContextDiagnosticsResult",
    "DiagnosticFailure",
    "SelfTestResult",
    "SelfTestRunner",
    "HealthcheckResult",  # Backward compatibility alias
    "HealthcheckRunner",  # Backward compatibility alias
    "CONTEXT_CHOICES",
    "EXPECTED_TOOLS_BY_CONTEXT",
    "MSG_CONFIG_CA_BUNDLE",
    "aggregate_tool_outcomes",
    "classify_failure",
    "collect_tool_map",
    "discover_context_tools",
    "prepare_server",
    "record_failure",
    "run_company_search_diagnostics",
    "run_company_search_interactive_diagnostics",
    "run_context_tool_diagnostics",
    "run_manage_subscriptions_diagnostics",
    "run_offline_checks",
    "run_online_checks",
    "run_rating_diagnostics",
    "run_request_company_diagnostics",
    "summarize_failure",
]
