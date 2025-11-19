# BiRRe

[![Python Version][python-badge]][python-link]
[![License][license-badge]][license-link]
[![Type Checked][type-checked-badge]][type-checked-link]
[![OpenSSF Scorecard report][ossf-scr-badge]][ossf-scr-link]
[![Dependabot Updates][dependabot-badge]][dependabot-link]
[![CodeQL][codeql-badge]][codeql-link]
[![SonarCloud Analysis][sonarcloud-badge]][sonarcloud-link]
[![CodeFactor][codefactor-badge]][codefactor-link]
[![MegaLinter][megalinter-badge]][megalinter-link]
[![Cross-Platform Testing][cross-platform-badge]][cross-platform-link]
[![Tests & Coverage][tests-coverage-badge]][tests-coverage-link]
[![codecov][codecov-badge]][codecov-link]

[codecov-badge]: <https://codecov.io/gh/boecht/birre/branch/main/graph/badge.svg>
[codecov-link]: <https://codecov.io/gh/boecht/birre>
[codefactor-badge]: <https://www.codefactor.io/repository/github/boecht/birre/badge>
[codefactor-link]: <https://www.codefactor.io/repository/github/boecht/birre>
[codeql-badge]: <https://github.com/boecht/birre/actions/workflows/github-code-scanning/codeql/badge.svg>
[codeql-link]: <https://github.com/boecht/birre/actions/workflows/github-code-scanning/codeql>
[cross-platform-badge]: <https://github.com/boecht/birre/actions/workflows/cross-platform.yml/badge.svg>
[cross-platform-link]: <https://github.com/boecht/birre/actions/workflows/cross-platform.yml>
[dependabot-badge]: <https://github.com/boecht/birre/actions/workflows/dependabot/dependabot-updates/badge.svg>
[dependabot-link]: <https://github.com/boecht/birre/actions/workflows/dependabot/dependabot-updates>
[license-badge]: <https://img.shields.io/badge/license-Unlicense-blue>
[license-link]: <LICENSE>
[megalinter-badge]: <https://github.com/boecht/birre/actions/workflows/megalinter.yml/badge.svg>
[megalinter-link]: <https://github.com/boecht/birre/actions/workflows/megalinter.yml>
[ossf-scr-badge]: <https://api.scorecard.dev/projects/github.com/boecht/birre/badge>
[ossf-scr-link]: <https://scorecard.dev/viewer/?uri=github.com/boecht/birre>
[python-badge]: <https://img.shields.io/badge/python-3.13%2B-blue>
[python-link]: <pyproject.toml>
[sonarcloud-badge]: <https://sonarcloud.io/api/project_badges/measure?project=boecht_birre&metric=alert_status>
[sonarcloud-link]: <https://sonarcloud.io/summary/new_code?id=boecht_birre>
[tests-coverage-badge]: <https://github.com/boecht/birre/actions/workflows/tests.yml/badge.svg>
[tests-coverage-link]: <https://github.com/boecht/birre/actions/workflows/tests.yml>
[type-checked-badge]: <https://img.shields.io/badge/type--checked-yes-success>
[type-checked-link]: <src/birre/py.typed>

<div align="center">
<img src="https://github.com/boecht/birre/blob/main/birre-logo.png?raw=true" alt="BiRRe Logo" width="350">
</div>

**BiRRe** (*Bi*tsight *R*ating *Re*triever) is a Model Context Protocol (MCP) server that turns a BitSight
subscription into LLM-friendly tools. It hides 400+ raw endpoints behind a curated, strongly-typed workflow surface,
handles ephemeral subscriptions automatically, and ships as a zero-install uv app so analysts and agents can run it
anywhere.

## Why use BiRRe?

- **Unified workflows** – LLMs gain one consistent toolset for search, ratings, onboarding, and subscription hygiene.
- **Safer operations** – automatic folder targeting, dry-run previews, and retry-aware helpers keep BitSight data tidy
  while preventing accidental churn.
- **Trustworthy releases** – strict typing (pyright), property-based tests, signed artifacts, and SBOMs make it easy to
  depend on BiRRe in regulated environments.

## What you need

| Requirement | Details |
|-------------|---------|
| BitSight access | API key with rights to the companies/folders you intend to query. |
| Runtime | Python 3.13+ (`uv` auto-installs across Linux/macOS/Windows). |
| Network | HTTPS to `api.bitsighttech.com` for live data; custom CAs are supported. |
| Client | Any MCP-compatible LLM or agent platform (GPTs, LangChain, local MCP clients, etc.). |

## Quick start

1. Export your BitSight API key.
2. Start the MCP server with uvx (install-free PyPI run):

    ```bash
    export BITSIGHT_API_KEY="your-bitsight-api-key"
    uvx birre
    ```

3. Point your MCP-compatible client/LLM at the server endpoint. Start with `company_search` to obtain
    GUIDs, then call `get_company_rating` or run the risk-manager workflows.
4. Use `--help` for every available command, subcommand, and option.

**The rest of this README assumes a local checkout:**
Create a local copy with `git clone https://github.com/boecht/birre`,
then start with `uv run birre` in the BiRRe directory.

### Configuration

Configuration layers merge in this order: `config.toml` → `config.local.toml` → environment variables →
CLI flags. Inspect or validate the effective settings with:

```bash
uv run birre config show
uv run birre config validate --config differently/named/config.toml
```

See [docs/CLI.md](docs/CLI.md) for full option tables and [config.toml](config.toml) for annotated defaults.

## Tooling overview

Switch contexts via `--context`, `BIRRE_CONTEXT`, or `[runtime].context`. Tool names map directly to MCP tool calls.

### Shared tools (`standard` + `risk_manager`)

| Tool | Inputs | Description |
|------|--------|-------------|
| `company_search` | Company `name` (fuzzy) or `domain` (exact). | Returns the matches (**GUID**, name, domain, count of eligible companies). |
| `get_company_rating` | Company `GUID`. | Compiles a rating payload: current value/color, 8‑week and 1‑year trends, prioritized findings, and the rating legend. (automatically subscribes and unsubscribes, if needed) |

### `risk_manager`-only tools

| Tool | Inputs | Description |
|------|--------|-------------|
| `company_search_interactive` | `name` or `domain` (same as `company_search`). | Enriches search result with current rating, number of employees, subscription state, and more) plus the same info about the parent company. |
| `manage_subscriptions` | `action` (`add`/`delete`), list of `GUIDs`, optional `folder`, `dry_run`. | Validates intent, resolves/creates folders for adds, then executes subscription changes. Returns either a dry-run preview or applied summary (added/deleted/errors, folder metadata). |
| `request_company` | Comma-separated `domains` (max 255), optional `folder`, `dry_run`. | Deduplicates submissions, reports already-requested domains, and submits BitSight bulk onboarding CSVs when available (legacy fallback otherwise). Includes a per-domain success/failure summary and folder info. |

## Self-test

Use the built-in self test to sanity-check your setup before connecting a
client. The command mirrors the `run` startup sequence, reports the resolved
configuration, and exercises BitSight connectivity, subscription, and tooling
checks against BitSight’s testing environment (staging). When invoked with
`--offline`, only the local configuration and logging checks run.

```bash
# Run the full diagnostics against the default BitSight testing endpoint.
uv run birre selftest

# Target the production API to exercise real subscription logic and permissions.
uv run birre selftest --production
```

Successful runs exit with `0`. Failures return `1`, and partial results with
warnings (for example, optional tooling gaps in offline mode) return `2`.
Expect occasional `403 Access Denied` responses when using BitSight’s testing
environment.

## Documentation, support & contributions

- [docs/CLI.md](docs/CLI.md) – full command reference, configuration helpers, option tables.
- [docs/ROADMAP.md](docs/ROADMAP.md) – current release summary plus upcoming milestones.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) – FastMCP layering and BitSight integration design.
- [docs/SECURITY_VERIFICATION.md](docs/SECURITY_VERIFICATION.md) – verifying signed releases (Sigstore, SBOM, PyPI).
- [docs/apis/](docs/apis) – curated BitSight endpoint overviews (v1/v2).
- [CONTRIBUTING.md](CONTRIBUTING.md) – development workflow, pytest/pyright instructions, PR expectations.
- [SECURITY.md](SECURITY.md) – reporting process and supported-release policy.

Issues and PRs are welcome; contributions are released under the [Unlicense](LICENSE).

## Disclaimer

**BiRRe** (*Bi*tsight *R*ating *Re*triever) is
**not affiliated with, endorsed by, or sponsored by BitSight Technologies, Inc.**

- This project is developed and maintained independently by the open source community
- "Bitsight" is a registered trademark of BitSight Technologies, Inc.
- This integration is provided "as-is" without any warranty
  or official support from BitSight Technologies, Inc.
- Use is intended for integration scenarios respecting BitSight’s terms.
