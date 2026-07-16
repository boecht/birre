---
id: 2
title: 'SA2-01: Define alert workflow request and cap contract'
status: archived
priority: high
created: 2026-07-10T11:47:55.031140+02:00
updated: 2026-07-10T17:50:58.405987+02:00
tags:
  - security-analyst
  - alert-workflow
  - scope:config
  - type:build
  - reshaped-v2
parent: 1
depends_on: []
ac:
  - 'AC-1: Given omitted cap inputs, `build_alert_workflow_request` returns `page_size=50`,
    `max_pages=10`, `max_companies=100`, `max_returned_priority=4`, and `human_factor=1`.'
  - 'AC-2: Given caller overrides `page_size=25`, `max_pages=2`, `max_companies=5`,
    `max_returned_priority=3`, and `human_factor=0`, `build_alert_workflow_request`
    returns those five values in the request object.'
  - 'AC-3: Given `page_size=0`, `build_alert_workflow_request` raises `ValueError`
    with message text containing `page_size`.'
  - "AC-4: Given supplier criticality input `{'c-1': 2, 'c-2': 3}`, `build_alert_workflow_request`
    stores criticality entries keyed by BitSight company GUID and does not derive
    entries from company names."
  - 'AC-5: Given no supplier criticality entry for company GUID `c-3`, `resolve_supplier_criticality`
    returns `1`.'
proof_bundle: behavioral
blocked: false
block_reason:
claimed_at:
archival_reason: completed
archival_refs: []
---
Brief: `.owlbear/briefs/draft-birre-alert-workflows/brief.md`

## Scope
Define the deterministic request and configuration contract for alert window, pagination caps, distinct-company cap, maximum returned priority, default human factor, and supplier criticality input.

## Local Architecture Anchors
- New workflow code should live under `src/birre/domain/security_analyst/`.
- Configuration precedent lives in `src/birre/config/settings.py` and CLI option helpers under `src/birre/cli/options/`.

## Dependencies
None.

## Non-Goals
- BitSight network calls.
- Server context registration.
- Jira adapter calls.
- Durable cursor state.

## Shape Notes
- Scope decision: keep pure request/config modeling separate from server context wiring.
- Challenger result: proceed after accepting the challenger request to preserve the split from context wiring.
- Verification focus: direct unit tests for request construction and supplier criticality fallback behavior.

[[2026-07-10T17:44:38+02:00]]
## Builder Notes

Implemented the alert workflow request contract in `src/birre/domain/security_analyst/request.py` and exported it from `src/birre/domain/security_analyst/__init__.py`. Added focused behavioral coverage in `tests/unit/test_security_analyst_request.py`.

Proof selected: behavioral unit tests plus focused lint and import smoke check.

Commands run:
- `uv run pytest tests/unit/test_security_analyst_request.py` -> 4 passed
- `uv run ruff check src/birre/domain/security_analyst/__init__.py src/birre/domain/security_analyst/request.py tests/unit/test_security_analyst_request.py` -> All checks passed
- `uv run python -c "from birre.domain.security_analyst import AlertWorkflowRequest, build_alert_workflow_request, resolve_supplier_criticality; print(AlertWorkflowRequest.__name__)"` -> imported successfully

Builder-challenger result: pass; no concrete blockers found.

Follow-up risk: broader workflow integration and server wiring are intentionally outside task 2 scope.

[[2026-07-10T17:50:41+02:00]]
## Verify Notes

Evidence reviewed:
- `src/birre/domain/security_analyst/request.py` defines the frozen request contract, explicit defaults, cap validation, GUID-keyed supplier criticality, and missing-GUID fallback.
- `src/birre/domain/security_analyst/__init__.py` exports the public request helpers.
- `tests/unit/test_security_analyst_request.py` covers all five acceptance criteria.

Checks run:
- `uv run pytest tests/unit/test_security_analyst_request.py` -> 4 passed.
- `uv run ruff check src/birre/domain/security_analyst/__init__.py src/birre/domain/security_analyst/request.py tests/unit/test_security_analyst_request.py` -> All checks passed.
- Public import/default/fallback smoke check -> imported successfully; assertions passed.
- `uv run pyright src/birre/domain/security_analyst/request.py src/birre/domain/security_analyst/__init__.py` -> 0 errors, 0 warnings, 0 informations.

Findings: No defects or unresolved acceptance criteria. No patch applied. Scope remains limited to pure request/config modeling and focused tests; workflow integration and server wiring are correctly outside this task.

Verifier-challenger result: pass. It confirmed AC satisfaction, sufficient proof, and no scope drift.

Final route: PASS -> collect.

[[2026-07-10T17:50:58+02:00]]
## Collect Notes

- Classification: leaf. Task has no child tasks; parent linkage to #1 does not make this task aggregate.
- Verification evidence: `## Verify Notes` is present with PASS route, all five ACs covered, focused unit tests (4 passed), Ruff clean, import/default/fallback smoke check passed, Pyright clean, and verifier-challenger pass.
- Decision/follow-up state: no pending decision requests for task #2; no unresolved Required Follow-up section found.
- Archive rationale: leaf verification is complete and closure evidence is sufficient; archive as completed.
