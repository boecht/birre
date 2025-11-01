# Agent Operations Guide

This guide aligns LLM agents with BiRRe workflows. Skim section 2 for philosophy,
section 3 for day-to-day execution, and section 5 for the commands you will run most often

## 1. Orientation & Reference Docs

### Quick Links

- Project Overview: @README.md
- Changelog: @CHANGELOG.md
- Changelog Standards: @docs/CHANGELOG_STANDARDS.md
- Project Architecture: @docs/ARCHITECTURE.md
- BitSight API v1 Reference: @docs/apis/bitsight.v1.overview.md
- BitSight API v2 Reference: @docs/apis/bitsight.v2.overview.md
- FastMCP framework: <https://gofastmcp.com/servers/server>

## 2. Core Principles

### Project Principles

1. **When anything is unclear, seems inconsistent, or is unsuitable to reach design goals:
   Stop and ask the user — never guess, assume, or silently default.**
   - Applies at all stages: requirements, system design, implementation
   - Always clarify technical ambiguities or specification gaps with a clear technical question
   - Watch for uncertainty signals such as "I think", "probably", "maybe", and investigate

2. **Build a Minimal Viable Product (MVP) for personal use first — iterate and refine only if requested.**
   - Prioritize functionality and stability over broad compatibility
   - Avoid premature optimization for universal use cases

3. **Quality and architecture trump backwards compatibility.**
   - Breaking changes are acceptable if they improve the codebase
   - Remove outdated patterns immediately; do not preserve legacy code
   - Avoid shortcuts; build the right solution once
   - Clean, maintainable architecture outranks legacy API stability

4. **Documentation focuses on user value, not internal implementation.**
   - CHANGELOG entries describe user benefits using @docs/CHANGELOG_STANDARDS.md
   - Highlight impact (reliability, performance, UX) instead of internal codes (TD-XXX, QA-XXX)
   - Keep technical specifics in commits and internal tracking
   - Example:
     - ❌ "Refactored 7 functions to reduce complexity (TD-003)"
     - ✅ "Enhanced reliability through simplified error handling"

5. **If you are Claude: Check section 6 "Claude-Specific Requirements" BEFORE starting any task.**
   - This includes mandatory CRASH tool usage requirements
   - Failure to check section 6 violates this core principle
   - Non-negotiable: read section 6 first, then proceed with the task

### Documentation Principles

- **Commit Messages (developer-facing)**
  - Audience: developers and maintainers
  - Focus: what changed, why it changed, and technical detail
  - Include: file names, function names, implementation approach
  - Example contrast: ✅ "Simplify sync_bridge.py by replacing reusable loop with asyncio.run()" vs. ❌ "Improved reliability"

- **Code Comments (implementation-facing)**
  - Capture the "why" for non-obvious behaviour
  - Document edge cases, workarounds, or framework patterns
  - Avoid obvious narrations or commented-out code

## 3. Standard Workflow

### Development Approach

- **Requirements Analysis**
  - Break down tasks into clear requirements, success criteria, and constraints
  - Evaluate feasibility with respect to FastMCP capabilities and project architecture
  - When uncertain, ask using the structured format
- **System Design**
  - Identify required modules, interfaces, integrations, and resources before coding
  - Map changes to FastMCP hybrid architecture components
- **Implementation Strategy**
  - Choose TDD when tests exist or are requested
  - Otherwise implement directly, component by component, leveraging FastMCP auto-generation
- **Quality Assurance**
  - Check against modular design principles, FastMCP compliance, and framework guidelines
  - Prefer targeted tests over full suite runs for speed

### Development Best Practices

- Think step-by-step about goals, architecture, and limitations
- Prefer editing existing files over creating new ones
- Verify assumptions with data; never guess
- Run the smallest relevant tests for rapid feedback
- Execute pertinent tests after every change to catch regressions early

### Commit Practices

- **One topic per commit**: Group related changes cohesively, but separate unrelated topics
  - ✅ Good: "Fix Python 3.13 compatibility across all workflows" (one topic, multiple files)
  - ❌ Bad: "Fix tests, update docs, add feature, refactor config" (mixing unrelated changes)
- **Safety boundary**: NEVER commit directly to `main` branch or approve pull requests
  - Only humans may manually merge PRs or commit to protected branches
  - If a task requires this, stop and ask the user to perform the action
  - This enforces branch protection and human oversight of production changes

### Quality Assurance Checklist

- Validate outputs against the original task description before finalizing
- Confirm tests were run (or explain why they were skipped) and record outcomes
- Ensure documentation and comments reflect any significant behaviour changes
- Cross-check that FastMCP integration points remain consistent

## 4. Communication Protocol

### Messaging Guidelines

- Be direct and technical; prioritize facts over tone
- Assume core programming literacy; skip over-explaining basics
- Flag bugs, performance issues, or maintainability risks immediately
- State opinions as such; do not present subjective preferences as facts

### Structured Clarification Requests

When asking the user for clarification, follow this template:

```text
**Question #X**: {Clear, specific question}
**Options**:
- A) {Option with trade-offs}
- B) {Option with trade-offs}
- C) {Additional options as needed}
**Context**: {Relevant best practices or constraints}
**Recommendation**: {Your recommendation with reasoning}
```

## 5. Tooling & Runtime

### Environment Requirements

- BiRRe requires **Python 3.13** or later. Install via uv if unavailable:

  ```bash
  uv python install 3.13
  ```

### Testing Commands

- Offline tests:

  ```bash
  uv run pytest -m offline
  ```

- Online smoke tests (requires `BITSIGHT_API_KEY`, assume it is exported in the user's shell):

  ```bash
  uv run pytest -m online
  ```

### Server Operations

- Run BiRRe locally (auto-installs dependencies):

  ```bash
  uv run birre
  ```

- FastMCP smoke test with timeout:

  ```bash
  timeout 15s uv run birre || echo "✅ Server test completed"
  ```

## 6. Model-Specific Addenda

### Claude-Specific Requirements

**If you are powered by Anthropic's Claude model, follow these mandatory requirements:**

#### CRASH Tool Usage

Use the CRASH tool (structured reasoning) for all multi-step tasks, including:

- Tasks requiring clarifying questions to the user
- Multi-step analysis, review, or planning tasks
- Code refactoring or architectural changes
- Bug investigation and fixes (beyond trivial typos)
- Feature implementation requiring multiple components
- Documentation updates (even single files with multiple sections)
- Version migrations or dependency updates

**Workflow**: Plan (step 1-2) → Execute one step at a time (step 3-N) → Final QA (last step)

**CRASH Features to Leverage**:

- Use `revises_step` to correct mistakes in earlier reasoning
- Use `branch_from` to explore alternative approaches
- Track `confidence` and `uncertainty_notes` when facing ambiguous situations

**If CRASH tool is unavailable**: Refuse to proceed on multi-step tasks.
Ask the user to install the CRASH MCP server from <https://github.com/nikkoxgonzales/crash-mcp>.

#### Mandatory QA Step

Every task must end with a QA review that compares all work to the initial task:

1. **Restate original task**: What did the user ask for?
2. **List file changes**: For each modified file, explain how the change serves the original task
3. **Identify misalignment**: Call out any changes that don't directly serve the task objective
4. **Reflect on alignment**: Does the complete set of changes accomplish what was requested?
   Are there gaps or overreach?
5. **Verify changes**: Read back edited content to confirm correctness

## 7. Appendix

### FastMCP Resources

- FastMCP framework documentation: <https://gofastmcp.com/servers/server>
