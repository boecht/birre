---
id: 13
title: 'SA2-12: Prove security analyst alert workflow end to end'
status: archived
priority: medium
created: 2026-07-10T11:49:21.574175+02:00
updated: 2026-07-10T19:16:46.412068+02:00
tags:
  - security-analyst
  - alert-workflow
  - scope:consolidation
  - type:test
  - reshaped-v2
parent: 1
depends_on:
  - 2
  - 3
  - 4
  - 5
  - 6
  - 7
  - 8
  - 9
  - 10
  - 11
  - 12
ac:
  - 'AC-1: Given fixture v2 alerts for two companies and fixture v1 company enrichment
    responses, the consolidation test observes `run_alert_workflow_action_payload`
    returning action items keyed by company GUID.'
  - 'AC-2: Given fixture pages that exceed the page cap and company cap, the consolidation
    test observes warning codes `alert_page_cap_reached` and `company_cap_reached`.'
  - 'AC-3: Given fixtures covering alert-derived movement, larger history movement,
    history fallback, missing movement, out-of-scope category, web-application-security
    ambiguity, and priority filtering, the consolidation test observes the expected
    movement source, eligibility, priority, and warning codes.'
  - 'AC-4: Given the CLI command with stubbed workflow dependencies, the consolidation
    test observes stdout JSON containing structured Jira-action fields and no top-level
    internal alert/company batch field.'
  - 'AC-5: Given the consolidation test executes, no Jira client is called and no
    durable queue/cursor artifact is written.'
proof_bundle: critical
blocked: false
block_reason:
claimed_at:
archival_reason: completed
archival_refs: []
---
Brief: `.owlbear/briefs/draft-birre-alert-workflows/brief.md`

## Scope
Add an integrated fixture proof that the shaped workflow produces deterministic structured Jira-action output from stubbed v2 alert pages and v1 company enrichment/rating-history responses through the API runner and CLI surface.

## Local Architecture Anchors
- Unit and CLI test precedent lives under `tests/unit/` and `tests/cli/`.
- The API runner from #12 and payload builder from #11 are the integration targets.

## Dependencies
Depends on #2 through #12.

## Non-Goals
- Live BitSight online test requirement.
- Direct Jira write tests.
- Durable queue/cursor tests.
- Management summary tests.

## Shape Notes
- Scope decision: keep a consolidation proof because the brief crosses multiple deterministic stages and the first useful output is an aggregate payload.
- Challenger result: accepted with caveat; consolidation is useful here because it proves the parent product promise, but it must stay fixture-based and avoid creating a second implementation path.
- Verification focus: one focused end-to-end fixture path plus CLI output assertion.

[[2026-07-10T19:13:27+02:00]]
## Builder Notes
- Files changed: `tests/unit/test_security_analyst_workflow.py`
- Commit: `cfd4fb0 test: prove alert workflow end to end`
- Added deterministic fixture coverage through `run_alert_workflow_action_payload` for action items keyed by company GUID, page/company cap warnings, alert/history movement precedence and fallback, missing movement, out-of-scope filtering, web-application-security ambiguity, and priority filtering.
- Added injected CLI proof for structured JSON action output with no top-level grouped internal batch field.
- Added AC-5 proof by making `Path.write_text`, `Path.write_bytes`, and `Path.touch` fail during the real runner and asserting the only observed calls are the fixture v2 `getAlerts` read and capped v1 company reads.
- Commands run: `uv run pytest tests/unit/test_security_analyst_workflow.py` (6 passed); `uv run ruff check tests/unit/test_security_analyst_workflow.py` (clean); `uv run ruff format --check tests/unit/test_security_analyst_workflow.py` (formatted); scoped `git diff --check` (clean).
- Builder-challenger result: pass; confirmed AC-1 through AC-5, including the no-Jira/no-durable-state proof.
- Follow-up risks: none identified; tests are fixture-only and do not require live BitSight access.

[[2026-07-10T19:15:52+02:00]]
## Verify Notes
- Evidence reviewed: `tests/unit/test_security_analyst_workflow.py` covers the deterministic v2/v1 fixture runner, company GUID action items, page/company caps, movement precedence and fallback, missing movement, category ambiguity, out-of-scope and priority filtering, injected CLI JSON, and no Jira/durable-state behavior.
- Checks run: `uv run pytest tests/unit/test_security_analyst_workflow.py` -> 6 passed; `uv run ruff check tests/unit/test_security_analyst_workflow.py` -> clean; `uv run ruff format --check tests/unit/test_security_analyst_workflow.py` -> already formatted; scoped `git diff --check` -> clean.
- Finding and patch: verifier-challenger initially identified that the CLI proof did not assert structured Jira fields. Added focused assertions for `movement_source`, `rating_before`, `rating_after`, `rating_drop`, `current_rating`, and absence of `groups`; reran all checks successfully. The observed CLI contract uses null before/after values and includes `current_rating`, while the direct runner matrix proves concrete movement values.
- Final verifier-challenger result: pass. Confirmed AC-1 through AC-5, sufficient evidence for collect, and no scope drift. Unrelated worktree changes were left untouched.
- Final route: PASS -> collect.

[[2026-07-10T19:16:46+02:00]]
## Collect Notes
- Classification: aggregate consolidation task; explicit `scope:consolidation` tag, integrated proof scope, and dependency fan-in distinguish it from an ordinary leaf.
- Aggregate intent source: task `## Scope` and `## Shape Notes`, grounded in `.owlbear/briefs/draft-birre-alert-workflows/brief.md`; intent is fixture-based end-to-end proof through the API runner and CLI without Jira writes or durable state.
- Child coverage: `list_tasks(parent=13)` returned no direct children; this consolidation task aggregates dependencies #2 through #12 rather than owning child tasks.
- Dependency gate: #13 depends on #2 through #12; every dependency is archived with archival reason `completed`, and the pre-claim board projection reported `dep_status: ok`.
- Completion evidence: `## Verify Notes` records final verifier-challenger pass for AC-1 through AC-5 after 6 focused tests passed and Ruff/check formatting evidence succeeded.
- Residual decisions: no pending request, block, unresolved Required Follow-up, or residual decision state found.
- Aggregate evidence: deterministic v2/v1 fixture workflow, cap warnings, movement and priority branches, structured CLI Jira-action fields, and absence of Jira/durable-state effects are covered by the accepted verifier evidence.
- Rationale: the explicit consolidation contract is satisfied and all dependency work is complete; archive as `completed`.
