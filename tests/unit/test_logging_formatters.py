import json
import logging

import pytest

from src.logging import DEFAULT_TEXT_FORMAT, ChannelNameFilter, JsonLogFormatter


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
