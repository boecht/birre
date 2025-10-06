import json
import logging
from pathlib import Path

import pytest

from src import startup_checks
from src.startup_checks import run_offline_startup_checks


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
