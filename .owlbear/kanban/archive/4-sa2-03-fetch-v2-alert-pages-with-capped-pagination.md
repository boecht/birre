---
id: 4
title: 'SA2-03: Fetch v2 alert pages with capped pagination'
status: archived
priority: high
created: 2026-07-10T11:48:10.316142+02:00
updated: 2026-07-10T17:59:53.136760+02:00
tags:
  - security-analyst
  - alert-workflow
  - scope:v2-intake
  - type:build
  - reshaped-v2
parent: 1
depends_on:
  - 2
  - 3
ac:
  - 'AC-1: Given `max_pages=2` and a first v2 alert page with a next-page link, `fetch_v2_alert_pages`
    calls `call_v2_tool` twice and returns two page envelopes.'
  - "AC-2: Given `page_size=50` and `alert_date_gte='2026-07-01'`, the first `fetch_v2_alert_pages`
    query contains `limit=50`, `offset=0`, `alert_date_gte='2026-07-01'`, and `expand='details'`."
  - 'AC-3: Given `max_pages=1` and a first page with a next-page link, `fetch_v2_alert_pages`
    returns metadata warning code `alert_page_cap_reached`.'
  - 'AC-4: Given a v2 response without a list-valued `results` field, `fetch_v2_alert_pages`
    raises `ValueError` with message text containing `results`.'
  - 'AC-5: Given request filters for severity, alert type, and folder, `fetch_v2_alert_pages`
    passes those filter keys to `call_v2_tool`.'
proof_bundle: behavioral
blocked: false
block_reason:
claimed_at:
archival_reason: completed
archival_refs: []
---
Brief: `.owlbear/briefs/draft-birre-alert-workflows/brief.md`

## Scope
Fetch v2 alert pages for the requested window using `expand=details`, deterministic pagination, configured filters, and cap metadata.

## Local Architecture Anchors
- `src/birre/integrations/bitsight/v1_bridge.py` exposes `call_v2_openapi_tool`.
- v2 server creation is assembled in `src/birre/application/server.py`.
- v2 API docs live under `docs/apis/` and resource schemas under `src/birre/resources/apis/`.

## Dependencies
Depends on #2 for caps/request input and #3 for v2 bridge availability.

## Non-Goals
- Alert trigger normalization.
- Company grouping.
- v1 company enrichment.
- Jira-action payload construction.

## Shape Notes
- Scope decision: isolate network paging and cap warnings from downstream normalization so fixture tests can prove request formation and truncation behavior.
- Challenger result: proceed for keeping v2 intake separate from normalization.
- Verification focus: async unit tests with stubbed `call_v2_tool`.

[[2026-07-10T17:58:44+02:00]]
## Builder Notes
- Files changed: `src/birre/domain/security_analyst/alerts.py`, `src/birre/domain/security_analyst/__init__.py`, `tests/unit/test_security_analyst_alerts.py`.
- Implemented `fetch_v2_alert_pages` with deterministic `getAlerts` pagination, `limit`/`offset`, `expand=details`, date/severity/alert-type/folder filters, page/source metadata, cap warning `alert_page_cap_reached`, and validation for a list-valued `results` field.
- Proof: `uv run ruff check src/birre/domain/security_analyst/alerts.py src/birre/domain/security_analyst/__init__.py tests/unit/test_security_analyst_alerts.py` passed. `uv run pytest tests/unit/test_security_analyst_alerts.py` passed: 2 tests.
- Builder-challenger: pass; confirmed AC-1 through AC-5 and found no concrete blockers.
- Follow-up risk: downstream normalization must consume the returned `pages` envelopes and preserve their metadata.

[[2026-07-10T17:59:35+02:00]]
## Verify Notes
- Evidence reviewed: implementation in `src/birre/domain/security_analyst/alerts.py`, public export in `src/birre/domain/security_analyst/__init__.py`, and focused tests in `tests/unit/test_security_analyst_alerts.py`.
- Checks run: `uv run pytest tests/unit/test_security_analyst_alerts.py` passed with 2 tests; `uv run ruff check src/birre/domain/security_analyst/alerts.py src/birre/domain/security_analyst/__init__.py tests/unit/test_security_analyst_alerts.py` passed.
- Findings: all five acceptance criteria are satisfied. Pagination uses deterministic limit/offset requests with `expand=details`; configured date, severity, alert type, and folder filters are forwarded; cap metadata is emitted; invalid results are rejected with a `results` error.
- Patches applied: none.
- Verifier-challenger result: pass. Confirmed AC coverage, proof sufficiency, and scope limited to the requested implementation, export, and unit-test files.
- Final route: PASS to collect.

[[2026-07-10T17:59:53+02:00]]
## Collect Notes
- Classification: leaf. Task #4 has no child tasks and no aggregate/EPIC intent.
- Leaf verification evidence: existing `## Verify Notes` record PASS, with focused `uv run pytest tests/unit/test_security_analyst_alerts.py` passing 2 tests and scoped `uv run ruff check src/birre/domain/security_analyst/alerts.py src/birre/domain/security_analyst/__init__.py tests/unit/test_security_analyst_alerts.py` passing.
- Closure checks: all five ACs were reported satisfied; verifier-challenger result was pass; no patches were pending; no unresolved Required Follow-up, decision state, or pending request was found.
- Archive rationale: verified leaf is complete and ready for terminal archival.
