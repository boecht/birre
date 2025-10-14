import json
import logging
from pathlib import Path

import pytest

from src import startup_checks
from src.startup_checks import run_offline_startup_checks


class DummyCallV1:
    def __init__(self, responses: dict[str, object]) -> None:
        self._responses = responses
        self.calls: list[str] = []

    async def __call__(self, name: str, ctx: object, payload: dict[str, object]) -> object:
        self.calls.append(name)
        response = self._responses.get(name)
        if isinstance(response, Exception):
            raise response
        return response


def test_offline_checks_fail_without_api_key(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("birre.startup.test")
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
        and record.message == "offline.config.api_key: BITSIGHT_API_KEY is not set"
        for record in caplog.records
    )


def test_offline_checks_success_logs_debug_and_warnings(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    schema_one = tmp_path / "bitsight.v1.schema.json"
    schema_two = tmp_path / "bitsight.v2.schema.json"
    schema_one.write_text(json.dumps({"title": "schema1"}), encoding="utf-8")
    schema_two.write_text(json.dumps({"title": "schema2"}), encoding="utf-8")

    monkeypatch.setattr(startup_checks, "SCHEMA_PATHS", (schema_one, schema_two))

    logger = logging.getLogger("birre.startup.test_success")
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
        if record.levelno == logging.DEBUG and "offline.config.schema" in record.message
    ]
    assert len(debug_messages) == 2
    assert all("Schema parsed successfully" in message for message in debug_messages)

    warning_messages = [
        record.message for record in caplog.records if record.levelno == logging.WARNING
    ]
    assert (
        "offline.config.subscription_folder: BIRRE_SUBSCRIPTION_FOLDER not set"
        in warning_messages
    )
    assert (
        "offline.config.subscription_type: BIRRE_SUBSCRIPTION_TYPE not set"
        in warning_messages
    )


@pytest.mark.asyncio
async def test_online_checks_skipped(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("birre.startup.online.skipped")
    caplog.set_level(logging.WARNING)

    result = await startup_checks.run_online_startup_checks(
        call_v1_tool=DummyCallV1({}),
        subscription_folder=None,
        subscription_type=None,
        logger=logger,
        skip_startup_checks=True,
    )

    assert result is True
    assert any(
        record.levelno == logging.WARNING
        and record.message
        == "online.startup_checks_skipped: Startup online checks skipped on request"
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_online_checks_missing_call_tool(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("birre.startup.online.missing")
    caplog.set_level(logging.CRITICAL)

    result = await startup_checks.run_online_startup_checks(
        call_v1_tool=None,  # type: ignore[arg-type]
        subscription_folder=None,
        subscription_type=None,
        logger=logger,
    )

    assert result is False
    assert any(
        record.levelno == logging.CRITICAL
        and record.message == "online.api_connectivity: v1 call tool unavailable"
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_online_checks_connectivity_failure(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("birre.startup.online.connectivity")
    caplog.set_level(logging.CRITICAL)

    call_v1 = DummyCallV1({"companySearch": RuntimeError("boom")})

    result = await startup_checks.run_online_startup_checks(
        call_v1_tool=call_v1,
        subscription_folder=None,
        subscription_type=None,
        logger=logger,
    )

    assert result is False
    assert call_v1.calls == ["companySearch"]
    assert any(
        record.levelno == logging.CRITICAL
        and record.message.startswith("online.api_connectivity: RuntimeError: boom")
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_online_checks_folder_failure(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("birre.startup.online.folder")
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

    assert result is False
    assert call_v1.calls == ["companySearch", "getFolders"]
    assert any(
        record.levelno == logging.CRITICAL
        and "online.subscription_folder_exists" in record.message
        and "Target" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_online_checks_quota_failure(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("birre.startup.online.quota")
    caplog.set_level(logging.INFO)

    call_v1 = DummyCallV1(
        {
            "companySearch": {"results": []},
            "getFolders": [{"name": "Target"}],
            "getCompanySubscriptions": {
                "continuous_monitoring": {"remaining": 0}
            },
        }
    )

    result = await startup_checks.run_online_startup_checks(
        call_v1_tool=call_v1,
        subscription_folder="Target",
        subscription_type="continuous_monitoring",
        logger=logger,
    )

    assert result is False
    assert call_v1.calls == ["companySearch", "getFolders", "getCompanySubscriptions"]
    assert any(
        record.levelno == logging.CRITICAL
        and "online.subscription_quota" in record.message
        and "no remaining licenses" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_online_checks_success(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("birre.startup.online.success")
    caplog.set_level(logging.INFO)

    call_v1 = DummyCallV1(
        {
            "companySearch": {"results": []},
            "getFolders": [{"name": "Target"}],
            "getCompanySubscriptions": {
                "continuous_monitoring": {"remaining": 2}
            },
        }
    )

    result = await startup_checks.run_online_startup_checks(
        call_v1_tool=call_v1,
        subscription_folder="Target",
        subscription_type="continuous_monitoring",
        logger=logger,
    )

    assert result is True
    assert call_v1.calls == ["companySearch", "getFolders", "getCompanySubscriptions"]
    expected_messages = {
        "online.api_connectivity: Successfully called companySearch",
        "online.subscription_folder_exists: Folder 'Target' verified via API",
        "online.subscription_quota: Subscription 'continuous_monitoring' has remaining licenses",
    }
    assert expected_messages.issubset({record.message for record in caplog.records})
