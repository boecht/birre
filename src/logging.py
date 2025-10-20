from __future__ import annotations

import logging
import sys
import uuid
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Optional

import structlog
from structlog.typing import Processor
from fastmcp import Context

from src.settings import LOG_FORMAT_JSON, LoggingSettings

BoundLogger = structlog.stdlib.BoundLogger

_configured_settings: Optional[LoggingSettings] = None


def _build_processors(json_logs: bool) -> list[Processor]:
    processors: list[Processor] = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    if json_logs:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=False))
    return processors


def _configure_structlog(settings: LoggingSettings) -> None:
    json_logs = settings.format == LOG_FORMAT_JSON
    structlog.configure(
        processors=_build_processors(json_logs),
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _build_handler(level: int, handler: logging.Handler) -> logging.Handler:
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(message)s"))
    return handler


def configure_logging(settings: LoggingSettings) -> None:
    global _configured_settings

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(settings.level)

    console_handler = _build_handler(settings.level, logging.StreamHandler(sys.stderr))
    root_logger.addHandler(console_handler)

    if settings.file_path:
        file_handler = _build_handler(
            settings.level,
            RotatingFileHandler(
                settings.file_path,
                maxBytes=settings.max_bytes,
                backupCount=settings.backup_count,
            ),
        )
        root_logger.addHandler(file_handler)

    _configure_structlog(settings)
    _configured_settings = settings


def get_logger(name: str) -> BoundLogger:
    return structlog.get_logger(name)


def _first_non_empty_str(values: Any) -> Optional[str]:
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


def attach_request_context(
    logger: BoundLogger,
    ctx: Optional[Context] = None,
    *,
    request_id: Optional[str] = None,
    tool: Optional[str] = None,
    **base_fields: Any,
) -> BoundLogger:
    resolved_request_id = request_id or _extract_request_id(ctx) or str(uuid.uuid4())
    bound = logger.bind(request_id=resolved_request_id)

    inferred_tool = tool
    if inferred_tool is None and ctx is not None:
        inferred_tool = getattr(ctx, "tool", None) or getattr(ctx, "tool_name", None)
    if inferred_tool:
        bound = bound.bind(tool=inferred_tool)

    extras = {key: value for key, value in base_fields.items() if value is not None}
    if extras:
        bound = bound.bind(**extras)

    return bound


def log_event(
    logger: BoundLogger,
    event: str,
    *,
    level: int = logging.INFO,
    ctx: Optional[Context] = None,
    message: Optional[str] = None,
    **fields: Any,
) -> None:
    bound = attach_request_context(logger, ctx)
    event_fields = {key: value for key, value in fields.items() if value is not None}
    event_logger = bound.bind(event=event)
    if event_fields:
        event_logger = event_logger.bind(**event_fields)
    event_logger.log(level, message or event)


def log_search_event(
    logger: BoundLogger,
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
    logger: BoundLogger,
    action: str,
    *,
    ctx: Optional[Context] = None,
    company_guid: Optional[str] = None,
    **fields: Any,
) -> None:
    event_name = f"company_rating.{action}"
    log_event(logger, event_name, ctx=ctx, company_guid=company_guid, **fields)


__all__ = [
    "BoundLogger",
    "configure_logging",
    "get_logger",
    "attach_request_context",
    "log_event",
    "log_search_event",
    "log_rating_event",
]
