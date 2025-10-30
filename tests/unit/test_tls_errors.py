import asyncio
import logging
from typing import Any

import httpx
import pytest

from birre.config.settings import LOG_FORMAT_TEXT, LoggingSettings
from birre.infrastructure.errors import ErrorCode, TlsCertificateChainInterceptedError
from birre.infrastructure.logging import configure_logging, get_logger
from birre.integrations.bitsight.v1_bridge import call_openapi_tool


class _StubContext:
    def __init__(self) -> None:
        self.errors: list[str] = []

    async def info(self, message: str) -> None:  # pragma: no cover - logging helper
        await asyncio.sleep(0)

    async def warning(self, message: str) -> None:  # pragma: no cover - logging helper
        await asyncio.sleep(0)

    async def error(self, message: str) -> None:
        await asyncio.sleep(0)
        self.errors.append(message)


class _FailingServer:
    async def _call_tool_middleware(self, tool_name: str, params: dict[str, Any]):
        await asyncio.sleep(0)
        request = httpx.Request(
            "GET",
            "https://api.bitsighttech.com/v1/companySearch",
        )
        raise httpx.ConnectError(
            "SSL CERTIFICATE_VERIFY_FAILED: self-signed certificate in certificate chain",
            request=request,
        )


@pytest.mark.asyncio
async def test_tls_error_maps_to_domain_error(capfd: "pytest.CaptureFixture[str]") -> None:
    settings = LoggingSettings(
        level=logging.INFO,
        format=LOG_FORMAT_TEXT,
        file_path=None,
        max_bytes=1024,
        backup_count=1,
    )
    configure_logging(settings)
    capfd.readouterr()

    ctx = _StubContext()
    logger = get_logger("birre.test.tls.info")

    with pytest.raises(TlsCertificateChainInterceptedError) as exc_info:
        await call_openapi_tool(
            _FailingServer(),
            "companySearch",
            ctx,
            {},
            logger=logger,
        )

    error = exc_info.value
    assert error.context.code == ErrorCode.TLS_CERT_CHAIN_INTERCEPTED.value
    assert "Configure corporate CA bundle" in error.user_message
    assert ctx.errors
    assert "--allow-insecure-tls" in ctx.errors[-1]

    log_output = capfd.readouterr().err.splitlines()
    assert log_output
    summary_line = log_output[0]
    assert "TLS verification failed for api.bitsighttech.com" in summary_line
    assert "tool=companySearch" in summary_line
    assert "op=GET /v1/companySearch" in summary_line
    assert f"code={ErrorCode.TLS_CERT_CHAIN_INTERCEPTED.value}" in summary_line
    assert "Hint: set BIRRE_CA_BUNDLE=/path/to/corp-root.pem" in log_output[1]
    assert "Traceback" not in "\n".join(log_output)


@pytest.mark.asyncio
async def test_tls_error_emits_traceback_in_debug(capfd: "pytest.CaptureFixture[str]") -> None:
    settings = LoggingSettings(
        level=logging.DEBUG,
        format=LOG_FORMAT_TEXT,
        file_path=None,
        max_bytes=1024,
        backup_count=1,
    )
    configure_logging(settings)
    capfd.readouterr()

    ctx = _StubContext()
    logger = get_logger("birre.test.tls.debug")

    with pytest.raises(TlsCertificateChainInterceptedError):
        await call_openapi_tool(
            _FailingServer(),
            "companySearch",
            ctx,
            {},
            logger=logger,
        )

    output = capfd.readouterr().err
    assert "Traceback" in output
    assert "TLS verification failed" in output
