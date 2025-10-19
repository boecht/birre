from __future__ import annotations

import logging
from typing import Any

import pytest
import structlog
from structlog.stdlib import ProcessorFormatter
from structlog.testing import capture_logs

from src.config import LOG_FORMAT_JSON, LoggingSettings
from src.logging import bind_request_context, configure_logging, get_logger, log_event


@pytest.fixture()
def restore_logging_state() -> Any:
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    original_level = root_logger.level
    try:
        yield
    finally:
        for handler in root_logger.handlers:
            handler.close()
        root_logger.handlers = original_handlers
        root_logger.setLevel(original_level)
        structlog.reset_defaults()


def test_configure_logging_installs_processor_formatter(restore_logging_state: Any) -> None:
    settings = LoggingSettings(
        level=logging.INFO,
        format=LOG_FORMAT_JSON,
        file_path=None,
        max_bytes=1024,
        backup_count=3,
    )

    configure_logging(settings)

    root_logger = logging.getLogger()
    assert root_logger.level == logging.INFO
    assert root_logger.handlers, "configure_logging should attach at least one handler"

    handler = root_logger.handlers[0]
    assert isinstance(handler.formatter, ProcessorFormatter)

    logger = get_logger("birre.test.configure")
    with capture_logs() as cap:
        logger.info("logging.configure_check", check="ok")

    assert cap, "structlog logger should emit events"
    entry = cap[0]
    assert entry["event"] == "logging.configure_check"
    assert entry["check"] == "ok"


def test_bind_request_context_binds_metadata() -> None:
    logger = get_logger("birre.test.bind")

    with capture_logs() as cap:
        bound = bind_request_context(
            logger,
            ctx=None,
            request_id="req-123",
            tool="search",
        )
        bound.info("binding.event", key="value")

    assert cap, "Expected captured log entry"
    entry = cap[0]
    assert entry["event"] == "binding.event"
    assert entry["request_id"] == "req-123"
    assert entry["tool"] == "search"
    assert entry["key"] == "value"


def test_log_event_preserves_custom_message() -> None:
    logger = get_logger("birre.test.log_event")

    with capture_logs() as cap:
        log_event(
            logger,
            "custom.event",
            message="Custom message",
            additional="field",
        )

    assert cap, "Expected captured log entry"
    entry = cap[0]
    assert entry["event"] == "Custom message"
    assert entry.get("_event_name") == "custom.event"
    assert entry.get("_log_message") == "Custom message"
    assert entry["additional"] == "field"
