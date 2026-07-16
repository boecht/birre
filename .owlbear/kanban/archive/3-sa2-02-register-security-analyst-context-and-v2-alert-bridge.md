---
id: 3
title: 'SA2-02: Register security_analyst context and v2 alert bridge'
status: archived
priority: high
created: 2026-07-10T11:48:03.061146+02:00
updated: 2026-07-10T17:54:59.137839+02:00
tags:
  - security-analyst
  - alert-workflow
  - scope:server
  - type:build
  - reshaped-v2
parent: 1
depends_on:
  - 2
ac:
  - "AC-1: Given `RuntimeInputs(context='security_analyst')`, `RuntimeSettings` accepts
    `context='security_analyst'` and rejects no context-related error."
  - 'AC-2: Given active context `security_analyst`, `_maybe_create_v2_api_server`
    returns the `FastMCP` instance produced by the injected v2 server factory.'
  - 'AC-3: Given active context `standard`, `_maybe_create_v2_api_server` returns
    `None`.'
  - 'AC-4: Given `create_business_server` runs with context `security_analyst`, the
    business server exposes a `call_v2_tool` attribute for workflow code to inject
    into the API runner.'
  - 'AC-5: Given `create_business_server` runs with context `security_analyst`, risk-manager-only
    tools `manage_subscriptions` and `request_company` are absent from the registered
    business tool names.'
proof_bundle: behavioral
blocked: false
block_reason:
claimed_at:
archival_reason: completed
archival_refs: []
---
Brief: `.owlbear/briefs/draft-birre-alert-workflows/brief.md`

## Scope
Add the `security_analyst` runtime context and wire the v2 alert bridge needed by the alert workflow without making the workflow MCP-first.

## Local Architecture Anchors
- `src/birre/config/settings.py` currently restricts contexts to `standard` and `risk_manager`.
- `src/birre/application/server.py` owns `INSTRUCTIONS_MAP`, `_maybe_create_v2_api_server`, and context-specific tool wiring.
- v2 calls are bridged through `call_v2_openapi_tool` in `src/birre/integrations/bitsight/v1_bridge.py`.

## Dependencies
Depends on #2 for the request/config contract.

## Non-Goals
- Direct Jira writes.
- Risk-manager subscription/request-company behavior changes.
- Normal MCP-tool-first workflow exposure.

## Shape Notes
- Scope decision: server context registration is separate from pure workflow modeling because it changes accepted runtime settings and server assembly.
- Challenger result: reconsider accepted; keep this split from #2.
- Verification focus: settings normalization and server assembly tests with stubbed v2 server factory.

[[2026-07-10T17:53:17+02:00]]
## Builder Notes
- Files changed: `src/birre/config/settings.py`, `src/birre/application/server.py`, `tests/unit/test_settings.py`, `tests/unit/test_birre_server.py`.
- Implemented `security_analyst` context normalization and instructions, enabled its v2 FastMCP server/`call_v2_tool` bridge, and retained the standard tool path so risk-manager-only tools remain absent.
- Proof: `uv run pytest tests/unit/test_settings.py tests/unit/test_birre_server.py -q` -> 18 passed.
- Proof: focused `uv run ruff check` on all four files -> passed; `uv run ruff format --check` on all four files -> passed; editor diagnostics -> no errors; `git diff --check` -> clean.
- Builder challenger: pass, no blockers.
- Follow-up risk: full-suite and online integration tests were not run; v2 behavior is covered with stubbed server factories in the focused unit slice.

[[2026-07-10T17:54:42+02:00]]
## Verify Notes
- Evidence reviewed: task AC-1 through AC-5, builder notes, `src/birre/config/settings.py`, `src/birre/application/server.py`, `tests/unit/test_settings.py`, and `tests/unit/test_birre_server.py`.
- Checks run: `uv run pytest tests/unit/test_settings.py tests/unit/test_birre_server.py -q` -> 18 passed. Scoped `git diff --check` -> clean. Scoped worktree review confirmed only the task's four files are involved.
- Findings: `security_analyst` is accepted by settings normalization; v2 server creation and `call_v2_tool` exposure are enabled for `security_analyst`; standard context does not create v2; risk-manager-only registrations remain guarded by `active_context == "risk_manager"`. All five ACs are satisfied. No patch applied.
- Verifier-challenger: pass. Confirmed intent-to-code alignment, sufficient focused proof, no scope drift, and no unresolved AC.
- Final route: PASS to collect.

[[2026-07-10T17:54:59+02:00]]
## Collect Notes
- Classification: leaf. The task has no child tasks and is not an aggregate/EPIC task.
- Verification evidence: existing `## Verify Notes` records verifier PASS, all five acceptance criteria satisfied, focused settings/server tests with 18 passed, scoped diff clean, and verifier-challenger pass.
- Follow-up and decision state: no unresolved Required Follow-up, decision request, or blocker is present. The noted full-suite/online-test risk does not prevent closure because focused behavioral proof is complete for this task's scope.
- Archive rationale: leaf verification is complete and the task is ready for mechanical archival as completed.
