"""Domain-specific error types for BiRRe."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum

import httpx

_TLS_INTERCEPT_MARKERS: tuple[str, ...] = (
    "self-signed certificate in certificate chain",
    "certificate verify failed: self signed certificate in certificate chain",
)


class ErrorCode(str, Enum):
    """Domain error codes."""

    TLS_CERT_CHAIN_INTERCEPTED = "TLS_CERT_CHAIN_INTERCEPTED"
    TLS_HANDSHAKE_ERROR = "TLS_HANDSHAKE_ERROR"


@dataclass(frozen=True)
class ErrorContext:
    """Structured context captured for a domain error."""

    tool: str
    op: str
    host: str
    code: str


class BirreError(Exception):
    """Base class for domain errors raised by BiRRe."""

    code: str = "UNKNOWN"

    def __init__(
        self,
        message: str,
        *,
        context: ErrorContext,
        hints: Sequence[str] = (),
    ) -> None:
        super().__init__(message)
        self._context = context
        self._hints: tuple[str, ...] = tuple(hints)

    @property
    def context(self) -> ErrorContext:
        return self._context

    @property
    def hints(self) -> tuple[str, ...]:
        return self._hints

    @property
    def user_message(self) -> str:
        return str(self)

    def log_fields(self) -> dict[str, str]:
        return {
            "tool": self._context.tool,
            "op": self._context.op,
            "host": self._context.host,
            "code": self._context.code,
        }


class TlsCertificateChainInterceptedError(BirreError):
    """TLS handshake failure caused by an interception proxy."""

    code = ErrorCode.TLS_CERT_CHAIN_INTERCEPTED.value

    def __init__(self, *, context: ErrorContext) -> None:
        summary = (
            f"TLS verification failed for {context.host}: self-signed certificate in chain "
            "(interception proxy likely)."
        )
        next_step = "Configure corporate CA bundle or run with --allow-insecure-tls (testing only)."
        super().__init__(
            f"{summary} {next_step}",
            context=context,
            hints=(
                "set BIRRE_CA_BUNDLE=/path/to/corp-root.pem or run with "
                "--allow-insecure-tls (testing only)",
            ),
        )
        self.summary = summary
        self.next_step = next_step


def _iter_exception_messages(exc: BaseException) -> Iterable[str]:
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        message = " ".join(str(arg) for arg in getattr(current, "args", ()) if arg)
        yield message or str(current)
        current = current.__cause__ or current.__context__


def _matches_intercept_marker(exc: BaseException) -> bool:
    for message in _iter_exception_messages(exc):
        lowered = message.lower()
        if any(marker in lowered for marker in _TLS_INTERCEPT_MARKERS):
            return True
    return False


def _coerce_operation_from_request(request: httpx.Request | None) -> tuple[str, str]:
    if request is None:
        return "UNKNOWN", "unknown"
    method = request.method or "UNKNOWN"
    path = (
        request.url.raw_path.decode("utf-8", "ignore")
        if request.url.raw_path
        else request.url.path
    )
    if not path:
        path = "/"
    return method.upper(), path


def classify_request_error(
    exc: BaseException,
    *,
    tool_name: str,
) -> BirreError | None:
    """Map HTTP client errors to BiRRe domain errors when possible."""

    request: httpx.Request | None
    if isinstance(exc, httpx.RequestError) and _matches_intercept_marker(exc):
        request = exc.request
    elif _matches_intercept_marker(exc):
        request_attr = getattr(exc, "request", None)
        request = request_attr if isinstance(request_attr, httpx.Request) else None
    else:
        cause = getattr(exc, "__cause__", None)
        if isinstance(cause, BaseException) and _matches_intercept_marker(cause):
            request_attr = getattr(cause, "request", None)
            request = request_attr if isinstance(request_attr, httpx.Request) else None
        else:
            return None

    method, path = _coerce_operation_from_request(request)
    host = "unknown"
    if request is not None and request.url.host:
        host = request.url.host

    context = ErrorContext(
        tool=tool_name,
        op=f"{method} {path}",
        host=host,
        code=TlsCertificateChainInterceptedError.code,
    )
    return TlsCertificateChainInterceptedError(context=context)


__all__ = [
    "ErrorCode",
    "BirreError",
    "ErrorContext",
    "TlsCertificateChainInterceptedError",
    "classify_request_error",
]
