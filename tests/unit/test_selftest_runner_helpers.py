from __future__ import annotations

from birre.cli.commands.selftest import runner as selftest_runner
from birre.config.settings import DEFAULT_MAX_FINDINGS, RuntimeSettings
from birre.domain.selftest_models import AttemptReport, DiagnosticFailure
from birre.infrastructure.logging import get_logger


def _make_runtime_settings(**overrides: object) -> RuntimeSettings:
    base = {
        "api_key": "",
        "subscription_folder": None,
        "subscription_type": None,
        "context": "standard",
        "risk_vector_filter": None,
        "max_findings": DEFAULT_MAX_FINDINGS,
        "skip_startup_checks": False,
        "debug": False,
        "allow_insecure_tls": False,
        "ca_bundle_path": None,
        "subscription_folder_guid": None,
        "warnings": (),
        "overrides": (),
    }
    base.update(overrides)
    return RuntimeSettings(**base)


def _make_runner() -> selftest_runner.SelfTestRunner:
    return selftest_runner.SelfTestRunner(
        runtime_settings=_make_runtime_settings(),
        logger=get_logger("test.selftest"),
        offline=False,
        environment_label="test-env",
        run_sync=lambda coro: coro,  # no-op runner for helper invocations
    )


def test_attempt_summaries_and_online_status() -> None:
    runner = _make_runner()
    attempt_reports = [
        AttemptReport(
            label="primary",
            success=True,
            failures=[],
            notes=["note"],
            allow_insecure_tls=False,
            ca_bundle=None,
            online_success=True,
            discovered_tools=["company_search"],
            missing_tools=[],
            tools={},
        ),
        AttemptReport(
            label="tls-fallback",
            success=False,
            failures=[],
            notes=[],
            allow_insecure_tls=True,
            ca_bundle=None,
            online_success=False,
            discovered_tools=["company_search"],
            missing_tools=[],
            tools={"company_search": {"status": "warning"}},
        ),
    ]
    summaries = runner._build_attempt_summaries(attempt_reports)
    assert summaries[0]["label"] == "primary"
    assert summaries[1]["allow_insecure_tls"] is True
    online_status = runner._calculate_online_status(summaries)
    assert online_status["status"] == "pass"
    assert online_status["attempts"]["primary"] == "pass"


def test_update_and_categorize_failure_sets() -> None:
    runner = _make_runner()
    failures = [
        DiagnosticFailure(tool="t", stage="s", message="TLS handshake error"),
        DiagnosticFailure(tool="t", stage="s", message="config ca missing"),
    ]
    encountered: set[str] = set()
    failure_categories: set[str] = set()
    report = AttemptReport(
        label="primary",
        success=False,
        failures=failures,
        notes=[],
        allow_insecure_tls=False,
        ca_bundle=None,
        online_success=False,
        discovered_tools=[],
        missing_tools=[],
        tools={},
    )
    runner._update_failure_categories(report, encountered, failure_categories)
    recoverable, unrecoverable = runner._categorize_failures(
        encountered, failure_categories
    )
    assert "tls" in recoverable
    assert unrecoverable == []


def test_warning_detection_helpers() -> None:
    runner = _make_runner()
    attempts = [
        AttemptReport(
            label="primary",
            success=False,
            failures=[],
            notes=[],
            allow_insecure_tls=False,
            ca_bundle=None,
            online_success=False,
            discovered_tools=[],
            missing_tools=[],
            tools={},
        )
    ]
    assert runner._has_tool_warnings({"tools": {"tool": {"status": "warning"}}})
    assert runner._tool_has_warning({"status": "warning"})
    assert not runner._tool_has_warning({"status": "pass"})
    assert runner._has_online_warnings({"online": {"status": "warning"}})
    assert not runner._has_online_warnings({"online": {"status": "pass"}})
    assert runner._has_failed_attempts(attempts)


def test_degraded_outcome_flags() -> None:
    runner = _make_runner()
    report = {
        "offline_mode": False,
        "notes": ["tls-cert"],
        "encountered_categories": ["tls"],
        "recoverable_categories": ["tls"],
        "fallback_attempted": True,
        "online": {"status": "warning"},
        "tools": {"company_search": {"status": "warning"}},
    }
    attempts = [
        AttemptReport(
            label="primary",
            success=False,
            failures=[],
            notes=[],
            allow_insecure_tls=False,
            ca_bundle=None,
            online_success=False,
            discovered_tools=[],
            missing_tools=[],
            tools={},
        )
    ]
    assert runner._has_degraded_outcomes(report, attempts) is True
    assert runner._has_degraded_mode_flags(report) is True
