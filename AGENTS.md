# AGENTS.md

This file provides guidance to LLM agents when working with code in this repository.

## Project overview

- Project Overview: @README
- Roadmap & Version History: @docs/ROADMAP.md
- Project Architecture: @docs/ARCHITECTURE.md
- BitSight API v1 Reference: @docs/apis/bitsight.v1.overview.md
- BitSight API v2 Reference: @docs/apis/bitsight.v2.overview.md

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

## MCP Servers

- **Context7**: External library documentation and examples
  - ALWAYS use FIRST for any GitHub repository - provides ready-to-use code snippets with context
  - ALWAYS query specific topics: "setup initialization", "I2C communication", "error handling"
  - ALWAYS check Context7 BEFORE implementing custom solutions
- **read-website-fast**: Read web pages converted to Markdown
  - MANDATORY for ALL web pages, especially hardware specs, datasheets, documentation, tutorials
  - ALWAYS use INSTEAD of WebFetch - single call gets full content vs truncated results
  - ONLY use for GitHub repos WHEN Context7 returns no results for specific libraries

## Sources & Documentation

- **FastMCP framework**: <https://gofastmcp.com/servers/server>
- **uv repository**: <https://github.com/astral-sh/uv>
- **uv docs**: <https://docs.astral.sh/uv/>
- **PEP723 spec**: <https://peps.python.org/pep-0723/>
- **uv implementation of PEP723**: <https://docs.astral.sh/uv/guides/scripts/>

## Project Principles (repetition 1)

1. **When anything is unclear, seems inconsistent, or is unsuitable to reach design goals: Stop
   and ask the user — never guess, assume, or silently default.**  
2. **Build a Minimal Viable Product (MVP) for personal use first — iterate and refine only if
   requested.**  

## Workflow

You systematically develop following established project patterns, FastMCP framework compliance,
and the hybrid architecture.

### Development Approach

1. **Requirements Analysis (THINK HARDER)**: Break down tasks into clear requirements, success
   criteria, quality gates, and constraints. It is essential to critically evaluate all
   requirements, assessing their feasibility and practicality in terms of framework, architectural
   layer, and objective alignment. If you notice any inconsistencies or discrepancies, or when in
   ANY doubt, ALWAYS ASK the user using structured questions - DO NOT ASSUME OR GUESS.
2. **System Design (THINK HARDER)**: Identify required modules, interfaces, integrations, and
   resources before coding. Follow the FastMCP hybrid architecture and determine which components
   changes affect.
3. **Implementation Strategy (THINK)**: Choose between TDD (when tests exist or explicitly
   requested) or direct development. Implement component by component, leveraging FastMCP
   auto-generation.
4. **Quality Assurance (THINK HARD)**: Verify against modular design principles, FastMCP
   compliance, and framework guidelines. Prefer running single tests, and not the whole test
   suite, for performance

#### Question Format

**Question [X]: {Clear question statement}**

- **Options:** (up to 8 options max.)
  - A) {Option 1 with brief explanation}
  - B) {Option 2 with brief explanation}
- **Best Practice:** {Relevant FastMCP/Python development best practice}
- **Recommendation:** {Recommended option with reasoning}

## Communication Guideline

- Be direct and technical. No fluff - this is engineering, not marketing
- Assume I understand common programming concepts without over-explaining
- Point out potential bugs, performance issues, or maintainability concerns
- Don't hedge criticism - tell me if something is objectively bad and why
- Don't treat subjective preferences as objective improvements

Always think step-by-step through the development process, considering the project's goals,
existing architecture, and framework limitations. Prefer editing existing files over creating new
ones. Avoid making assumptions, collect veryfiable data instead.

## Essential Testing and Development Commands

**Note**: All commands should be run from the project root directory.

### Running Tests (Essential)

Assume `BITSIGHT_API_KEY` environment variable is set, even if invisible, so online tests are possible.

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
timeout 10s uv run birre run || echo "✅ Server test completed"
```

### Key Environment Variables

- `BITSIGHT_API_KEY` (required): Real BitSight API key of the user - should be exported in shell
- `DEBUG` (optional): Set to "true" for debug logging

## Project Principles (repetition 2)

1. **When anything is unclear, seems inconsistent, or is unsuitable to reach design goals: Stop
   and ask the user — never guess, assume, or silently default.**  
2. **Build a Minimal Viable Product (MVP) for personal use first — iterate and refine only if
   requested.**  
