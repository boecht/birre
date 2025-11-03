# BiRRe Roadmap

**Last updated**: 2025-10-28

## Released Versions

### 4.0.0-alpha.2 — Quality & Security Infrastructure (current pre-release)

- Strict type checking with mypy catches errors before runtime
- Property-based testing with Hypothesis for edge case discovery
- Performance benchmarks establish regression tracking baselines
- Cross-platform CI validates Windows, macOS, and Linux compatibility
- Sigstore release signing for cryptographic verification
- SBOM generation for supply chain transparency
- Comprehensive branch protection and security scanning
- **Breaking:** Python 3.13+ required (modern async, type inference)

### 3.0.0 — Context-Aware Toolsets (latest stable)

- Ships two personas: `standard` (rating + search) and `risk_manager` (adds interactive search,
  subscription management, and company requests).
- CLI rebuilt around the `birre` console script (`uv run birre …`, `uvx --from … birre …`) with
  structured `config`, `selftest`, and `run` subcommands.
- OpenAPI schemas packaged under `birre.resources`, enabling installs from PyPI/uvx without cloning
  the repository.
- Offline and online startup checks produce structured diagnostics, including JSON summaries for
  automation.
- Offline (`pytest --offline`) and online (`pytest --online-only`) suites pass; selftest defaults to
  BitSight's staging environment with an opt-in production flag.

### 2.0.0 — Top Findings Insights

- `get_company_rating` enriches responses with a `top_findings` section ranked by severity, asset
  importance, and recency.
- Relaxed filtering keeps the payload useful even when high-severity findings are sparse
  (supplements with moderate + web-appsec items).
- Normalised narrative fields (detection/remediation text) improve downstream consumption by MCP
  clients.

### 1.0.0 — Initial MVP

- FastMCP-based MCP server exposes curated tools while keeping the generated API surface hidden.
- `company_search` finds companies by name/domain; `get_company_rating` handles ephemeral subscriptions automatically.
- Startup diagnostics run before the server binds, ensuring API key presence and schema availability.

## Upcoming Roadmap

### 4.0.0 — Structural Hardening & Developer Ergonomics (planned)

- Lock in strict typing, property-based tests, and benchmark suites as release criteria.
- Expand cross-platform CI coverage and surface performance telemetry from new benchmarks.
- Harden release/security workflows (Sigstore signing, SBOMs, dependency review, branch protection).
- Finish CLI/diagnostics refactors, logging safeguards, and prompt documentation for contributors.

### 5.0.0 — Caching & Company Reports (planned)

- Persist recent rating payloads and BitSight report artefacts to reduce redundant API calls.
- Respect expiry windows, surface cache hits/misses, and reuse cached assets when exporting reports.
- Provide transport options for BitSight PDF reports (direct response, email, or configured file share).

### 6.0.0 — Multi-Tenant Service (planned)

- Promote BiRRe to a shared service with authentication, concurrency controls, and optional service discovery.
- Enforce per-tenant quota handling and structured error reporting.

## Ongoing Initiatives

- **CI automation:** Integrate the offline regression suite into continuous integration, and define
  how/when to run the optional online smoke tests.
- **Observability:** Continue improving subscription lifecycle logging and diagnostics for
  production deployments.
- **Schema refresh cadence:** Periodically update the packaged BitSight schemas
  (`birre.resources/apis`) as the upstream APIs evolve.
- **Tooling ergonomics:** Expand documentation (CLI guide, architecture notes) and keep
  `config`/`selftest` flows aligned with user expectations.
