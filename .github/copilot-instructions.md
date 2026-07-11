# BiRRe - Copilot Workspace Instructions

## 1. Project Identity

BiRRe (BitSight Rating Retriever) is a Python FastMCP server that exposes curated,
strongly typed BitSight workflows to MCP clients. It supports the standard and
`risk_manager` runtime contexts, including safe subscription and onboarding workflows.

## 2. Directory Structure

| Path | Purpose |
| ------ | --------- |
| `src/birre/` | Application source, runtime contexts, CLI, and BitSight API clients |
| `src/birre/domain/` | Domain workflows and business rules |
| `tests/unit/` | Unit tests |
| `tests/cli/` | CLI tests |
| `tests/integration/` | Integration tests |
| `docs/` | Architecture, CLI, and BitSight API reference documentation |
| `.github/instructions/` | Project-specific file instructions |

## 3. Tech Stack

| Component | Technology | Notes |
| ------ | ------------ | ------- |
| Language | Python 3.14+ | Managed with `uv` |
| MCP server | FastMCP 3 | Entrypoint: `birre:create_birre_server` |
| CLI | Typer | Entrypoint: `uv run birre` |
| Validation | pytest, Ruff, Pyright | Run focused checks for changed behavior |
| HTTP and models | httpx, Pydantic v2 | Use existing clients and models before adding abstractions |

## 4. Project Rules

### Ponytail Principles

Prefer the smallest correct change after tracing the real control path:

1. Reuse existing code, the standard library, platform capabilities, or installed dependencies before writing new code.
2. Fix defects at their shared root cause; inspect callers before patching a named symptom.
3. Avoid unrequested abstractions, dependencies, boilerplate, and unrelated refactors.
4. Choose the edge-case-correct option when solutions are similarly small.
5. Leave proportional runnable proof for non-trivial logic. A `ponytail:` comment marks an intentional simplification
   and its known ceiling.

### Domain Boundaries

- Preserve BitSight trust boundaries: validate external input and prevent unintended subscription, onboarding,
  or data-changing operations.
- Prefer the existing typed API clients and domain workflows over direct ad hoc HTTP calls.
- Documentation and changelog entries describe user impact; follow
  `.github/instructions/edit-changelog.instructions.md` when editing `CHANGELOG.md`.

Shared agent lifecycle, memory, commits, Kanban, communication, and escalation rules are owned by OwlBear skills and instructions.

## 5. Useful Commands

- `uv run pytest` - full test suite
- `uv run pytest --offline` - offline-only tests
- `uv run pytest --online-only` - online-only tests when BitSight credentials are configured
- `uv run ruff check src tests` - lint changed Python surfaces
- `uv run pyright` - type check
- `uv run birre` - run the local MCP server

## 6. Resources

- [README.md](../README.md)
- [Architecture](../docs/ARCHITECTURE.md)
- [CLI reference](../docs/CLI.md)
- [BitSight API v1 reference](../docs/apis/bitsight.v1.overview.md)
- [BitSight API v2 reference](../docs/apis/bitsight.v2.overview.md)
