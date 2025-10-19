import json
from pathlib import Path

import pytest
from structlog.testing import capture_logs

from src import startup_checks
from src.logging import get_logger
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


def _collect_events(entries: list[dict]) -> set[str]:
    return {entry.get("event", "") for entry in entries}


def test_offline_checks_fail_without_api_key() -> None:
    logger = get_logger("birre.startup.test")

    with capture_logs() as cap:
        result = run_offline_startup_checks(
            has_api_key=False,
            subscription_folder="API",
            subscription_type="continuous_monitoring",
            logger=logger,
        )

    assert result is False
    events = _collect_events(cap)
    assert "offline.config.api_key_missing" in events


def test_offline_checks_success_logs_debug_and_warnings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schema_one = tmp_path / "bitsight.v1.schema.json"
    schema_two = tmp_path / "bitsight.v2.schema.json"
    schema_one.write_text(json.dumps({"title": "schema1"}), encoding="utf-8")
    schema_two.write_text(json.dumps({"title": "schema2"}), encoding="utf-8")

    monkeypatch.setattr(startup_checks, "SCHEMA_PATHS", (schema_one, schema_two))

    logger = get_logger("birre.startup.test_success")

    with capture_logs() as cap:
        result = run_offline_startup_checks(
            has_api_key=True,
            subscription_folder=None,
            subscription_type=None,
            logger=logger,
        )

    assert result is True

    debug_entries = [
        entry for entry in cap if entry.get("event") == "offline.config.schema_valid"
    ]
    assert {entry.get("schema") for entry in debug_entries} == {
        schema_one.name,
        schema_two.name,
    }

    events = _collect_events(cap)
    assert "offline.config.subscription_folder_missing" in events
    assert "offline.config.subscription_type_missing" in events


@pytest.mark.asyncio
async def test_online_checks_skipped() -> None:
    logger = get_logger("birre.startup.online.skipped")

    with capture_logs() as cap:
        result = await startup_checks.run_online_startup_checks(
            call_v1_tool=DummyCallV1({}),
            subscription_folder=None,
            subscription_type=None,
            logger=logger,
            skip_startup_checks=True,
        )

    assert result is True
    assert any(
        entry.get("event") == "online.startup_checks_skipped"
        and entry.get("requested") is True
        for entry in cap
    )


@pytest.mark.asyncio
async def test_online_checks_missing_call_tool() -> None:
    logger = get_logger("birre.startup.online.missing")

    with capture_logs() as cap:
        result = await startup_checks.run_online_startup_checks(
            call_v1_tool=None,  # type: ignore[arg-type]
            subscription_folder=None,
            subscription_type=None,
            logger=logger,
        )

    assert result is False
    events = _collect_events(cap)
    assert "online.api_connectivity_missing_tool" in events


@pytest.mark.asyncio
async def test_online_checks_connectivity_failure() -> None:
    logger = get_logger("birre.startup.online.connectivity")
    call_v1 = DummyCallV1({"companySearch": RuntimeError("boom")})

    with capture_logs() as cap:
        result = await startup_checks.run_online_startup_checks(
            call_v1_tool=call_v1,
            subscription_folder=None,
            subscription_type=None,
            logger=logger,
        )

    assert result is False
    assert call_v1.calls == ["companySearch"]
    assert any(
        entry.get("event") == "online.api_connectivity_failed"
        and "RuntimeError: boom" in str(entry.get("issue"))
        for entry in cap
    )


@pytest.mark.asyncio
async def test_online_checks_folder_failure() -> None:
    logger = get_logger("birre.startup.online.folder")
    call_v1 = DummyCallV1(
        {
            "companySearch": {"results": []},
            "getFolders": [{"name": "Other"}],
        }
    )

    with capture_logs() as cap:
        result = await startup_checks.run_online_startup_checks(
            call_v1_tool=call_v1,
            subscription_folder="Target",
            subscription_type=None,
            logger=logger,
        )

    assert result is False
    assert call_v1.calls == ["companySearch", "getFolders"]
    assert any(
        entry.get("event") == "online.subscription_folder_invalid"
        and "Target" in str(entry.get("issue"))
        for entry in cap
    )


@pytest.mark.asyncio
async def test_online_checks_quota_failure() -> None:
    logger = get_logger("birre.startup.online.quota")
    call_v1 = DummyCallV1(
        {
            "companySearch": {"results": []},
            "getFolders": [{"name": "Target"}],
            "getCompanySubscriptions": {
                "continuous_monitoring": {"remaining": 0}
            },
        }
    )

    with capture_logs() as cap:
        result = await startup_checks.run_online_startup_checks(
            call_v1_tool=call_v1,
            subscription_folder="Target",
            subscription_type="continuous_monitoring",
            logger=logger,
        )

    assert result is False
    assert call_v1.calls == ["companySearch", "getFolders", "getCompanySubscriptions"]
    assert any(
        entry.get("event") == "online.subscription_quota_failed"
        and "no remaining licenses" in str(entry.get("issue"))
        for entry in cap
    )


@pytest.mark.asyncio
async def test_online_checks_success() -> None:
    logger = get_logger("birre.startup.online.success")
    call_v1 = DummyCallV1(
        {
            "companySearch": {"results": []},
            "getFolders": [{"name": "Target"}],
            "getCompanySubscriptions": {
                "continuous_monitoring": {"remaining": 2}
            },
        }
    )

    with capture_logs() as cap:
        result = await startup_checks.run_online_startup_checks(
            call_v1_tool=call_v1,
            subscription_folder="Target",
            subscription_type="continuous_monitoring",
            logger=logger,
        )

    assert result is True
    assert call_v1.calls == ["companySearch", "getFolders", "getCompanySubscriptions"]

    events = _collect_events(cap)
    assert {
        "online.api_connectivity_success",
        "online.subscription_folder_verified",
        "online.subscription_quota_ok",
    }.issubset(events)

    folder_records = [
        entry
        for entry in cap
        if entry.get("event") == "online.subscription_folder_verified"
    ]
    assert any(entry.get("folder") == "Target" for entry in folder_records)

    quota_records = [
        entry
        for entry in cap
        if entry.get("event") == "online.subscription_quota_ok"
    ]
    assert any(
        entry.get("subscription_type") == "continuous_monitoring"
        for entry in quota_records
    )
