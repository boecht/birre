---
id: 6
title: 'SA2-05: Group alert triggers by company GUID with company cap'
status: archived
priority: medium
created: 2026-07-10T11:48:22.313317+02:00
updated: 2026-07-10T18:07:44.506872+02:00
tags:
  - security-analyst
  - alert-workflow
  - scope:grouping
  - type:build
  - reshaped-v2
parent: 1
depends_on:
  - 5
ac:
  - 'AC-1: Given enrichable triggers for company GUIDs `c-1`, `c-1`, and `c-2`, `group_alert_triggers_by_company`
    returns groups keyed by `c-1` and `c-2`.'
  - 'AC-2: Given two triggers for company GUID `c-1` with alert GUIDs `a-1` and `a-2`,
    the `c-1` group contains trigger references for `a-1` and `a-2`.'
  - 'AC-3: Given `max_companies=1` and enrichable triggers for `c-1` and `c-2`, `group_alert_triggers_by_company`
    returns one company group and warning code `company_cap_reached`.'
  - 'AC-4: Given a trigger with `enrichable=False`, `group_alert_triggers_by_company`
    excludes it from company groups and returns its warning code in group metadata.'
  - 'AC-5: Given an empty trigger list, `group_alert_triggers_by_company` returns
    an empty group mapping and an empty warning list.'
proof_bundle: behavioral
blocked: false
block_reason:
claimed_at:
archival_reason: completed
archival_refs: []
---
Brief: `.owlbear/briefs/draft-birre-alert-workflows/brief.md`

## Scope
Group enrichable trigger records by company GUID, preserve distinct alert triggers inside each company group, and apply the distinct-company cap with warning metadata.

## Local Architecture Anchors
- New workflow grouping should live under `src/birre/domain/security_analyst/`.
- The brief requires company GUID as the company-watch correlation key and alert GUID as provenance.

## Dependencies
Depends on #5 for normalized trigger records.

## Non-Goals
- v1 company enrichment.
- Rating movement derivation.
- Priority scoring.
- Jira-action payload construction.

## Shape Notes
- Scope decision: group by company GUID after normalization so missing-GUID anomaly behavior remains visible.
- Challenger result: proceed for keeping grouping separate from normalization.
- Verification focus: pure unit tests for grouping, cap truncation, and trigger preservation.

[[2026-07-10T18:06:22+02:00]]
## Builder Notes
- Files changed: `src/birre/domain/security_analyst/alerts.py`, `src/birre/domain/security_analyst/__init__.py`, `tests/unit/test_security_analyst_alerts.py`.
- Implemented `group_alert_triggers_by_company` with deterministic company-GUID grouping, preserved normalized trigger records and alert provenance, `max_companies` truncation, and warning metadata for cap and non-enrichable records.
- Proof: `uv run pytest tests/unit/test_security_analyst_alerts.py` -> 7 passed.
- Static checks: focused `uv run ruff check` -> all checks passed; focused `uv run pyright` -> 0 errors, 0 warnings, 0 informations.
- Builder challenger: `builder-challenger` decision `pass`; no concrete blockers.
- Follow-up risk: downstream tasks should consume `result["groups"]` and `result["metadata"]["warnings"]` as the grouping contract.
- Existing unrelated/pre-existing worktree changes were preserved and not staged or committed.

[[2026-07-10T18:07:30+02:00]]
## Verify Notes
- Evidence reviewed: `src/birre/domain/security_analyst/alerts.py`, `src/birre/domain/security_analyst/__init__.py`, and `tests/unit/test_security_analyst_alerts.py`; implementation satisfies grouping by company GUID, trigger preservation, company cap warning, non-enrichable warning propagation, and empty-input behavior.
- Checks run: `uv run pytest tests/unit/test_security_analyst_alerts.py` -> 7 passed; focused `uv run ruff check src/birre/domain/security_analyst/alerts.py src/birre/domain/security_analyst/__init__.py tests/unit/test_security_analyst_alerts.py` -> all checks passed; focused `uv run pyright src/birre/domain/security_analyst/alerts.py src/birre/domain/security_analyst/__init__.py` -> 0 errors, 0 warnings, 0 informations.
- Findings: no implementation defect, scope drift, or unresolved acceptance criterion. No patch applied.
- Verifier-challenger: decision `pass`; no concrete blocker or unresolved risk.
- Final route: PASS to collect.

[[2026-07-10T18:07:44+02:00]]
## Collect Notes
- Classification: leaf. Task 6 has no child tasks; its parent reference is organizational, not aggregate intent.
- Verification evidence: existing `## Verify Notes` records PASS, 7 focused unit tests passed, focused ruff passed, focused pyright reported 0 errors, 0 warnings, and 0 informations, and verifier-challenger passed.
- Dependency gate: dependency #5 is archived with archival reason `completed`.
- Residual decisions/follow-up: no pending decision requests for task 6; no unresolved Required Follow-up section or acceptance criterion remains.
- Archive rationale: verified leaf task is complete and ready for terminal archival.
