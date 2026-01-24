from __future__ import annotations

import io
import logging
import sys
import uuid
from collections.abc import MutableMapping
from logging.handlers import RotatingFileHandler
from typing import Any, cast

import structlog
from fastmcp import Context
from structlog.typing import Processor

from birre.config.settings import LOG_FORMAT_JSON, LoggingSettings

BoundLogger = structlog.stdlib.BoundLogger

_configured_settings: LoggingSettings | None = None


def _prepare_utf8_stream(stream: Any | None) -> Any:
    if stream is None:
        stream = sys.stderr

    text_stream = stream
    reconfigure = getattr(text_stream, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(encoding="utf-8", errors="replace")
            return text_stream
        except Exception:  # pragma: no cover - fallback wrapper
            pass

    encoding = getattr(text_stream, "encoding", "") or ""
    errors = getattr(text_stream, "errors", "") or ""
    if encoding.lower() == "utf-8" and errors == "replace":
        return text_stream

    buffer = getattr(text_stream, "buffer", None)
    if buffer is not None:
        try:
            return io.TextIOWrapper(
                buffer,
                encoding="utf-8",
                errors="replace",
                write_through=True,
            )
        except Exception:  # pragma: no cover - fallback to original stream
            return text_stream

    return text_stream


class Utf8StreamHandler(logging.StreamHandler[Any]):
    """Stream handler that never raises on Unicode encoding errors."""

    def __init__(self, stream: Any | None = None) -> None:
        prepared_stream = _prepare_utf8_stream(stream)
        super().__init__(prepared_stream)
        self.encoding = "utf-8"
        self.errors = "replace"

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            stream = self.stream
            try:
                stream.write(msg + self.terminator)
            except UnicodeEncodeError:
                data = (msg + self.terminator).encode("utf-8", "replace")
                buffer = getattr(stream, "buffer", None)
                if buffer is not None:
                    buffer.write(data)
                else:
                    stream.write(data.decode("utf-8", "replace"))
            except (ValueError, OSError):
                # Stream was closed during test teardown or other scenarios
                pass
            self.flush()
        except Exception:  # pragma: no cover - defensive
            self.handleError(record)


def _strip_exc_info(
    logger: logging.Logger,
    name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    exc_info = event_dict.pop("exc_info", None)
    if not exc_info:
        return event_dict
    if isinstance(exc_info, BaseException):
        event_dict["error"] = str(exc_info)
    elif isinstance(exc_info, tuple) and len(exc_info) >= 2:
        event_dict["error"] = str(exc_info[1])
    return event_dict


def _single_line_renderer(
    logger: logging.Logger,
    name: str,
    event_dict: MutableMapping[str, Any],
) -> str:
    timestamp = event_dict.pop("timestamp", None)
    level = event_dict.pop("level", None)
    logger_name = event_dict.pop("logger", None)
    event = str(event_dict.pop("event", ""))
    exception_text = event_dict.pop("exception", None)
    exc_info_value = event_dict.pop("exc_info", None)

    prefix = event
    if level:
        prefix = f"{level}: {event}".strip()

    extras = " ".join(f"{key}={event_dict[key]}" for key in sorted(event_dict))
    parts = [part for part in (prefix, extras) if part]
    if timestamp:
        parts.append(f"ts={timestamp}")
    if logger_name:
        parts.append(f"logger={logger_name}")
    if exception_text:
        parts.append(exception_text)
    elif exc_info_value:
        parts.append(str(exc_info_value))
    return " ".join(parts)


def _build_processors(json_logs: bool, debug_enabled: bool) -> list[Processor]:
    processors: list[Processor] = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    if debug_enabled:
        processors.append(structlog.processors.StackInfoRenderer())
        processors.append(structlog.processors.format_exc_info)
    else:
        processors.append(cast(Processor, _strip_exc_info))
    if json_logs:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(cast(Processor, _single_line_renderer))
    return processors


def _configure_structlog(settings: LoggingSettings) -> None:
    json_logs = settings.format == LOG_FORMAT_JSON
    debug_enabled = settings.level <= logging.DEBUG
    structlog.configure(
        processors=_build_processors(json_logs, debug_enabled),
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

    console_handler = _build_handler(settings.level, Utf8StreamHandler(sys.stderr))
    root_logger.addHandler(console_handler)

    if settings.file_path:
        file_handler = _build_handler(
            settings.level,
            RotatingFileHandler(
                settings.file_path,
                maxBytes=settings.max_bytes,
                backupCount=settings.backup_count,
                encoding="utf-8",
            ),
        )
        root_logger.addHandler(file_handler)

    _configure_structlog(settings)
    _configured_settings = settings


def get_logger(name: str) -> BoundLogger:
    return cast(BoundLogger, structlog.get_logger(name))


def _first_non_empty_str(values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return None


def _extract_request_id(ctx: Context | None) -> str | None:
    if ctx is None:
        return None

    candidate_attrs = ("request_id", "call_id", "id")
    direct_match = _first_non_empty_str(
        getattr(ctx, attr, None) for attr in candidate_attrs
    )
    if direct_match:
        return direct_match

    metadata = getattr(ctx, "metadata", None)
    if isinstance(metadata, dict):
        return _first_non_empty_str(metadata.get(key) for key in candidate_attrs)
    return None


def attach_request_context(
    logger: BoundLogger,
    ctx: Context | None = None,
    *,
    request_id: str | None = None,
    tool: str | None = None,
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
    ctx: Context | None = None,
    message: str | None = None,
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
    ctx: Context | None = None,
    company_name: str | None = None,
    company_domain: str | None = None,
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
    ctx: Context | None = None,
    company_guid: str | None = None,
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
