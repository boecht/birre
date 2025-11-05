import importlib
import json
import logging
import re
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

import birre.application.diagnostics as diagnostics_module
import birre.cli.invocation as cli_invocation
import birre.cli.runtime as cli_runtime
from birre.cli.commands import logs as logs_command
from birre.cli.commands.selftest import command as selftest_command
from birre.cli.commands.selftest import runner as selftest_runner
from birre.config.settings import LoggingSettings, RuntimeSettings

server = importlib.import_module("birre.cli.app")


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
        "context_choices": cli_runtime.CONTEXT_CHOICES,
        "config_path": None,
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
    return cli_invocation.build_invocation(**defaults)


def test_main_exits_when_offline_checks_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_settings = _runtime_settings()
    logging_settings = _logging_settings()

    root_logger = MagicMock(name="root_logger")
    runner = CliRunner()

    with (
        patch(
            "birre.cli.commands.run.resolve_runtime_and_logging",
            return_value=(runtime_settings, logging_settings, object()),
        ) as resolve_mock,
        patch("birre.cli.commands.run.initialize_logging", return_value=root_logger) as init_mock,
        patch("birre.cli.commands.run.run_offline_checks", return_value=False) as offline_mock,
        patch("birre.cli.commands.run.run_online_checks") as online_mock,
        patch("birre.cli.commands.run.prepare_server") as prepare_server,
    ):
        result = runner.invoke(server.app, ["run"], env={"BITSIGHT_API_KEY": "dummy"}, color=False)

    assert result.exit_code == 1
    resolve_mock.assert_called_once()
    init_mock.assert_called_once()
    offline_mock.assert_called_once()
    args, kwargs = offline_mock.call_args
    assert args[0] is runtime_settings
    assert kwargs["logger"] is root_logger
    online_mock.assert_not_called()
    prepare_server.assert_not_called()


def test_main_runs_server_when_checks_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_settings = _runtime_settings()
    logging_settings = _logging_settings()

    root_logger = MagicMock(name="root_logger")

    fake_server = SimpleNamespace(run=MagicMock(name="run"))

    async_online = AsyncMock(return_value=True)
    runner = CliRunner()

    with (
        patch(
            "birre.cli.commands.run.resolve_runtime_and_logging",
            return_value=(runtime_settings, logging_settings, object()),
        ) as resolve_mock,
        patch("birre.cli.commands.run.initialize_logging", return_value=root_logger) as init_mock,
        patch("birre.cli.commands.run.run_offline_checks", return_value=True) as offline_mock,
        patch("birre.cli.commands.run.run_online_checks", async_online) as online_mock,
        patch("birre.cli.commands.run.prepare_server", return_value=fake_server) as prepare_server,
    ):
        result = runner.invoke(server.app, ["run"], env={"BITSIGHT_API_KEY": "dummy"}, color=False)

    assert result.exit_code == 0

    resolve_mock.assert_called_once()
    init_mock.assert_called_once()
    offline_mock.assert_called_once()
    args, kwargs = offline_mock.call_args
    assert args[0] is runtime_settings
    assert kwargs["logger"] is root_logger

    assert online_mock.await_count == 1
    await_args = online_mock.await_args
    assert await_args is not None
    assert await_args.args[0] is runtime_settings
    assert await_args.kwargs["logger"] is root_logger

    prepare_server.assert_called_once()
    prep_args, _ = prepare_server.call_args
    assert prep_args[0] == runtime_settings
    assert prep_args[1] is root_logger

    fake_server.run.assert_called_once()


def test_build_invocation_strips_log_file() -> None:
    invocation = _build_invocation(log_file="  custom.log  ")

    assert invocation.logging.file_path == "custom.log"


def test_logging_inputs_returns_none_when_no_overrides() -> None:
    invocation = _build_invocation()

    assert cli_invocation.logging_inputs(invocation.logging) is None


def test_logging_inputs_disables_file_logging_via_sentinel() -> None:
    invocation = _build_invocation(log_file=" none ")

    logging_inputs = cli_invocation.logging_inputs(invocation.logging)
    assert logging_inputs is not None
    assert logging_inputs.file_path == ""


def test_check_conf_masks_api_key_and_labels_env() -> None:
    runner = CliRunner()
    result = runner.invoke(
        server.app,
        ["config", "show"],
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
        ["config", "show", "--log-level", "DEBUG"],
        env={"BITSIGHT_API_KEY": "maskedkey"},
        color=False,
    )

    assert result.exit_code in (0, 2), result.stdout
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


def test_config_validate_uses_provided_config(tmp_path: Path) -> None:
    runner = CliRunner()
    config_path = tmp_path / "config.local.toml"
    config_path.write_text(
        "\n".join(
            [
                "[bitsight]",
                'api_key = "demo"',
                "",
                "[runtime]",
                "debug = false",
            ]
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        server.app,
        ["config", "validate", "--config", str(config_path)],
        color=False,
    )

    assert result.exit_code == 0, result.stdout
    assert "TOML parsing succeeded" in result.stdout


def test_config_validate_without_config_flag_shows_help() -> None:
    runner = CliRunner()
    result = runner.invoke(
        server.app,
        ["config", "validate"],
        color=False,
    )

    assert result.exit_code == 0
    # Rich may still include formatting codes in CI, so strip ANSI codes
    # ANSI escape sequences start with \x1b[ and end with a letter
    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    clean_output = ansi_escape.sub("", result.stdout)
    assert "config validate" in clean_output
    assert "--config" in clean_output


def test_local_conf_create_generates_preview_and_file(tmp_path: Path) -> None:
    runner = CliRunner()
    output_path = tmp_path / "config.local.toml"
    input_data = (
        "\n".join(
            [
                "supersecretvalue",
                "subscriptions",
                "continuous_monitoring",
                "standard",
                "n",
            ]
        )
        + "\n"
    )

    result = runner.invoke(
        server.app,
        ["config", "init", "--output", str(output_path)],
        input=input_data,
        color=False,
    )

    assert result.exit_code in (0, 2), result.stdout
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
    input_data = (
        "\n".join(
            [
                "",
                "final-secret",
                "",
                "",
                "",
                "n",
            ]
        )
        + "\n"
    )

    result = runner.invoke(
        server.app,
        ["config", "init", "--output", str(output_path)],
        input=input_data,
        color=False,
    )

    assert result.exit_code in (0, 2), result.stdout
    assert "A value is required" in result.stdout
    assert output_path.exists()
    file_content = output_path.read_text(encoding="utf-8")
    assert "final-secret" in file_content


def test_local_conf_create_respects_cli_overrides(tmp_path: Path) -> None:
    runner = CliRunner()
    output_path = tmp_path / "config.local.toml"
    input_data = (
        "\n".join(
            [
                "anothersecret",
                "client-subscriptions",
                "risk_manager",
            ]
        )
        + "\n"
    )

    result = runner.invoke(
        server.app,
        [
            "config",
            "init",
            "--output",
            str(output_path),
            "--subscription-type",
            "vendor_monitoring",
            "--debug",
        ],
        input=input_data,
        color=False,
    )

    assert result.exit_code in (0, 2), result.stdout
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
        ["config", "init", "--output", str(output_path)],
        input="n\n",
        color=False,
    )

    assert result.exit_code == 1
    assert "Aborted" in result.stdout
    assert output_path.read_text(encoding="utf-8") == "existing"


def test_config_init_respects_config_flag(tmp_path: Path) -> None:
    runner = CliRunner()
    destination = tmp_path / "custom.local.toml"
    input_data = (
        "\n".join(
            [
                "secretkey",
                "subscriptions",
                "continuous",
                "standard",
                "n",
            ]
        )
        + "\n"
    )

    result = runner.invoke(
        server.app,
        [
            "config",
            "init",
            "--config",
            str(destination),
        ],
        input=input_data,
        color=False,
    )

    assert result.exit_code in (0, 2), result.stdout
    assert destination.exists()
    content = destination.read_text(encoding="utf-8")
    assert "secretkey" in content
    assert "subscriptions" in content


def test_selftest_defaults_to_online_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    runner_init_args: list[dict] = []

    class FakeSelfTestRunner:
        def __init__(self, **kwargs):
            runner_init_args.append(kwargs)
            self.runtime_settings = kwargs["runtime_settings"]
            self.offline = kwargs["offline"]
            self.target_base_url = kwargs["target_base_url"]
            self.expected_tools_by_context = kwargs.get("expected_tools_by_context", {})

        def run(self):
            # Verify that offline mode is False (online checks enabled by default)
            assert self.offline is False
            # Verify testing base URL is used
            assert self.target_base_url == server.HEALTHCHECK_TESTING_V1_BASE_URL

            contexts = sorted(self.expected_tools_by_context.keys())
            summary = {
                "environment": "testing",
                "offline_check": {"status": "pass"},
                "contexts": {
                    context: {
                        "offline_mode": False,
                        "online": {"status": "pass"},
                        "tools": {
                            tool: {"status": "pass"}
                            for tool in self.expected_tools_by_context[context]
                        },
                    }
                    for context in contexts
                },
                "overall_success": True,
            }
            return diagnostics_module.SelfTestResult(
                success=True,
                degraded=False,
                summary=summary,
                contexts=tuple(contexts),
                alerts=(),
            )

    with patch("birre.cli.commands.selftest.command.SelfTestRunner", FakeSelfTestRunner):
        result = runner.invoke(
            server.app,
            ["selftest"],
            env={
                "BIRRE_SKIP_STARTUP_CHECKS": "true",
                "BITSIGHT_API_KEY": "dummy",
            },
            color=False,
        )

    assert result.exit_code == 0, result.stdout
    assert len(runner_init_args) == 1

    # Verify the runner was initialized with correct parameters
    init_args = runner_init_args[0]
    assert init_args["offline"] is False
    assert init_args["target_base_url"] == server.HEALTHCHECK_TESTING_V1_BASE_URL
    assert init_args["environment_label"] == "testing"


def test_selftest_outputs_summary_report(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()

    class FakeSelfTestRunner:
        def __init__(self, **kwargs):
            self.expected_tools_by_context = kwargs.get("expected_tools_by_context", {})

        def run(self):
            contexts = sorted(self.expected_tools_by_context.keys())
            summary = {
                "environment": "testing",
                "offline_check": {"status": "pass"},
                "contexts": {
                    context: {
                        "offline_mode": False,
                        "online": {"status": "pass"},
                        "tools": {
                            tool: {"status": "pass"}
                            for tool in self.expected_tools_by_context[context]
                        },
                    }
                    for context in contexts
                },
                "overall_success": True,
            }
            return diagnostics_module.SelfTestResult(
                success=True,
                degraded=False,
                summary=summary,
                contexts=tuple(contexts),
                alerts=(),
            )

    with patch("birre.cli.commands.selftest.command.SelfTestRunner", FakeSelfTestRunner):
        result = runner.invoke(
            server.app,
            ["selftest"],
            env={"BITSIGHT_API_KEY": "dummy"},
            color=False,
        )

    assert result.exit_code == 0, result.stdout
    assert "Healthcheck Summary" in result.stdout

    # Extract JSON portion that appears after "Machine-readable summary:" line
    # and before the "Healthcheck Summary" table
    output = result.stdout

    # Find the marker line
    marker = "Machine-readable summary:"
    marker_pos = output.find(marker)
    assert marker_pos != -1, "Machine-readable summary marker not found"

    # Skip past the marker and any whitespace/newlines to find JSON start
    search_start = marker_pos + len(marker)
    remaining = output[search_start:]

    # Find first '{' after the marker (should be on next line)
    json_start_offset = remaining.find("{")
    assert json_start_offset != -1, "JSON opening brace not found after marker"
    json_start = search_start + json_start_offset

    # Find the end of JSON by matching braces
    brace_count = 0
    json_end = json_start
    for i, char in enumerate(output[json_start:], start=json_start):
        if char == "{":
            brace_count += 1
        elif char == "}":
            brace_count -= 1
            if brace_count == 0:
                json_end = i + 1
                break

    json_payload = output[json_start:json_end]
    # Strip ANSI escape codes that Rich console may add even with color=False
    json_payload = re.sub(r"\x1b\[[0-9;]*m", "", json_payload)
    summary = json.loads(json_payload)

    assert summary["offline_check"]["status"] == "pass"
    for context in cli_runtime.CONTEXT_CHOICES:
        context_entry = summary["contexts"].get(context)
        assert context_entry is not None
        assert context_entry["online"]["status"] == "pass"
        assert context_entry["tools"], context_entry


def test_selftest_offline_flag_skips_network_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()

    class FakeSelfTestRunner:
        def __init__(self, **kwargs):
            self.offline = kwargs["offline"]
            self.runtime_settings = kwargs["runtime_settings"]
            self.expected_tools_by_context = kwargs.get("expected_tools_by_context", {})

        def run(self):
            # Verify offline mode is True
            assert self.offline is True
            # Verify skip_startup_checks is also True when using --offline
            assert self.runtime_settings.skip_startup_checks is True

            contexts = sorted(self.expected_tools_by_context.keys())
            summary = {
                "environment": "testing",
                "offline_check": {"status": "pass"},
                "contexts": {
                    context: {
                        "offline_mode": True,
                        "tools": {
                            tool: {"status": "pass"}
                            for tool in self.expected_tools_by_context[context]
                        },
                    }
                    for context in contexts
                },
                "overall_success": True,
            }
            # Offline mode returns degraded=True (exit code 2)
            return diagnostics_module.SelfTestResult(
                success=True,
                degraded=True,
                summary=summary,
                contexts=tuple(contexts),
                alerts=(),
            )

    with patch("birre.cli.commands.selftest.command.SelfTestRunner", FakeSelfTestRunner):
        result = runner.invoke(
            server.app,
            ["selftest", "--offline"],
            env={
                "BITSIGHT_API_KEY": "dummy",
            },
            color=False,
        )

    assert result.exit_code == 2, result.stdout


def test_selftest_passes_shared_options_to_build_invocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    captured = {}

    # Import the selftest command module to patch the right location
    from birre.cli.commands.selftest import command as selftest_command

    original_build = cli_invocation.build_invocation

    def record_build_invocation(**kwargs):
        captured.update(kwargs)
        return original_build(**kwargs)

    # Patch in both locations to be safe
    monkeypatch.setattr(cli_invocation, "build_invocation", record_build_invocation)
    monkeypatch.setattr(selftest_command, "build_invocation", record_build_invocation)

    class FakeSelfTestRunner:
        def __init__(self, **kwargs):
            self.expected_tools_by_context = kwargs.get("expected_tools_by_context", {})

        def run(self):
            contexts = sorted(self.expected_tools_by_context.keys())
            summary = {
                "environment": "testing",
                "offline_check": {"status": "pass"},
                "contexts": {
                    context: {
                        "offline_mode": False,
                        "online": {"status": "pass"},
                        "tools": {
                            tool: {"status": "pass"}
                            for tool in self.expected_tools_by_context[context]
                        },
                    }
                    for context in contexts
                },
                "overall_success": True,
            }
            return diagnostics_module.SelfTestResult(
                success=True,
                degraded=False,
                summary=summary,
                contexts=tuple(contexts),
                alerts=(),
            )

    with patch("birre.cli.commands.selftest.command.SelfTestRunner", FakeSelfTestRunner):
        result = runner.invoke(
            server.app,
            [
                "selftest",
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

    # The command might fail due to missing config file, but we only care that
    # build_invocation was called with the right parameters
    assert result.exit_code in (0, 1), result.stdout
    assert "config_path" in captured, (
        f"build_invocation not called or not captured. Keys: {list(captured.keys())}"
    )
    assert captured["config_path"] == "custom.toml"
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


def test_selftest_uses_environment_config_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runner = CliRunner()
    captured = {}

    # Import the selftest command module to patch the right location
    from birre.cli.commands.selftest import command as selftest_command

    original_build = cli_invocation.build_invocation

    def record_build_invocation(**kwargs):
        captured.update(kwargs)
        return original_build(**kwargs)

    # Apply monkeypatch to both locations
    monkeypatch.setattr(cli_invocation, "build_invocation", record_build_invocation)
    monkeypatch.setattr(selftest_command, "build_invocation", record_build_invocation)

    class FakeSelfTestRunner:
        def __init__(self, **kwargs):
            self.expected_tools_by_context = kwargs.get("expected_tools_by_context", {})

        def run(self):
            contexts = sorted(self.expected_tools_by_context.keys())
            summary = {
                "environment": "testing",
                "offline_check": {"status": "pass"},
                "contexts": {
                    context: {
                        "offline_mode": False,
                        "online": {"status": "pass"},
                        "tools": {
                            tool: {"status": "pass"}
                            for tool in self.expected_tools_by_context[context]
                        },
                    }
                    for context in contexts
                },
                "overall_success": True,
            }
            return diagnostics_module.SelfTestResult(
                success=True,
                degraded=False,
                summary=summary,
                contexts=tuple(contexts),
                alerts=(),
            )

    config_path = tmp_path / "env-config.toml"
    config_path.write_text("[bitsight]\napi_key = 'test'\n", encoding="utf-8")

    # Use patch as decorator instead of context manager
    with patch("birre.cli.commands.selftest.command.SelfTestRunner", FakeSelfTestRunner):
        result = runner.invoke(
            server.app,
            ["selftest"],
            env={
                "BITSIGHT_API_KEY": "abc",
                "BIRRE_CONFIG": str(config_path),
            },
            color=False,
        )

    assert result.exit_code in (0, 2), result.stdout
    # build_invocation should have been called with the config path from environment
    assert "config_path" in captured, f"captured keys: {list(captured.keys())}"
    assert Path(captured["config_path"]) == config_path


def test_selftest_fails_when_context_tools_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()

    monkeypatch.setattr(selftest_runner, "run_offline_checks", lambda runtime, logger: True)
    logger = MagicMock(name="logger")
    monkeypatch.setattr(
        selftest_command,
        "initialize_logging",
        lambda runtime, logging_settings, *, show_banner=False, banner_printer=None: logger,
    )

    expected = {
        context: set(server._EXPECTED_TOOLS_BY_CONTEXT[context])
        for context in cli_runtime.CONTEXT_CHOICES
    }

    def fake_prepare(settings, log, **kwargs):
        names = list(expected[settings.context])
        if settings.context == "risk_manager":
            names = [name for name in names if name != "request_company"]

        def get_tools():
            return {name: object() for name in names}

        return SimpleNamespace(
            tools={name: object() for name in names},
            get_tools=get_tools,
            call_v1_tool=object(),
        )

    monkeypatch.setattr(selftest_runner, "prepare_server", fake_prepare)
    monkeypatch.setattr(
        selftest_runner,
        "run_online_checks",
        lambda runtime, logger, *, run_sync=None, v1_base_url=None: True,
    )

    def fake_diagnostics(
        *,
        context,
        logger,
        server_instance,
        expected_tools,
        summary,
        failures=None,
        run_sync=None,
    ):
        if summary is not None:
            for tool_name in expected_tools:
                summary[tool_name] = {"status": "pass"}
        return True

    monkeypatch.setattr(selftest_runner, "run_context_tool_diagnostics", fake_diagnostics)

    result = runner.invoke(
        server.app,
        ["selftest"],
        env={"BITSIGHT_API_KEY": "dummy"},
        color=False,
    )

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert result.exception.code == 1


def test_selftest_fails_when_diagnostics_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr(selftest_runner, "run_offline_checks", lambda runtime, logger: True)
    logger = MagicMock(name="logger")
    monkeypatch.setattr(
        selftest_command,
        "initialize_logging",
        lambda runtime, logging_settings, *, show_banner=False, banner_printer=None: logger,
    )

    expected = {
        context: set(server._EXPECTED_TOOLS_BY_CONTEXT[context])
        for context in cli_runtime.CONTEXT_CHOICES
    }

    def fake_prepare(settings, log, **kwargs):
        names = list(expected[settings.context])

        def get_tools():
            return {name: object() for name in names}

        return SimpleNamespace(
            tools={name: object() for name in names},
            get_tools=get_tools,
            call_v1_tool=object(),
        )

    monkeypatch.setattr(selftest_runner, "prepare_server", fake_prepare)
    monkeypatch.setattr(
        selftest_runner,
        "run_online_checks",
        lambda runtime, logger, *, run_sync=None, v1_base_url=None: True,
    )

    def fake_diagnostics(
        *,
        context,
        logger,
        server_instance,
        expected_tools,
        summary,
        failures=None,
        run_sync=None,
    ):
        if summary is not None:
            for tool_name in expected_tools:
                summary[tool_name] = {"status": "pass"}
        return context != "risk_manager"

    monkeypatch.setattr(selftest_runner, "run_context_tool_diagnostics", fake_diagnostics)

    result = runner.invoke(
        server.app,
        ["selftest"],
        env={"BITSIGHT_API_KEY": "dummy"},
        color=False,
    )

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert result.exception.code == 1


def test_selftest_production_flag_uses_production_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that --production flag passes correct base URL to SelfTestRunner."""
    from birre.cli.commands.selftest import command as selftest_command

    runner = CliRunner()
    captured_args: list[dict] = []

    # Mock SelfTestRunner to capture initialization arguments
    class FakeSelfTestRunner:
        def __init__(self, **kwargs):
            captured_args.append(kwargs)
            self.target_base_url = kwargs.get("target_base_url")
            self.environment_label = kwargs.get("environment_label")

        def run(self):
            # Return a successful self-test result
            from birre.application.diagnostics import SelfTestResult

            return SelfTestResult(
                success=True,
                degraded=False,
                summary={
                    "environment": self.environment_label,
                    "offline_check": {"status": "pass"},
                    "contexts": {
                        "standard": {"success": True, "online": {"status": "pass"}, "tools": {}},
                        "risk_manager": {
                            "success": True,
                            "online": {"status": "pass"},
                            "tools": {},
                        },
                    },
                    "overall_success": True,
                },
                contexts=("standard", "risk_manager"),
                alerts=(),
            )

    # Patch where SelfTestRunner is actually used (in the command module)
    monkeypatch.setattr(selftest_command, "SelfTestRunner", FakeSelfTestRunner)

    result = runner.invoke(
        server.app,
        ["selftest", "--production"],
        env={"BITSIGHT_API_KEY": "dummy"},
        color=False,
    )

    assert result.exit_code in (0, 2), result.stdout
    assert len(captured_args) == 1
    assert captured_args[0]["target_base_url"] == server.HEALTHCHECK_PRODUCTION_V1_BASE_URL
    assert captured_args[0]["environment_label"] == "production"


def test_selftest_retries_after_tls_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()

    class FakeSelfTestRunner:
        def __init__(self, **kwargs):
            self.expected_tools_by_context = kwargs.get("expected_tools_by_context", {})

        def run(self):
            # Simulate TLS failure with retry - returns success with TLS alert (exit code 2)
            contexts = sorted(self.expected_tools_by_context.keys())
            summary = {
                "environment": "testing",
                "offline_check": {"status": "pass"},
                "contexts": {
                    context: {
                        "offline_mode": False,
                        "online": {"status": "pass"},
                        "attempts": [{"status": "fail", "error": "TLS error"}, {"status": "pass"}]
                        if context == "standard"
                        else [{"status": "pass"}],
                        "fallback_attempted": context == "standard",
                        "fallback_success": context == "standard",
                        "tools": {
                            tool: {"status": "pass"}
                            for tool in self.expected_tools_by_context[context]
                        },
                    }
                    for context in contexts
                },
                "overall_success": True,
            }
            # TLS interception alert triggers exit code 2
            # Use the correct error code value
            from birre.infrastructure.errors import ErrorCode

            return diagnostics_module.SelfTestResult(
                success=True,
                degraded=False,
                summary=summary,
                contexts=tuple(contexts),
                alerts=(ErrorCode.TLS_CERT_CHAIN_INTERCEPTED.value,),
            )

    with patch("birre.cli.commands.selftest.command.SelfTestRunner", FakeSelfTestRunner):
        result = runner.invoke(
            server.app,
            ["selftest"],
            env={"BITSIGHT_API_KEY": "dummy"},
            color=False,
        )

    assert result.exit_code == 2, result.stdout


def test_selftest_missing_ca_bundle_falls_back_to_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()

    class FakeSelfTestRunner:
        def __init__(self, **kwargs):
            self.runtime_settings = kwargs["runtime_settings"]
            self.expected_tools_by_context = kwargs.get("expected_tools_by_context", {})

        def run(self):
            # Verify that ca_bundle_path was provided (will be handled by SelfTestRunner internally)
            # The runner should detect missing bundle and fall back to defaults
            contexts = sorted(self.expected_tools_by_context.keys())
            summary = {
                "environment": "testing",
                "offline_check": {"status": "pass"},
                "contexts": {
                    context: {
                        "offline_mode": False,
                        "online": {"status": "pass"},
                        "notes": ["ca-bundle-defaulted"],  # Note that fallback occurred
                        "tools": {
                            tool: {"status": "pass"}
                            for tool in self.expected_tools_by_context[context]
                        },
                    }
                    for context in contexts
                },
                "overall_success": True,
            }
            # CA bundle fallback causes degraded=True (exit code 2)
            return diagnostics_module.SelfTestResult(
                success=True,
                degraded=True,
                summary=summary,
                contexts=tuple(contexts),
                alerts=(),
            )

    with (
        patch("birre.cli.commands.selftest.command.SelfTestRunner", FakeSelfTestRunner),
        patch("birre.cli.invocation.resolve_runtime_and_logging") as resolve_mock,
    ):
        # Configure the mock to return settings with nonexistent CA bundle
        runtime = replace(_runtime_settings(), ca_bundle_path="/nonexistent/ca.pem")
        logging_settings = _logging_settings()
        resolve_mock.return_value = (runtime, logging_settings, {})

        result = runner.invoke(
            server.app,
            ["selftest"],
            env={"BITSIGHT_API_KEY": "dummy"},
            color=False,
        )

    assert result.exit_code == 2, result.stdout


def test_logs_clear_truncates_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    log_path = tmp_path / "birre.log"
    log_path.write_text("existing\n", encoding="utf-8")

    def fake_resolver(
        *,
        config_path,
        log_level,
        log_format,
        log_file,
        log_max_bytes,
        log_backup_count,
    ):
        assert log_file == str(log_path)
        return (
            None,
            SimpleNamespace(file_path=str(log_path), backup_count=2, format="text"),
        )

    monkeypatch.setattr(logs_command, "_resolve_logging_settings_from_cli", fake_resolver)

    result = runner.invoke(
        server.app,
        ["logs", "clear", "--log-file", str(log_path)],
        color=False,
    )

    assert result.exit_code == 0, result.stdout
    assert log_path.read_text(encoding="utf-8") == ""


def test_logs_rotate_uses_override_backup_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runner = CliRunner()
    log_path = tmp_path / "birre.log"
    log_path.write_text("content\n", encoding="utf-8")

    captured_backup_count: list[int] = []

    def fake_resolver(
        *,
        config_path,
        log_level,
        log_format,
        log_file,
        log_max_bytes,
        log_backup_count,
    ):
        assert log_backup_count == 3
        return (
            None,
            SimpleNamespace(file_path=str(log_path), backup_count=1, format="text"),
        )

    def fake_rotate(path: Path, backup_count: int) -> None:
        captured_backup_count.append(backup_count)

    monkeypatch.setattr(logs_command, "_resolve_logging_settings_from_cli", fake_resolver)
    monkeypatch.setattr(logs_command, "_rotate_logs", fake_rotate)

    result = runner.invoke(
        server.app,
        ["logs", "rotate", "--log-file", str(log_path), "--log-backup-count", "3"],
        color=False,
    )

    assert result.exit_code == 0, result.stdout
    assert captured_backup_count == [3]


def test_logs_path_prints_resolved_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    log_path = tmp_path / "birre.log"

    def fake_resolver(
        *,
        config_path,
        log_level,
        log_format,
        log_file,
        log_max_bytes,
        log_backup_count,
    ):
        return (None, SimpleNamespace(file_path=str(log_path), format="json", backup_count=2))

    monkeypatch.setattr(logs_command, "_resolve_logging_settings_from_cli", fake_resolver)

    result = runner.invoke(
        server.app,
        ["logs", "path"],
        color=False,
    )

    assert result.exit_code == 0, result.stdout
    # Rich Console may wrap long paths, so remove newlines but preserve other characters
    normalized_output = result.stdout.replace("\n", "")
    assert str(log_path) in normalized_output


def test_logs_show_filters_by_level_and_since(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runner = CliRunner()
    log_path = tmp_path / "birre.log"
    log_path.write_text(
        "\n".join(
            [
                "2025-10-26T06:00:00Z INFO system boot",
                "2025-10-26T07:00:00Z WARNING disk usage high",
                "2025-10-26T07:30:00Z ERROR outage detected",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_resolver(
        *,
        config_path,
        log_level,
        log_format,
        log_file,
        log_max_bytes,
        log_backup_count,
    ):
        assert log_file == str(log_path)
        return (None, SimpleNamespace(file_path=str(log_path), format="text", backup_count=2))

    monkeypatch.setattr(logs_command, "_resolve_logging_settings_from_cli", fake_resolver)

    result = runner.invoke(
        server.app,
        [
            "logs",
            "show",
            "--log-file",
            str(log_path),
            "--level",
            "WARNING",
            "--since",
            "2025-10-26T06:30:00Z",
            "--tail",
            "5",
        ],
        color=False,
    )

    assert result.exit_code == 0, result.stdout
    output = result.stdout.strip().splitlines()
    assert len(output) == 2
    assert "WARNING" in output[0]
    assert "ERROR" in output[1]
