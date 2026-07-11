---
id: 8
title: 'SA2-07: Derive rating movement with alert/history precedence'
status: archived
priority: medium
created: 2026-07-10T11:48:36.135600+02:00
updated: 2026-07-10T18:15:29.690584+02:00
tags:
  - security-analyst
  - alert-workflow
  - scope:rating-movement
  - type:build
  - reshaped-v2
parent: 1
depends_on:
  - 7
ac:
  - "AC-1: Given an alert trigger with `rating_before=800` and `rating_after=700`,
    `derive_rating_movement` returns `drop=100` and `source='alert_rating'`."
  - "AC-2: Given alert-derived drop `50` and company-history drop `120`, `derive_rating_movement`
    returns `drop=120` and `source='company_history'`."
  - "AC-3: Given no alert-derived drop and company-history drop `80`, `derive_rating_movement`
    returns `drop=80` and `source='company_history'`."
  - 'AC-4: Given no alert-derived drop and no company-history drop, `derive_rating_movement`
    returns warning code `rating_movement_missing`.'
  - "AC-5: Given category movement `A` to `C` and category rating map `{'A': 900,
    'C': 600}`, `derive_rating_movement` returns `drop=50` and `source='alert_category'`."
proof_bundle: behavioral
blocked: false
block_reason:
claimed_at:
archival_reason: completed
archival_refs: []
---
Brief: `.owlbear/briefs/draft-birre-alert-workflows/brief.md`

## Scope
Derive per-alert rating movement from alert before/after rating or category fields, compare it with company rating-history movement, and select the movement evidence required by the brief.

## Local Architecture Anchors
- Rating history summarization patterns live in `src/birre/domain/company_rating/service.py`.
- New pure movement helpers should live under `src/birre/domain/security_analyst/`.

## Dependencies
Depends on #7 for enriched company records and rating history.

## Non-Goals
- v1 enrichment calls.
- Priority scoring.
- Jira-action payload construction.
- Direct Jira writes.

## Shape Notes
- Scope decision: rating movement is pure deterministic evidence selection and should not be coupled to API fanout.
- Challenger result: proceed for keeping movement separate from enrichment.
- Verification focus: pure unit tests covering alert-derived, history-derived, larger-history, and missing-data branches.

[[2026-07-10T18:14:09+02:00]]
## Builder Notes
- Files changed: `src/birre/domain/security_analyst/movement.py`, `src/birre/domain/security_analyst/__init__.py`, `tests/unit/test_security_analyst_alerts.py`.
- Implemented pure `derive_rating_movement` evidence selection for alert rating drops, category-level drops, largest adjacent company-history drop, and `rating_movement_missing` warnings.
- Proof selected: focused behavioral tests plus focused Ruff and diff whitespace checks.
- Commands run: `uv run pytest tests/unit/test_security_analyst_alerts.py` (13 passed); `uv run ruff check src/birre/domain/security_analyst/movement.py src/birre/domain/security_analyst/__init__.py tests/unit/test_security_analyst_alerts.py` (all checks passed); `git diff --check` (passed).
- Builder-challenger: pass; no concrete blockers or scope drift. Follow-up risk noted: category normalization is order-based if future category rules become more complex.
- Commit: `ae4d8d0` (`feat: derive alert rating movement`).
- Repository caveat: an already-staged unrelated task-7 Kanban archive rename was included in the same commit; it was not modified or reverted by this task.


[[2026-07-10T18:14:52+02:00]]
## Verify Notes
- Evidence reviewed: `src/birre/domain/security_analyst/movement.py`, `tests/unit/test_security_analyst_alerts.py`, builder notes, and latest commit `ae4d8d0`.
- Commands run: `uv run pytest tests/unit/test_security_analyst_alerts.py` (13 passed); `uv run ruff check src/birre/domain/security_analyst/movement.py src/birre/domain/security_analyst/__init__.py tests/unit/test_security_analyst_alerts.py` (passed); `git diff --check` (passed); direct AC exercise via `uv run python -c ...` (5/5 acceptance examples passed).
- Findings: implementation selects the largest available alert numeric, alert category, or company-history drop and returns `rating_movement_missing` when none exists. No local defect found; no patch applied.
- Scope review: task-8 implementation files are committed in `ae4d8d0`; unrelated task-7 Kanban metadata and request files in the worktree were not modified.
- Verifier-challenger: pass; no concrete scope, intent, or proof defect.
- Final route: PASS to collect.

[[2026-07-10T18:15:12+02:00]]
Verification complete: focused tests, Ruff, diff check, and direct AC examples all pass; verifier-challenger returned pass.

[[2026-07-10T18:15:29+02:00]]
## Collect Notes
- Classification: leaf. The task has no child tasks, no aggregate or EPIC title/tag, and no aggregate intent section.
- Verification evidence: existing `## Verify Notes` records verifier PASS, verifier-challenger pass, focused unit tests (13 passed), Ruff, `git diff --check`, and 5/5 direct acceptance examples.
- Dependency and request checks: dependency gate was `ok` before claim; no pending decision requests or unresolved follow-up was found for task #8.
- Archive rationale: implementation and proof are complete, all acceptance criteria have verification evidence, and no residual decision state remains. Archived mechanically without re-reviewing implementation details.
