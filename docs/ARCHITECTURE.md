# BiRRe Architecture

## Overview

BiRRe is a Model Context Protocol (MCP) server that provides simplified access to BitSight security
rating APIs. The server uses FastMCP's tool filtering capabilities to expose only essential
business logic tools while maintaining access to comprehensive API functionality.

## Design Requirements

### API Complexity Challenge

BitSight provides extensive APIs across two versions:

- **v1 API**: 383 endpoints covering core functionality
- **v2 API**: 20 endpoints with enhanced features (does not replace v1)
- **Total**: 478+ available endpoints

Direct exposure of all endpoints to MCP clients would create interface complexity and poor user
experience. The solution requires:

- Complete API functionality access for business logic
- Simplified interface with focused tools for end users
- Efficient API orchestration for complex workflows

### Solution Approach

The architecture uses FastMCP's tool filtering mechanism to separate API tools from business tools:

1. **Auto-generation**: Generate all API tools from OpenAPI specifications

2. **Tool filtering**: Hide API tools from client visibility while maintaining internal access
3. **Business abstraction**: Expose curated business logic tools that orchestrate API calls

## Technical Architecture

### Component Structure

```text
MCP Client
    ↓ (context-specific business tools)
BiRRe FastMCP Server
├── Standard context tools
│   ├── company_search
│   └── get_company_rating
└── Risk-manager context tools (superset)
    ├── company_search
    ├── get_company_rating
    ├── company_search_interactive
    ├── manage_subscriptions
    └── request_company (uses v2 bulk onboarding when available)
        ↓ (internal access via stored call_v1_tool / call_v2_tool)
Selected BitSight API Tools kept enabled
├── v1: companySearch, manageSubscriptionsBulk, getCompany, getCompaniesFindings,
│      getFolders, getCompanySubscriptions
└── v2: getCompanyRequests, createCompanyRequestBulk, createCompanyRequest
        ↓ (HTTP calls)
BitSight REST APIs (v1: 383 endpoints, v2: 20 complementary endpoints)
```

### FastMCP Tool Filtering Implementation

The server uses FastMCP's tool disabling feature as documented at <https://gofastmcp.com/servers/tools#disable-tools>.

**Core Pattern**:

```python
# Generate API tools from OpenAPI specification
server = FastMCP.from_openapi(openapi_spec=v1_spec, client=v1_client, name="BiRRe")

# Disable all auto-generated API tools for client visibility
api_tools = await server.get_tools()
for tool_name, tool in api_tools.items():
    tool.disable()  # Hidden from list_tools(), accessible via call_tool()

# Add business logic tools
@server.tool()
async def company_search(ctx, name=None, domain=None):
    result = await server.call_tool("companies_search_get", {"q": name})
    return process_business_result(result)
```

**Technical Details**:

- `tool.disable()` removes tools from MCP `list_tools` responses
- Disabled tools remain callable through `server.call_tool()` for internal use
- Business tools can orchestrate multiple API calls transparently
- Maintains full type safety and validation from OpenAPI schemas

Reference: FastMCP tool management documentation at <https://gofastmcp.com/servers/tools>

### Server Factory Pattern

BiRRe uses a factory function to create and configure the FastMCP server instance.

**Factory Function** (`application/server.py`):

```python
def create_birre_server(runtime_settings: RuntimeSettings) -> FastMCP:
    """Create and configure a BiRRe MCP server instance.

    This factory:

    1. Creates FastMCP server from OpenAPI specs (v1 + v2)

    2. Disables auto-generated API tools (hides from client)
    3. Registers context-specific business tools
    4. Returns configured server ready to serve
    """
    server = FastMCP.from_openapi(...)
    # ... configuration ...
    return server
```

**Key Design Decisions**:

- **Server in application/**: Business logic layer, orchestrates domain tools
- **Context Switching**: Runtime selection of tool sets (standard vs risk_manager)
- **Lazy Loading**: API tools generated on demand, not at import time
- **Stateless**: Server configuration is immutable after creation

### MCP Context vs Mock Context

BiRRe uses two different context objects depending on execution mode:

**Production: FastMCP Context** (MCP protocol):

- Provided by FastMCP framework during MCP protocol communication
- Includes logging methods: `ctx.info()`, `ctx.warning()`, `ctx.error()`
- Has metadata about the client request
- Used by business tools in `domain/` layer

**Testing: _MockSelfTestContext** (diagnostics):

- Defined in `domain/selftest_models.py`
- Simulates MCP Context interface for selftest validation
- Enables testing tool logic without MCP client connection
- Used by diagnostic functions in `application/diagnostics.py`

**Why the separation?**

- Allows testing business logic without running MCP server
- Diagnostic validation works offline (no client needed)
- Mock context captures logging for test assertions
- Clean boundary between production and test code

### Tool Discovery and Registration

BiRRe uses a multi-stage tool registration process:

**Stage 1: Auto-generation** (startup)

1. Load OpenAPI schemas from `resources/apis/`

2. FastMCP generates 478+ API tools automatically
3. All tools get type validation from schemas

**Stage 2: Filtering** (startup)

1. Disable all auto-generated tools via `tool.disable()`

2. Tools remain callable internally via `server.call_tool()`
3. Hidden from MCP `list_tools` protocol response

**Stage 3: Business Tool Registration** (startup)

1. Register domain tools based on selected context

2. Standard context: 2 tools (search, rating)
3. Risk-manager context: 5 tools (adds interactive search, subscriptions, requests)
4. Each tool orchestrates multiple internal API calls

**Stage 4: Runtime** (per request)

1. Client calls business tool via MCP protocol

2. Business tool calls internal API tools via `server.call_tool()`
3. Results aggregated and returned to client

### API Resources

**BitSight API Documentation** (no access, requires manual authentication):

- **v1 API**: <https://service.bitsighttech.com/customer-api/v1/ui>
- **v2 API**: <https://service.bitsighttech.com/customer-api/v2/ui>

**Local Schema Files**:

- `src/birre/resources/apis/bitsight.v1.schema.json` (+ `src/birre/resources/apis/v1/`) – packaged OpenAPI v1 schema
- `src/birre/resources/apis/bitsight.v2.schema.json` (+ `src/birre/resources/apis/v2/`) – packaged OpenAPI v2 schema
- `docs/apis/bitsight.v1.overview.md` – v1 API endpoint overview (human-readable)
- `docs/apis/bitsight.v2.overview.md` – v2 API endpoint overview (human-readable)

### Business Logic Layer

**Exposed Tools**:

- Standard context: `company_search`, `get_company_rating`
- Risk-manager context: standard tools plus `company_search_interactive`, `manage_subscriptions`, `request_company`

**Internal Capabilities**:

- Ephemeral subscription lifecycle management (create/cleanup)
- Severity-aware top findings ranking (BitSight findings API)
- Error handling and response normalization
- Opportunistic use of BitSight v2 tooling for workflows that require it (e.g., bulk company requests)

### API Version Strategy

- **v1 API (Primary)**: All shipping business tools rely exclusively on v1 endpoints for search,
  ratings, findings, folder lookups, and subscription management. Non-essential v1 tools are
  disabled at startup to minimize surface area.
- **v2 API (Complementary)**: The v2 schema ships with the package and is invoked only when it
  provides capabilities unavailable in v1 (e.g., bulk onboarding), so runtime behaviour remains
  v1-centric unless optional features require it.
- **Future Work**: Targeted v2 integrations (e.g., richer findings or financial metrics) will
  continue to be layered on per feature; v2 augments v1 and there is no plan for a wholesale
  replacement.

## Implementation Details

### Authentication

- Uses the `BITSIGHT_API_KEY` environment variable for BitSight API access
- FastMCP handles HTTP client configuration and authentication headers
- httpx.AsyncClient provides connection pooling and timeout management

### Startup Checks

BiRRe performs validation checks before starting the MCP server to ensure proper configuration and API connectivity.

**Architecture**:

- **Core Logic** (`application/startup.py`): Implements `run_offline_startup_checks()` and
  `run_online_startup_checks()` with no external dependencies
- **Diagnostic Wrappers** (`application/diagnostics.py`): Provides `run_offline_checks()` and
  `run_online_checks()` convenience functions that add diagnostic logging and orchestration

**Checks Performed**:

- **Offline**: API key presence, subscription folder/type configuration, OpenAPI schema validation
- **Online**: API key validity, subscription folder access, remaining quota verification

**Configuration**:

- Executed automatically before the MCP server starts serving requests
- Can be skipped via `--skip-startup-checks`, `BIRRE_SKIP_STARTUP_CHECKS`,
  or `[runtime].skip_startup_checks` when operators intentionally defer validation
- Emits structured log events (`startup_checks.run`) and aborts startup on errors

**Design Rationale**: The separation between startup.py (pure logic) and diagnostics.py (diagnostic
tooling) maintains clean layer boundaries while providing convenient diagnostic entry points for
CLI commands.

### Dependencies and Layer Architecture

BiRRe follows a strict 3-layer architecture with clear dependency rules:

**Layer Structure**:

```text
cli/              (UI Layer)
  ↓ depends on
application/      (Business Logic Layer)
  ↓ depends on
domain/           (Core Domain Layer)
  ↓ depends on
infrastructure/   (Cross-cutting Concerns)
```

**Key Dependencies**:

- **FastMCP** (`fastmcp>=2.13.0`): MCP server framework with OpenAPI integration
- **Typer** (`typer>=0.12.3`): CLI framework with Rich integration
- **Rich** (`rich>=13.7.0`): Terminal formatting and tables
- **Dynaconf** (`dynaconf>=3.2.3`): Configuration management with layering
- **Pydantic** (`pydantic>=2.6.0`): Data validation and models
- **httpx** (`httpx>=0.27.0`): Async HTTP client for BitSight APIs
- **structlog** (`structlog>=24.1.0`): Structured logging

**Dependency Rules**:

1. **No Circular Dependencies**: All imports flow downward through layers

2. **Infrastructure Independence**: domain/ only depends on infrastructure/ for errors and logging
3. **CLI Isolation**: CLI code cannot be imported by application/ or domain/
4. **External Dependencies**: Concentrated in infrastructure/ and application/ layers

**Import Patterns**:

- ✅ `cli/` → `application/` → `domain/` → `infrastructure/`
- ✅ All layers → `infrastructure/` (errors, logging)
- ❌ `domain/` → `application/`
- ❌ `application/` → `cli/`

See pyproject.toml for complete dependency list and version constraints.

### Error Handling

- Structured error responses for all failure scenarios
- Transparent operation status reporting (subscription creation, API versions used)
- BitSight-specific error code handling and user-friendly messages

### Performance Considerations

- Direct tool calls with no proxy overhead
- Connection pooling through httpx.AsyncClient
- Minimal abstraction layers between business logic and API calls
- Type validation through OpenAPI schema integration

### CLI Architecture

BiRRe provides a Typer-based CLI with modular command organization:

**Structure**:

```text
src/birre/cli/
├── app.py              # Main CLI app with command registration
├── main.py             # Console entry point
├── helpers.py          # Shared CLI utilities and config resolution (382 lines)
├── options.py          # Reusable Typer option factories (360 lines)
├── models.py           # CLI dataclasses (CliInvocation, etc.)
├── formatting.py       # Rich console formatting utilities (200 lines)
├── validation.py       # Common validators and error handling (188 lines)
└── commands/           # Command group implementations
    ├── run.py          # MCP server startup command
    ├── config.py       # Config management (init, show, validate)
    ├── logs.py         # Log maintenance (clear, rotate, show, path)
    └── selftest/       # Diagnostics command group
        ├── command.py  # Selftest command registration
        ├── runner.py   # Test execution logic
        └── rendering.py # Rich console output formatting
```

**Key Patterns**:

- **Command Registration**: Each command module exports a `register(app, ...)` function that
  registers commands with the main Typer app
- **Option Factories**: Reusable option definitions in `options.py` ensure consistent flag names
  and environment variable mappings
- **Configuration Layering**: `helpers.py` provides utilities for merging config.toml →
  config.local.toml → environment → CLI flags
- **Rich Console**: All CLI output uses Rich for formatted tables, styled text, and progress
  indicators
- **Shared Formatting**: Common utilities (table creation, value masking,
  config formatting) in `formatting.py` eliminate duplication
- **Validation Utilities**: `validation.py` provides reusable validators (file existence, TOML parsing,
  parameter validation) with consistent error handling

**Module Sizing Philosophy**:

BiRRe CLI modules follow a pragmatic sizing approach:

- **helpers.py (382 lines)**: 16 functions organized into 6 clear categories (sync bridge, invocation building,
  settings conversion, runtime utilities, diagnostics)
- **options.py (360 lines)**: 20+ Typer option declarations with normalization helpers, organized by concern (auth,
  runtime, logging)
- **validation.py (188 lines)**: 6 reusable validators for common CLI validation patterns

These modules remain intentionally unified rather than split because:

1. **Cohesion**: Each module has a single, clear responsibility

2. **Discoverability**: Related functions are co-located for easy navigation
3. **Simplicity**: Splitting would increase import complexity without improving maintainability
4. **Threshold**: All modules are under the 400-line practical limit for CLI utilities
5. **MVP Principle**: Avoid premature abstraction when current organization serves its purpose

See [docs/CLI.md](CLI.md) for complete command reference.

## Benefits

**Interface Simplicity**: Context-specific business toolsets (2 for standard,
  5 for risk-manager) instead of 478 API endpoints
**Complete Coverage**: Full API functionality available through auto-generation
**Maintainability**: Minimal custom HTTP client code, handled by FastMCP
**Framework Compliance**: Uses standard FastMCP patterns as documented
**Performance**: Direct tool invocation without delegation overhead
**Extensibility**: New business tools easily added using existing hidden API tools

## References

- **FastMCP Documentation**: <https://gofastmcp.com/>
- **FastMCP Tools**: <https://gofastmcp.com/servers/tools>
- **FastMCP OpenAPI Integration**: <https://gofastmcp.com/servers/server#from-openapi>
- **BitSight API v1 Documentation**: <https://service.bitsighttech.com/customer-api/v1/ui>
- **BitSight API v2 Documentation**: <https://service.bitsighttech.com/customer-api/v2/ui>
- **BitSight API v1 Production**: `https://api.bitsighttech.com/v1`
- **BitSight API v2 Production**: `https://api.bitsighttech.com/v2`

## Testing Strategy

The project maintains both offline and online suites:

- **Offline (`uv run pytest --offline`)** – Runs quickly without network access. It covers
  configuration layering, logging formatters, startup checks, and the risk-manager tools
  (interactive search, subscription management, company requests) using lightweight stubs.
- **Online (`uv run pytest --online-only`)** – Executes the FastMCP client end-to-end against
  BitSight, verifying the company search/rating workflow and the online startup checks. Requires
  a valid `BITSIGHT_API_KEY` and installs `fastmcp` inside the uv-managed virtual environment.

Future work should extend the offline suite to the standard company rating/search flows and ensure
any new tooling lands with matching tests.
