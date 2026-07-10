---
id: 3
title: 'SA2-02: Register security_analyst context and v2 alert bridge'
status: shape
priority: high
created: 2026-07-10T11:48:03.061146+02:00
updated: 2026-07-10T11:48:03.061146+02:00
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
archival_reason:
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
