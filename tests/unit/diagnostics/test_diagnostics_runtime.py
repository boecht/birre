from __future__ import annotations

import asyncio

from birre.application import diagnostics as dx
from birre.application.startup import OnlineStartupResult
from birre.config.settings import RuntimeSettings


class DummyLogger:
    def bind(self, **kwargs):  # noqa: D401
        return self

    def info(self, *a, **k):
        return None

    def warning(self, *a, **k):
        return None

    def error(self, *a, **k):
        return None

    def exception(self, *a, **k):
        return None

    def critical(self, *a, **k):
        return None


def _rs(**kwargs):  # type: ignore[no-untyped-def]
    defaults = {
        "api_key": "k",
        "subscription_folder": None,
        "subscription_type": None,
        "subscription_folder_guid": None,
        "context": "standard",
        "risk_vector_filter": None,
        "max_findings": 10,
        "skip_startup_checks": False,
        "debug": False,
        "allow_insecure_tls": False,
        "ca_bundle_path": None,
    }
    defaults.update(kwargs)
    return RuntimeSettings(**defaults)


def test_run_offline_checks_true_false(monkeypatch) -> None:  # noqa: ANN001
    called = {"n": 0}

    def fake_offline(**k):  # type: ignore[no-untyped-def]
        called["n"] += 1
        return called["n"] == 1

    monkeypatch.setattr(dx, "run_offline_startup_checks", fake_offline)
    assert dx.run_offline_checks(_rs(), DummyLogger()) is True
    assert dx.run_offline_checks(_rs(), DummyLogger()) is False


def test_run_online_checks_success_and_cleanup(monkeypatch) -> None:  # noqa: ANN001
    # Resolve TLS verification
    monkeypatch.setattr(dx, "_resolve_tls_verification", lambda *a, **k: True)

    class FakeClient:
        async def aclose(self):  # noqa: D401
            await asyncio.sleep(0)
            return None

    class FakeApi:
        def __init__(self):  # noqa: D401
            self._client = FakeClient()

        def shutdown(self):  # noqa: D401
            return None

    monkeypatch.setattr(dx, "create_v1_api_server", lambda *a, **k: FakeApi())

    async def fake_checks(**k):  # type: ignore[no-untyped-def]
        await asyncio.sleep(0)
        return OnlineStartupResult(success=True, subscription_folder_guid="guid-1")

    monkeypatch.setattr(dx, "run_online_startup_checks", fake_checks)

    # Use asyncio.run for the sync runner (creates new loop)
    def run_sync(coro):  # noqa: ANN001
        return asyncio.run(coro)

    runtime_settings = _rs()
    assert (
        dx.run_online_checks(
            runtime_settings,
            DummyLogger(),
            run_sync=run_sync,
        )
        is True
    )
    assert runtime_settings.subscription_folder_guid == "guid-1"


def test_run_online_checks_failure(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(dx, "_resolve_tls_verification", lambda *a, **k: False)
    monkeypatch.setattr(dx, "create_v1_api_server", lambda *a, **k: object())

    async def fake_checks(**k):  # type: ignore[no-untyped-def]
        await asyncio.sleep(0)
        return OnlineStartupResult(success=False)

    monkeypatch.setattr(dx, "run_online_startup_checks", fake_checks)

    # Use asyncio.run for the sync runner (creates new loop)
    def run_sync(coro):  # noqa: ANN001
        return asyncio.run(coro)

    assert (
        dx.run_online_checks(
            _rs(),
            DummyLogger(),
            run_sync=run_sync,
        )
        is False
    )
