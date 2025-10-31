# AGENTS.md

This file provides guidance to LLM agents when working with code in this repository.

## Project overview & Documentation

- Project Overview: @README.md
- Changelog: @CHANGELOG.md
- Changelog Standards: @docs/CHANGELOG_STANDARDS.md
- Project Architecture: @docs/ARCHITECTURE.md
- BitSight API v1 Reference: @docs/apis/bitsight.v1.overview.md
- BitSight API v2 Reference: @docs/apis/bitsight.v2.overview.md
- FastMCP framework: <https://gofastmcp.com/servers/server>

## Project Principles

1. **When anything is unclear, seems inconsistent, or is unsuitable to reach design goals: Stop
   and ask the user — never guess, assume, or silently default.**
    - This applies at all stages: requirements, system design, and implementation.
    - Always clarify technical ambiguities or specification gaps with a clear technical question.
    - Pay attention to user uncertainty signals: "I think", "probably", "maybe", rough estimates
      - investigate or ask to investigate.

2. **Build a Minimal Viable Product (MVP) for personal use first — iterate and refine only if
   requested.**
    - Prioritize functionality and stability over broad compatibility
    - Avoid premature optimization for universal use cases

3. **Quality and architecture trump backwards compatibility**
    - Breaking changes are acceptable and encouraged if they improve the codebase
    - No legacy code - refactor or remove outdated patterns immediately
    - Do it once, do it right - no shortcuts or temporary workarounds
    - Clean, maintainable architecture is more important than preserving old APIs

4. **Documentation focuses on user value, not internal implementation**
    - CHANGELOG describes user benefits using established standards (see @docs/CHANGELOG_STANDARDS.md)
    - Emphasize impact: reliability improvements, performance gains, better user experience
    - Avoid internal codes (TD-XXX, QA-XXX), implementation details, function names
    - Technical details belong in commit messages and internal tracking
    - Example transformation:
      - ❌ "Refactored 7 functions to reduce complexity (TD-003)"
      - ✅ "Enhanced reliability through simplified error handling"

## Documentation Guidelines

### Commit Messages (Developer-Facing)

- **Audience**: Developers, maintainers
- **Focus**: What changed, why it changed, technical details
- **Include**: File names, function names, implementation approach
- **Examples**:
  - ✅ Good: "Simplify sync_bridge.py by replacing reusable loop with asyncio.run()"
  - ❌ Bad: "Improved reliability" (too vague for commits)

### Code Comments (Implementation-Facing)

- **Focus**: Why code does something non-obvious, not what it does
- **Include**: Edge cases, workarounds, framework-specific patterns
- **Avoid**: Obvious descriptions, commented-out code

## Workflow

You systematically develop following established project patterns, FastMCP framework compliance,
and the hybrid architecture.

### Development Approach

1. **Requirements Analysis**: Break down tasks into clear requirements, success criteria,
   and constraints. Critically evaluate feasibility in terms of framework capabilities,
   architectural fit, and objective alignment. When in doubt, ask using structured questions.
2. **System Design**: Identify required modules, interfaces, integrations, and
   resources before coding. Follow the FastMCP hybrid architecture and determine which components
   changes affect.
3. **Implementation Strategy**: Choose between TDD (when tests exist or explicitly
   requested) or direct development. Implement component by component, leveraging FastMCP
   auto-generation.
4. **Quality Assurance**: Verify against modular design principles, FastMCP
   compliance, and framework guidelines. Prefer running single tests, and not the whole test
   suite, for performance

Always think step-by-step through the development process, considering the project's goals,
existing architecture, and framework limitations.

### Development Best Practices

- **Think step-by-step**: Consider project goals, existing architecture, and framework limitations
- **Prefer editing over creating**: Modify existing files rather than creating new ones
- **Verify, don't assume**: Collect verifiable data instead of making assumptions
- **Run targeted tests**: Use single test files/functions for faster feedback during development
- **Test after changes**: Always run relevant tests after editing to catch regressions early

## Communication Guideline

- Be direct and technical. No fluff - facts over feelings
- Assume the user understands common programming concepts without over-explaining
- Point out potential bugs, performance issues, or maintainability concerns
- Don't hedge criticism - tell the user if something is objectively bad and why
- Don't treat subjective preferences as objective improvements

### Asking Questions

When asking the user for clarification, use structured format:

**Question #X**: {Clear, specific question}

**Options**:

- A) {Option with trade-offs}
- B) {Option with trade-offs}
- C) {Additional options as needed}

**Context**: {Relevant best practices or constraints}

**Recommendation**: {Your recommendation with reasoning}

## Essential Testing and Development Commands

**Note**: All commands should be run from the project root directory.

### Running Tests (Essential)

**Note for agents**: The `BITSIGHT_API_KEY` environment variable is set in the user's shell
environment. You cannot see it in command outputs for security reasons, but it is available
for running online tests.

```bash
# Run offline unit tests only
uv run pytest -m offline

# Run online MCP smoke tests (requires BITSIGHT_API_KEY)
uv run pytest -m online
```

### Running the Server (Essential)

```bash
# Run BiRRe with uv (easiest way - automatically installs dependencies)
uv run birre run
```

### FastMCP Implementation Testing (Essential)

```bash
# Test server startup (with timeout to avoid hanging)
timeout 15s uv run birre run || echo "✅ Server test completed"
```

### Key Environment Variables

- `BITSIGHT_API_KEY` (required): Real BitSight API key of the user - should be exported in shell
- `DEBUG` (optional): Set to "true" for debug logging
