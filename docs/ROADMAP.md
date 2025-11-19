# BiRRe Roadmap

**Last updated**: 2025-11-19

## Released Versions

### 4.0.0 — Structural Hardening & Developer Ergonomics (released 2025-11-19)

- **CLI & workflows:** Bulk company requests via CSV (deduped, BitSight v2 upload), automatic folder placement,
  enriched interactive search output, and typed CLI inputs streamline everyday operator flows.
- **Diagnostics & selftest:** Offline replay samples, standardized `--offline/--online-only` switches, clearer
  runtime context logging, and CLI version detection keep troubleshooting reliable even without BitSight access.
- **Reliability & performance:** Simplified async/sync bridge, deep diagnostics refactors, property-based tests,
  benchmarks, and ≥90% Wave A coverage hold regressions in check while surfacing performance baselines.
- **Developer experience:** Repository-wide pyright adoption (mypy removed), stricter Protocol/type coverage,
  MegaLinter local runner, ruff auto-fix guidance, and richer risk-manager tool docs reduce contributor friction.
- **Security & supply chain:** Sigstore signing, SBOM generation, dependency review, Scorecard, StepSecurity
  guardrails, and least-privilege workflow permissions provide verifiable releases; Dependabot keeps CI current.
- **Breaking:** Require Python 3.13+ across all commands (up from 3.11+), tighten event-loop handling, and enforce
  pyright-based typing to unlock the new diagnostics/runtime stack.

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

### 5.0.0 — Cached Insights & Report Delivery (next major)

- Persist recent rating payloads and BitSight artefacts locally to reduce redundant API calls and create deterministic
  exports.
- Respect BitSight expiry semantics, emit cache-hit telemetry, and allow CLI/MCP clients to reuse cached payloads
  when exporting reports.
- Provide multiple report delivery mechanisms: structured JSON, PDF passthrough, and optional email/file-share
  integration for operators.
- Introduce governance-aware configuration (retention periods, encryption at rest) to keep cached data compliant.

### 6.0.0 — Multi-Tenant Service & Advanced Observability (future major)

- Promote BiRRe to a shared service with authentication, workload isolation, and quota enforcement across tenants.
- Add service discovery plus connection pooling so MCP clients can route to dedicated BiRRe instances when required.
- Provide first-class observability (structured metrics, health/readiness endpoints, error tracking integrations)
  tuned for SRE workflows.
- Expand schema refresh automation to keep packaged BitSight specs aligned with upstream releases.

### Future Concepts (post-6.x exploration)

- SDK + REST surface (INT-001/002) for non-MCP consumers seeking BiRRe’s business logic without the MCP
  transport.
- Distribution improvements (Docker/installer targets) for self-hosted deployments that need reproducible
  environments.
- Portfolio management and proactive alerting layers once caching + multi-tenant foundations mature.

## Ongoing Initiatives

These efforts stay active every release cycle and ensure BiRRe’s operational posture keeps pace with users’ needs.

- **CI automation:** Keep offline regression + pyright + security scans in PR validation, and continuously verify the
  release automation/smoke-test paths remain green.
- **Distribution:** Maintain the trusted-publisher PyPI pipeline and signed artifact verification flow while expanding
  installer parity (Docker, Homebrew, winget) as new platforms come online.
- **Observability:** Continue improving subscription lifecycle logging and diagnostics while broadening metrics and
  error-tracking coverage as new tooling ships.
- **Schema refresh cadence:** Periodically update the packaged BitSight schemas (`birre.resources/apis`) as upstream
  APIs evolve.
- **Tooling ergonomics:** Expand documentation (CLI guide, architecture notes) and keep `config`/`selftest` flows
  aligned with contributor expectations.
