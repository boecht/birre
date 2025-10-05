<div align="center">
<img src="birre-logo.png" alt="BiRRe Logo" width="375">
</div>

**BiRRe** (*Bi*tsight *R*ating *Re*triever) is a Model Context Protocol (MCP) server that provides access to BitSight security rating data through an existing subscription.
It utilizes [FastMCP](https://gofastmcp.com/) for API integration with BitSight and can be run easily without installation in a temporary, isolated Python environment with uv.

## Installation

### Quick start

- Set your BitSight API key, then start BiRRe:

```bash
export BITSIGHT_API_KEY="your-bitsight-api-key"
uvx --from git+https://github.com/boecht/birre server.py
```

- Point your LLM of choice to the MCP server and ask it for the BitSight rating of any company.

### Configuration

Configuration sources (lowest → highest): `config.toml` → `config.local.toml` → environment → CLI.
See the header in `config.toml` for available fields and details. For CLI options, run with `--help`.

### Run directly from GitHub with uvx

```bash
uvx --from git+https://github.com/boecht/birre server.py
```

### Or run locally

```bash
git clone https://github.com/boecht/birre
uv run server.py
```

That's it! The script will automatically install all dependencies using uv.

Alternatively run with `fastmcp` for more options, like **HTTP transport**.

## Disclaimer

**BiRRe** (*Bi*tsight *R*ating *Re*triever) is **not affiliated with, endorsed by, or sponsored by BitSight Technologies, Inc.** This is an unofficial, community-developed MCP server that provides integration with Bitsight's publicly available services.

- This project is developed and maintained independently by the open source community
- "Bitsight" is a registered trademark of BitSight Technologies, Inc.
- This integration is provided "as-is" without any warranty or official support from BitSight Technologies, Inc.

This project enables third-party access to Bitsight services through their public APIs and is intended for educational and integration purposes only.

## Features

### Available Tools

**BiRRe** currently exposes two business tools:

- **`get_company_rating`** - Get security ratings with automatic subscription management
- **`company_search`** - Search for companies by name or domain (required for get_company_rating)

## BitSight API Documentation

**API Version**: This implementation is based on BitSight APIs as of July 24th, 2025. For the latest API changes and updates, refer to the [BitSight API Change Log](https://help.bitsighttech.com/hc/en-us/articles/231655907-API-Change-Log).

**Interactive API Documentation** (requires BitSight account login):

- **v1 API**: <https://service.bitsighttech.com/customer-api/v1/ui> (383 endpoints)
- **v2 API**: <https://service.bitsighttech.com/customer-api/v2/ui> (20 enhanced features)

**Schema Updates**: To update API schemas when forking or contributing:

1. Log into BitSight web interface
2. Download schemas from:
   - **v1**: <https://service.bitsighttech.com/customer-api/ratings/v1/schema>
   - **v2**: <https://service.bitsighttech.com/customer-api/ratings/v2/schema>  
3. Save as `apis/bitsight.v1.schema.json` and `apis/bitsight.v2.schema.json`

## Version History and Outlook

### Version 1.0: MVP

- **Company Search**: Search for companies by name or domain via BitSight v1 `companySearch`
- **Company Rating**: Retrieve core rating details with automatic subscription management
- **Ephemeral Subscriptions**: Subscribe/unsubscribe on demand to avoid license leakage
- **Structured Error Handling**: Clear responses for quota/subscription failures
- **uv/uvx Compatible**: Run easily with uv using PEP 723 inline script metadata

### Version 2.0: Top Vulnerability Insights (Current)

- **Top Findings Summary**: Attach the most impactful vulnerabilities to the rating payload, using relaxed severity filters (severe/material first, then moderate with web-appsec padding when needed)
- **Enhanced Sorting**: Prioritise findings by severity, asset importance, and recency to keep the worst issues on top
- **Narrative Improvements**: Normalise detection/remediation text for quick consumption by MCP clients
- **Configuration Hooks**: Continue to rely on v1 findings endpoints while keeping v2 tooling optional via `BIRRE_ENABLE_V2`

### Version 3.0: Context Modes (Planned)

- Two personas: `standard` (quick ratings) and `risk_manager` (subscription operations)
- Context-driven tool filtering via CLI (`--context`) or env (`BIRRE_CONTEXT`)
- Interactive company search and batch subscription management for risk managers

### Version 4.0: Caching Layer (Not Implemented)

- Daily caching of ratings and reusable storage for PDF artifacts
- Reduce duplicate API calls and avoid re-downloading recent reports

### Version 5.0: Company Reports (Not Implemented)

- Download official PDF reports
- Deliver via direct attachment, email, or configured file share (POSIX path or SharePoint)

### Version 6.0: Multi-Tenant Service (Not Implemented)

- Remote deployment support
- Authentication and authorization
- Concurrent user support
