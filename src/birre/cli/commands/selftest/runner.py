"""Self-test runner - CLI orchestration for BiRRe diagnostics.

This module contains the SelfTestRunner class that orchestrates the execution
of BiRRe self-tests. It's part of the CLI layer and uses diagnostic functions
from the application layer.

Business logic for individual diagnostic checks lives in application.diagnostics.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from birre.application.diagnostics import (
    EXPECTED_TOOLS_BY_CONTEXT,
    MSG_CONFIG_CA_BUNDLE,
    MSG_EXPECTED_TOOL_NOT_REGISTERED,
    MSG_TOOL_NOT_REGISTERED,
    _default_run_sync,
    aggregate_tool_outcomes,
    classify_failure,
    discover_context_tools,
    prepare_server,
    record_failure,
    run_company_search_diagnostics,
    run_context_tool_diagnostics,
    run_offline_checks,
    run_online_checks,
    summarize_failure,
)
from birre.application.offline_samples import COMPANY_SEARCH_SAMPLE_PAYLOADS
from birre.config.settings import RuntimeSettings
from birre.domain.company_search.service import normalize_company_search_results
from birre.domain.selftest_models import (
    AttemptReport,
    ContextDiagnosticsResult,
    DiagnosticFailure,
    SelfTestResult,
)
from birre.infrastructure.errors import BirreError
from birre.infrastructure.logging import BoundLogger
from birre.integrations.bitsight import DEFAULT_V1_API_BASE_URL

SyncRunner = Callable[[Awaitable[Any]], Any]


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

    def run(self) -> SelfTestResult:
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
            return SelfTestResult(
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

        return SelfTestResult(
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

        context_settings: RuntimeSettings = replace(
            self._base_runtime_settings, context=context_name
        )
        effective_settings, notes, degraded = self._resolve_ca_bundle(
            logger, context_settings
        )
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

        self._apply_offline_company_search_report(
            context_name=context_name,
            report=report,
            logger=logger,
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
                original_errors=[
                    summarize_failure(failure) for failure in tls_failures
                ],
            )
        else:
            logger.error(
                "TLS fallback failed to resolve diagnostics",
                attempt="tls-fallback",
                original_errors=[
                    summarize_failure(failure) for failure in tls_failures
                ],
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

        tool_report: dict[str, dict[str, Any]]
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
            tool_report = {}
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
            notes=[n for n in attempt_notes if n is not None],  # Filter None values
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

    def _apply_offline_company_search_report(
        self,
        *,
        context_name: str,
        report: dict[str, Any],
        logger: BoundLogger,
    ) -> None:
        tool_summary = report.setdefault("tools", {})
        summary_payload: dict[str, Any] = {}
        offline_failures: list[DiagnosticFailure] = []
        normalized_samples = {
            mode: normalize_company_search_results(raw_payload)
            for mode, raw_payload in COMPANY_SEARCH_SAMPLE_PAYLOADS.items()
        }
        success = run_company_search_diagnostics(
            context=context_name,
            logger=logger,
            tool=None,
            failures=offline_failures,
            summary=summary_payload,
            run_sync=self._run_sync,
            sample_payloads=normalized_samples,
        )
        tool_summary["company_search"] = {
            "status": "pass" if success else "warning",
            "details": {"reason": "offline replay"},
            "modes": summary_payload.get("modes"),
        }

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
                "failures": [
                    summarize_failure(failure) for failure in attempt.failures
                ],
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
            failure.category for failure in attempt_report.failures if failure.category
        )

    def _categorize_failures(
        self,
        encountered_categories: set[str],
        failure_categories: set[str],
    ) -> tuple[list[str], list[str]]:
        recoverable = sorted(
            (failure_categories | encountered_categories)
            & {"tls", MSG_CONFIG_CA_BUNDLE}
        )
        unrecoverable = sorted(
            (failure_categories | encountered_categories)
            - {"tls", MSG_CONFIG_CA_BUNDLE}
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
        """Check if selftest report contains degraded outcomes or warnings."""
        return (
            self._has_degraded_mode_flags(report)
            or self._has_failed_attempts(attempts)
            or self._has_online_warnings(report)
            or self._has_tool_warnings(report)
        )

    def _has_degraded_mode_flags(self, report: Mapping[str, Any]) -> bool:
        """Check for degraded mode flags in report."""
        degraded_flags = (
            "offline_mode",
            "notes",
            "encountered_categories",
            "recoverable_categories",
            "fallback_attempted",
        )
        return any(report.get(flag) for flag in degraded_flags)

    def _has_failed_attempts(self, attempts: Sequence[AttemptReport]) -> bool:
        """Check if any attempts failed."""
        return any(not attempt.success for attempt in attempts)

    def _has_online_warnings(self, report: Mapping[str, Any]) -> bool:
        """Check for warnings in online section."""
        online_section = report.get("online")
        if not isinstance(online_section, Mapping):
            return False
        return online_section.get("status") == "warning"

    def _has_tool_warnings(self, report: Mapping[str, Any]) -> bool:
        """Check for warnings in tools section."""
        tools_section = report.get("tools")
        if not isinstance(tools_section, Mapping):
            return False
        return any(self._tool_has_warning(entry) for entry in tools_section.values())

    def _tool_has_warning(self, entry: Any) -> bool:
        """Check if a tool entry has warnings."""
        if not isinstance(entry, Mapping):
            return False
        if entry.get("status") == "warning":
            return True
        attempts_map = entry.get("attempts")
        if not isinstance(attempts_map, Mapping):
            return False
        return any(value == "warning" for value in attempts_map.values())


__all__ = ["SelfTestRunner"]
