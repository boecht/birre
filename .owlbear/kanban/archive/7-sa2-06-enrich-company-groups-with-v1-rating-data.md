---
id: 7
title: 'SA2-06: Enrich company groups with v1 rating data'
status: archived
priority: medium
created: 2026-07-10T11:48:29.949447+02:00
updated: 2026-07-10T18:11:02.492026+02:00
tags:
  - security-analyst
  - alert-workflow
  - scope:enrichment
  - type:build
  - reshaped-v2
parent: 1
depends_on:
  - 6
ac:
  - 'AC-1: Given company groups for `c-1` and `c-2`, `enrich_company_groups` calls
    the injected company fetcher for `c-1` and `c-2` and returns enrichment entries
    keyed by company GUID.'
  - 'AC-2: Given repeated input for company GUID `c-1`, `enrich_company_groups` calls
    the injected company fetcher once for `c-1`.'
  - 'AC-3: Given a company fetcher response with `name`, `primary_domain`, `current_rating`,
    and `ratings`, `enrich_company_groups` stores those four fields in the enrichment
    entry.'
  - 'AC-4: Given the company fetcher raises for `c-1`, `enrich_company_groups` returns
    warning code `company_enrichment_failed` and preserves trigger references for
    `c-1`.'
  - 'AC-5: Given a company group with three trigger references, `enrich_company_groups`
    returns those three trigger references unchanged in the enriched company record.'
proof_bundle: behavioral
blocked: false
block_reason:
claimed_at:
archival_reason: completed
archival_refs: []
---
Brief: `.owlbear/briefs/draft-birre-alert-workflows/brief.md`

## Scope
Fetch v1 company profile data once per distinct company GUID and attach current rating, company identity fields, rating history, enrichment status, and enrichment warnings to grouped trigger data.

## Local Architecture Anchors
- Existing company rating retrieval lives in `src/birre/domain/company_rating/service.py`.
- v1 OpenAPI bridge helpers live in `src/birre/integrations/bitsight/v1_bridge.py`.
- Existing domain call type aliases live in `src/birre/domain/common.py`.

## Dependencies
Depends on #6 for grouped company trigger records.

## Non-Goals
- Rating movement precedence logic.
- Priority scoring.
- Jira-action payload construction.
- Direct Jira writes.

## Shape Notes
- Scope decision: v1 enrichment owns async fanout, dedupe, and failure warning behavior; movement calculation comes after enrichment data exists.
- Challenger result: proceed for keeping enrichment separate from rating movement derivation.
- Verification focus: async unit tests with stubbed company fetcher responses and failures.

[[2026-07-10T18:10:02+02:00]]
## Builder Notes
- Files changed: `src/birre/domain/security_analyst/alerts.py`, `src/birre/domain/security_analyst/__init__.py`, `tests/unit/test_security_analyst_alerts.py`.
- Implemented async v1 company enrichment with one fetch per grouped company GUID, requested profile fields, enrichment status/warnings, and trigger preservation on failure.
- Proof selected: focused behavioral tests plus Ruff.
- Commands run: `uv run pytest tests/unit/test_security_analyst_alerts.py` (9 passed); `uv run ruff check src/birre/domain/security_analyst/alerts.py src/birre/domain/security_analyst/__init__.py tests/unit/test_security_analyst_alerts.py` (all checks passed).
- Builder-challenger: pass; no blockers or auto-fixes.
- Commit: `b311bc4` (`feat: enrich alert company groups`).
- Follow-up risk: none identified for shaped acceptance criteria.

[[2026-07-10T18:10:49+02:00]]
## Verify Notes
- Evidence reviewed: task AC, builder notes, `src/birre/domain/security_analyst/alerts.py`, `src/birre/domain/security_analyst/__init__.py`, and `tests/unit/test_security_analyst_alerts.py`.
- AC-1 and AC-2: focused enrichment test verifies entries keyed by `c-1` and `c-2` and one fetch per distinct GUID.
- AC-3: focused enrichment test verifies `name`, `primary_domain`, `current_rating`, and `ratings` are attached.
- AC-4 and AC-5: focused failure test verifies `company_enrichment_failed` and preservation of all three trigger references.
- Checks run: `uv run pytest tests/unit/test_security_analyst_alerts.py` passed, 9 passed. `uv run ruff check src/birre/domain/security_analyst/alerts.py src/birre/domain/security_analyst/__init__.py tests/unit/test_security_analyst_alerts.py` passed with all checks passed.
- Findings: no defects, unresolved acceptance criteria, or scope drift. No patch applied.
- Verifier-challenger: pass; no concrete findings.
- Final route: PASS to collect.

[[2026-07-10T18:11:02+02:00]]
## Collect Notes
- Classification: leaf; no child tasks under parent=7 and no aggregate/EPIC intent on this task.
- Leaf verification evidence: verifier PASS is recorded for all five acceptance criteria, with focused `uv run pytest tests/unit/test_security_analyst_alerts.py` result of 9 passed and focused Ruff checks passing.
- Closure checks: no unresolved Required Follow-up, no pending decision requests, task unblocked, and dependency gate was `ok` before claim.
- Archive rationale: complete verifier evidence and no residual decision state or follow-up remain.
