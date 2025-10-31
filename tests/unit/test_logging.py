from __future__ import annotations

import json
import logging

import pytest
from birre.config.settings import LOG_FORMAT_JSON, LOG_FORMAT_TEXT, LoggingSettings
from birre.infrastructure.logging import (
    attach_request_context,
    configure_logging,
    get_logger,
    log_event,
)


def test_text_logging_renders_structured_fields(capfd: pytest.CaptureFixture[str]) -> None:
    settings = LoggingSettings(
        level=logging.INFO,
        format=LOG_FORMAT_TEXT,
        file_path=None,
        max_bytes=1024,
        backup_count=1,
    )
    configure_logging(settings)
    capfd.readouterr()

    logger = get_logger("birre.test.text")
    logger.info("structured event", component="startup", status="ok")

    output = capfd.readouterr().err.strip()
    assert "structured event" in output
    assert "component=startup" in output
    assert "status=ok" in output


def test_json_logging_emits_valid_payload(capfd: pytest.CaptureFixture[str]) -> None:
    settings = LoggingSettings(
        level=logging.INFO,
        format=LOG_FORMAT_JSON,
        file_path=None,
        max_bytes=1024,
        backup_count=1,
    )
    configure_logging(settings)
    capfd.readouterr()

    logger = get_logger("birre.test.json")
    logger.info("json event", action="configure")

    payload = json.loads(capfd.readouterr().err)
    assert payload["event"] == "json event"
    assert payload["action"] == "configure"
    assert payload["logger"] == "birre.test.json"


class _DummyContext:
    def __init__(self, request_id: str, tool: str) -> None:
        self.request_id = request_id
        self.tool = tool


def test_attach_request_context_binds_fields(capfd: pytest.CaptureFixture[str]) -> None:
    settings = LoggingSettings(
        level=logging.INFO,
        format=LOG_FORMAT_JSON,
        file_path=None,
        max_bytes=1024,
        backup_count=1,
    )
    configure_logging(settings)
    capfd.readouterr()

    logger = get_logger("birre.test.context")
    ctx = _DummyContext("ctx-123", "search")
    bound = attach_request_context(logger, ctx, session="alpha")
    bound.info("context event", scope="unit")

    payload = json.loads(capfd.readouterr().err)
    assert payload["request_id"] == "ctx-123"
    assert payload["tool"] == "search"
    assert payload["session"] == "alpha"
    assert payload["scope"] == "unit"


def test_log_event_includes_event_field(capfd: pytest.CaptureFixture[str]) -> None:
    settings = LoggingSettings(
        level=logging.INFO,
        format=LOG_FORMAT_JSON,
        file_path=None,
        max_bytes=1024,
        backup_count=1,
    )
    configure_logging(settings)
    capfd.readouterr()

    logger = get_logger("birre.test.event")
    log_event(logger, "custom.event", ctx=None, user="alice")

    payload = json.loads(capfd.readouterr().err)
    assert payload["event"] == "custom.event"
    assert payload["user"] == "alice"
    assert payload["logger"] == "birre.test.event"
