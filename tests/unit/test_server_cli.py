import asyncio
import logging
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

import ssl
import pytest
from typer.testing import CliRunner

import server
from src.settings import LoggingSettings, RuntimeSettings


def _runtime_settings() -> RuntimeSettings:
    return RuntimeSettings(
        api_key="test-key",
        subscription_folder="API",
        subscription_type="continuous_monitoring",
        risk_vector_filter="botnet_infections",
        max_findings=5,
        context="standard",
        skip_startup_checks=False,
        debug=False,
        allow_insecure_tls=False,
        ca_bundle_path=None,
        warnings=("reminder",),
    )


def _logging_settings() -> LoggingSettings:
    return LoggingSettings(
        level=logging.INFO,
        format="text",
        file_path=None,
        max_bytes=1024,
        backup_count=1,
    )


def _build_invocation(**overrides):
    defaults = {
        "config_path": "config.toml",
        "api_key": None,
        "subscription_folder": None,
        "subscription_type": None,
        "context": None,
        "debug": None,
        "risk_vector_filter": None,
        "max_findings": None,
        "skip_startup_checks": None,
        "allow_insecure_tls": None,
        "ca_bundle": None,
        "log_level": None,
        "log_format": None,
        "log_file": None,
        "log_max_bytes": None,
        "log_backup_count": None,
        "profile_path": None,
    }
    defaults.update(overrides)
    return server._build_invocation(**defaults)


def test_main_exits_when_offline_checks_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_settings = _runtime_settings()
    logging_settings = _logging_settings()

    root_logger = MagicMock(name="root_logger")

    monkeypatch.setattr(sys, "argv", ["server.py"])

    with (
        patch("server.load_settings", return_value=object()) as load_mock,
        patch("server.apply_cli_overrides") as apply_mock,
        patch("server.runtime_from_settings", return_value=runtime_settings),
        patch("server.logging_from_settings", return_value=logging_settings),
        patch("server.configure_logging"),
        patch("server.get_logger", return_value=root_logger),
        patch("server.run_offline_startup_checks", return_value=False) as offline_mock,
        patch("server.run_online_startup_checks") as online_mock,
        patch("server.create_birre_server") as create_server,
        patch("server.asyncio.run") as asyncio_run,
    ):
        with pytest.raises(SystemExit) as excinfo:
            server.main()

    assert excinfo.value.code == 1
    load_mock.assert_called_once()
    apply_mock.assert_called_once()
    offline_mock.assert_called_once()
    assert offline_mock.call_args.kwargs["logger"] is root_logger
    online_mock.assert_not_called()
    create_server.assert_not_called()
    asyncio_run.assert_not_called()


def test_main_runs_server_when_checks_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_settings = _runtime_settings()
    logging_settings = _logging_settings()

    root_logger = MagicMock(name="root_logger")

    fake_server = SimpleNamespace(run=MagicMock(name="run"))

    monkeypatch.setattr(sys, "argv", ["server.py"])

    async_online = AsyncMock(return_value=True)

    with (
        patch("server.load_settings", return_value=object()) as load_mock,
        patch("server.apply_cli_overrides") as apply_mock,
        patch("server.runtime_from_settings", return_value=runtime_settings),
        patch("server.logging_from_settings", return_value=logging_settings),
        patch("server.configure_logging"),
        patch("server.get_logger", return_value=root_logger),
        patch("server.run_offline_startup_checks", return_value=True) as offline_mock,
        patch("server.run_online_startup_checks", async_online) as online_mock,
        patch("server.create_birre_server", return_value=fake_server) as create_server,
        patch("server.asyncio.run", wraps=asyncio.run) as asyncio_run,
    ):
        with pytest.raises(SystemExit) as excinfo:
            server.main()

    assert excinfo.value.code == 0

    load_mock.assert_called_once()
    apply_mock.assert_called_once()
    offline_mock.assert_called_once()
    assert offline_mock.call_args.kwargs["logger"] is root_logger

    assert online_mock.await_count == 1
    await_args = online_mock.await_args
    assert await_args is not None
    kwargs = await_args.kwargs
    assert kwargs["logger"] is root_logger

    create_server.assert_called_once()
    create_kwargs = create_server.call_args.kwargs
    assert create_kwargs["settings"] == runtime_settings
    assert create_kwargs["logger"] is root_logger

    asyncio_run.assert_called_once()

    fake_server.run.assert_called_once()


def test_build_invocation_strips_log_file() -> None:
    invocation = _build_invocation(log_file="  custom.log  ")

    assert invocation.logging.file_path == "custom.log"


def test_logging_inputs_returns_none_when_no_overrides() -> None:
    invocation = _build_invocation()

    assert server._logging_inputs(invocation.logging) is None


def test_logging_inputs_disables_file_logging_via_sentinel() -> None:
    invocation = _build_invocation(log_file=" none ")

    logging_inputs = server._logging_inputs(invocation.logging)
    assert logging_inputs is not None
    assert logging_inputs.file_path == ""


def test_check_conf_masks_api_key_and_labels_env() -> None:
    runner = CliRunner()
    result = runner.invoke(
        server.app,
        ["check-conf"],
        env={"BITSIGHT_API_KEY": "supersecretvalue"},
        color=False,
    )

    assert result.exit_code == 0
    rows = [line for line in result.stdout.splitlines() if "bitsight.api_key" in line]
    assert rows, result.stdout
    row = rows[0]
    assert "supersecretvalue" not in row
    assert row.count("*") >= 4
    assert "ENV" in row


def test_check_conf_reports_sources_for_cli_and_defaults() -> None:
    runner = CliRunner()
    result = runner.invoke(
        server.app,
        ["check-conf", "--log-level", "DEBUG"],
        env={"BITSIGHT_API_KEY": "maskedkey"},
        color=False,
    )

    assert result.exit_code == 0, result.stdout
    lines = result.stdout.splitlines()

    level_rows = [line for line in lines if "logging.level" in line]
    assert level_rows, result.stdout
    level_row = level_rows[0]
    assert "CLI" in level_row
    assert "DEBUG" in level_row

    tls_rows = [line for line in lines if "runtime.allow_insecure_tls" in line]
    assert tls_rows, result.stdout
    tls_row = tls_rows[0]
    assert "Default" in tls_row
    assert "false" in tls_row.lower()

    context_rows = [line for line in lines if "roles.context" in line]
    assert context_rows, result.stdout
    assert "Config File" in context_rows[0]


def test_local_conf_create_generates_preview_and_file(tmp_path: Path) -> None:
    runner = CliRunner()
    output_path = tmp_path / "config.local.toml"
    input_data = "\n".join(
        [
            "supersecretvalue",
            "subscriptions",
            "continuous_monitoring",
            "standard",
            "n",
        ]
    ) + "\n"

    result = runner.invoke(
        server.app,
        ["local-conf-create", "--output", str(output_path)],
        input=input_data,
        color=False,
    )

    assert result.exit_code == 0, result.stdout
    stdout = result.stdout
    assert "Local configuration preview" in stdout
    assert "bitsight.api_key" in stdout
    assert "supersecretvalue" not in stdout
    assert output_path.exists()
    file_content = output_path.read_text(encoding="utf-8")
    assert "bitsight" in file_content
    assert "api_key" in file_content


def test_local_conf_create_reprompts_for_required_api_key(tmp_path: Path) -> None:
    runner = CliRunner()
    output_path = tmp_path / "config.local.toml"
    input_data = "\n".join([
        "",
        "final-secret",
        "",
        "",
        "",
        "n",
    ]) + "\n"

    result = runner.invoke(
        server.app,
        ["local-conf-create", "--output", str(output_path)],
        input=input_data,
        color=False,
    )

    assert result.exit_code == 0, result.stdout
    assert "A value is required" in result.stdout
    assert output_path.exists()
    file_content = output_path.read_text(encoding="utf-8")
    assert "final-secret" in file_content


def test_local_conf_create_respects_cli_overrides(tmp_path: Path) -> None:
    runner = CliRunner()
    output_path = tmp_path / "config.local.toml"
    input_data = "\n".join(
        [
            "anothersecret",
            "client-subscriptions",
            "risk_manager",
        ]
    ) + "\n"

    result = runner.invoke(
        server.app,
        [
            "local-conf-create",
            "--output",
            str(output_path),
            "--subscription-type",
            "vendor_monitoring",
            "--debug",
        ],
        input=input_data,
        color=False,
    )

    assert result.exit_code == 0, result.stdout
    stdout = result.stdout
    assert "Default subscription type" not in stdout
    assert "vendor_monitoring" in stdout
    assert "CLI Option" in stdout


def test_local_conf_create_requires_confirmation_to_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    output_path = tmp_path / "config.local.toml"
    output_path.write_text("existing", encoding="utf-8")

    result = runner.invoke(
        server.app,
        ["local-conf-create", "--output", str(output_path)],
        input="n\n",
        color=False,
    )

    assert result.exit_code == 1
    assert "Aborted" in result.stdout
    assert output_path.read_text(encoding="utf-8") == "existing"


def test_healthcheck_defaults_to_online_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    observed_offline: List[bool] = []
    prepared_contexts: List[Tuple[str, str]] = []
    online_calls: List[Tuple[str, bool]] = []
    diagnostic_calls: List[str] = []

    def fake_initialize(runtime_settings, logging_settings, *, show_banner: bool = False):
        return MagicMock(name="logger")

    def fake_offline(runtime_settings, logger):
        observed_offline.append(runtime_settings.skip_startup_checks)
        return True

    expected_tools_by_context = {
        context: server._EXPECTED_TOOLS_BY_CONTEXT[context]
        for context in server._CONTEXT_CHOICES
    }

    def fake_prepare(runtime_settings, logger, **kwargs):
        prepared_contexts.append((runtime_settings.context, kwargs.get("v1_base_url")))
        names = list(expected_tools_by_context[runtime_settings.context])

        def get_tools():
            return {name: object() for name in names}

        return SimpleNamespace(
            tools={name: object() for name in names},
            get_tools=get_tools,
            call_v1_tool=object(),
        )

    def fake_online(runtime_settings, logger, server_instance):
        online_calls.append((runtime_settings.context, runtime_settings.skip_startup_checks))
        return True

    def fake_diagnostics(*, context, logger, server_instance, failures=None):
        diagnostic_calls.append(context)
        return True

    with (
        patch("server._initialize_logging", side_effect=fake_initialize),
        patch("server._run_offline_checks", side_effect=fake_offline),
        patch("server._prepare_server", side_effect=fake_prepare),
        patch("server._run_online_checks", side_effect=fake_online),
        patch("server._run_context_tool_diagnostics", side_effect=fake_diagnostics),
    ):
        result = runner.invoke(
            server.app,
            ["healthcheck"],
            env={
                "BIRRE_SKIP_STARTUP_CHECKS": "true",
                "BITSIGHT_API_KEY": "dummy",
            },
            color=False,
        )

    assert result.exit_code == 0, result.stdout

    assert observed_offline == [False]
    assert prepared_contexts
    contexts_seen = [context for context, _ in prepared_contexts]
    assert contexts_seen.count("standard") == 1
    assert contexts_seen.count("risk_manager") == 1
    assert all(base_url == server.HEALTHCHECK_TESTING_V1_BASE_URL for _, base_url in prepared_contexts)

    assert online_calls
    assert sorted(context for context, _ in online_calls) == sorted(server._CONTEXT_CHOICES)
    for _, skip_flag in online_calls:
        assert skip_flag is False

    assert sorted(diagnostic_calls) == sorted(server._CONTEXT_CHOICES)


def test_healthcheck_offline_flag_skips_network_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    prepared_contexts: List[Tuple[str, bool, str]] = []

    def fake_initialize(runtime_settings, logging_settings, *, show_banner: bool = False):
        return MagicMock(name="logger")

    def fake_offline(runtime_settings, logger):
        return True

    def fake_prepare(runtime_settings, logger, **kwargs):
        prepared_contexts.append(
            (runtime_settings.context, runtime_settings.skip_startup_checks, kwargs.get("v1_base_url"))
        )
        names = list(server._EXPECTED_TOOLS_BY_CONTEXT[runtime_settings.context])

        def get_tools():
            return {name: object() for name in names}

        return SimpleNamespace(
            tools={name: object() for name in names},
            get_tools=get_tools,
            call_v1_tool=object(),
        )

    with (
        patch("server._initialize_logging", side_effect=fake_initialize),
        patch("server._run_offline_checks", side_effect=fake_offline),
        patch("server._prepare_server", side_effect=fake_prepare),
        patch("server._run_online_checks") as online_mock,
        patch("server._run_context_tool_diagnostics") as diagnostics_mock,
    ):
        result = runner.invoke(
            server.app,
            ["healthcheck", "--offline"],
            env={
                "BITSIGHT_API_KEY": "dummy",
            },
            color=False,
        )

    assert result.exit_code == 0, result.stdout
    online_mock.assert_not_called()
    diagnostics_mock.assert_not_called()
    assert prepared_contexts
    for context_name, skip_flag, base_url in prepared_contexts:
        assert context_name in server._CONTEXT_CHOICES
        assert skip_flag is True
        assert base_url == server.HEALTHCHECK_TESTING_V1_BASE_URL


def test_healthcheck_passes_shared_options_to_build_invocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    captured = {}

    original_build = server._build_invocation

    def record_build_invocation(**kwargs):
        captured.update(kwargs)
        return original_build(**kwargs)

    monkeypatch.setattr(server, "_build_invocation", record_build_invocation)

    def fake_resolve(invocation):
        runtime = replace(
            _runtime_settings(),
            context=None,
            skip_startup_checks=bool(
                getattr(invocation.runtime, "skip_startup_checks", False)
            ),
        )
        logging_settings = replace(
            _logging_settings(),
            level=logging.INFO,
            file_path="log",
            backup_count=3,
        )
        return (runtime, logging_settings, {})

    monkeypatch.setattr(server, "_resolve_runtime_and_logging", fake_resolve)
    logger = MagicMock(name="logger")
    monkeypatch.setattr(
        server,
        "_initialize_logging",
        lambda runtime, logging_settings, *, show_banner=False: logger,
    )
    monkeypatch.setattr(server, "_run_offline_checks", lambda runtime, log: True)

    def fake_prepare(runtime, log, **kwargs):
        names = list(server._EXPECTED_TOOLS_BY_CONTEXT[runtime.context])

        def get_tools():
            return {name: object() for name in names}

        return SimpleNamespace(
            tools={name: object() for name in names},
            get_tools=get_tools,
            call_v1_tool=object(),
        )

    monkeypatch.setattr(server, "_prepare_server", fake_prepare)
    monkeypatch.setattr(server, "_run_online_checks", lambda runtime, log, srv: True)
    monkeypatch.setattr(
        server,
        "_run_context_tool_diagnostics",
        lambda *, context, logger, server_instance, failures=None: True,
    )

    result = runner.invoke(
        server.app,
        [
            "healthcheck",
            "--config",
            "custom.toml",
            "--bitsight-api-key",
            "abc",
            "--subscription-folder",
            "folder",
            "--subscription-type",
            "continuous_monitoring",
            "--debug",
            "--allow-insecure-tls",
            "--ca-bundle",
            "bundle.pem",
            "--risk-vector-filter",
            "botnet",
            "--max-findings",
            "5",
            "--log-level",
            "DEBUG",
            "--log-format",
            "json",
            "--log-file",
            "logs/app.log",
            "--log-max-bytes",
            "1024",
            "--log-backup-count",
            "3",
        ],
        color=False,
    )

    assert result.exit_code == 0, result.stdout
    assert captured["config_path"] == Path("custom.toml")
    assert captured["api_key"] == "abc"
    assert captured["subscription_folder"] == "folder"
    assert captured["subscription_type"] == "continuous_monitoring"
    assert captured["debug"] is True
    assert captured["allow_insecure_tls"] is True
    assert captured["ca_bundle"] == "bundle.pem"
    assert captured["risk_vector_filter"] == "botnet"
    assert captured["max_findings"] == 5
    assert captured["log_level"] == "DEBUG"
    assert captured["log_format"] == "json"
    assert captured["log_file"] == "logs/app.log"
    assert captured["log_max_bytes"] == 1024
    assert captured["log_backup_count"] == 3
    assert captured["skip_startup_checks"] is False


def test_healthcheck_fails_when_context_tools_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()

    monkeypatch.setattr(server, "_run_offline_checks", lambda runtime, log: True)
    logger = MagicMock(name="logger")
    monkeypatch.setattr(
        server,
        "_initialize_logging",
        lambda runtime, logging_settings, *, show_banner=False: logger,
    )

    expected = {context: set(server._EXPECTED_TOOLS_BY_CONTEXT[context]) for context in server._CONTEXT_CHOICES}

    def fake_prepare(runtime, log, **kwargs):
        names = list(expected[runtime.context])
        if runtime.context == "risk_manager":
            names = [name for name in names if name != "request_company"]

        def get_tools():
            return {name: object() for name in names}

        return SimpleNamespace(
            tools={name: object() for name in names},
            get_tools=get_tools,
            call_v1_tool=object(),
        )

    monkeypatch.setattr(server, "_prepare_server", fake_prepare)
    monkeypatch.setattr(server, "_run_online_checks", lambda runtime, log, srv: True)
    monkeypatch.setattr(
        server,
        "_run_context_tool_diagnostics",
        lambda *, context, logger, server_instance, failures=None: True,
    )

    result = runner.invoke(
        server.app,
        ["healthcheck"],
        env={"BITSIGHT_API_KEY": "dummy"},
        color=False,
    )

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert result.exception.code == 1


def test_healthcheck_fails_when_diagnostics_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr(server, "_run_offline_checks", lambda runtime, log: True)
    logger = MagicMock(name="logger")
    monkeypatch.setattr(
        server,
        "_initialize_logging",
        lambda runtime, logging_settings, *, show_banner=False: logger,
    )

    expected = {context: set(server._EXPECTED_TOOLS_BY_CONTEXT[context]) for context in server._CONTEXT_CHOICES}

    def fake_prepare(runtime, log, **kwargs):
        names = list(expected[runtime.context])

        def get_tools():
            return {name: object() for name in names}

        return SimpleNamespace(
            tools={name: object() for name in names},
            get_tools=get_tools,
            call_v1_tool=object(),
        )

    monkeypatch.setattr(server, "_prepare_server", fake_prepare)
    monkeypatch.setattr(server, "_run_online_checks", lambda runtime, log, srv: True)

    def fake_diagnostics(*, context, logger, server_instance, failures=None):
        return context != "risk_manager"

    monkeypatch.setattr(server, "_run_context_tool_diagnostics", fake_diagnostics)

    result = runner.invoke(
        server.app,
        ["healthcheck"],
        env={"BITSIGHT_API_KEY": "dummy"},
        color=False,
    )

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert result.exception.code == 1


def test_healthcheck_production_flag_uses_production_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    base_urls: List[str] = []

    monkeypatch.setattr(server, "_run_offline_checks", lambda runtime, log: True)
    logger = MagicMock(name="logger")
    monkeypatch.setattr(
        server,
        "_initialize_logging",
        lambda runtime, logging_settings, *, show_banner=False: logger,
    )

    def fake_prepare(runtime, log, **kwargs):
        base_urls.append(kwargs.get("v1_base_url"))
        names = list(server._EXPECTED_TOOLS_BY_CONTEXT[runtime.context])

        def get_tools():
            return {name: object() for name in names}

        return SimpleNamespace(
            tools={name: object() for name in names},
            get_tools=get_tools,
            call_v1_tool=object(),
        )

    monkeypatch.setattr(server, "_prepare_server", fake_prepare)
    monkeypatch.setattr(server, "_run_online_checks", lambda runtime, log, srv: True)
    monkeypatch.setattr(
        server,
        "_run_context_tool_diagnostics",
        lambda *, context, logger, server_instance, failures=None: True,
    )

    result = runner.invoke(
        server.app,
        ["healthcheck", "--production"],
        env={"BITSIGHT_API_KEY": "dummy"},
        color=False,
    )

    assert result.exit_code == 0, result.stdout
    assert base_urls
    assert all(base_url == server.HEALTHCHECK_PRODUCTION_V1_BASE_URL for base_url in base_urls)


def test_healthcheck_retries_after_tls_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr(server, "_run_offline_checks", lambda runtime, log: True)
    logger = MagicMock(name="logger")
    monkeypatch.setattr(
        server,
        "_initialize_logging",
        lambda runtime, logging_settings, *, show_banner=False: logger,
    )

    expected = {
        context: set(server._EXPECTED_TOOLS_BY_CONTEXT[context])
        for context in server._CONTEXT_CHOICES
    }

    prepare_calls: List[Tuple[str, bool]] = []

    def fake_prepare(runtime, log, **kwargs):
        prepare_calls.append((runtime.context, runtime.allow_insecure_tls))
        names = list(expected[runtime.context])

        def get_tools():
            return {name: object() for name in names}

        return SimpleNamespace(
            tools={name: object() for name in names},
            get_tools=get_tools,
            call_v1_tool=object(),
        )

    monkeypatch.setattr(server, "_prepare_server", fake_prepare)
    monkeypatch.setattr(server, "_run_online_checks", lambda runtime, log, srv: True)

    standard_attempts = {"count": 0}

    def fake_diagnostics(*, context, logger, server_instance, failures=None):
        if context == "standard":
            standard_attempts["count"] += 1
            if standard_attempts["count"] == 1:
                if failures is not None:
                    failures.append(
                        server.DiagnosticFailure(
                            tool="company_search",
                            stage="call",
                            message="ssl failure",
                            exception=ssl.SSLError("self signed certificate"),
                        )
                    )
                return False
        return True

    monkeypatch.setattr(server, "_run_context_tool_diagnostics", fake_diagnostics)

    result = runner.invoke(
        server.app,
        ["healthcheck"],
        env={"BITSIGHT_API_KEY": "dummy"},
        color=False,
    )

    assert result.exit_code == 0, result.stdout
    assert standard_attempts["count"] == 2
    standard_flags = [flag for context, flag in prepare_calls if context == "standard"]
    assert standard_flags.count(False) == 1
    assert standard_flags.count(True) == 1


def test_healthcheck_missing_ca_bundle_falls_back_to_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()

    runtime = replace(_runtime_settings(), ca_bundle_path="/nonexistent/ca.pem")
    logging_settings = _logging_settings()

    monkeypatch.setattr(server, "_run_offline_checks", lambda runtime, log: True)
    monkeypatch.setattr(
        server,
        "_resolve_runtime_and_logging",
        lambda invocation: (runtime, logging_settings, {}),
    )

    logger = MagicMock(name="logger")
    monkeypatch.setattr(
        server,
        "_initialize_logging",
        lambda runtime_settings, logging_settings, *, show_banner=False: logger,
    )

    prepare_invocations: List[Tuple[str, Optional[str], bool]] = []

    def fake_prepare(runtime_settings, log, **kwargs):
        prepare_invocations.append(
            (
                runtime_settings.context,
                runtime_settings.ca_bundle_path,
                runtime_settings.allow_insecure_tls,
            )
        )
        names = list(server._EXPECTED_TOOLS_BY_CONTEXT[runtime_settings.context])

        def get_tools():
            return {name: object() for name in names}

        return SimpleNamespace(
            tools={name: object() for name in names},
            get_tools=get_tools,
            call_v1_tool=object(),
        )

    monkeypatch.setattr(server, "_prepare_server", fake_prepare)
    monkeypatch.setattr(server, "_run_online_checks", lambda runtime, log, srv: True)
    monkeypatch.setattr(
        server,
        "_run_context_tool_diagnostics",
        lambda *, context, logger, server_instance, failures=None: True,
    )

    result = runner.invoke(
        server.app,
        ["healthcheck"],
        env={"BITSIGHT_API_KEY": "dummy"},
        color=False,
    )

    assert result.exit_code == 0, result.stdout
    assert prepare_invocations
    for _, ca_bundle_path, allow_insecure in prepare_invocations:
        assert ca_bundle_path is None
        assert allow_insecure is False
