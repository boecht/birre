# Bitsight API v2

## API information

- 2.0.0
- Servers
  - <https://api.bitsighttech.com/v2> - production server
  - <https://service.bitsighttech.com/customer-api/v2> - testing server

## Other files

- `bitsight.v2.endpoints.md` list of endpoints
- `../../src/birre/resources/apis/bitsight.v2.schema.json` full API definition. DO NOT READ! For details look up API excerpt files in sub folders (see next chapter)

## Folder Structure for API excerpt files

### Core Files (v2/)

- `openapi.json` - OpenAPI specification
- `info.json` - API information
- `servers.json` - Server definitions
- `tags.json` - Endpoint tags
- `security.json` - Security definitions
- `x-common-definitions.json` - Common definitions

### Components (v2/components/)

- `schemas.json` - Data schemas
- `parameters.json` - Reusable parameters
- `responses.json` - Response definitions
- `securitySchemes.json` - Security schemes

### Endpoints by Category (v2/components/paths/)

- `alerts.json` - Alert-related endpoints
- `company_requests.json` - Company request endpoints
- `financial_quantification.json` - Financial quantification endpoints
- `portfolio.json` - Portfolio management endpoints
- `users.json` - User management endpoints
