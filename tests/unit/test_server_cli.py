import asyncio
import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import typer
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
        server.main()

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


def test_invoke_server_conflicting_log_file_options() -> None:
    invocation = server._build_invocation(
        config_path="config.toml",
        api_key=None,
        runtime_context=None,
        debug=None,
        log_level=None,
        log_format=None,
        log_file="custom.log",
        no_log_file=True,
        context_alias=None,
    )

    with pytest.raises(typer.BadParameter):
        server._invoke_server(invocation)


def test_invoke_server_disables_file_logging() -> None:
    invocation = server._build_invocation(
        config_path="config.toml",
        api_key=None,
        runtime_context=None,
        debug=None,
        log_level=None,
        log_format=None,
        log_file=None,
        no_log_file=True,
        context_alias=None,
    )

    runtime_settings = _runtime_settings()
    logging_settings = _logging_settings()

    fake_logger = MagicMock(name="logger")

    with (
        patch("server.LoggingInputs") as logging_inputs,
        patch("server.load_settings", return_value=object()) as load_mock,
        patch("server.apply_cli_overrides") as apply_mock,
        patch("server.runtime_from_settings", return_value=runtime_settings),
        patch("server.logging_from_settings", return_value=logging_settings),
        patch("server.configure_logging"),
        patch("server.get_logger", return_value=fake_logger),
        patch("server.run_offline_startup_checks", return_value=False),
    ):
        with pytest.raises(SystemExit):
            server._invoke_server(invocation)

    logging_inputs.assert_called_once()
    kwargs = logging_inputs.call_args.kwargs
    assert kwargs["file_path"] == ""
    load_mock.assert_called_once()
    apply_mock.assert_called_once()


def test_invoke_server_disables_file_logging_via_sentinel() -> None:
    invocation = server._build_invocation(
        config_path="config.toml",
        api_key=None,
        runtime_context=None,
        debug=None,
        log_level=None,
        log_format=None,
        log_file=" none ",
        no_log_file=False,
        context_alias=None,
    )

    runtime_settings = _runtime_settings()
    logging_settings = _logging_settings()

    fake_logger = MagicMock(name="logger")

    with (
        patch("server.LoggingInputs") as logging_inputs,
        patch("server.load_settings", return_value=object()) as load_mock,
        patch("server.apply_cli_overrides") as apply_mock,
        patch("server.runtime_from_settings", return_value=runtime_settings),
        patch("server.logging_from_settings", return_value=logging_settings),
        patch("server.configure_logging"),
        patch("server.get_logger", return_value=fake_logger),
        patch("server.run_offline_startup_checks", return_value=False),
    ):
        with pytest.raises(SystemExit):
            server._invoke_server(invocation)

    logging_inputs.assert_called_once()
    kwargs = logging_inputs.call_args.kwargs
    assert kwargs["file_path"] == ""
    load_mock.assert_called_once()
    apply_mock.assert_called_once()


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
