# Bitsight API v2 endpoints

## Alerts

GET /alerts
GET /alerts/customer
GET /alerts/latest
GET /alerts/{guid}/affected-companies

## Users

GET /users
POST /users
GET /users/current
PATCH /users/current
POST /users/query
DELETE /users/{user_guid}
GET /users/{user_guid}
PATCH /users/{user_guid}
POST /users/{user_guid}/require-mfa
POST /users/{user_guid}/resend-activation-email
POST /users/{user_guid}/reset-mfa
POST /users/{user_guid}/reset-pending-mfa

## Financial Quantification

GET /companies/{company_guid}/financial-quantifications
POST /companies/{company_guid}/financial-quantifications
GET /companies/{company_guid}/financial-quantifications/latest
GET /companies/{company_guid}/financial-quantifications/{fq_guid}
PUT /companies/{company_guid}/financial-quantifications/{fq_guid}

## Company Requests

GET /company-requests
POST /company-requests
POST /company-requests/bulk
DELETE /company-requests/{guid}
GET /company-requests/{guid}
PATCH /company-requests/{guid}

## Portfolio

GET /portfolio
POST /portfolio
GET /portfolio/summaries
