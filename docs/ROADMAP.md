# BiRRe Roadmap

_Last updated: 2025-10-28_

## Released Versions

### 3.0.0 — Context-Aware Toolsets (current)

- Ships two personas: `standard` (rating + search) and `risk_manager` (adds interactive search, subscription management, and company requests).
- CLI rebuilt around the `birre` console script (`uv run birre …`, `uvx --from … birre …`) with structured `config`, `selftest`, and `run` subcommands.
- OpenAPI schemas packaged under `birre.resources`, enabling installs from PyPI/uvx without cloning the repository.
- Offline and online startup checks produce structured diagnostics, including JSON summaries for automation.
- Offline (`pytest -m offline`) and online (`pytest -m online`) suites pass; selftest defaults to BitSight’s staging environment with an opt-in production flag.

### 2.0.0 — Top Findings Insights

- `get_company_rating` enriches responses with a `top_findings` section ranked by severity, asset importance, and recency.
- Relaxed filtering keeps the payload useful even when high-severity findings are sparse (supplements with moderate + web-appsec items).
- Normalised narrative fields (detection/remediation text) improve downstream consumption by MCP clients.

### 1.0.0 — Initial MVP

- FastMCP-based MCP server exposes curated tools while keeping the generated API surface hidden.
- `company_search` finds companies by name/domain; `get_company_rating` handles ephemeral subscriptions automatically.
- Startup diagnostics run before the server binds, ensuring API key presence and schema availability.

## Upcoming Roadmap

### 4.0.0 — Caching Layer (planned)

- Persist recent rating payloads and BitSight report artefacts to reduce redundant API calls.
- Respect expiry windows and surface cache hits/misses in telemetry.

### 5.0.0 — Company Reports Delivery (planned)

- Provide transport options for BitSight PDF reports (direct response, email, or configured file share).
- Integrate with the caching layer to avoid repeated downloads.

### 6.0.0 — Multi-Tenant Service (planned)

- Promote BiRRe to a shared service with authentication, concurrency controls, and optional service discovery.
- Enforce per-tenant quota handling and structured error reporting.

## Ongoing Initiatives

- **CI automation:** Integrate the offline regression suite into continuous integration, and define how/when to run the optional online smoke tests.
- **Observability:** Continue improving subscription lifecycle logging and diagnostics for production deployments.
- **Schema refresh cadence:** Periodically update the packaged BitSight schemas (`birre.resources/apis`) as the upstream APIs evolve.
- **Tooling ergonomics:** Expand documentation (CLI guide, architecture notes) and keep `config`/`selftest` flows aligned with user expectations.
