# BiRRe Architecture

## Overview

BiRRe is a Model Context Protocol (MCP) server that provides simplified access to BitSight security rating APIs. The server uses FastMCP's tool filtering capabilities to expose only essential business logic tools while maintaining access to comprehensive API functionality.

## Design Requirements

### API Complexity Challenge

BitSight provides extensive APIs across two versions:

- **v1 API**: 383 endpoints covering core functionality
- **v2 API**: 20 endpoints with enhanced features (does not replace v1)
- **Total**: 478+ available endpoints

Direct exposure of all endpoints to MCP clients would create interface complexity and poor user experience. The solution requires:

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

### API Resources

**BitSight API Documentation** (no access, requires manual authentication):

- **v1 API**: <https://service.bitsighttech.com/customer-api/v1/ui>
- **v2 API**: <https://service.bitsighttech.com/customer-api/v2/ui>

**Local Schema Files**:

- `apis/bitsight.v1.overview.md` - v1 API endpoint overview (human-readable)
- `apis/bitsight.v2.overview.md` - v2 API endpoint overview (human-readable)

### Business Logic Layer

**Exposed Tools**:

- Standard context: `company_search`, `get_company_rating`
- Risk-manager context: standard tools plus `company_search_interactive`, `manage_subscriptions`, `request_company`

**Internal Capabilities**:

- Ephemeral subscription lifecycle management (create/cleanup)
- Severity-aware top findings ranking (BitSight findings API)
- Error handling and response normalization
- Optional v2 preloading via `BIRRE_ENABLE_V2` for complementary endpoints (used when workflows require functionality v1 does not offer, such as bulk company requests)

### API Version Strategy

- **v1 API (Primary)**: All shipping business tools rely exclusively on v1 endpoints for search, ratings, findings, folder lookups, and subscription management. Non-essential v1 tools are disabled at startup to minimise surface area.
- **v2 API (Complementary)**: The v2 schema can be preloaded by setting `BIRRE_ENABLE_V2=true`. Business tooling invokes v2 only when it provides capabilities unavailable in v1 (e.g., bulk onboarding), so runtime behaviour remains v1-centric unless optional features require it.
- **Future Work**: Targeted v2 integrations (e.g., richer findings or financial metrics) will continue to be layered on per feature; v2 augments v1 and there is no plan for a wholesale replacement.

## Implementation Details

### Authentication

- Uses the `BITSIGHT_API_KEY` environment variable for BitSight API access
- FastMCP handles HTTP client configuration and authentication headers
- httpx.AsyncClient provides connection pooling and timeout management

### Startup Checks

- Executed automatically before the MCP server starts serving requests
- Validates BitSight API connectivity (API key access, subscription folder presence, remaining quota)
- Can be skipped via `--skip-startup-checks`, `BIRRE_SKIP_STARTUP_CHECKS`, or `[runtime].skip_startup_checks` when operators intentionally defer validation
- Emits structured log events (`startup_checks.run`) and aborts startup on errors

### Error Handling

- Structured error responses for all failure scenarios
- Transparent operation status reporting (subscription creation, API versions used)
- BitSight-specific error code handling and user-friendly messages

### Performance Considerations

- Direct tool calls with no proxy overhead
- Connection pooling through httpx.AsyncClient
- Minimal abstraction layers between business logic and API calls
- Type validation through OpenAPI schema integration

## Benefits

**Interface Simplicity**: Context-specific business toolsets (2 for standard, 5 for risk-manager) instead of 478 API endpoints
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

- **Offline (`uv run pytest -m offline`)** – Runs quickly without network access. It covers configuration layering, logging formatters, startup checks, and the risk-manager tools (interactive search, subscription management, company requests) using lightweight stubs.
- **Online (`uv run pytest -m online`)** – Executes the FastMCP client end-to-end against BitSight, verifying the company search/rating workflow and the online startup checks. Requires a valid `BITSIGHT_API_KEY` and installs `fastmcp` inside the uv-managed virtual environment.

Future work should extend the offline suite to the standard company rating/search flows and ensure any new tooling lands with matching tests.
