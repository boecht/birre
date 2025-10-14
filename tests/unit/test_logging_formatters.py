import json
import logging

import pytest

from src.config import LoggingSettings
from src.logging import (
    DEFAULT_TEXT_FORMAT,
    ChannelNameFilter,
    JsonLogFormatter,
    RequestContextAdapter,
    configure_logging,
)


@pytest.fixture()
def sample_record() -> logging.LogRecord:
    logger = logging.getLogger("birre.server.startup")
    return logger.makeRecord(
        name=logger.name,
        level=logging.INFO,
        fn=__file__,
        lno=42,
        msg="sample message",
        args=(),
        exc_info=None,
        func="sample_record",
    )


def test_channel_name_filter_sets_root_segment(
    sample_record: logging.LogRecord,
) -> None:
    filt = ChannelNameFilter()

    assert filt.filter(sample_record) is True
    assert getattr(sample_record, "channel") == "birre"

    other = logging.getLogger("httpx").makeRecord(
        name="httpx",
        level=logging.INFO,
        fn=__file__,
        lno=12,
        msg="external",
        args=(),
        exc_info=None,
        func="test",
    )
    filt.filter(other)
    assert getattr(other, "channel") == "httpx"


def test_default_text_format_uses_channel(sample_record: logging.LogRecord) -> None:
    filt = ChannelNameFilter()
    filt.filter(sample_record)

    formatter = logging.Formatter(DEFAULT_TEXT_FORMAT)
    formatted = formatter.format(sample_record)

    assert "birre" in formatted
    assert "birre.server" not in formatted
    assert "sample message" in formatted


def test_json_formatter_includes_source_metadata(
    sample_record: logging.LogRecord,
) -> None:
    filt = ChannelNameFilter()
    filt.filter(sample_record)

    formatter = JsonLogFormatter()
    payload = json.loads(formatter.format(sample_record))

    assert payload["channel"] == "birre"
    assert payload["logger"] == "birre.server.startup"
    assert payload["module"] in {"test_logging_formatters", "pytest"}
    assert payload["function"] == "sample_record"
    assert payload["line"] == sample_record.lineno
    assert payload["message"] == "sample message"


def test_request_context_adapter_merges_and_filters_extra() -> None:
    base_extra = {"request_id": "base-id", "tool": "search"}
    adapter = RequestContextAdapter(logging.getLogger("birre.adapter"), base_extra)

    msg, kwargs = adapter.process(
        "message",
        {
            "extra": {
                "request_id": "override-id",
                "user": "alice",
                "tool": None,
                "ignore": None,
            }
        },
    )

    assert msg == "message"
    assert kwargs["extra"] == {
        "request_id": "override-id",
        "tool": "search",
        "user": "alice",
    }
    assert base_extra == {"request_id": "base-id", "tool": "search"}


def test_configure_logging_attaches_channel_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    original_level = root_logger.level

    added_handler = None
    try:
        settings = LoggingSettings(
            level=logging.INFO,
            format="text",
            file_path=None,
            max_bytes=1024,
            backup_count=3,
        )

        configure_logging(settings)

        assert root_logger.level == logging.INFO
        assert len(root_logger.handlers) == 1
        handler = root_logger.handlers[0]
        added_handler = handler
        filters = getattr(handler, "filters", [])
        assert any(isinstance(filt, ChannelNameFilter) for filt in filters)

        record = logging.getLogger("birre.configure").makeRecord(
            name="birre.configure",
            level=logging.INFO,
            fn=__file__,
            lno=123,
            msg="configured",
            args=(),
            exc_info=None,
            func="test",
        )
        for filt in filters:
            filt.filter(record)
        assert getattr(record, "channel") == "birre"
    finally:
        if added_handler is not None:
            added_handler.close()
        root_logger.handlers = original_handlers
        root_logger.setLevel(original_level)
        monkeypatch.setattr("src.logging._configured_settings", None, raising=False)
