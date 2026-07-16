---
id: 11
title: 'SA2-10: Build structured Jira-action payload'
status: archived
priority: medium
created: 2026-07-10T11:49:08.691829+02:00
updated: 2026-07-10T18:31:50.362576+02:00
tags:
  - security-analyst
  - alert-workflow
  - scope:jira-action-payload
  - type:build
  - reshaped-v2
parent: 1
depends_on:
  - 10
ac:
  - 'AC-1: Given a scored company candidate, `build_jira_action_payload` returns an
    action item with `company_guid`, `correlation_key` equal to company GUID, company
    identity fields, and current company rating.'
  - 'AC-2: Given trigger alert records, `build_jira_action_payload` includes alert
    GUID provenance, event date, seen-at date, severity, trigger, and raw evidence
    reference fields in the action item.'
  - 'AC-3: Given rating movement evidence, `build_jira_action_payload` includes rating
    before, rating after, calculated drop amount, movement source, and current rating
    in proposed Jira body fields.'
  - 'AC-4: Given priority and eligibility data, `build_jira_action_payload` includes
    priority score, priority level, eligibility, and filtered-candidate metadata.'
  - 'AC-5: Given warning and missing-data inputs, `build_jira_action_payload` includes
    warning codes and missing-data flags in the action item and run metadata.'
  - 'AC-6: Given internal grouped alert/company data, `build_jira_action_payload`
    returns top-level keys `action_items` and `metadata` and no top-level key named
    `internal_batch`.'
proof_bundle: behavioral
blocked: false
block_reason:
claimed_at:
archival_reason: completed
archival_refs: []
---
Brief: `.owlbear/briefs/draft-birre-alert-workflows/brief.md`

## Scope
Build the caller-facing structured Jira-action payload for company performance watch tickets, with company GUID as the correlation key and alert GUIDs/details retained as trigger provenance.

## Local Architecture Anchors
- New payload models/builders should live under `src/birre/domain/security_analyst/`.
- The brief defines the first visible product as structured Jira-action data, not the internal alert/company batch.

## Dependencies
Depends on #10 for filtered action candidates.

## Non-Goals
- Direct Jira lookup, create, append, transition, or closure.
- Durable correlation ledger.
- Management summary generation.
- Raw-batch-as-product caller output.

## Shape Notes
- Scope decision: payload construction is the first product boundary and must hide internal batch plumbing while preserving evidence needed by a later Jira adapter.
- Challenger result: proceed for keeping payload construction separate from runner/CLI exposure.
- Verification focus: pure unit tests for payload shape, evidence fields, warnings, and absence of internal-batch top-level data.

[[2026-07-10T18:29:00+02:00]]
## Builder Notes
- Files changed: `src/birre/domain/security_analyst/payload.py`, `src/birre/domain/security_analyst/__init__.py`, `tests/unit/test_security_analyst_payload.py`
- Implemented `build_jira_action_payload` as a pure caller-facing boundary. It joins filtered action candidates to grouped company records by company GUID, preserves company identity/current rating, alert GUID/date/seen-at/severity/trigger/raw evidence references, rating movement evidence in proposed Jira body fields, priority/eligibility, warnings, missing-data flags, and filtered-candidate metadata.
- Output top-level keys are `action_items` and `metadata`; internal grouped batch data is not exposed.
- Proof: `uv run pytest -q tests/unit/test_security_analyst_payload.py` passed (1 test). `uv run ruff check src/birre/domain/security_analyst/payload.py src/birre/domain/security_analyst/__init__.py tests/unit/test_security_analyst_payload.py` passed.
- Builder challenger: `builder-challenger` returned `decision: pass` with no concrete blocker.
- Follow-up risk: payload naming is newly established from the shaped AC because no prior Jira adapter contract exists; verifier should check integration expectations against the brief/consumer shape.
- Worktree intentionally left uncommitted because the workspace instruction says not to create commits unless explicitly requested.

[[2026-07-10T18:31:26+02:00]]
## Verify Notes
- Verdict: PASS after a small local fix in the touched payload slice.
- Evidence reviewed: task AC-1 through AC-6, builder notes, `src/birre/domain/security_analyst/payload.py`, `src/birre/domain/security_analyst/__init__.py`, and `tests/unit/test_security_analyst_payload.py`.
- Initial focused proof: `uv run pytest -q tests/unit/test_security_analyst_payload.py` passed (`1 passed`); Ruff passed for the three task files.
- Finding: verifier-challenger identified an AC-2 edge case where normalized triggers containing both `raw_alert` and `source_metadata` preferred page metadata and lost complete raw alert evidence.
- Patch applied: `payload.py` now prefers explicit `raw_evidence_reference`, then `raw_alert`, then `source_metadata`; the focused test now supplies both fields and confirms the raw alert remains the evidence reference.
- Post-patch proof: `uv run pytest -q tests/unit/test_security_analyst_payload.py` passed (`1 passed`); `uv run ruff check src/birre/domain/security_analyst/payload.py src/birre/domain/security_analyst/__init__.py tests/unit/test_security_analyst_payload.py` passed (`All checks passed!`).
- Final verifier-challenger: `decision: pass`; no concrete problem, AC-2 precedence covered, evidence sufficient for scoped payload change.
- Worktree note: unrelated task-board and neighboring workflow changes were present and were left untouched.
- Final route: verify -> collect.

[[2026-07-10T18:31:50+02:00]]
## Collect Notes
- Classification: leaf; no child tasks, aggregate title/tag, or aggregate intent section.
- Leaf verification evidence: `## Verify Notes` records PASS, focused payload test passing (`1 passed`), Ruff passing for all three touched files, and final verifier-challenger `decision: pass`.
- Closure checks: no pending decision requests; no unresolved Required Follow-up; task is unblocked; dependency gate is `ok` for #10.
- Archive rationale: all six acceptance criteria have explicit verifier coverage and no residual decision state or follow-up remains. Archive as completed.
