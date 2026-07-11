---
id: 10
title: 'SA2-09: Map priority levels and filter returned candidates'
status: archived
priority: medium
created: 2026-07-10T11:49:00.687188+02:00
updated: 2026-07-10T18:26:34.349259+02:00
tags:
  - security-analyst
  - alert-workflow
  - scope:priority-gate
  - type:build
  - reshaped-v2
parent: 1
depends_on:
  - 9
ac:
  - 'AC-1: Given candidates with priorities `3` and `4` and `max_returned_priority=3`,
    `filter_action_candidates` returns the priority `3` candidate and records the
    priority `4` candidate with reason `priority_filtered`.'
  - 'AC-2: Given a candidate with out-of-scope category `DNSSEC`, `filter_action_candidates`
    returns `eligible=False`, no action item, and reason `out_of_scope_category`.'
  - 'AC-3: Given category `web application security`, `filter_action_candidates` returns
    warning code `category_ambiguous` on the candidate metadata.'
  - 'AC-4: Given a priority-filtered candidate, `filter_action_candidates` records
    `company_guid`, `priority`, and `filter_reason` in `filtered_candidates`.'
  - 'AC-5: Given a candidate with priority equal to `max_returned_priority`, `filter_action_candidates`
    includes the candidate in returned action candidates.'
proof_bundle: behavioral
blocked: false
block_reason:
claimed_at:
archival_reason: completed
archival_refs: []
---
Brief: `.owlbear/briefs/draft-birre-alert-workflows/brief.md`

## Scope
Apply alert-driven action eligibility rules, preserve category ambiguity metadata, and filter returned new-ticket action candidates above the configured maximum priority.

## Local Architecture Anchors
- Scoring helpers from #9 supply component points and priority levels.
- New filtering helpers should live under `src/birre/domain/security_analyst/`.

## Dependencies
Depends on #9 for priority component scoring.

## Non-Goals
- Jira-action payload rendering.
- Existing-ticket update workflow.
- Direct Jira writes.
- Category clarification beyond the brief's stated ambiguity.

## Shape Notes
- Scope decision: filtering is separate from score calculation because it decides caller-visible inclusion and metadata for suppressed alert-driven candidates.
- Challenger result: proceed for keeping filtering separate from scoring.
- Verification focus: pure unit tests for priority threshold, out-of-scope suppression, ambiguity warning, and filtered metadata.

[[2026-07-10T18:25:27+02:00]]
## Builder Notes

- Files inspected: `src/birre/domain/security_analyst/priority.py`, `tests/unit/test_security_analyst_alerts.py`, and `tests/unit/test_security_analyst_priority.py`.
- No product files were modified in this invocation; the task implementation and focused tests were already present in the worktree.
- Proof selected: behavioral unit tests covering priority threshold inclusion, priority filtering metadata, out-of-scope suppression, and category ambiguity warning.
- Command: `uv run pytest tests/unit/test_security_analyst_alerts.py tests/unit/test_security_analyst_priority.py` -> 58 passed.
- Builder challenger: `builder-challenger` returned `decision: pass`; no blockers or auto-fixed files.
- Follow-up risk: broader workflow integration remains covered by downstream tasks, especially payload construction and runner exposure.

[[2026-07-10T18:26:19+02:00]]
## Verify Notes

- Evidence reviewed: `src/birre/domain/security_analyst/priority.py`, `tests/unit/test_security_analyst_alerts.py`, `tests/unit/test_security_analyst_priority.py`, and the task acceptance criteria.
- AC-1 and AC-5: `filter_action_candidates` includes priority equal to `max_returned_priority` and filters higher priorities with `priority_filtered`.
- AC-2: out-of-scope `DNSSEC` produces no action candidate and a filtered record with `eligible=False`, `action_item=None`, and `filter_reason=out_of_scope_category`.
- AC-3: `web application security` adds candidate metadata warning `category_ambiguous`.
- AC-4: filtered records retain `company_guid`, `priority`, and `filter_reason`.
- Check run: `uv run pytest tests/unit/test_security_analyst_alerts.py tests/unit/test_security_analyst_priority.py` -> 58 passed in 1.00s.
- Findings: no local defects; no verifier patch applied. Unrelated worktree changes were left untouched.
- Verifier challenger: `verifier-challenger` returned `decision: pass`; all five ACs were confirmed, proof was sufficient, and scope drift was not found.
- Final route: PASS to collect.

[[2026-07-10T18:26:34+02:00]]
## Collect Notes

- Classification: leaf.
- Verification evidence: verifier PASS; all five acceptance criteria confirmed.
- Focused check: `uv run pytest tests/unit/test_security_analyst_alerts.py tests/unit/test_security_analyst_priority.py` -> 58 passed in 1.00s.
- Builder and verifier challengers both returned pass.
- Child lookup: no child tasks.
- Pending requests: none.
- Residual decisions or required follow-up: none.
- Archive rationale: leaf verification is complete and the task has no unresolved closure state.
