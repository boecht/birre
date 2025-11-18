---
description: Fix all current SonarQube findings and Problems
agent: gpt-5-beast-mode
model: GPT-5 (copilot)
tools: [
  'edit/editFiles',            # Apply code changes
  'edit/createFile',           # Extract constants / helpers into new file if beneficial
  'edit/createDirectory',      # Create new package folder if logically grouping shared constants (avoid unless needed)
  'search',                    # Locate patterns/usages across repo
  'usages',                    # Find symbol references to ensure complete replacement/refactor
  'problems',                  # Retrieve IDE Problems (lint/type) issues
  'sonarqube/analyze_code_snippet',           # Generic snippet analysis
  'sonarsource.sonarlint-vscode/sonarqube_analyzeFile', # Precise file re-analysis after edits
  'sonarsource.sonarlint-vscode/sonarqube_getPotentialSecurityIssues', # Direct listing of security hotspots
  'sonarsource.sonarlint-vscode/sonarqube_excludeFiles', # (Use only for justified false positives; last resort)
  'sonarsource.sonarlint-vscode/sonarqube_setUpConnectedMode', # (If connection/setup required before analysis)
  'sonarqube/show_rule',       # Fetch rule metadata for context-driven fixes
  'runTests',                  # Run unit/integration tests to prevent regressions
  'changes',                   # Inspect working tree diff to keep fix batches small & reviewable
  'think',                     # Deep reasoning for complex or ambiguous fixes
  'todos',                     # Structured task management
  'fetch',                     # Pull authoritative external best-practice references (HTTPS enforcement, etc.)
  'runCommands',               # Execute auxiliary commands (git status, grep, formatting) when needed
  'testFailure'                # Inspect failing test details rapidly if regressions appear
]
---

## Objective

Drive the codebase to a state where SonarQube (security / code quality hotspots surfaced
via list_potential_security_issues) AND the IDE Problems list report zero outstanding actionable findings for the
targeted files. Maintain functional and test integrity while applying minimally invasive, high-quality fixes.

## Scope

1. Start with files currently showing findings.
2. Enumerate ALL findings from BOTH sources:
    - Sonar (security & code quality): prefer `sonarsource.sonarlint-vscode/sonarqube_getPotentialSecurityIssues`
      plus `sonarsource.sonarlint-vscode/sonarqube_analyzeFile` for full file after every change. Fallback:
      `sonarqube/analyze_code_snippet` for targeted snippet validation; `sonarqube/show_rule` for rule metadata.
    - Problems: use `problems` (get_errors) per file.
3. Treat both sources as complementary; merge/normalize into a unified issue list (deduplicate identical root causes).
4. Expand scope if fixes introduce new findings elsewhere (iterate until stable zero state).

## Issue Categories & Typical Fixes

| Category | Source(s) | Fix Strategy |
|----------|-----------|--------------|
| Insecure protocol (http→https) | Sonar | Replace with https if endpoint supports it (most public domains). Canonicalize duplicated literals simultaneously. |
| Duplicate string literals | Problems | Introduce a module-level constant (ALL_CAPS) or reuse existing constants; avoid over-abstraction. |
| Other (if discovered) | Both | Apply least intrusive change preserving semantics, with docstring/comment only when intent could be unclear. |

## Process

1. Planning: Use `todos` to outline each issue (security > maintainability priority).
2. Enumeration: For each candidate file, collect Sonar + Problems findings.
3. Normalization: For each finding record: source(s), rule/message, line(s), proposed fix,
  risk level (security/maintainability).
4. Fix Implementation Order:
  a. Security hotspots (Bugs, Vulnerabilities, other blocking and critical findings).
  b. Refactors reducing duplication or maintainability warnings.
5. Apply edits in cohesive commits (the assistant session groups them; human will commit later).
  Keep changes minimal; do not introduce new deps.
6. Re-run Problems + Sonar listing after each batch:
    - If residual issues remain, iterate.
7. Run tests (`runTests`) focusing on affected unit tests or full suite if low cost.
8. If a reported issue is a false positive or intentionally retained (rare):
    - Verify via rule description (`sonarqube/show_rule`).
    - Only if justified, consider marking accepted (`sonarqube/change_sonar_issue_status`),
      but PREFER code fix—document rationale inline in a concise comment.
9. Finish when both sources return zero actionable findings and tests pass.

## Acceptance Criteria

All must be satisfied:

1. Sonar: `sonarsource.sonarlint-vscode/sonarqube_getPotentialSecurityIssues`
  and `sonarsource.sonarlint-vscode/sonarqube_analyzeFile` return zero actionable findings for
  modified files (no insecure protocol, duplication causing hotspots, or other flagged issues).
  Snippet checks (`sonarqube/analyze_code_snippet`) also clean.
2. Problems: no duplication or related warnings for those files.
3. All tests pass (or unchanged failing tests are unrelated and disclosed).
4. No new warnings introduced elsewhere.
5. Code adheres to project Python style instructions (types, line length ≤100, clarity).
6. No behavioral regression (semantic meaning unchanged except improved safety).

## Constraints & Guidelines

- Do NOT add external dependencies.
- Keep fixes surgical: prefer small local changes over broad refactors.
- Avoid over-engineering; MVP-quality improvements only.
- Preserve existing public APIs.
- Honor `# NOSONAR` markers: NEVER modify a line containing `# NOSONAR` unless (a) the line is explicitly requested
  by the user to change, OR (b) Sonar/Problems currently reports an actionable finding for that exact line.
  Otherwise treat such lines as immutable.

## Reporting Format (End of Run)

Produce a final summary table:
| File | Issue (Before) | Source(s) | Fix Applied | Status |
And a short narrative confirming acceptance criteria met or listing remaining blockers.

## Fallback & Ambiguity Handling

If a fix path is uncertain, pause and create a TODO with a clarifying question rather than guessing.
Provide rationale + options.

## Execution Heuristics

- Batch small, related literal replacements together.
- After each batch, re-analyze only changed files first (fast feedback) before broad scans.
- If Sonar still flags the identical issue after replacement, confirm no shadow copies (search).

Proceed with this structured loop until clean state is confirmed.
