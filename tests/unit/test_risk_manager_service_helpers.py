from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastmcp import Context

from birre.domain.risk_manager import service as risk_service
from birre.infrastructure.logging import get_logger


class StubContext(Context):
    def __init__(self) -> None:
        self.tool = "test"
        self._request_id = "req-1"
        self.infos: list[str] = []
        self.warnings: list[str] = []
        self.errors: list[str] = []

    async def info(self, message: str) -> None:  # type: ignore[override]
        await asyncio.sleep(0)
        self.infos.append(message)

    async def warning(self, message: str) -> None:  # type: ignore[override]
        await asyncio.sleep(0)
        self.warnings.append(message)

    async def error(self, message: str) -> None:  # type: ignore[override]
        await asyncio.sleep(0)
        self.errors.append(message)

    @property
    def request_id(self) -> str:  # type: ignore[override]
        return self._request_id

    @property
    def call_id(self) -> str:  # type: ignore[override]
        return self._request_id


def test_guid_and_search_helpers() -> None:
    assert risk_service._coerce_guid_list("a , b,,") == ["a", "b"]
    assert risk_service._coerce_guid_list(["x", " ", 5]) == ["x", "5"]
    assert risk_service._normalize_action("Subscribe") == "add"
    assert risk_service._normalize_action("UNSUBSCRIBE") == "delete"
    assert risk_service._normalize_action("noop") is None

    params, term = risk_service._build_company_search_params("Acme", None)
    assert params["name"] == "Acme" and term == "Acme"
    params_domain, term_domain = risk_service._build_company_search_params(
        "Acme", "acme.com"
    )
    assert params_domain["domain"] == "acme.com" and term_domain == "acme.com"
    assert "error" in risk_service._validate_company_search_inputs(None, None)
    assert risk_service._validate_company_search_inputs("Acme", None) is None


def test_tree_helpers_extract_parent_path() -> None:
    tree = {
        "guid": "root",
        "children": [
            {
                "guid": "parent",
                "children": [{"guid": "child", "children": []}],
            }
        ],
    }
    path = risk_service._find_company_in_tree(tree, "child")
    assert path == ["root", "parent"]
    node = risk_service._find_node_in_tree(tree, "parent")
    assert node and node["guid"] == "parent"
    parents = risk_service._extract_parent_guids(tree, "child")
    assert parents == ["parent", "root"]
    assert risk_service._extract_parent_guids(tree, "missing") == []


@pytest.mark.asyncio
async def test_fetch_folder_memberships_success_and_failure() -> None:
    logger = get_logger("test.folders")
    ctx = StubContext()

    async def call_success(
        tool_name: str, _ctx: Context, params: dict[str, Any]
    ) -> list[dict[str, Any]]:
        import asyncio

        await asyncio.sleep(0)
        assert tool_name == "getFolders" and params == {}
        return [
            {"name": "Ops", "companies": ["guid-1", "extra"]},
            {"description": "Legacy", "companies": ["guid-2"]},
        ]

    mapping = await risk_service._fetch_folder_memberships(
        call_success,
        ctx,
        ["guid-1", "guid-2"],
        logger=logger,
    )
    assert mapping == {"guid-1": ["Ops"], "guid-2": ["Legacy"]}

    async def call_failure(*_: Any, **__: Any) -> list[dict[str, Any]]:
        raise RuntimeError("boom")

    fallback = await risk_service._fetch_folder_memberships(
        call_failure,
        ctx,
        ["guid-1"],
        logger=logger,
    )
    assert fallback == {}
    assert ctx.warnings  # warning recorded for failed fetch


def test_candidate_extraction_and_enrichment() -> None:
    raw = {
        "results": [
            {
                "guid": "guid-1",
                "name": "Acme",
                "primary_domain": "acme.com",
                "details": {"employee_count": "50"},
                "in_portfolio": False,
                "subscription_type": "continuous",
            }
        ]
    }
    candidates = risk_service._extract_search_candidates(raw)
    candidate = candidates[0]
    detail = {
        "guid": "guid-1",
        "name": "Acme Holdings",
        "primary_domain": "acme.com",
        "homepage": "https://acme.com",
        "description": "Security",
        "people_count": 49,
        "current_rating": "90",
        "in_spm_portfolio": True,
        "subscription_type": "continuous",
        "subscription_end_date": "2025-01-01",
    }
    folders = ["Ops"]
    entry = risk_service._format_result_entry(candidate, detail, folders)
    assert entry["label"].startswith("Acme")
    assert entry["rating"] == 90 and entry["subscription"]["active"] is True

    enriched = risk_service._enrich_candidates(
        candidates, {"guid-1": detail}, {"guid-1": folders}
    )
    assert enriched[0]["subscription"]["folders"] == folders

    order = risk_service._build_guid_order(candidates + [{"guid": " ", "name": "bad"}])
    assert order == ["guid-1"]

    non_subscribed = risk_service._identify_non_subscribed_companies(
        [
            {"guid": "guid-1", "in_portfolio": False},
            {"guid": "guid-2", "in_portfolio": True},
        ]
    )
    assert non_subscribed == ["guid-1"]

    assert risk_service._normalize_candidate_results({"companies": [1, 2]}) == [1, 2]
    assert risk_service._normalize_candidate_results({"unexpected": 5}) == [
        {"unexpected": 5}
    ]


@pytest.mark.asyncio
async def test_bulk_subscribe_and_unsubscribe_paths() -> None:
    logger = get_logger("test.bulk")
    ctx = StubContext()
    payloads: list[dict[str, Any]] = []

    async def call_success(
        tool_name: str, _ctx: Context, params: dict[str, Any]
    ) -> dict[str, Any]:
        import asyncio

        await asyncio.sleep(0)
        payloads.append(params)
        return {"status": "ok"}

    subscribed = await risk_service._bulk_subscribe_companies(
        call_success,
        ctx,
        ["g1", "g2"],
        logger=logger,
        folder="Ops",
        subscription_type="managed",
    )
    assert subscribed == {"g1", "g2"}
    assert payloads[-1]["add"][0]["folder"] == ["Ops"]

    async def call_failure(*_: Any, **__: Any) -> dict[str, Any]:
        raise RuntimeError("boom")

    failed = await risk_service._bulk_subscribe_companies(
        call_failure,
        ctx,
        ["g1"],
        logger=logger,
        folder=None,
        subscription_type=None,
    )
    assert failed == set()
    assert ctx.warnings  # warning recorded for failure

    delete_payloads: list[dict[str, Any]] = []

    async def call_delete(
        tool_name: str, _ctx: Context, params: dict[str, Any]
    ) -> dict[str, Any]:
        import asyncio

        await asyncio.sleep(0)
        delete_payloads.append(params)
        return {"status": "ok"}

    await risk_service._bulk_unsubscribe_companies(
        call_delete,
        ctx,
        ["g1"],
        logger=logger,
    )
    assert delete_payloads[0]["delete"][0]["guid"] == "g1"

    await risk_service._bulk_unsubscribe_companies(
        call_failure,
        ctx,
        ["g1"],
        logger=logger,
    )


def test_subscription_payload_and_validation_errors() -> None:
    add_payload = risk_service._build_subscription_payload(
        "add",
        ["g1"],
        folder_guid="folder-1",
        subscription_type="managed",
    )
    assert add_payload["add"][0]["folder"] == ["folder-1"]
    assert add_payload["add"][0]["type"] == "managed"

    delete_payload = risk_service._build_subscription_payload(
        "delete",
        ["g2"],
        folder_guid=None,
        subscription_type=None,
    )
    assert delete_payload == {"delete": [{"guid": "g2"}]}

    summary = risk_service._summarize_bulk_result({"added": ["g1"], "errors": []})
    assert summary["added"] == ["g1"]
    raw_summary = risk_service._summarize_bulk_result("oops")
    assert raw_summary == {"raw": "oops"}

    error_payload = risk_service._manage_subscriptions_error("boom")
    assert error_payload["error"] == "boom"

    action, guids, validation_error = (
        risk_service._validate_manage_subscriptions_inputs("noop", [], default_type="t")
    )
    assert action is None and "Unsupported" in validation_error["error"]

    action, guids, validation_error = (
        risk_service._validate_manage_subscriptions_inputs("add", [], default_type="t")
    )
    assert validation_error["error"].startswith("At least one company")

    action, guids, validation_error = (
        risk_service._validate_manage_subscriptions_inputs(
            "add", ["g1"], default_type=None
        )
    )
    assert "Subscription type" in validation_error["error"]

    action, guids, validation_error = (
        risk_service._validate_manage_subscriptions_inputs(
            "delete", ["g1"], default_type=None
        )
    )
    assert action == "delete" and guids == ["g1"] and validation_error is None


def test_parse_domain_string_and_deduplicate() -> None:
    logger = get_logger("test.request")
    ctx = StubContext()
    _, error = risk_service._parse_domain_string(" ", logger=logger, ctx=ctx)
    assert error and "Provide at least one" in error["error"]

    tokens, error = risk_service._parse_domain_string(
        "Example.com, example.com , new.io", logger=logger, ctx=ctx
    )
    assert error is None
    assert tokens == ["example.com", "example.com", "new.io"]

    unique, duplicates = risk_service._deduplicate_domains(tokens)
    assert unique == ["example.com", "new.io"]
    assert duplicates == ["example.com"]


def test_register_existing_domain_and_entries() -> None:
    order: list[str] = []
    mapping: dict[str, str | None] = {}
    risk_service._register_existing_domain(order, mapping, "a.com", None)
    risk_service._register_existing_domain(order, mapping, "b.com", "B Corp")
    risk_service._register_existing_domain(order, mapping, "a.com", "A Corp")
    entries = risk_service._build_existing_entries(order, mapping)
    assert entries[0].company_name == "A Corp"
    assert entries[1].company_name == "B Corp"


@pytest.mark.asyncio
async def test_partition_submitted_domains_marks_existing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_find(
        _call_v1_tool: Any, _ctx: Any, *, logger: Any, domain: str
    ) -> str | None:
        import asyncio

        await asyncio.sleep(0)
        return "Known" if domain == "existing.com" else None

    monkeypatch.setattr(risk_service, "_find_existing_company", fake_find)
    existing_order: list[str] = []
    existing_mapping: dict[str, str | None] = {}

    logger = get_logger("test.partition")

    remaining = await risk_service._partition_submitted_domains(
        ["existing.com", "fresh.com"],
        call_v1_tool=None,
        ctx=None,
        logger=logger,
        existing_order=existing_order,
        existing_mapping=existing_mapping,
    )

    assert remaining == ["fresh.com"]
    assert existing_order == ["existing.com"]
    assert existing_mapping["existing.com"] == "Known"


def _existing_entries_example() -> list[risk_service.RequestCompanyExistingEntry]:
    return [risk_service.RequestCompanyExistingEntry(domain="existing.com")]


def test_short_circuit_request_company_paths() -> None:
    entries = _existing_entries_example()
    payload = risk_service._short_circuit_request_company(
        dry_run=True,
        submitted_domains=["a.com"],
        existing_entries=entries,
        remaining_domains=["b.com"],
        selected_folder="Ops",
        folder_guid="folder-1",
        folder_created=False,
        csv_body="domain\nb.com",
        folder_pending_reason=None,
    )
    assert payload and payload["status"] == "dry_run"

    all_existing = risk_service._short_circuit_request_company(
        dry_run=False,
        submitted_domains=["a.com"],
        existing_entries=entries,
        remaining_domains=[],
        selected_folder="Ops",
        folder_guid="folder-1",
        folder_created=True,
        csv_body="domain\na.com",
        folder_pending_reason=None,
    )
    assert all_existing and all_existing["status"] == "already_existing"

    none = risk_service._short_circuit_request_company(
        dry_run=False,
        submitted_domains=["a.com"],
        existing_entries=entries,
        remaining_domains=["b.com"],
        selected_folder="Ops",
        folder_guid="folder-1",
        folder_created=False,
        csv_body="domain\nb.com",
        folder_pending_reason=None,
    )
    assert none is None


@pytest.mark.asyncio
async def test_collect_company_trees_filters_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []

    async def fake_tree(
        call_v1_tool: Any,
        ctx: Context,
        guid: str,
        *,
        logger: Any,
    ) -> dict[str, Any] | None:
        await asyncio.sleep(0)
        captured.append(guid)
        if guid == "alpha":
            return {"guid": guid, "tree": True}
        return None

    monkeypatch.setattr(risk_service, "_fetch_company_tree", fake_tree)

    details = {
        "alpha": {"has_company_tree": True},
        "beta": {"has_company_tree": False},
    }

    trees = await risk_service._fetch_company_trees(
        None,
        StubContext(),
        details,
        logger=get_logger("test.collect"),
    )

    assert trees == {"alpha": {"guid": "alpha", "tree": True}}
    assert captured == ["alpha"]


@pytest.mark.asyncio
async def test_process_parent_companies_enriches_relations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_subscribe(
        call_v1_tool: Any,
        ctx: Context,
        *,
        parent_guid: str,
        tree_data: dict[str, Any],
        logger: Any,
        defaults: Any,
    ) -> tuple[set[str], dict[str, Any] | None]:
        await asyncio.sleep(0)
        return {parent_guid}, {"guid": parent_guid, "has_company_tree": False}

    monkeypatch.setattr(risk_service, "_subscribe_and_fetch_parent", fake_subscribe)

    trees = {
        "child-guid": {
            "guid": "parent-guid",
            "children": [{"guid": "child-guid", "children": []}],
        }
    }
    details = {"child-guid": {"has_company_tree": True}}
    defaults = risk_service.CompanySearchDefaults(
        folder="Ops",
        subscription_type="managed",
        limit=5,
    )

    (
        parent_details,
        parent_children,
        ephemerals,
    ) = await risk_service._process_parent_companies(
        None,
        StubContext(),
        trees=trees,
        details=details,
        logger=get_logger("test.parents"),
        defaults=defaults,
    )

    assert parent_details["parent-guid"]["guid"] == "parent-guid"
    assert parent_children["parent-guid"] == ["child-guid"]
    assert ephemerals == {"parent-guid"}


@pytest.mark.asyncio
async def test_initialize_request_company_state_error() -> None:
    logger = get_logger("test.init.error")
    state, error = await risk_service._initialize_request_company_state(
        domains="",
        folder=None,
        default_folder=None,
        default_folder_guid=None,
        call_v1_tool=None,
        ctx=None,
        logger=logger,
    )
    assert state is None
    assert error and "Provide at least one domain" in error["error"]


@pytest.mark.asyncio
async def test_initialize_request_company_state_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_partition(*_args: Any, **_kwargs: Any) -> list[str]:
        await asyncio.sleep(0)
        return ["new.io"]

    monkeypatch.setattr(risk_service, "_partition_submitted_domains", fake_partition)

    logger = get_logger("test.init.success")
    state, error = await risk_service._initialize_request_company_state(
        domains="dup.com,dup.com,new.io",
        folder="Ops",
        default_folder="Ops",
        default_folder_guid="cached-guid",
        call_v1_tool=None,
        ctx=None,
        logger=logger,
    )
    assert error is None and state is not None
    assert state.remaining_domains == ["new.io"]
    assert state.existing_entries[0].domain == "dup.com"
    assert state.folder_guid == "cached-guid"


@pytest.mark.asyncio
async def test_finalize_request_company_state_returns_folder_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = risk_service.RequestCompanyState(
        submitted_domains=["a.com"],
        remaining_domains=["b.com"],
        existing_entries=[],
        selected_folder="Ops",
        folder_guid=None,
        folder_created=False,
        folder_pending_reason=None,
        csv_body="domain\nb.com",
    )

    async def fake_maybe(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        await asyncio.sleep(0)
        return {"error": "folder missing"}

    monkeypatch.setattr(
        risk_service,
        "_maybe_resolve_request_company_folder",
        fake_maybe,
    )

    result = await risk_service._finalize_request_company_state(
        state,
        dry_run=False,
        call_v1_tool=None,
        ctx=None,
        logger=get_logger("test.finalize.error"),
        default_folder=None,
        default_folder_guid=None,
    )
    assert result == {"error": "folder missing"}


@pytest.mark.asyncio
async def test_finalize_request_company_state_returns_short_circuit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = risk_service.RequestCompanyState(
        submitted_domains=["a.com"],
        remaining_domains=["b.com"],
        existing_entries=[],
        selected_folder=None,
        folder_guid=None,
        folder_created=False,
        folder_pending_reason=None,
        csv_body="domain\nb.com",
    )

    calls: list[int] = []

    async def fake_maybe(*_args: Any, **_kwargs: Any) -> dict[str, Any] | None:
        await asyncio.sleep(0)
        return None

    def fake_short(state_arg: risk_service.RequestCompanyState, *, dry_run: bool):
        calls.append(1)
        if len(calls) == 1:
            return None
        return {"status": "dry_run", "folder": state_arg.selected_folder}

    monkeypatch.setattr(
        risk_service,
        "_maybe_resolve_request_company_folder",
        fake_maybe,
    )
    monkeypatch.setattr(
        risk_service,
        "_short_circuit_request_company_state",
        fake_short,
    )

    result = await risk_service._finalize_request_company_state(
        state,
        dry_run=True,
        call_v1_tool=None,
        ctx=None,
        logger=get_logger("test.finalize.short"),
        default_folder=None,
        default_folder_guid=None,
    )
    assert result == {"status": "dry_run", "folder": None}


def test_serialize_and_build_bulk_payload() -> None:
    csv_body = risk_service._serialize_bulk_csv(["one.com", "two.com"])
    csv_lines = csv_body.strip().splitlines()
    assert csv_lines == ["domain", "one.com", "two.com"]
    payload = risk_service._build_bulk_payload(csv_body, "folder-1")
    assert payload["file"].splitlines()[:3] == ["domain", "one.com", "two.com"]
    assert payload["folder_guid"] == "folder-1"
