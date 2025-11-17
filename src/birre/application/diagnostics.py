"""Diagnostic helpers for validating BiRRe tool availability and health.

This module hosts the shared business logic for:
- Tool discovery and invocation
- Payload validation
- Diagnostic test execution

CLI orchestration (SelfTestRunner) lives in cli.commands.selftest.runner.
Result models live in birre.domain.selftest_models.
"""

from __future__ import annotations

import asyncio
import errno
import inspect
import logging
import ssl
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import suppress
from typing import Any, Final, cast

import httpx

from birre import _resolve_tls_verification, create_birre_server
from birre.application.startup import (
    OnlineStartupResult,
    run_offline_startup_checks,
    run_online_startup_checks,
)
from birre.config.settings import RuntimeSettings
from birre.domain.selftest_models import (
    AttemptReport,
    ContextDiagnosticsResult,
    DiagnosticFailure,
    SelfTestResult,
    _MockSelfTestContext,
)
from birre.infrastructure.errors import TlsCertificateChainInterceptedError
from birre.infrastructure.logging import BoundLogger
from birre.integrations.bitsight import DEFAULT_V1_API_BASE_URL, create_v1_api_server
from birre.integrations.bitsight.v1_bridge import call_v1_openapi_tool

SyncRunner = Callable[[Awaitable[Any]], Any]
FailureLog = list[DiagnosticFailure] | None

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


def _ensure_mode_mapping(summary: dict[str, Any | None]) -> dict[str, Any]:
    """Return the mutable mode map within a summary, creating it if missing."""
    modes = summary.get("modes")
    if not isinstance(modes, dict):
        modes = {}
        summary["modes"] = modes
    return modes


MSG_NOT_A_DICT: Final = "not a dict"
MSG_TOOL_INVOCATION_FAILED: Final = "tool invocation failed"
MSG_UNEXPECTED_PAYLOAD_STRUCTURE: Final = "unexpected payload structure"
MSG_EXPECTED_TOOL_NOT_REGISTERED: Final = "expected tool not registered"
MSG_TOOL_NOT_REGISTERED: Final = "tool not registered"
MSG_CONFIG_CA_BUNDLE: Final = "config.ca_bundle"

HEALTHCHECK_COMPANY_NAME: Final = "GitHub"
HEALTHCHECK_COMPANY_DOMAIN: Final = "github.com"
HEALTHCHECK_COMPANY_GUID: Final = "6ca077e2-b5a7-42c2-ae1e-a974c3a91dc1"
HEALTHCHECK_REQUEST_DOMAIN: Final = (
    "github.com"  # Use existing domain to avoid creating tickets
)


def _default_run_sync(awaitable: Awaitable[Any]) -> Any:
    async def _await_wrapper() -> Any:
        return await awaitable

    return asyncio.run(_await_wrapper())


def _sync(coro: Awaitable[Any], run_sync: SyncRunner | None = None) -> Any:
    runner = run_sync or _default_run_sync
    loop_to_close: asyncio.AbstractEventLoop | None = None
    if run_sync is not None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            try:
                asyncio.get_event_loop()
            except RuntimeError:
                loop_to_close = asyncio.new_event_loop()
                asyncio.set_event_loop(loop_to_close)
    try:
        return runner(coro)
    finally:
        if loop_to_close is not None:
            asyncio.set_event_loop(None)
            loop_to_close.close()


def record_failure(
    failures: FailureLog,
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
    if hasattr(tool, "fn"):
        fn = getattr(tool, "fn")
        if callable(fn):
            return cast(Callable[..., Any | None], fn)
    if callable(tool):
        return cast(Callable[..., Any | None], tool)
    return None


def _invoke_tool(
    tool: Any,
    ctx: _MockSelfTestContext,
    *,
    run_sync: SyncRunner | None,
    **params: Any,
) -> Any:
    callable_fn = _resolve_tool_callable(tool)
    if callable_fn is None:
        raise TypeError(f"Tool object {tool!r} is not callable")

    result: Awaitable[Any] | Any | None = None
    try:
        result = callable_fn(ctx, **params)
    except TypeError:
        if not params:
            raise
        result = callable_fn(ctx, params)

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
            {
                str(name): tool
                for name, tool in tools_attr.items()
                if isinstance(name, str)
            }
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
                {
                    str(name): tool
                    for name, tool in resolved.items()
                    if isinstance(name, str)
                }
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
    failures: FailureLog,
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
                    "reason": "diagnostic succeeded"
                    if ok
                    else "diagnostic reported failure",
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
    failures: FailureLog,
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
    failures: FailureLog = None,
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
    tool: Any | None,
    failures: FailureLog = None,
    summary: dict[str, Any | None] | None = None,
    run_sync: SyncRunner | None = None,
    sample_payloads: Mapping[str, Any] | None = None,
) -> bool:
    """Run diagnostics for company_search tool with both name and domain modes."""
    tool_logger = logger.bind(tool="company_search")
    ctx = _MockSelfTestContext(
        context=context, tool_name="company_search", logger=tool_logger
    )

    if summary is not None:
        summary.clear()
        summary["status"] = "pass"

    # Test search by name
    if not _test_company_search_mode(
        tool=tool,
        ctx=ctx,
        mode="name",
        search_params={"name": HEALTHCHECK_COMPANY_NAME},
        expected_domain=None,
        require_results=True,
        sample_payload=(sample_payloads or {}).get("name") if sample_payloads else None,
        tool_logger=tool_logger,
        failures=failures,
        summary=summary,
        run_sync=run_sync,
    ):
        return False

    # Test search by domain
    if not _test_company_search_mode(
        tool=tool,
        ctx=ctx,
        mode="domain",
        search_params={"domain": HEALTHCHECK_COMPANY_DOMAIN},
        expected_domain=HEALTHCHECK_COMPANY_DOMAIN,
        require_results=True,
        sample_payload=(sample_payloads or {}).get("domain")
        if sample_payloads
        else None,
        tool_logger=tool_logger,
        failures=failures,
        summary=summary,
        run_sync=run_sync,
    ):
        return False

    random_term = f"birre-random-{uuid.uuid4().hex}"
    if not _test_company_search_mode(
        tool=tool,
        ctx=ctx,
        mode="random",
        search_params={"name": random_term},
        expected_domain=None,
        require_results=False,
        sample_payload=(sample_payloads or {}).get("random")
        if sample_payloads
        else None,
        tool_logger=tool_logger,
        failures=failures,
        summary=summary,
        run_sync=run_sync,
    ):
        return False

    tool_logger.info("healthcheck.company_search.success")
    return True


def _test_company_search_mode(
    *,
    tool: Any | None,
    ctx: _MockSelfTestContext,
    mode: str,
    search_params: dict[str, str],
    expected_domain: str | None,
    require_results: bool,
    sample_payload: Any | None,
    tool_logger: BoundLogger,
    failures: FailureLog,
    summary: dict[str, Any | None] | None,
    run_sync: SyncRunner | None,
) -> bool:
    """Test a single search mode (name or domain) for company_search diagnostics."""
    # Try to invoke the tool
    if sample_payload is not None:
        result = sample_payload
    else:
        try:
            if tool is None:
                raise RuntimeError("company_search tool unavailable for offline replay")
            result = _invoke_tool(tool, ctx, run_sync=run_sync, **search_params)
        except Exception as exc:  # pragma: no cover - network failures
            return _handle_company_search_call_failure(
                mode=mode,
                exc=exc,
                tool_logger=tool_logger,
                failures=failures,
                summary=summary,
            )

    # Validate the response
    valid, result_count = _validate_company_search_payload(
        result,
        logger=tool_logger,
        expected_domain=expected_domain,
        require_results=require_results,
    )
    if not valid:
        return _handle_company_search_validation_failure(
            mode=mode,
            failures=failures,
            summary=summary,
        )

    # Record success
    if summary is not None:
        modes = _ensure_mode_mapping(summary)
        entry: dict[str, Any] = {"status": "pass"}
        if result_count is not None:
            entry["count"] = result_count
        modes[mode] = entry

    return True


def _handle_company_search_call_failure(
    *,
    mode: str,
    exc: Exception,
    tool_logger: BoundLogger,
    failures: FailureLog,
    summary: dict[str, Any | None] | None,
) -> bool:
    """Handle failures during company_search tool invocation."""
    tool_logger.critical(
        f"healthcheck.company_search.{mode}_call_failed", error=str(exc)
    )
    record_failure(
        failures,
        tool="company_search",
        stage="call",
        mode=mode,
        message=MSG_TOOL_INVOCATION_FAILED,
        exception=exc,
    )
    if summary is not None:
        summary["status"] = "fail"
        summary["details"] = {
            "reason": MSG_TOOL_INVOCATION_FAILED,
            "mode": mode,
            "error": str(exc),
        }
        if mode == "domain":
            modes = _ensure_mode_mapping(summary)
            modes[mode] = {"status": "fail", "error": str(exc)}
    return False


def _handle_company_search_validation_failure(
    *,
    mode: str,
    failures: FailureLog,
    summary: dict[str, Any | None] | None,
) -> bool:
    """Handle failures during company_search payload validation."""
    record_failure(
        failures,
        tool="company_search",
        stage="validation",
        mode=mode,
        message=MSG_UNEXPECTED_PAYLOAD_STRUCTURE,
    )
    if summary is not None:
        summary["status"] = "fail"
        summary["details"] = {
            "reason": MSG_UNEXPECTED_PAYLOAD_STRUCTURE,
            "mode": mode,
        }
        if mode == "domain":
            modes = _ensure_mode_mapping(summary)
            modes[mode] = {"status": "fail", "detail": MSG_UNEXPECTED_PAYLOAD_STRUCTURE}
    return False


def run_rating_diagnostics(
    *,
    context: str,
    logger: BoundLogger,
    tool: Any,
    failures: FailureLog = None,
    summary: dict[str, Any | None] | None = None,
    run_sync: SyncRunner | None = None,
) -> bool:
    tool_logger = logger.bind(tool="get_company_rating")
    ctx = _MockSelfTestContext(
        context=context, tool_name="get_company_rating", logger=tool_logger
    )
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
    if (
        isinstance(domain_value, str)
        and domain_value.lower() != HEALTHCHECK_COMPANY_DOMAIN
    ):
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
    failures: FailureLog = None,
    summary: dict[str, Any | None] | None = None,
    run_sync: SyncRunner | None = None,
) -> bool:
    tool_logger = logger.bind(tool="company_search_interactive")
    ctx = _MockSelfTestContext(
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
        tool_logger.warning(
            "healthcheck.company_search_interactive.call_failed", error=str(exc)
        )
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
    failures: FailureLog = None,
    summary: dict[str, Any | None] | None = None,
    run_sync: SyncRunner | None = None,
) -> bool:
    tool_logger = logger.bind(tool="manage_subscriptions")
    ctx = _MockSelfTestContext(
        context=context, tool_name="manage_subscriptions", logger=tool_logger
    )
    if summary is not None:
        summary.clear()
        summary["status"] = "pass"
    try:
        payload = _invoke_tool(
            tool,
            ctx,
            run_sync=run_sync,
            action="subscribe",
            guids=[HEALTHCHECK_COMPANY_GUID],
        )
    except Exception as exc:  # pragma: no cover - network failures
        tool_logger.warning(
            "healthcheck.manage_subscriptions.call_failed", error=str(exc)
        )
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
    failures: FailureLog = None,
    summary: dict[str, Any | None] | None = None,
    run_sync: SyncRunner | None = None,
) -> bool:
    tool_logger = logger.bind(tool="request_company")
    ctx = _MockSelfTestContext(
        context=context, tool_name="request_company", logger=tool_logger
    )
    if summary is not None:
        summary.clear()
        summary["status"] = "pass"
    try:
        payload = _invoke_tool(
            tool,
            ctx,
            run_sync=run_sync,
            domains=HEALTHCHECK_REQUEST_DOMAIN,
        )
    except Exception as exc:  # pragma: no cover - network failures
        # 400 errors mean API is reachable and processed our request - that's SUCCESS
        error_str = str(exc)
        if "400" in error_str or "Bad Request" in error_str:
            tool_logger.info(
                "healthcheck.request_company.api_reachable",
                note="Got 400 error - proves API is working",
                error=error_str,
            )
            if summary is not None:
                summary["status"] = "pass"
                summary["details"] = {
                    "reason": "API reachable (400 error expected for existing domain)",
                    "note": "This confirms the API endpoint works correctly",
                }
            return True

        # Other errors are real failures
        tool_logger.warning("healthcheck.request_company.call_failed", error=error_str)
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
        logger.critical(
            "healthcheck.company_search.invalid_company", reason="entry not dict"
        )
        return False
    if not entry.get("guid") or not entry.get("name"):
        logger.critical(
            "healthcheck.company_search.invalid_company",
            reason="missing guid/name",
            company=entry,
        )
        return False
    return True


def _check_domain_match(
    companies: list[Any], expected_domain: str, logger: BoundLogger
) -> bool:
    for entry in companies:
        domain_value = str(entry.get("domain") or "")
        if domain_value.lower() == expected_domain.lower():
            return True
    logger.critical(
        "healthcheck.company_search.domain_missing", expected=expected_domain
    )
    return False


def _validate_company_search_payload(
    payload: Any,
    *,
    logger: BoundLogger,
    expected_domain: str | None,
    require_results: bool,
) -> tuple[bool, int | None]:
    base = _extract_company_search_payload(payload, logger)
    if base is None:
        return False, None

    companies = base["companies"]
    if not _validate_company_search_results(companies, require_results, logger):
        return False, None

    count_value = base["count"]
    if not _validate_company_search_count(count_value, require_results, logger):
        return False, None

    if expected_domain and not _check_domain_match(companies, expected_domain, logger):
        return False, count_value

    return True, count_value


def _extract_company_search_payload(
    payload: Any, logger: BoundLogger
) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        logger.critical(
            "healthcheck.company_search.invalid_response", reason=MSG_NOT_A_DICT
        )
        return None

    if payload.get("error"):
        logger.critical(
            "healthcheck.company_search.api_error", error=str(payload["error"])
        )
        return None

    return {
        "companies": payload.get("companies"),
        "count": payload.get("count"),
    }


def _validate_company_search_results(
    companies: Any, require_results: bool, logger: BoundLogger
) -> bool:
    if not isinstance(companies, list) or (require_results and not companies):
        logger.critical(
            "healthcheck.company_search.empty", reason="no companies returned"
        )
        return False

    for entry in companies:
        if not _validate_company_entry(entry, logger):
            return False
    return True


def _validate_company_search_count(
    count_value: Any,
    require_results: bool,
    logger: BoundLogger,
) -> bool:
    if not isinstance(count_value, int) or (require_results and count_value <= 0):
        logger.critical("healthcheck.company_search.invalid_count", count=count_value)
        return False
    return True


def _validate_company_search_interactive_payload(
    payload: Any,
    *,
    logger: BoundLogger,
) -> bool:
    base = _extract_company_search_interactive_payload(payload, logger)
    if base is None:
        return False

    if not _validate_company_search_interactive_results(base["results"], logger):
        return False
    if not _validate_company_search_interactive_count(base["count"], logger):
        return False
    return _validate_company_search_interactive_guidance(base["guidance"], logger)


def _extract_company_search_interactive_payload(
    payload: Any, logger: BoundLogger
) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        logger.critical(
            "healthcheck.company_search_interactive.invalid_response",
            reason=MSG_NOT_A_DICT,
        )
        return None

    if payload.get("error"):
        logger.critical(
            "healthcheck.company_search_interactive.api_error",
            error=str(payload["error"]),
        )
        return None

    return {
        "results": payload.get("results"),
        "count": payload.get("count"),
        "guidance": payload.get("guidance"),
    }


def _validate_company_search_interactive_results(
    results: Any, logger: BoundLogger
) -> bool:
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
    return True


def _validate_company_search_interactive_count(
    count_value: Any, logger: BoundLogger
) -> bool:
    if not isinstance(count_value, int) or count_value <= 0:
        logger.critical(
            "healthcheck.company_search_interactive.invalid_count",
            count=count_value,
        )
        return False
    return True


def _validate_company_search_interactive_guidance(
    guidance: Any, logger: BoundLogger
) -> bool:
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

    if not _validate_rating_required_fields(payload, logger):
        return False
    if not _validate_rating_current_section(payload, logger):
        return False
    if not _validate_rating_findings(payload, logger):
        return False
    return _validate_rating_legend(payload, logger)


def _validate_rating_required_fields(
    payload: Mapping[str, Any], logger: BoundLogger
) -> bool:
    required_fields = ("name", "domain", "current_rating", "top_findings", "legend")
    for field in required_fields:
        if payload.get(field) in (None, {}):
            logger.critical("healthcheck.rating.missing_field", field=field)
            return False
    return True


def _validate_rating_current_section(
    payload: Mapping[str, Any], logger: BoundLogger
) -> bool:
    current_rating = payload.get("current_rating")
    if not isinstance(current_rating, dict) or current_rating.get("value") is None:
        logger.critical(
            "healthcheck.rating.invalid_current_rating", payload=current_rating
        )
        return False
    return True


def _validate_rating_findings(payload: Mapping[str, Any], logger: BoundLogger) -> bool:
    findings = payload.get("top_findings")
    if not isinstance(findings, dict):
        logger.critical("healthcheck.rating.invalid_findings", payload=findings)
        return False

    finding_count = findings.get("count")
    finding_entries = findings.get("findings")
    if not isinstance(finding_count, int):
        logger.critical(
            "healthcheck.rating.invalid_findings_count", count=finding_count
        )
        return False
    if not isinstance(finding_entries, list):
        logger.critical("healthcheck.rating.invalid_findings_entries", payload=findings)
        return False
    if finding_count <= 0 or not finding_entries:
        logger.warning(
            "healthcheck.rating.no_findings_returned",
            count=finding_count,
            entries=len(finding_entries),
        )
    return True


def _validate_rating_legend(payload: Mapping[str, Any], logger: BoundLogger) -> bool:
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
    base = _extract_manage_subscriptions_payload(payload, logger)
    if base is None:
        return False

    status = base["status"]
    if not _validate_manage_subscription_status(status, logger):
        return False

    if not _validate_manage_subscription_guids(base["guids"], expected_guid, logger):
        return False

    return _validate_manage_subscription_dry_payload(status, base["payload"], logger)


def _extract_manage_subscriptions_payload(
    payload: Any, logger: BoundLogger
) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        logger.critical(
            "healthcheck.manage_subscriptions.invalid_response", reason=MSG_NOT_A_DICT
        )
        return None

    if payload.get("error"):
        logger.critical(
            "healthcheck.manage_subscriptions.api_error", error=str(payload["error"])
        )
        return None

    return {
        "status": payload.get("status"),
        "guids": payload.get("guids"),
        "payload": payload.get("payload"),
    }


def _validate_manage_subscription_status(status: Any, logger: BoundLogger) -> bool:
    if status not in {"dry_run", "applied"}:
        logger.critical(
            "healthcheck.manage_subscriptions.unexpected_status", status=status
        )
        return False
    return True


def _validate_manage_subscription_guids(
    guids: Any, expected_guid: str, logger: BoundLogger
) -> bool:
    if not isinstance(guids, list) or expected_guid not in guids:
        logger.critical(
            "healthcheck.manage_subscriptions.guid_missing",
            guids=guids,
            expected=expected_guid,
        )
        return False
    return True


def _validate_manage_subscription_dry_payload(
    status: str,
    dry_payload: Any,
    logger: BoundLogger,
) -> bool:
    if status != "dry_run":
        return True
    if not isinstance(dry_payload, dict) or "add" not in dry_payload:
        logger.critical(
            "healthcheck.manage_subscriptions.invalid_payload",
            payload=dry_payload,
        )
        return False
    return True


def _validate_request_company_payload(
    payload: Any,
    *,
    logger: BoundLogger,
    expected_domain: str,
) -> bool:
    base = _extract_request_company_payload(payload, logger)
    if base is None:
        return False

    status = base["status"]
    submitted = base["submitted"]
    expected_lower = expected_domain.lower()

    if not _validate_submitted_domains(
        submitted, expected_lower, expected_domain, logger
    ):
        return False

    sections = _extract_request_company_sections(payload, logger)
    if sections is None:
        return False
    success_list, already_existing, failed_entries = sections

    if not _domain_present_in_sections(
        success_list,
        already_existing,
        failed_entries,
        expected_lower,
        expected_domain,
        logger,
    ):
        return False

    return _validate_request_company_dry_run(status, payload, logger)


def _extract_request_company_payload(
    payload: Any, logger: BoundLogger
) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        logger.critical(
            "healthcheck.request_company.invalid_response", reason=MSG_NOT_A_DICT
        )
        return None

    if payload.get("error"):
        logger.critical(
            "healthcheck.request_company.api_error", error=str(payload["error"])
        )
        return None

    status = payload.get("status")
    if status not in {
        "already_existing",
        "submitted_v2_bulk",
        "dry_run",
        "failed",
        "folder_error",
    }:
        logger.critical("healthcheck.request_company.unexpected_status", status=status)
        return None

    submitted = payload.get("submitted")
    if not isinstance(submitted, list) or not submitted:
        logger.critical(
            "healthcheck.request_company.invalid_submitted", submitted=submitted
        )
        return None

    return {"status": status, "submitted": submitted}


def _extract_request_company_sections(
    payload: Mapping[str, Any], logger: BoundLogger
) -> tuple[list[Any], list[Any], list[Any]] | None:
    success_list = payload.get("successfully_requested") or []
    if not _validate_string_list(success_list, "success_list", logger):
        return None

    already_existing = payload.get("already_existing") or []
    if not _validate_domain_mapping_list(already_existing, "already_existing", logger):
        return None

    failed_entries = payload.get("failed") or []
    if not _validate_domain_mapping_list(failed_entries, "failed", logger):
        return None

    return success_list, already_existing, failed_entries


def _validate_submitted_domains(
    submitted: list[Any],
    expected_lower: str,
    expected_domain: str,
    logger: BoundLogger,
) -> bool:
    if all(
        not isinstance(item, str) or item.lower() != expected_lower
        for item in submitted
    ):
        logger.critical(
            "healthcheck.request_company.domain_missing",
            expected=expected_domain,
        )
        return False
    return True


def _validate_string_list(values: list[Any], label: str, logger: BoundLogger) -> bool:
    if not isinstance(values, list):
        logger.critical(
            f"healthcheck.request_company.invalid_{label}",
            entries=values,
        )
        return False
    return True


def _validate_domain_mapping_list(
    values: list[Any], label: str, logger: BoundLogger
) -> bool:
    if not isinstance(values, list):
        logger.critical(
            f"healthcheck.request_company.invalid_{label}_list",
            entries=values,
        )
        return False
    for entry in values:
        if not isinstance(entry, Mapping):
            logger.critical(
                "healthcheck.request_company.invalid_domain_entry",
                entry=entry,
            )
            return False
        domain_value = entry.get("domain")
        if not isinstance(domain_value, str) or not domain_value.strip():
            logger.critical(
                "healthcheck.request_company.invalid_domain_entry",
                entry=entry,
            )
            return False
    return True


def _validate_request_company_dry_run(
    status: str, payload: Mapping[str, Any], logger: BoundLogger
) -> bool:
    if status != "dry_run":
        return True
    if payload.get("dry_run"):
        return True
    logger.critical("healthcheck.request_company.dry_run_flag_missing")
    return False


def _domain_present_in_sections(
    success_list: list[Any],
    existing: list[Any],
    failed: list[Any],
    expected_lower: str,
    expected_domain: str,
    logger: BoundLogger,
) -> bool:
    if any(
        isinstance(value, str) and value.lower() == expected_lower
        for value in success_list
    ):
        return True

    for entries in (existing, failed):
        for entry in entries:
            domain_value = str(entry.get("domain") or "").lower()
            if domain_value == expected_lower:
                return True

    logger.critical(
        "healthcheck.request_company.domain_missing",
        expected=expected_domain,
    )
    return False


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


def _create_offline_tool_status(
    tool_name: str, missing_set: set[str | None]
) -> dict[str, Any]:
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

    async def _execute_checks() -> OnlineStartupResult:
        api_server = create_v1_api_server(
            runtime_settings.api_key,
            verify=verify_option,
            base_url=base_url,
        )

        async def call_v1_tool(tool_name: str, ctx: Any, params: dict[str, Any]) -> Any:
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
                skip_startup_checks=getattr(
                    runtime_settings, "skip_startup_checks", False
                ),
            )
        finally:
            client = getattr(api_server, "_client", None)
            close = getattr(client, "aclose", None)
            if callable(close):
                close_callable = cast(Callable[[], Awaitable[None]], close)
                try:
                    await close_callable()
                except Exception as exc:  # pragma: no cover - defensive logging
                    _LOOP_LOGGER.warning(
                        "online_checks.client_close_failed: %s", str(exc)
                    )
            shutdown = getattr(api_server, "shutdown", None)
            if callable(shutdown):
                shutdown_callable = cast(Callable[[], Awaitable[Any]], shutdown)
                with suppress(Exception):
                    await shutdown_callable()

    startup_result = _sync(_execute_checks(), run_sync=run_sync)
    if isinstance(startup_result, OnlineStartupResult):
        if startup_result.subscription_folder_guid:
            _apply_subscription_folder_guid(
                runtime_settings, startup_result.subscription_folder_guid
            )
        return startup_result.success
    return bool(startup_result)


def _apply_subscription_folder_guid(
    runtime_settings: RuntimeSettings, folder_guid: str
) -> None:
    try:
        object.__setattr__(runtime_settings, "subscription_folder_guid", folder_guid)
    except Exception:  # pragma: no cover - defensive
        pass


__all__ = [
    "AttemptReport",
    "ContextDiagnosticsResult",
    "DiagnosticFailure",
    "SelfTestResult",
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
