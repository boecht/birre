from __future__ import annotations

import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Optional

from fastmcp import Context
from src.config import LOG_FORMAT_JSON, LoggingSettings

STANDARD_RECORD_KEYS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
}

DEFAULT_TEXT_FORMAT = (
    "%(asctime)s [%(levelname)s] %(channel)s (%(module)s:%(funcName)s) — %(message)s"
)


_configured_settings: Optional[LoggingSettings] = None


class ChannelNameFilter(logging.Filter):
    """Ensure log records expose a short channel name for formatting."""

    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        name = getattr(record, "name", "")
        record.channel = name.split(".")[0] if name else name
        return True


class JsonLogFormatter(logging.Formatter):
    """Render log records as structured JSON lines."""

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        timestamp = datetime.fromtimestamp(record.created, timezone.utc).isoformat()
        channel = getattr(record, "channel", record.name)
        payload: Dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "channel": channel,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
        }

        event_name = record.__dict__.get("event")
        if isinstance(event_name, str) and event_name:
            payload["event"] = event_name

        request_id = record.__dict__.get("request_id")
        if isinstance(request_id, str) and request_id:
            payload["request_id"] = request_id

        tool_name = record.__dict__.get("tool")
        if isinstance(tool_name, str) and tool_name:
            payload["tool"] = tool_name

        company_guid = record.__dict__.get("company_guid")
        if isinstance(company_guid, str) and company_guid:
            payload["company_guid"] = company_guid

        extras: Dict[str, Any] = {}
        for key, value in record.__dict__.items():
            if key in STANDARD_RECORD_KEYS or key in payload:
                continue
            if key.startswith("_"):
                continue
            extras[key] = value
        if extras:
            payload["extras"] = extras

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


class RequestContextAdapter(logging.LoggerAdapter):
    """Logger adapter that ensures contextual fields are merged into extra."""

    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:  # type: ignore[override]
        base_extra = self.extra if isinstance(self.extra, dict) else {}
        extra = dict(base_extra)
        incoming = kwargs.get("extra")
        if isinstance(incoming, dict):
            for key, value in incoming.items():
                if value is not None:
                    extra[key] = value
        kwargs["extra"] = extra
        return msg, kwargs


def _build_formatter(format_name: str) -> logging.Formatter:
    if format_name == LOG_FORMAT_JSON:
        return JsonLogFormatter()
    formatter = logging.Formatter(DEFAULT_TEXT_FORMAT)
    formatter.converter = lambda *args: datetime.now(timezone.utc).timetuple()
    return formatter


def configure_logging(settings: LoggingSettings) -> None:
    global _configured_settings

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(settings.level)

    channel_filter = ChannelNameFilter()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(settings.level)
    console_handler.addFilter(channel_filter)
    console_handler.setFormatter(_build_formatter(settings.format))
    root_logger.addHandler(console_handler)

    if settings.file_path:
        file_handler = RotatingFileHandler(
            settings.file_path,
            maxBytes=settings.max_bytes,
            backupCount=settings.backup_count,
        )
        file_handler.setLevel(settings.level)
        file_handler.addFilter(channel_filter)
        file_handler.setFormatter(_build_formatter(settings.format))
        root_logger.addHandler(file_handler)

    _configured_settings = settings


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def _extract_request_id(ctx: Optional[Context]) -> Optional[str]:
    if ctx is None:
        return None
    for attr in ("request_id", "call_id", "id"):
        value = getattr(ctx, attr, None)
        if isinstance(value, str) and value:
            return value
    metadata = getattr(ctx, "metadata", None)
    if isinstance(metadata, dict):
        for key in ("request_id", "call_id", "id"):
            value = metadata.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def attach_request_context(
    logger: logging.Logger,
    ctx: Optional[Context] = None,
    *,
    request_id: Optional[str] = None,
    tool: Optional[str] = None,
    **base_fields: Any,
) -> RequestContextAdapter:
    resolved_request_id = request_id or _extract_request_id(ctx) or str(uuid.uuid4())
    extras: Dict[str, Any] = {"request_id": resolved_request_id}

    inferred_tool = tool
    if inferred_tool is None and ctx is not None:
        inferred_tool = getattr(ctx, "tool", None) or getattr(ctx, "tool_name", None)
    if inferred_tool:
        extras["tool"] = inferred_tool

    for key, value in base_fields.items():
        if value is not None:
            extras[key] = value

    return RequestContextAdapter(logger, extras)


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    ctx: Optional[Context] = None,
    message: Optional[str] = None,
    **fields: Any,
) -> None:
    adapter = attach_request_context(logger, ctx)
    extra = {"event": event}
    for key, value in fields.items():
        if value is not None:
            extra[key] = value
    adapter.log(level, message or event, extra=extra)


def log_search_event(
    logger: logging.Logger,
    action: str,
    *,
    ctx: Optional[Context] = None,
    company_name: Optional[str] = None,
    company_domain: Optional[str] = None,
    **fields: Any,
) -> None:
    event_name = f"company_search.{action}"
    log_event(
        logger,
        event_name,
        ctx=ctx,
        company_name=company_name,
        company_domain=company_domain,
        **fields,
    )


def log_rating_event(
    logger: logging.Logger,
    action: str,
    *,
    ctx: Optional[Context] = None,
    company_guid: Optional[str] = None,
    **fields: Any,
) -> None:
    event_name = f"company_rating.{action}"
    log_event(logger, event_name, ctx=ctx, company_guid=company_guid, **fields)


__all__ = [
    "DEFAULT_TEXT_FORMAT",
    "ChannelNameFilter",
    "JsonLogFormatter",
    "configure_logging",
    "get_logger",
    "attach_request_context",
    "log_event",
    "log_search_event",
    "log_rating_event",
]
