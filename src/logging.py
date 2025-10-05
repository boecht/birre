from __future__ import annotations

import json
import logging
import os
import sys
import tomllib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Mapping, Optional

from fastmcp import Context

LOG_FORMAT_TEXT = "text"
LOG_FORMAT_JSON = "json"
DEFAULT_LOG_FORMAT = LOG_FORMAT_TEXT
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_MAX_BYTES = 10_000_000
DEFAULT_BACKUP_COUNT = 5

ENV_LOG_LEVEL = "BIRRE_LOG_LEVEL"
ENV_LOG_FORMAT = "BIRRE_LOG_FORMAT"
ENV_LOG_FILE = "BIRRE_LOG_FILE"
ENV_LOG_MAX_BYTES = "BIRRE_LOG_MAX_BYTES"
ENV_LOG_BACKUP_COUNT = "BIRRE_LOG_BACKUP_COUNT"

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

DEFAULT_TEXT_FORMAT = "%(asctime)s %(levelname)s %(name)s — %(message)s"


@dataclass(frozen=True)
class LoggingSettings:
    level: int
    format: str
    file_path: Optional[str]
    max_bytes: int
    backup_count: int

    @property
    def level_name(self) -> str:
        return logging.getLevelName(self.level)


_configured_settings: Optional[LoggingSettings] = None


class JsonLogFormatter(logging.Formatter):
    """Render log records as structured JSON lines."""

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        timestamp = datetime.fromtimestamp(record.created, timezone.utc).isoformat()
        payload: Dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
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


def _resolve_level(level_value: Optional[str]) -> int:
    if level_value is None:
        return logging.getLevelNamesMapping().get(DEFAULT_LOG_LEVEL, logging.INFO)
    if isinstance(level_value, int):
        return level_value
    upper = level_value.upper()
    if upper.isdigit():
        return int(upper)
    mapping = logging.getLevelNamesMapping()
    if upper not in mapping:
        raise ValueError(f"Unknown log level: {level_value}")
    return mapping[upper]


def _coerce_positive_int(candidate: Optional[Any], default: int) -> int:
    if candidate is None:
        return default
    try:
        value = int(candidate)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
        raise ValueError(f"Invalid integer value: {candidate}") from exc
    if value <= 0:
        raise ValueError(f"Value must be positive: {candidate}")
    return value


def _read_logging_section(config_path: Optional[str]) -> Mapping[str, Any]:
    if not config_path:
        return {}
    try:
        with open(config_path, "rb") as fh:
            data = tomllib.load(fh)
    except FileNotFoundError:
        return {}
    section = data.get("logging", {})
    return section if isinstance(section, dict) else {}


def resolve_logging_settings(
    *,
    config_path: Optional[str] = None,
    level_override: Optional[str] = None,
    format_override: Optional[str] = None,
    file_override: Optional[str] = None,
    max_bytes_override: Optional[int] = None,
    backup_count_override: Optional[int] = None,
) -> LoggingSettings:
    config_section = _read_logging_section(config_path)

    level_value = (
        level_override
        or os.getenv(ENV_LOG_LEVEL)
        or config_section.get("level")
        or DEFAULT_LOG_LEVEL
    )
    format_value = (
        format_override
        or os.getenv(ENV_LOG_FORMAT)
        or config_section.get("format")
        or DEFAULT_LOG_FORMAT
    )

    file_value = file_override or os.getenv(ENV_LOG_FILE) or config_section.get("file")
    file_path = str(file_value).strip() if file_value else None
    if file_path == "":
        file_path = None

    max_bytes_value = (
        max_bytes_override
        or os.getenv(ENV_LOG_MAX_BYTES)
        or config_section.get("max_bytes")
    )
    backup_count_value = (
        backup_count_override
        or os.getenv(ENV_LOG_BACKUP_COUNT)
        or config_section.get("backup_count")
    )

    resolved_level = _resolve_level(level_value)
    resolved_format = format_value.lower()
    if resolved_format not in {LOG_FORMAT_TEXT, LOG_FORMAT_JSON}:
        raise ValueError(f"Unsupported log format: {format_value}")

    resolved_max_bytes = _coerce_positive_int(max_bytes_value, DEFAULT_MAX_BYTES)
    resolved_backup_count = _coerce_positive_int(
        backup_count_value, DEFAULT_BACKUP_COUNT
    )

    return LoggingSettings(
        level=resolved_level,
        format=resolved_format,
        file_path=file_path,
        max_bytes=resolved_max_bytes,
        backup_count=resolved_backup_count,
    )


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

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(settings.level)
    console_handler.setFormatter(_build_formatter(settings.format))
    root_logger.addHandler(console_handler)

    if settings.file_path:
        file_handler = RotatingFileHandler(
            settings.file_path,
            maxBytes=settings.max_bytes,
            backupCount=settings.backup_count,
        )
        file_handler.setLevel(settings.level)
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
    "LoggingSettings",
    "resolve_logging_settings",
    "configure_logging",
    "get_logger",
    "attach_request_context",
    "log_event",
    "log_search_event",
    "log_rating_event",
]
