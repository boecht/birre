from __future__ import annotations

import logging
import sys
import uuid
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Optional, Union, cast

import structlog
from fastmcp import Context
from structlog.stdlib import BoundLogger, ProcessorFormatter, get_logger as _get_logger

from src.config import LOG_FORMAT_JSON, LoggingSettings


LoggerLike = Union[BoundLogger, logging.Logger]

_configured_settings: Optional[LoggingSettings] = None


def _add_channel(_: logging.Logger, __: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Populate a short channel name derived from the logger name."""

    logger_name = event_dict.get("logger")
    if isinstance(logger_name, str) and logger_name:
        event_dict.setdefault("channel", logger_name.split(".")[0])
    return event_dict


def _finalize_event_fields(
    _: logging.Logger, __: str, event_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """Ensure event dictionaries expose explicit event and message fields."""

    original_message = event_dict.get("event")
    event_name = event_dict.pop("_event_name", None)
    explicit_message = event_dict.pop("_log_message", None)

    if event_name is not None:
        event_dict["event"] = event_name

    if explicit_message is not None:
        event_dict["message"] = explicit_message
    elif original_message is not None:
        event_dict.setdefault("message", original_message)

    return event_dict


def _build_renderer(format_name: str) -> structlog.types.Processor:
    if format_name == LOG_FORMAT_JSON:
        return structlog.processors.JSONRenderer()
    return structlog.dev.ConsoleRenderer(colors=False)


def configure_logging(settings: LoggingSettings) -> None:
    """Initialise the logging infrastructure using structlog."""

    global _configured_settings

    renderer = _build_renderer(settings.format)

    pre_chain = [
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _add_channel,
        _finalize_event_fields,
    ]

    formatter = ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=pre_chain,
    )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(settings.level)

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(settings.level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    if settings.file_path:
        file_handler = RotatingFileHandler(
            settings.file_path,
            maxBytes=settings.max_bytes,
            backupCount=settings.backup_count,
        )
        file_handler.setLevel(settings.level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _add_channel,
            _finalize_event_fields,
            ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _configured_settings = settings


def get_logger(name: str) -> BoundLogger:
    """Return a structlog bound logger for the provided namespace."""

    return _get_logger(name)


def _first_non_empty_str(values: Any) -> Optional[str]:
    """Return the first truthy string from an iterable of candidates."""

    for value in values:
        if isinstance(value, str) and value:
            return value
    return None


def _extract_request_id(ctx: Optional[Context]) -> Optional[str]:
    if ctx is None:
        return None

    candidate_attrs = ("request_id", "call_id", "id")
    direct_match = _first_non_empty_str(getattr(ctx, attr, None) for attr in candidate_attrs)
    if direct_match:
        return direct_match

    metadata = getattr(ctx, "metadata", None)
    if isinstance(metadata, dict):
        return _first_non_empty_str(metadata.get(key) for key in candidate_attrs)
    return None


def ensure_bound_logger(logger: LoggerLike, *, name: Optional[str] = None) -> BoundLogger:
    """Coerce standard library loggers into structlog ``BoundLogger`` instances."""

    if hasattr(logger, "bind"):
        return cast(BoundLogger, logger)

    resolved_name = name or getattr(logger, "name", None) or "birre"
    return get_logger(resolved_name)


def bind_request_context(
    logger: LoggerLike,
    ctx: Optional[Context] = None,
    *,
    request_id: Optional[str] = None,
    tool: Optional[str] = None,
    **base_fields: Any,
) -> BoundLogger:
    """Bind request metadata onto a logger for contextual logging."""

    base_logger = ensure_bound_logger(logger)
    request_logger = base_logger.new()

    resolved_request_id = request_id or _extract_request_id(ctx) or str(uuid.uuid4())
    bound_fields: Dict[str, Any] = {"request_id": resolved_request_id}

    inferred_tool = tool
    if inferred_tool is None and ctx is not None:
        inferred_tool = getattr(ctx, "tool", None) or getattr(ctx, "tool_name", None)
    if inferred_tool:
        bound_fields["tool"] = inferred_tool

    for key, value in base_fields.items():
        if value is not None:
            bound_fields[key] = value

    return request_logger.bind(**bound_fields)


def log_event(
    logger: LoggerLike,
    event: str,
    *,
    level: int = logging.INFO,
    ctx: Optional[Context] = None,
    message: Optional[str] = None,
    **fields: Any,
) -> None:
    event_fields: Dict[str, Any] = {"_event_name": event}
    if message is not None:
        event_fields["_log_message"] = message
    for key, value in fields.items():
        if value is not None:
            event_fields[key] = value

    bound_logger = bind_request_context(logger, ctx)
    bound_logger.bind(**event_fields).log(level, message or event)


def log_search_event(
    logger: LoggerLike,
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
    logger: LoggerLike,
    action: str,
    *,
    ctx: Optional[Context] = None,
    company_guid: Optional[str] = None,
    **fields: Any,
) -> None:
    event_name = f"company_rating.{action}"
    log_event(logger, event_name, ctx=ctx, company_guid=company_guid, **fields)


__all__ = [
    "ensure_bound_logger",
    "bind_request_context",
    "configure_logging",
    "get_logger",
    "log_event",
    "log_search_event",
    "log_rating_event",
]
