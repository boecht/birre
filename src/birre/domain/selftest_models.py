"""Data structures representing self-test results and diagnostic failures."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from birre.infrastructure.errors import ErrorCode
from birre.infrastructure.logging import BoundLogger


@dataclass
class DiagnosticFailure:
    """Record of a diagnostic test failure."""

    tool: str
    stage: str
    message: str
    mode: str | None = None
    exception: BaseException | None = None
    category: str | None = None


@dataclass
class AttemptReport:
    """Report of a single diagnostic attempt (e.g., with/without TLS fallback)."""

    label: str
    success: bool
    failures: list[DiagnosticFailure]
    notes: list[str]
    allow_insecure_tls: bool
    ca_bundle: str | None
    online_success: bool | None
    discovered_tools: list[str]
    missing_tools: list[str]
    tools: dict[str, dict[str, Any]]


@dataclass
class ContextDiagnosticsResult:
    """Result of diagnostic tests for a specific context (e.g., 'standard', 'risk_manager')."""

    name: str
    success: bool
    degraded: bool
    report: dict[str, Any]


@dataclass
class SelfTestResult:
    """Result of running BiRRe self-tests/diagnostics."""

    success: bool
    degraded: bool
    summary: dict[str, Any]
    contexts: tuple[str, ...]
    alerts: tuple[str, ...] = ()

    def exit_code(self) -> int:
        """Determine exit code based on test results.

        Returns:
            0: All tests passed
            1: Tests failed
            2: Tests degraded or TLS interception detected
        """
        if ErrorCode.TLS_CERT_CHAIN_INTERCEPTED.value in self.alerts:
            return 2
        if not self.success:
            return 1
        if self.degraded:
            return 2
        return 0


# Backward compatibility alias
HealthcheckResult = SelfTestResult


class _MockSelfTestContext:
    """Mock context object for diagnostic tool invocations.

    Simulates the MCP Context interface for selftest tool execution.
    Provides logging methods and metadata for diagnostic tool invocations.
    """

    def __init__(self, *, context: str, tool_name: str, logger: BoundLogger) -> None:
        self._context = context
        self._tool_name = tool_name
        self._logger = logger
        self._request_id = f"healthcheck-{context}-{tool_name}-{uuid4().hex}"
        self.metadata: dict[str, Any] = {
            "healthcheck": True,
            "context": context,
            "tool": tool_name,
        }
        self.tool = tool_name

    async def info(self, message: str) -> None:
        """Log an info message."""
        await asyncio.sleep(0)
        self._logger.info(
            "healthcheck.ctx.info",
            message=message,
            request_id=self._request_id,
            tool=self._tool_name,
        )

    async def warning(self, message: str) -> None:
        """Log a warning message."""
        await asyncio.sleep(0)
        self._logger.warning(
            "healthcheck.ctx.warning",
            message=message,
            request_id=self._request_id,
            tool=self._tool_name,
        )

    async def error(self, message: str) -> None:
        """Log an error message."""
        await asyncio.sleep(0)
        self._logger.error(
            "healthcheck.ctx.error",
            message=message,
            request_id=self._request_id,
            tool=self._tool_name,
        )

    @property
    def request_id(self) -> str:
        """Get the unique request ID for this healthcheck invocation."""
        return self._request_id

    @property
    def call_id(self) -> str:
        """Get the unique call ID (alias for request_id)."""
        return self._request_id


__all__ = [
    "DiagnosticFailure",
    "AttemptReport",
    "ContextDiagnosticsResult",
    "SelfTestResult",
    "HealthcheckResult",
]
