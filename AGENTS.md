# AGENTS.md

This file provides guidance to LLM agents when working with code in this repository.

## Project overview

- Project Overview: @README
- Requirements Specification: @docs/REQUIREMENTS.md
- Project Architecture: @docs/ARCHITECTURE.md
- Implementation Status: @docs/STATUS.md
- BitSight API v1 Reference: @apis/bitsight.v1.overview.md
- BitSight API v2 Reference: @apis/bitsight.v2.overview.md

## Project Principles

1. **When anything is unclear, seems inconsistent, or is unsuitable to reach design goals: Stop and ask the user — never guess, assume, or silently default.**  
    - This applies at all stages: requirements, system design, and implementation.
    - Always clarify technical ambiguities or specification gaps with a clear technical question.
    - Pay attention to user uncertainty signals: "I think", "probably", "maybe", rough estimates - investigate or ask to investigate.

2. **Build a Minimal Viable Product (MVP) for personal use first — iterate and refine only if requested.**  
    - Prioritize functionality and stability over broad compatibility
    - Avoid premature optimization for universal use cases

3. **Utilize Gemini Bridge strategically for free analysis, validation, and error resolution.**
   - Escalate to Gemini immediately when failing to resolve any error or technical issue
   - Leverage Gemini's 1M token capacity for large-context analysis requiring concise, technical responses
   - Use Gemini to validate significant code changes via concise diff review before implementation
   - Compare solutions from both models for critical architectural decisions

## MCP Servers

- **Serena**: Code analysis, navigation, and editing
  - ALWAYS use `get_symbols_overview` BEFORE reading files
  - ALWAYS use symbol tools INSTEAD of Read for source file exploration
  - ALWAYS use `find_symbol` + `find_referencing_symbols` INSTEAD of Grep for code analysis
  - PREFER `insert_before_symbol`/`insert_after_symbol` for semantic code placement
  - USE `search_for_pattern` with `restrict_search_to_code_files=true` to avoid cache noise
  - NEVER use `find_file` INSTEAD of Glob for complex file patterns and discovery
  - ONLY fallback to Edit tool when symbols have declaration/definition conflicts
- **Context7**: External library documentation and examples
  - ALWAYS use FIRST for any GitHub repository - provides ready-to-use code snippets with context
  - ALWAYS query specific topics: "setup initialization", "I2C communication", "error handling"
  - ALWAYS check Context7 BEFORE implementing custom solutions
- **read-website-fast**: Read web pages converted to Markdown
  - MANDATORY for ALL web pages, especially hardware specs, datasheets, documentation, tutorials
  - ALWAYS use INSTEAD of WebFetch - single call gets full content vs truncated results
  - ONLY use for GitHub repos WHEN Context7 returns no results for specific libraries
- **Gemini Bridge**: Google Gemini AI consultation via MCP bridge
  - ALWAYS escalate to Gemini if you cannot solve ANY error after first attempt
  - ALWAYS use for analysis requiring 50k+ token context (large codebases, comprehensive docs, security reviews)
  - CONSIDER using for code review of significant changes before implementation (diffs preferred for efficiency)
  - REQUEST concise, technical responses: "You're consulting with another AI system - provide direct technical analysis without explanations, examples, or verbose context. Focus on actionable insights only."
  - PREFER for cost-heavy analysis tasks due to free tier availability

## Sources & Documentation

- **FastMCP framework**: <https://gofastmcp.com/servers/server>
- **uv repository**: <https://github.com/astral-sh/uv>
- **uv docs**: <https://docs.astral.sh/uv/>
- **PEP723 spec**: <https://peps.python.org/pep-0723/>
- **uv implementation of PEP723**: <https://docs.astral.sh/uv/guides/scripts/>

## AI Collaboration Strategy

**Multi-Model Development Approach**: Optimize development costs and quality through strategic AI model selection based on task complexity and token economics.

### Token Economics

- Gemini processing is free; you pay your own input tokens for MCP calls and receiving responses
- Request concise, technical responses to minimize your own input costs while maximizing free analysis
- Use Gemini's 1M context window for tasks that would consume your own tokens excessively (>50k)

### Workflow Integration

- **Immediate Escalation**: Route failed attempts directly to Gemini with context
- **Proactive Validation**: Use Gemini for diff review before implementing significant changes  
- **Large Context Delegation**: Send comprehensive analysis tasks to Gemini's superior context capacity
- **Cost-Conscious Collaboration**: Balance free Gemini processing against own token costs for optimal efficiency

### Quality Assurance

- **Cross-Model Validation**: Compare critical solutions across both models for architectural decisions
- **Strategic Selection**: Choose model based on task complexity rather than defaulting to single-AI workflows
- **Continuous Optimization**: Monitor token costs and adjust output limits based on actual usage patterns

## Project Principles (repetition 1)

1. **When anything is unclear, seems inconsistent, or is unsuitable to reach design goals: Stop and ask the user — never guess, assume, or silently default.**  
2. **Build a Minimal Viable Product (MVP) for personal use first — iterate and refine only if requested.**  
3. **Utilize Gemini Bridge strategically for free analysis, validation, and error resolution.**

## Workflow

You systematically develop following established project patterns, FastMCP framework compliance, and the hybrid architecture.

### Development Approach

1. **Requirements Analysis (THINK HARDER)**: Break down tasks into clear requirements, success criteria, quality gates, and constraints. It is essential to critically evaluate all requirements, assessing their feasibility and practicality in terms of framework, architectural layer, and objective alignment. If you notice any inconsistencies or discrepancies, or when in ANY doubt, ALWAYS ASK the user using structured questions - DO NOT ASSUME OR GUESS.
2. **System Design (THINK HARDER)**: Identify required modules, interfaces, integrations, and resources before coding. Follow the FastMCP hybrid architecture and determine which components changes affect.
3. **Implementation Strategy (THINK)**: Choose between TDD (when tests exist or explicitly requested) or direct development. Implement component by component, leveraging FastMCP auto-generation.
4. **Quality Assurance (THINK HARD)**: Verify against modular design principles, FastMCP compliance, and framework guidelines. Prefer running single tests, and not the whole test suite, for performance

#### Question Format

**Question [X]: {Clear question statement}**

- **Options:** (up to 8 options max.)
  - A) {Option 1 with brief explanation}
  - B) {Option 2 with brief explanation}
- **Best Practice:** {Relevant FastMCP/Python development best practice}
- **Recommendation:** {Recommended option with reasoning}

## Communication Guideline

- Be direct and technical. No fluff - this is engineering, not marketing.
- Assume I understand common programming concepts without over-explaining
- Point out potential bugs, performance issues, or maintainability concerns
- Don't hedge criticism - Tell me if something is objectively bad and why
- Don't treat subjective preferences as objective improvements

Always think step-by-step through the development process, considering the project's goals, existing architecture, and framework limitations. Prefer editing existing files over creating new ones. Avoid making assumptions, collect veryfiable data instead.

## Essential Testing and Development Commands

**Note**: All commands should be run from the project root directory.

### Running Tests (Essential)

Assume `BITSIGHT_API_KEY` environment variable is set, even if invisible, so online tests are possible.

```bash
# Run offline unit tests only (default selection)
uv run pytest -v

# Run online MCP smoke tests (requires BITSIGHT_API_KEY)
uv run pytest -m online -rs

# Fetch rating summary for the default sample query
uv run python scripts/min_mcp_client.py
```

### Running the Server (Essential)

```bash
# Run BiRRe with uv (easiest way - automatically installs dependencies)
uv run server.py run

# Or run from GitHub
uvx --from git+https://github.com/boecht/birre server.py run
```

### FastMCP Implementation Testing (Essential)

```bash
# Test server startup (with timeout to avoid hanging)
timeout 10s uv run server.py run || echo "✅ Server test completed"
```

### Key Environment Variables

- `BITSIGHT_API_KEY` (required): Real BitSight API key of the user - should be exported in shell
- `DEBUG` (optional): Set to "true" for debug logging

## Project Principles (repetition 2)

1. **When anything is unclear, seems inconsistent, or is unsuitable to reach design goals: Stop and ask the user — never guess, assume, or silently default.**  
2. **Build a Minimal Viable Product (MVP) for personal use first — iterate and refine only if requested.**  
3. **Utilize Gemini Bridge strategically for free analysis, validation, and error resolution.**
