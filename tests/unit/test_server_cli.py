import asyncio
import logging
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import server
from src.settings import LoggingSettings


def _runtime_settings() -> dict:
    return {
        "api_key": "test-key",
        "subscription_folder": "API",
        "subscription_type": "continuous_monitoring",
        "risk_vector_filter": "botnet_infections",
        "max_findings": 5,
        "context": "standard",
        "skip_startup_checks": False,
        "debug": False,
        "allow_insecure_tls": False,
        "ca_bundle_path": None,
        "warnings": ["reminder"],
    }


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
        patch("server.logging.getLogger", return_value=root_logger),
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
        patch("server.logging.getLogger", return_value=root_logger),
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
