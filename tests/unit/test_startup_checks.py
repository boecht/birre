import json
import logging
from pathlib import Path

import pytest

from birre.application import startup as startup_checks
from birre.application.startup import run_offline_startup_checks
from birre.config.settings import LOG_FORMAT_TEXT, LoggingSettings
from birre.infrastructure.logging import configure_logging, get_logger


@pytest.fixture(autouse=True)
def _configure_structured_logging() -> None:
    """Install deterministic structured logging for startup-check tests."""

    configure_logging(
        LoggingSettings(
            level=logging.DEBUG,
            format=LOG_FORMAT_TEXT,
            file_path=None,
            max_bytes=1024,
            backup_count=1,
        )
    )


class DummyCallV1:
    def __init__(self, responses: dict[str, object]) -> None:
        self._responses = responses
        self.calls: list[str] = []

    async def __call__(
        self, name: str, ctx: object, payload: dict[str, object]
    ) -> object:
        self.calls.append(name)
        response = self._responses.get(name)
        if isinstance(response, Exception):
            raise response
        return response


def test_offline_checks_fail_without_api_key(caplog: pytest.LogCaptureFixture) -> None:
    logger = get_logger("birre.startup.test")
    caplog.set_level(logging.CRITICAL)

    result = run_offline_startup_checks(
        has_api_key=False,
        subscription_folder="API",
        subscription_type="continuous_monitoring",
        logger=logger,
    )

    assert result is False
    assert any(
        record.levelno == logging.CRITICAL
        and "offline.config.api_key.missing" in record.message
        for record in caplog.records
    )


def test_offline_checks_success_logs_debug_and_warnings(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    schema_dir = tmp_path / "apis"
    schema_dir.mkdir()
    schema_one = schema_dir / "bitsight.v1.schema.json"
    schema_two = schema_dir / "bitsight.v2.schema.json"
    schema_one.write_text(json.dumps({"title": "schema1"}), encoding="utf-8")
    schema_two.write_text(json.dumps({"title": "schema2"}), encoding="utf-8")

    monkeypatch.setattr(startup_checks.resources, "files", lambda _: tmp_path)

    logger = get_logger("birre.startup.test_success")
    caplog.set_level(logging.DEBUG)

    result = run_offline_startup_checks(
        has_api_key=True,
        subscription_folder=None,
        subscription_type=None,
        logger=logger,
    )

    assert result is True

    debug_messages = [
        record.message
        for record in caplog.records
        if record.levelno == logging.DEBUG
        and "offline.config.schema.parsed" in record.message
    ]
    assert len(debug_messages) == 2

    warning_messages = [
        record.message for record in caplog.records if record.levelno == logging.WARNING
    ]
    assert any(
        "offline.config.subscription_folder.missing" in message
        for message in warning_messages
    )
    assert any(
        "offline.config.subscription_type.missing" in message
        for message in warning_messages
    )


@pytest.mark.asyncio
async def test_online_checks_skipped(caplog: pytest.LogCaptureFixture) -> None:
    logger = get_logger("birre.startup.online.skipped")
    caplog.set_level(logging.WARNING)

    result = await startup_checks.run_online_startup_checks(
        call_v1_tool=DummyCallV1({}),
        subscription_folder=None,
        subscription_type=None,
        logger=logger,
        skip_startup_checks=True,
    )

    assert result.success is True
    assert result.subscription_folder_guid is None
    assert any(
        record.levelno == logging.WARNING
        and "online.startup_checks.skipped" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_online_checks_missing_call_tool(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger = get_logger("birre.startup.online.missing")
    caplog.set_level(logging.CRITICAL)

    result = await startup_checks.run_online_startup_checks(
        call_v1_tool=None,  # type: ignore[arg-type]
        subscription_folder=None,
        subscription_type=None,
        logger=logger,
    )

    assert result.success is False
    assert any(
        record.levelno == logging.CRITICAL
        and "online.api_connectivity.unavailable" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_online_checks_connectivity_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger = get_logger("birre.startup.online.connectivity")
    caplog.set_level(logging.CRITICAL)

    call_v1 = DummyCallV1({"companySearch": RuntimeError("boom")})

    result = await startup_checks.run_online_startup_checks(
        call_v1_tool=call_v1,
        subscription_folder=None,
        subscription_type=None,
        logger=logger,
    )

    assert result.success is False
    assert call_v1.calls == ["companySearch"]
    assert any(
        record.levelno == logging.CRITICAL
        and "online.api_connectivity.failed" in record.message
        and "RuntimeError: boom" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_online_checks_folder_failure(caplog: pytest.LogCaptureFixture) -> None:
    logger = get_logger("birre.startup.online.folder")
    caplog.set_level(logging.INFO)

    call_v1 = DummyCallV1(
        {
            "companySearch": {"results": []},
            "getFolders": [{"name": "Other"}],
        }
    )

    result = await startup_checks.run_online_startup_checks(
        call_v1_tool=call_v1,
        subscription_folder="Target",
        subscription_type=None,
        logger=logger,
    )

    assert result.success is False
    assert call_v1.calls == ["companySearch", "getFolders"]
    assert any(
        record.levelno == logging.CRITICAL
        and "online.subscription_folder_exists.failed" in record.message
        and "Target" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_online_checks_quota_failure(caplog: pytest.LogCaptureFixture) -> None:
    logger = get_logger("birre.startup.online.quota")
    caplog.set_level(logging.INFO)

    call_v1 = DummyCallV1(
        {
            "companySearch": {"results": []},
            "getFolders": [{"name": "Target", "guid": "target-guid"}],
            "getCompanySubscriptions": {"continuous_monitoring": {"remaining": 0}},
        }
    )

    result = await startup_checks.run_online_startup_checks(
        call_v1_tool=call_v1,
        subscription_folder="Target",
        subscription_type="continuous_monitoring",
        logger=logger,
    )

    assert result.success is False
    assert call_v1.calls == ["companySearch", "getFolders", "getCompanySubscriptions"]
    assert any(
        record.levelno == logging.CRITICAL
        and "online.subscription_quota.failed" in record.message
        and "no remaining licenses" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_online_checks_success(caplog: pytest.LogCaptureFixture) -> None:
    logger = get_logger("birre.startup.online.success")
    caplog.set_level(logging.INFO)

    call_v1 = DummyCallV1(
        {
            "companySearch": {"results": []},
            "getFolders": [{"name": "Target", "guid": "target-guid"}],
            "getCompanySubscriptions": {"continuous_monitoring": {"remaining": 2}},
        }
    )

    result = await startup_checks.run_online_startup_checks(
        call_v1_tool=call_v1,
        subscription_folder="Target",
        subscription_type="continuous_monitoring",
        logger=logger,
    )

    assert result.success is True
    assert result.subscription_folder_guid == "target-guid"
    assert call_v1.calls == ["companySearch", "getFolders", "getCompanySubscriptions"]
    expected_fragments = [
        "online.api_connectivity.success",
        "online.subscription_folder_exists.verified",
        "online.subscription_quota.verified",
    ]
    messages = [record.message for record in caplog.records]
    for fragment in expected_fragments:
        assert any(fragment in message for message in messages)
