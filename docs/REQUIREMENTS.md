# BiRRe – Requirements Specification

## 1. Context and Scope

- **Purpose:** Build a general-purpose MCP server for the BitSight security rating platform. This server exposes BitSight data retrieval/functionality as callable MCP "tools" (endpoints) to any client able to speak the Model Context Protocol (MCP).
- **MCP Role:** This is a backend service ("MCP server"), not an LLM client, plugin, or IDE extension. It responds to standardized MCP method calls from AI clients; it does not initiate them.
- **Deployment:** Service can be run locally or remotely (cloud/server), and must support multi-tenant LLM/AI agent access, with basic authentication in advanced versions.
- **BitSight Interaction:** Business tools call BitSight v1 endpoints via FastMCP. The v2 schema is bundled and loads automatically when the `risk_manager` context is active to support complementary features (e.g., bulk company requests).

## 2. Functional Requirements, by Version

### Version 1.0 – MVP

#### 2.1. Authentication

- The server uses the BitSight API key, read from the `BITSIGHT_API_KEY` environment variable. No interactive authentication is required at runtime.

#### 2.2. Endpoints/Tools

- **Company Search**
  - **Purpose:** Find companies by name or domain using BitSight search endpoints.
  - **Inputs:**
    - `name` (string, optional) — company name to search for
    - `domain` (string, optional) — company domain to search for
  - **Output:**
    - List of companies matching the query, each with:
      - `guid` (BitSight unique identifier; referred to below simply as the company GUID)
      - `name`
      - `domain`
      - `industry`
      - Any additional fields provided by the package
    - Total `count` of matches
  - **Behavior:** Must handle both single and multiple matches gracefully, and partial or exact queries.
- **Get Company Rating**
  - **Purpose:** Retrieve security rating data while managing an ephemeral BitSight subscription when required.
  - **Inputs:**
    - `guid` (string, required) — company GUID
  - **Behavior:**
    - If already subscribed to the company, fetch and return rating.
    - If not subscribed, subscribe, fetch rating, then unsubscribe immediately.
    - If the BitSight API quota or subscription fails, return an explicit error and abort.
  - **Output:**
    - Rating number
    - Date of rating
    - Grade or other context fields returned by BitSight
    - Any errors in a structured response format

#### 2.3. General

- No data is cached or persisted—each request operates independently.
- Errors are returned as structured objects for user-facing failures; system/internal errors may raise exceptions.

### Version 2.0 – Top Vulnerability Insights

- **Enhanced Rating Payload**
  - **Purpose:** Enrich `get_company_rating` responses with the most critical BitSight findings (“top vulnerabilities”).
  - **Inputs:**
    - `guid` (string, required) — company GUID (same contract as v1).
  - **Behaviour:**
    - Query v1 findings endpoints with relaxed filters: start with severe/material severity impacting the rating, then broaden to moderate and supplement with web application security findings when fewer than three items are available.
    - Rank findings by numerical severity, categorical severity, asset importance, and recency to surface the highest-risk items first.
    - Normalise narrative fields (detection text, remediation hints, infection descriptions) for readability in MCP clients.
  - **Output:**
    - `top_findings` block in the rating payload including policy metadata (applied filters), total count, and ordered findings with key attributes (finding name, details, asset, first/last seen).
    - Error formats remain aligned with v1 (structured `{ "error": str }`).

### Version 3.0 – Context Modes for Targeted Workflows

- **Purpose:** Provide two streamlined server personas that expose only the tooling each role needs while preserving the underlying v1 FastMCP workflow.
- **Context Selection:** Server accepts a context parameter (CLI flag `--context`, env `BIRRE_CONTEXT`, or config via `[roles].context`). Invalid values fall back to the default standard context with a warning.

#### Context Definitions

- **`standard` (default)**
  - **Audience:** Everyday users and agents that only need quick, single-company ratings.
  - **Tools exposed:** `company_search`, `get_company_rating` (and any light-weight diagnostics required for support).
  - **Behaviour:** Company lookup remains AI-driven (callers rely on upstream tooling to choose the GUID); rating tool continues to auto-manage ephemeral subscriptions.

- **`risk_manager`**
  - **Audience:** Human risk managers handling subscription portfolios and data hygiene.
  - **Tools exposed:**
    - `company_search_interactive`: returns enriched search results (name with GUID, domain, website, description, employee count, folder membership, subscription snapshot) so the calling LLM can drive the clarification dialogue with the human. When no fit exists the LLM is instructed to invoke the `request_company` tool—no in-tool prompts.
    - `request_company`: Dedicated BitSight onboarding helper. Checks `/v2/company-requests` for duplicates, prefers the `createCompanyRequestBulk` workflow (so folder/type metadata can be supplied) and falls back to `createCompanyRequest` on errors—demonstrating how v2 augments v1 rather than replacing it.
    - `manage_subscriptions`: create, update, or remove subscriptions for single GUIDs or CSV-style batches (wrapping `manageSubscriptionsBulk`) with the option to define a target folder (default is the regular subscription_folder, currently API).
    - `get_company_rating`: same payload as the standard context for spot checks after subscription changes.
  - **Behaviour:**
    - Search responses highlight folder placement, subscription status, and include guidance text instructing the LLM to ask the user which company to proceed with.
    - Batch operations support dry-run payload previews, confirm target folder usage, and return granular success/error lists suitable for audit logs.
    - Failed searches emit an escalation payload instructing callers to trigger the `request_company` tool for onboarding when the entity is absent.

#### Implementation Requirements

- **Tool Filtering:** Only the tools defined above are registered under each context; hidden API tools remain accessible internally via `server.call_tool`.
- **Interactive Guidance:** `company_search_interactive` outputs enriched metadata and explicit guidance strings; the operator conversation is driven by the LLM rather than in-tool prompts.
- **Batch Safety:** `manage_subscriptions` must support dry-run mode and emit summaries suitable for audit logs (success, duplicate, failure counts).
- **Extensibility:** Future contexts (e.g., `admin`) can be layered on, but Version 3.0 ships with exactly these two personas.

### Version 4.0 – Caching Layer Enhancements

- **Daily Company Data Caching**
  - **Purpose:** Cache per-company rating data (JSON) for a full day to avoid duplicate live API calls.
  - **Inputs:**
    - Any input to rating endpoints may trigger/use caching behavior.
  - **Behavior:**
    - If rating data for the requested company GUID is cached for the current day, return cache instantly.
    - Otherwise, do a live fetch, then store the new result in the cache for that day.
  - **Output:**
    - Same as in previous endpoint, with cache/miss status indicator.
    - Errors per previous conventions.
- **PDF Artifact Caching**
  - **Purpose:** When reports (introduced in Version 5.0) are generated, store the PDF in the cache/store so subsequent requests within its freshness window avoid re-downloading from BitSight.
  - **Behaviour:**
    - Tag cached PDFs with GUID + report type + date; respect BitSight retention policies for invalidation.
    - Provide metadata so higher layers know whether the payload came from cache or a fresh API pull.

### Version 5.0 – Retrieve Company Report (PDF)

- **Download Company Report**
  - **Purpose:** Retrieve/download the official BitSight report (PDF) for a given company.
  - **Inputs:**
    - `guid` (string, required) — company GUID
    - Optional delivery parameters (see below)
  - **Delivery Options:**
    - **Direct attachment**: Return the PDF bytes/stream to the caller when their MCP transport supports file payloads.
    - **Email delivery**: Send the PDF to a specified recipient when SMTP credentials are configured (server, port, username/password or token). Tool invocation must include recipient address and optional subject/body.
    - **File share drop**: Persist the PDF to an operator-configured share. Supported targets:
      - POSIX path (e.g., NFS/SMB mount on Linux) provided via configuration.
      - SharePoint/OneDrive document library using Microsoft Graph credentials.
  - **Behaviour:**
    - Validate configuration before accepting a delivery mode; emit actionable errors when prerequisites are missing.
    - Respect caching hints from Version 4.0: reuse cached PDFs when fresh, otherwise fetch anew and refresh the cache.
    - Provide a structured response indicating delivery status (success, failure, location/email message-id).
  - **Error Handling:**
    - If report generation/downloading is unsupported or rate/feature limits are exceeded, return an explanatory error.

### Version 6.0 – Standalone, Multi-LLM, Remote Service with Authentication

- **Multi-User, Cloud/Distributed Deployment**
  - **Purpose:** Run as a network-facing service, available to multiple LLMs/clients concurrently, no local-only constraint.
  - **Authentication:** All endpoints/tools must require valid credentials or tokens for access.
  - **Security:** API keys or credentials never exposed to clients; authentication must follow secure best practices (e.g., token-based, password, or API key auth).
  - **Concurrency:** Must allow for multiple simultaneous calls/users; enforce concurrent usage/error/rate limits as needed.
  - **Service Registry/Discovery:** (Optional/future-proofing) Allow for registration/discovery of endpoints if deployed in distributed/cloud environments.
  - **Interface/Protocol:** All interaction is through standard MCP tool contracts; no direct HTTP/REST, CLI, or IDE-bound interfaces.
  - **Error Handling and Quotas:** Must handle and communicate API quota/rate limit errors per-user/client; clean, structured error reporting.

## 3. Non-Functional Requirements

- **Performance:** The service enforces BitSight API quota restrictions and avoids exceeding limits. On quota breach, errors are returned directly with no retries or waiting.
- **Security:** All sensitive configuration, especially `BITSIGHT_API_KEY`, is handled securely; never logged or included in outputs or client responses.
- **Extensibility:** Requirements ensure future expansion to new endpoints, data formats, authentication strategies, and deployment models without major redesign.
- **Maintainability:** Codebase modularity and clarity are a must; all endpoints and logic should be independently updatable and testable.
- **Compatibility:** The MCP server must work with any LLM/AI agent that supports the MCP protocol and should be designed for maximum protocol compliance.
- **Testing:** Provide an opt-in live integration suite (`pytest -m live`) that uses the in-process FastMCP client to hit BitSight endpoints when `BITSIGHT_API_KEY` is configured, while keeping offline tests fixture-driven.
- **Offline coverage:** Maintain a fast `uv run pytest -m "not live"` suite that exercises configuration layering, logging, startup checks, and risk-manager tooling without requiring network access.
- **Startup Checks:** On every launch the server validates BitSight connectivity (API key, subscriptions, quota). Allow operators to skip these checks via `--skip-startup-checks`, `BIRRE_SKIP_STARTUP_CHECKS`, or `[runtime].skip_startup_checks` when running in controlled environments.

## 4. Technical Architecture

The project uses a **FastMCP hybrid architecture** that leverages OpenAPI schema auto-generation while maintaining custom business logic control.

**Key Components**:

- **Auto-Generated API Clients** - FastMCP clients for v1 (383 endpoints) and v2 (20 endpoints) APIs from OpenAPI schemas
- **Service Layer** - Custom business logic with planned multi-version API support and complex workflows
- **MCP Business Server** - FastMCP server with custom tools preserving existing interfaces

**Implementation Details**: See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for complete design overview.

## 5. Guidance for Architect

- Requirements specify interface, contract, data flow, error handling, and now architectural structure.
- Implementation decisions within each layer—such as specific HTTP client library, async patterns, or data validation strategies—are left to architectural preference.
- The FastMCP hybrid architecture is mandatory for maintainability and extensibility goals; future iterations will continue to layer in complementary v2 tooling alongside the v1-centric core.
- If ambiguity or edge cases arise, clarify with explicit options and recommendations (don't default or assume).
