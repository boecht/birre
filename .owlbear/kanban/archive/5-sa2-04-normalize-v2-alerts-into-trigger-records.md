---
id: 5
title: 'SA2-04: Normalize v2 alerts into trigger records'
status: archived
priority: high
created: 2026-07-10T11:48:16.215002+02:00
updated: 2026-07-10T18:03:08.821117+02:00
tags:
  - security-analyst
  - alert-workflow
  - scope:normalization
  - type:build
  - reshaped-v2
parent: 1
depends_on:
  - 4
ac:
  - 'AC-1: Given a v2 alert item with `guid`, `company_guid`, `alert_date`, `severity`,
    `trigger`, and `details`, `normalize_alert_trigger` returns those values plus
    `raw_alert`.'
  - 'AC-2: Given a v2 alert item without `company_guid`, `normalize_alert_trigger`
    returns warning code `company_guid_missing_anomaly` and `enrichable=False`.'
  - 'AC-3: Given a v2 alert item with `folder_guid` and `alert_set_guid`, `normalize_alert_trigger`
    returns those values in `folder_context`.'
  - 'AC-4: Given page metadata containing endpoint, query, page index, and offset,
    `normalize_alert_trigger` includes those values in `source_metadata`.'
  - 'AC-5: Given a v2 alert item with nested `details`, `normalize_alert_trigger`
    preserves the nested details object without field loss.'
proof_bundle: behavioral
blocked: false
block_reason:
claimed_at:
archival_reason: completed
archival_refs: []
---
Brief: `.owlbear/briefs/draft-birre-alert-workflows/brief.md`

## Scope
Convert raw v2 alert result items into loss-aware trigger records while preserving alert identity, company identity, dates, severity, trigger text, folder context, details, endpoint/query metadata, page metadata, and raw payloads.

## Local Architecture Anchors
- New workflow normalization should live under `src/birre/domain/security_analyst/`.
- Existing Pydantic model patterns are visible in `src/birre/domain/company_rating/service.py` and `src/birre/domain/risk_manager/service.py`.

## Dependencies
Depends on #4 for fetched page envelopes.

## Non-Goals
- Company grouping.
- Company enrichment.
- Priority scoring.
- Jira-action payload construction.

## Shape Notes
- Scope decision: normalization preserves evidence and records company GUID anomalies without deciding grouping or enrichment behavior.
- Challenger result: proceed for keeping normalization separate from grouping.
- Verification focus: pure unit tests using fixture v2 alert dictionaries.

[[2026-07-10T18:01:53+02:00]]
## Builder Notes
- Files changed: `src/birre/domain/security_analyst/alerts.py`, `src/birre/domain/security_analyst/__init__.py`, `tests/unit/test_security_analyst_alerts.py`.
- Implemented `normalize_alert_trigger` as a pure loss-aware normalizer. It preserves alert/company identity, dates, severity, trigger text, folder and alert-set context, nested details, raw alert payload, and page source metadata; missing company GUIDs are retained as non-enrichable records with `company_guid_missing_anomaly`.
- Proof: `uv run pytest tests/unit/test_security_analyst_alerts.py` -> 4 passed.
- Lint: `uv run ruff check src/birre/domain/security_analyst/alerts.py src/birre/domain/security_analyst/__init__.py tests/unit/test_security_analyst_alerts.py` -> all checks passed.
- Additional check: `git diff --check` passed for the task paths.
- Builder-challenger: pass; no concrete blocker or scope drift found.
- Follow-up risk: the touched files are untracked in the current worktree, so they were not staged or committed to avoid absorbing unrelated pre-existing work; verify should account for that worktree state.

[[2026-07-10T18:02:52+02:00]]
## Verify Notes
- Evidence reviewed: `src/birre/domain/security_analyst/alerts.py`, `src/birre/domain/security_analyst/__init__.py`, and `tests/unit/test_security_analyst_alerts.py` against AC-1 through AC-5.
- AC result: PASS. The normalizer preserves required alert/company identity, dates, severity, trigger, raw payload, nested details, folder context, and source metadata; missing company GUIDs produce `company_guid_missing_anomaly` and `enrichable=False`.
- Checks run:
  - `uv run pytest tests/unit/test_security_analyst_alerts.py` -> 4 passed.
  - `uv run pytest tests/unit/test_security_analyst_alerts.py tests/unit/test_security_analyst_request.py` -> 8 passed.
  - `uv run ruff check src/birre/domain/security_analyst/alerts.py src/birre/domain/security_analyst/__init__.py tests/unit/test_security_analyst_alerts.py` -> all checks passed.
  - Task-path worktree check -> only the task package and `tests/unit/test_security_analyst_alerts.py` are untracked; no unrelated task-path changes observed.
- Findings: no implementation defect, missing AC, or scope drift. No patch applied.
- Verifier-challenger: pass; confirmed all five ACs, proof sufficiency, and scope.
- Final route: PASS to collect.

[[2026-07-10T18:03:08+02:00]]
## Collect Notes
- Classification: leaf. Task #5 has no child tasks (`list_tasks(parent=5)` returned none), no aggregate or EPIC title/tag, and no aggregate intent section.
- Leaf verification evidence: `## Verify Notes` records PASS against AC-1 through AC-5, including focused unit tests (4 passed; 8 passed with the neighboring request test), Ruff clean, and verifier-challenger pass.
- Dependency and decision state: dependency status was OK before collection; no pending decision requests were found for task #5.
- Residual follow-up: none. The builder's note about untracked task files was explicitly reviewed by verification and does not block archival.
- Archive rationale: implementation was verified, scope remained within normalization, and no unresolved follow-up or decision state remains.
