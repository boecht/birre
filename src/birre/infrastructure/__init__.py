"""Infrastructure utilities (logging, errors, adapters)."""

from birre.infrastructure.errors import (
    BirreError,
    ErrorCode,
    TlsCertificateChainInterceptedError,
    classify_request_error,
)
from birre.infrastructure.logging import (
    BoundLogger,
    configure_logging,
    get_logger,
    log_event,
    log_rating_event,
)

__all__ = [
    "BirreError",
    "ErrorCode",
    "TlsCertificateChainInterceptedError",
    "classify_request_error",
    "BoundLogger",
    "configure_logging",
    "get_logger",
    "log_event",
    "log_rating_event",
]
