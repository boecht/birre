---
id: 9
title: 'SA2-08: Compute alert workflow priority score components'
status: archived
priority: medium
created: 2026-07-10T11:48:53.927750+02:00
updated: 2026-07-10T18:20:00.050735+02:00
tags:
  - security-analyst
  - alert-workflow
  - scope:priority-scoring
  - type:build
  - reshaped-v2
parent: 1
depends_on:
  - 8
ac:
  - 'AC-1: Given supplier criticality values `1`, `2`, `3`, and missing, `score_supplier_criticality`
    returns points `0`, `1`, `3`, and `1`.'
  - 'AC-2: Given event categories `public disclosure` and `security incident`, `score_event_category`
    returns `-1` for each category.'
  - 'AC-3: Given event categories `botnet infection`, `malware`, and `potentially
    exploited`, `score_event_category` returns `0` for each category.'
  - 'AC-4: Given event categories `open ports`, `patching cadence`, `server software`,
    and `insecure systems`, `score_event_category` returns `1` for each category.'
  - 'AC-5: Given event categories `TLS certificates`, `TLS configuration`, `spam propagation`,
    `mobile app security`, `desktop software`, `mobile software`, `exposed credentials`,
    `web application headers`, and `web application security`, `score_event_category`
    returns `3` for each category.'
  - 'AC-6: Given event categories `DNSSEC`, `DMARC`, `DKIM`, `SPF`, `domain squatting`,
    `unsolicited communication`, and `file sharing`, `score_event_category` returns
    `out_of_scope=True` for each category.'
  - 'AC-7: Given rating drops `151`, `101`, `41`, and `40`, `score_rating_change`
    returns points `-1`, `0`, `1`, and `3`.'
  - 'AC-8: Given total point values `1`, `2`, `3`, `4`, `5`, and `6`, `compute_priority_level`
    returns priorities `0`, `1`, `2`, `3`, `3`, and `4`.'
  - 'AC-9: Given omitted human factor, `score_human_factor` returns `1`; given `many_events`,
    `normal`, and `low_relevance`, it returns `0`, `1`, and `3`.'
proof_bundle: behavioral
blocked: false
block_reason:
claimed_at:
archival_reason: completed
archival_refs: []
---
Brief: `.owlbear/briefs/draft-birre-alert-workflows/brief.md`

## Scope
Implement the initial priority point system for supplier criticality, event category, rating change, human factor, and total-to-priority mapping.

## Local Architecture Anchors
- New pure scoring helpers should live under `src/birre/domain/security_analyst/`.
- Request-level supplier criticality input is defined by #2.
- Rating movement evidence is produced by #8.

## Dependencies
Depends on #8 for rating movement evidence.

## Non-Goals
- Returned-candidate filtering.
- Jira-action payload construction.
- Direct Jira writes.
- Supplier criticality list ingestion from an external system.

## Shape Notes
- Scope decision: keep point calculations pure and exhaustive before filtering consumes the result.
- Challenger result: proceed for keeping scoring separate from filtering.
- Verification focus: pure unit tests for each point function and priority mapping.

[[2026-07-10T18:17:52+02:00]]
## Builder Notes
- Files changed: `src/birre/domain/security_analyst/priority.py`, `src/birre/domain/security_analyst/__init__.py`, `tests/unit/test_security_analyst_priority.py`.
- Implemented pure scoring helpers for supplier criticality, event category (including `out_of_scope` metadata), rating drops, human factor, and total-to-priority mapping.
- Proof selected: behavioral unit coverage for all AC branches and threshold boundaries.
- Commands run: `uv run pytest tests/unit/test_security_analyst_priority.py` (43 passed); `uv run ruff check src/birre/domain/security_analyst/priority.py src/birre/domain/security_analyst/__init__.py tests/unit/test_security_analyst_priority.py` (all checks passed); `uv run pytest tests/unit/test_security_analyst_alerts.py tests/unit/test_security_analyst_request.py` (17 passed); `git diff --check` (clean).
- Builder-challenger result: pass; confirmed AC-1 through AC-9 and no concrete blocker.
- Follow-up risk: event category intentionally returns a structured mapping so downstream filtering can consume both points and `out_of_scope`; web application security remains the specified 3-point category.

[[2026-07-10T18:19:44+02:00]]
## Verify Notes
- Evidence reviewed: `src/birre/domain/security_analyst/priority.py`, `src/birre/domain/security_analyst/__init__.py`, and `tests/unit/test_security_analyst_priority.py`; live task state confirmed `verify`, claimed, and dependency-satisfied.
- Checks run: `uv run pytest tests/unit/test_security_analyst_priority.py` (43 passed); `uv run ruff check src/birre/domain/security_analyst/priority.py src/birre/domain/security_analyst/__init__.py tests/unit/test_security_analyst_priority.py` (all checks passed); path-scoped `git diff --check` (clean).
- Findings: AC-1 through AC-9 are implemented and directly covered, including threshold boundaries and out-of-scope category metadata. No local patch was required; no scope drift or unresolved acceptance criteria found.
- Verifier-challenger result: pass. Initial challenge reported a stale `build` state, disproven by live `show_task(9)`; second challenge confirmed the task is in `verify` and approved PASS.
- Final route: advance to `collect`.

[[2026-07-10T18:20:00+02:00]]
## Collect Notes
- Classification: leaf. Task #9 has no child tasks, no aggregate or EPIC title/tag, and no aggregate intent section.
- Verification evidence: existing `## Verify Notes` records verifier PASS and verifier-challenger pass; focused priority unit tests passed (43 tests), Ruff passed, and `git diff --check` was clean. AC-1 through AC-9 were explicitly covered, including threshold boundaries and out-of-scope category metadata.
- Dependency gate: dependency #8 is archived with archival reason `completed`; task #9 dependency status was satisfied before claim.
- Decision and follow-up checks: no pending decision requests for task #9; no unresolved Required Follow-up is present in the task record.
- Archive rationale: implementation and proof are complete, acceptance criteria are verified, and no residual decision state remains. Archived mechanically without re-reviewing implementation details.
