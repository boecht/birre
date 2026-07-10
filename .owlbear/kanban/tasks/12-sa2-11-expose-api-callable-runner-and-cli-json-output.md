---
id: 12
title: 'SA2-11: Expose API-callable runner and CLI JSON output'
status: shape
priority: medium
created: 2026-07-10T11:49:15.319222+02:00
updated: 2026-07-10T11:49:15.319222+02:00
tags:
  - security-analyst
  - alert-workflow
  - scope:api-cli
  - type:build
  - reshaped-v2
parent: 1
depends_on:
  - 3
  - 11
ac:
  - 'AC-1: Given stubbed `call_v2_tool` and company fetcher dependencies, `run_alert_workflow_action_payload`
    returns the structured payload produced by `build_jira_action_payload`.'
  - 'AC-2: Given stubbed dependencies that emit warnings from fetch, normalization,
    enrichment, movement, scoring, and filtering, `run_alert_workflow_action_payload`
    returns those warning codes in run metadata.'
  - 'AC-3: Given the CLI command is invoked with alert window and cap options, the
    command writes JSON to stdout containing `action_items` and `metadata`.'
  - 'AC-4: Given bad CLI cap input `page_size=0`, the CLI command exits with a nonzero
    code and stderr text containing `page_size`.'
  - 'AC-5: Given the runner and CLI execute, neither path calls a Jira client or writes
    durable queue/cursor state.'
proof_bundle: behavioral
blocked: false
block_reason:
claimed_at:
archival_reason:
archival_refs: []
---
Brief: `.owlbear/briefs/draft-birre-alert-workflows/brief.md`

## Scope
Expose the deterministic workflow through an API-callable runner and a CLI command that returns JSON structured Jira-action data.

## Local Architecture Anchors
- `src/birre/cli/app.py` registers Typer command modules.
- Existing command modules live under `src/birre/cli/commands/`.
- CLI tests use `CliRunner` in `tests/cli/test_cli_app_commands.py`.
- Server/context wiring from #3 provides the role-oriented runtime context, while this workflow remains API/CLI-first.

## Dependencies
Depends on #3 for security-analyst context wiring and #11 for payload construction.

## Non-Goals
- Direct Jira writes.
- Durable queue/cursor state.
- Normal MCP-tool-first exposure.
- Management summaries.

## Shape Notes
- Scope decision: combine runner and CLI because both are thin surfaces over the deterministic workflow core.
- Challenger result: proceed for API and CLI merge; keep consolidation proof separate.
- Verification focus: unit tests for injectable runner dependencies and Typer CLI JSON/error behavior.
