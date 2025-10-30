# Bitsight API v1 endpoints

## Access Groups

GET /access-groups
POST /access-groups
PUT /access-groups/companies
POST /access-groups/query
DELETE /access-groups/{guid}
GET /access-groups/{guid}
PATCH /access-groups/{guid}
GET /access-groups/{guid}/companies/guids
PUT /access-groups/{guid}/companies/guids

## Alerts

GET /alert-preferences
GET /alert-preferences/by-target
PATCH /alert-preferences/by-target
GET /alert-preferences/{guid}
GET /alert-sets
POST /alert-sets
PUT /alert-sets/email-preferences
DELETE /alert-sets/{guid}
GET /alert-sets/{guid}
PATCH /alert-sets/{guid}
DELETE /alert-sets/{guid}/users/{user_guid}
GET /alerts
GET /alerts/informational/{guid}
GET /alerts/latest
GET /alerts/nist/{guid}
GET /alerts/percent/{guid}
GET /alerts/portfolio/{guid}
GET /alerts/public-disclosure/{guid}
GET /alerts/risk-categories/{guid}
GET /alerts/summaries
GET /alerts/threshold/{guid}
GET /alerts/vulnerability/{guid}
GET /alerts/{guid}

## Assessments

GET /assessment/assessments/templates/{template_guid}/companies/{company_guid}
GET /assessment/customers/{customer_guid}/assessments/templates
GET /assessments/templates
PATCH /assessments/templates/{assessment_template_guid}
POST /companies/{company_guid}/assessments
GET /iq/assessments/frameworks

## AssetConfig

DELETE /assets/config
GET /assets/config
PUT /assets/config

## Assets

GET /companies/{guid}/assets
DELETE /companies/{guid}/assets/overrides
GET /companies/{guid}/assets/overrides
POST /companies/{guid}/assets/overrides
GET /companies/{guid}/assets/summaries
PATCH /companies/{guid}/assets/tags
GET /portfolio/monitored-assets
POST /portfolio/monitored-assets/bulk
POST /portfolio/monitored-assets/bulk/validate
GET /portfolio/monitored-assets/quota
GET /portfolio/monitored-assets/summaries
GET /portfolio/monitored-assets/threats

## Async Job

GET /jobs/{guid}

## Benchmarking Configuration

GET /benchmarking-configs
POST /benchmarking-configs
DELETE /benchmarking-configs/{guid}
GET /benchmarking-configs/{guid}
PUT /benchmarking-configs/{guid}

## Breaches

GET /companies/{company_guid}/company-tree/providers/breaches
GET /companies/{company_guid}/company-tree/providers/breaches/reduced
GET /companies/{company_guid}/company-tree/providers/breaches/{breach_guid}
GET /companies/{company_guid}/providers/breaches
GET /companies/{company_guid}/providers/breaches/{breach_guid}
GET /folders/{folder_guid}/providers/breaches
GET /folders/{folder_guid}/providers/breaches/reduced
GET /folders/{folder_guid}/providers/breaches/{breach_guid}
GET /portfolio/providers/breaches
GET /portfolio/providers/breaches/reduced
GET /portfolio/providers/breaches/{breach_guid}
GET /tiers/{tier_guid}/providers/breaches
GET /tiers/{tier_guid}/providers/breaches/reduced
GET /tiers/{tier_guid}/providers/breaches/{breach_guid}

## Client Access Links

GET /client-access-links
POST /client-access-links
DELETE /client-access-links/{guid}
PATCH /client-access-links/{guid}

## Cloud Service Providers

## Collaboration Hub

GET /collaboration/summary

## Companies

POST /companies/collaboration-contacts/query
POST /companies/infrastructure/bulk
POST /companies/infrastructure/expiration
GET /companies/infrastructure/requests
GET /companies/infrastructure/requests/summaries
GET /companies/probable-infrastructure/requests
POST /companies/probable-infrastructure/requests
GET /companies/probable-infrastructure/requests/{guid}/response
POST /companies/probable-infrastructure/requests/{guid}/response/bulk
GET /companies/search
POST /companies/search
GET /companies/trending
POST /companies/validate-recipient-emails
GET /companies/{company_guid}/company-tree/products/{product_guid}/companies
GET /companies/{company_guid}/company-tree/providers/{provider_guid}/companies
GET /companies/{company_guid}/diligence/historical-statistics
GET /companies/{company_guid}/domains/{domain_name}/products
GET /companies/{company_guid}/domains/{domain_name}/providers
GET /companies/{company_guid}/findings/statistics
GET /companies/{company_guid}/findings/summaries/
GET /companies/{company_guid}/findings/summary/
GET /companies/{company_guid}/findings/{risk_type}/eol-grade-changes
GET /companies/{company_guid}/findings/{rolledup_observation_id}/history-timeline
GET /companies/{company_guid}/fourth-parties
POST /companies/{company_guid}/fourth-parties
DELETE /companies/{company_guid}/fourth-parties/{fourth_party_guid}
GET /companies/{company_guid}/fourth-parties/{fourth_party_guid}
GET /companies/{company_guid}/products
POST /companies/{company_guid}/products
GET /companies/{company_guid}/products/{product_guid}/domains
GET /companies/{company_guid}/providers
GET /companies/{company_guid}/providers/breaches
GET /companies/{company_guid}/providers/breaches/{breach_guid}
GET /companies/{company_guid}/providers/{provider_guid}/domains
POST /companies/{company_guid}/self-published-requests
GET /companies/{guid}
PATCH /companies/{guid}
GET /companies/{guid}/assets
DELETE /companies/{guid}/assets/overrides
GET /companies/{guid}/assets/overrides
POST /companies/{guid}/assets/overrides
GET /companies/{guid}/assets/statistics
GET /companies/{guid}/assets/summaries
PATCH /companies/{guid}/assets/tags
GET /companies/{guid}/bundle
GET /companies/{guid}/countries
GET /companies/{guid}/data-privacy-report
GET /companies/{guid}/data-privacy-report/download
GET /companies/{guid}/diligence/statistics
GET /companies/{guid}/findings
POST /companies/{guid}/findings
GET /companies/{guid}/findings/core-affects-ratings-download
GET /companies/{guid}/findings/core-affects-ratings-download/created-date
GET /companies/{guid}/findings/filters
GET /companies/{guid}/findings/pcap
GET /companies/{guid}/findings/pcap/{pcap_id}
GET /companies/{guid}/findings/refresh-requests
POST /companies/{guid}/findings/refresh-requests/notified
GET /companies/{guid}/findings/refresh-requests/summaries
GET /companies/{guid}/findings/refresh/summaries
PATCH /companies/{guid}/findings/{rolledup_observation_id}
GET /companies/{guid}/findings/{rolledup_observation_id}/comments
GET /companies/{guid}/graph_data
GET /companies/{guid}/industries/statistics
GET /companies/{guid}/infections
POST /companies/{guid}/infections/query
GET /companies/{guid}/infrastructure/changes
GET /companies/{guid}/infrastructure/reasons
GET /companies/{guid}/logo-image
GET /companies/{guid}/mobile-forensics
GET /companies/{guid}/observations
GET /companies/{guid}/observations/statistics
GET /companies/{guid}/open-ports
GET /companies/{guid}/pdf
GET /companies/{guid}/preview
GET /companies/{guid}/rating-release-previews
GET /companies/{guid}/remediation-plans
GET /companies/{guid}/reports/overview
GET /companies/{guid}/risk-vectors/summaries
GET /companies/{guid}/software-counts/desktop-software
GET /companies/{guid}/software-counts/mobile-software
GET /companies/{guid}/software-counts/server-software
GET /companies/{guid}/subscribers/statistics
GET /companies/{guid}/subscribers/summaries
GET /companies/{guid}/subsidiaries
POST /companies/{guid}/summary-risk-vector-report
GET /companies/{guid}/tags
GET /companies/{guid}/threats/attestations
POST /companies/{guid}/threats/attestations/bulk
GET /companies/{guid}/user-behavior/statistics
GET /contacts
POST /contacts
PUT /contacts/bulk
GET /contacts/latest
POST /contacts/latest/query
POST /contacts/query
DELETE /contacts/{contact_guid}
GET /contacts/{contact_guid}
PATCH /contacts/{contact_guid}
GET /folders/{folder_guid}/products/{product_guid}/companies
GET /folders/{folder_guid}/providers/{provider_guid}/companies
GET /portfolio/products/{product_guid}/companies
GET /portfolio/providers/{provider_guid}/companies
GET /tiers/{tier_guid}/products/{product_guid}/companies
GET /tiers/{tier_guid}/providers/{provider_guid}/companies

## Company

GET /companies/{guid}/location-information
GET /companies/{guid}/reports/company-preview
POST /companies/{guid}/reports/company-preview
GET /companies/{guid}/reports/spi
GET /companies/{guid}/reports/spi/{report_name}/evaluations
POST /companies/{guid}/reports/spi/{report_name}/evaluations
DELETE /companies/{guid}/reports/spi/{report_name}/evaluations/{evaluation_guid}
PATCH /companies/{guid}/reports/spi/{report_name}/evaluations/{evaluation_guid}
GET /companies/{guid}/reports/spi/{spi_report_version}/
GET /companies/{guid}/tier/recommendation

## Company Assessment

GET /assessment/assessments/templates/{template_guid}/companies/{company_guid}

## Company Recommendations

GET /company-recommendations
GET /company-recommendations/my-company

## Company Relationships

GET /company-relationships

## Company Relationships Bulk Operation

PATCH /company-relationships/bulk

## CompanyTree

GET /companies/{company_guid}/company-tree/product-types
GET /companies/{company_guid}/company-tree/products
GET /companies/{company_guid}/company-tree/products/{product_guid}/companies
GET /companies/{company_guid}/company-tree/providers
GET /companies/{company_guid}/company-tree/providers/breaches
GET /companies/{company_guid}/company-tree/providers/breaches/reduced
GET /companies/{company_guid}/company-tree/providers/breaches/{breach_guid}
GET /companies/{company_guid}/company-tree/providers/{provider_guid}/companies
GET /companies/{company_guid}/company-tree/providers/{provider_guid}/products
GET /companies/{guid}/company-tree
GET /companies/{guid}/company-tree/countries
GET /companies/{guid}/company-tree/guids

## Compliance Claim

DELETE /companies/{guid}/compliance-claim
GET /companies/{guid}/compliance-claim
POST /companies/{guid}/compliance-claim
POST /companies/{guid}/compliance-claim/validate-link

## Contacts

POST /companies/collaboration-contacts/query
POST /companies/validate-recipient-emails
GET /contacts
POST /contacts
PUT /contacts/bulk
GET /contacts/latest
POST /contacts/latest/query
POST /contacts/query
DELETE /contacts/{contact_guid}
GET /contacts/{contact_guid}
PATCH /contacts/{contact_guid}

## Current Ratings

GET /current-ratings
POST /current-ratings

## Customers

POST /api-tokens/retrieve
GET /contacts
POST /contacts
PUT /contacts/bulk
GET /contacts/latest
POST /contacts/latest/query
POST /contacts/query
DELETE /contacts/{contact_guid}
GET /contacts/{contact_guid}
PATCH /contacts/{contact_guid}
POST /customers
GET /customers/current
PATCH /customers/current
GET /customers/current/features
POST /customers/current/features
GET /customers/{customer-guid}/api-tokens
POST /customers/{customer-guid}/api-tokens
DELETE /customers/{customer-guid}/api-tokens/{api-guid}
DELETE /customers/{guid}
GET /customers/{guid}
PATCH /customers/{guid}
POST /customers/{guid}/companies
Add a List of Companies to the Customer
GET /customers/{guid}/purchases
Get a List of all Purchases of the given Customer
POST /customers/{guid}/purchases
Add a List of Purchases to the Customer
POST /customers/{guid}/purchases/bulk
Update a List of Purchases for a Customer
DELETE /customers/{guid}/purchases/{purchase_guid}
PATCH /customers/{guid}/purchases/{purchase_guid}
Update a given Purchase for a Customer
POST /customers/{guid}/users

## Dashboards

GET /dashboards/{dashboard_key}
PUT /dashboards/{dashboard_key}

## DCEs

GET /delegated-security-controls-summary

## Defaults

GET /alerts/types
GET /defaults
GET /defaults/compliance-certifications
GET /defaults/risk-correlations

## Domains

GET /companies/{company_guid}/domains/{domain_name}/products
GET /companies/{company_guid}/domains/{domain_name}/providers
GET /companies/{company_guid}/products/{product_guid}/domains
GET /companies/{company_guid}/providers/{provider_guid}/domains

## Exposed Credentials

GET /companies/{company_guid}/exposed-credentials/credentials
GET /companies/{company_guid}/exposed-credentials/events
GET /companies/{company_guid}/exposed-credentials/events/{event_guid}
GET /companies/{company_guid}/exposed-credentials/premium/summaries
GET /companies/{company_guid}/exposed-credentials/summaries
GET /exposed-credentials/affected-companies
GET /exposed-credentials/data-classes
GET /exposed-credentials/leaks

## Feature

GET /companies/features/{feature}
POST /companies/features/{feature}/bulk

## Financial Quantification (Insurance)

## Financial Quantification (Security Performance Management)

GET /companies/{company_guid}/financial-quantifications/enhanced/latest
GET /companies/{guid}/financial-quantifications/enhanced
POST /companies/{guid}/financial-quantifications/enhanced
PUT /companies/{guid}/financial-quantifications/enhanced
GET /companies/{guid}/financial-quantifications/enhanced/{fq_guid}
PATCH /companies/{guid}/financial-quantifications/enhanced/{fq_guid}

## Financial Quantification Draft (Security Performance Management)

## Folders

GET /folders
POST /folders
GET /folders/{folder_guid}/findings/summary/
GET /folders/{folder_guid}/graph_data
GET /folders/{folder_guid}/industry-median/statistics/
GET /folders/{folder_guid}/product-types
GET /folders/{folder_guid}/products
GET /folders/{folder_guid}/products/{product_guid}/companies
GET /folders/{folder_guid}/providers
GET /folders/{folder_guid}/providers/breaches
GET /folders/{folder_guid}/providers/breaches/reduced
GET /folders/{folder_guid}/providers/breaches/{breach_guid}
GET /folders/{folder_guid}/providers/{provider_guid}/companies
GET /folders/{folder_guid}/providers/{provider_guid}/products
DELETE /folders/{guid}
Delete folders you've created
GET /folders/{guid}
PATCH /folders/{guid}

## Industries

GET /industries
GET /industries/{slug}/graph_data
GET /industries/{slug}/statistics

## Insights

GET /insights
POST /insights/get_companies
GET /insights/observations
GET /insights/rating_changes

## Integrations

GET /integrations/slack
POST /integrations/slack
POST /integrations/slack/access-token
POST /integrations/slack/authorization-code
DELETE /integrations/slack/{id}
PATCH /integrations/slack/{id}
GET /integrations/teams
POST /integrations/teams
POST /integrations/teams/access-token
POST /integrations/teams/authorization-code
DELETE /integrations/teams/{id}
PATCH /integrations/teams/{id}

## Knowledge Base

GET /infections
GET /knowledge-base/infections/{id}
GET /open-port-services
POST /open-port-services/query

## Licenses

GET /assessment/assessments/templates/{template_guid}/companies/{company_guid}
GET /current-ratings
POST /current-ratings
GET /licenses/summaries

## Life Cycles

GET /company-life-cycle-types
GET /company-life-cycles
POST /company-life-cycles
PATCH /company-life-cycles/{life_cycle_guid}/activities/{activity_slug}

## Managed Monitoring

GET /managed-monitoring/agreement
PATCH /managed-monitoring/agreement
GET /managed-monitoring/companies
PATCH /managed-monitoring/companies
GET /managed-monitoring/config
PATCH /managed-monitoring/config

## Notifications

GET /notifications
POST /notifications
POST /notifications/mark-all-as-read
GET /notifications/{id}
PATCH /notifications/{id}

## Partners

GET /partners/{partner_guid}/customers
POST /partners/{partner_guid}/customers
POST /partners/{partner_guid}/customers/{customer_guid}/purchase-orders
DELETE /partners/{partner_guid}/customers/{guid}
GET /partners/{partner_guid}/customers/{guid}

## Peer Analytics

GET /companies/{company_guid}/peer-analytics/dashboard/
GET /companies/{company_guid}/peer-analytics/graph-data/compromised-systems/
GET /companies/{company_guid}/peer-analytics/peer-group/count/
GET /companies/{company_guid}/peer-analytics/ratings-distribution/
GET /companies/{company_guid}/peer-analytics/recommended-peers
GET /companies/{company_guid}/peer-analytics/reports/diligence
POST /companies/{company_guid}/peer-analytics/reports/peer-group-company-names
GET /companies/{company_guid}/peer-analytics/statistics/compromised-systems/
GET /companies/{company_guid}/peer-analytics/statistics/diligence
GET /companies/{company_guid}/peer-analytics/statistics/user-behavior/
GET /peer-analytics/configs/user
PATCH /peer-analytics/configs/user
PUT /peer-analytics/configs/user
POST /peer-analytics/peer-group-summary
GET /peer-analytics/peer-groups
POST /peer-analytics/peer-groups
DELETE /peer-analytics/peer-groups/{guid}
GET /peer-analytics/peer-groups/{guid}
PATCH /peer-analytics/peer-groups/{guid}
PUT /peer-analytics/peer-groups/{guid}
POST /peer-analytics/ratings-distribution

## Portfolio

GET /peer-analytics/peer-groups/{guid}/statistics
GET /portfolio
GET /portfolio/breaches
POST /portfolio/entity-custom-ids/bulk
GET /portfolio/filters/vulnerabilities
GET /portfolio/findings/counts
POST /portfolio/infections/statistics
GET /portfolio/monitored-assets
POST /portfolio/monitored-assets/bulk
POST /portfolio/monitored-assets/bulk/validate
GET /portfolio/monitored-assets/quota
GET /portfolio/monitored-assets/summaries
GET /portfolio/monitored-assets/threats
GET /portfolio/product-types
GET /portfolio/products
GET /portfolio/products/{product_guid}/companies
GET /portfolio/providers
GET /portfolio/providers/breaches
GET /portfolio/providers/breaches/reduced
GET /portfolio/providers/breaches/{breach_guid}
GET /portfolio/providers/{provider_guid}/companies
GET /portfolio/providers/{provider_guid}/products
GET /portfolio/ratings
GET /portfolio/risk-vectors/grades
GET /portfolio/statistics
GET /portfolio/territories/industries/risk-vectors/grades
GET /portfolio/territories/risk-vectors/grades
POST /portfolio/vulnerabilities/statistics

## Product Types

GET /companies/{company_guid}/company-tree/product-types
GET /filters/portfolio/product-types
GET /folders/{folder_guid}/product-types
GET /portfolio/product-types
GET /tiers/{tier_guid}/product-types

## Products

GET /companies/{company_guid}/company-tree/products
GET /companies/{company_guid}/company-tree/products/{product_guid}/companies
GET /companies/{company_guid}/company-tree/providers/{provider_guid}/products
GET /companies/{company_guid}/domains/{domain_name}/products
GET /companies/{company_guid}/fourth-parties
POST /companies/{company_guid}/fourth-parties
DELETE /companies/{company_guid}/fourth-parties/{fourth_party_guid}
GET /companies/{company_guid}/fourth-parties/{fourth_party_guid}
GET /companies/{company_guid}/products
POST /companies/{company_guid}/products
GET /filters/portfolio/products
GET /folders/{folder_guid}/products
GET /folders/{folder_guid}/products/{product_guid}/companies
GET /folders/{folder_guid}/providers/{provider_guid}/products
GET /portfolio/products
GET /portfolio/products/{product_guid}/companies
GET /portfolio/providers/{provider_guid}/products
GET /products/{product_guid}
GET /tiers/{tier_guid}/products
GET /tiers/{tier_guid}/products/{product_guid}/companies
GET /tiers/{tier_guid}/providers/{provider_guid}/products

## Providers

GET /companies/{company_guid}/company-tree/providers
GET /companies/{company_guid}/company-tree/providers/breaches
GET /companies/{company_guid}/company-tree/providers/breaches/reduced
GET /companies/{company_guid}/company-tree/providers/breaches/{breach_guid}
GET /companies/{company_guid}/company-tree/providers/{provider_guid}/companies
GET /companies/{company_guid}/company-tree/providers/{provider_guid}/products
GET /companies/{company_guid}/domains/{domain_name}/providers
GET /companies/{company_guid}/fourth-parties
POST /companies/{company_guid}/fourth-parties
DELETE /companies/{company_guid}/fourth-parties/{fourth_party_guid}
GET /companies/{company_guid}/fourth-parties/{fourth_party_guid}
GET /companies/{company_guid}/products/{product_guid}/domains
GET /companies/{company_guid}/providers
GET /companies/{company_guid}/providers/breaches
GET /companies/{company_guid}/providers/breaches/{breach_guid}
GET /companies/{company_guid}/providers/{provider_guid}/domains
GET /filters/portfolio/providers
GET /folders/{folder_guid}/providers
GET /folders/{folder_guid}/providers/breaches
GET /folders/{folder_guid}/providers/breaches/reduced
GET /folders/{folder_guid}/providers/breaches/{breach_guid}
GET /folders/{folder_guid}/providers/{provider_guid}/companies
GET /folders/{folder_guid}/providers/{provider_guid}/products
GET /portfolio/providers
GET /portfolio/providers/breaches
GET /portfolio/providers/breaches/reduced
GET /portfolio/providers/breaches/{breach_guid}
GET /portfolio/providers/{provider_guid}/companies
GET /portfolio/providers/{provider_guid}/products
GET /providers/{provider_guid}
GET /tiers/{tier_guid}/providers
GET /tiers/{tier_guid}/providers/breaches
GET /tiers/{tier_guid}/providers/breaches/reduced
GET /tiers/{tier_guid}/providers/breaches/{breach_guid}
GET /tiers/{tier_guid}/providers/{provider_guid}/companies
GET /tiers/{tier_guid}/providers/{provider_guid}/products

## Quick View

GET /companies/{guid}/quick-view/ai-summary

## Quota

GET /fast-ratings/quota
GET /portfolio/monitored-assets/quota

## Rapid Underwriting Assessments

POST /fast-ratings
GET /fast-ratings/quota
GET /fast-ratings/requests
GET /fast-ratings/requests/summaries
GET /fast-ratings/requests/{request_guid}/response

## ReleaseNote

GET /release-notes
GET /release-notes/{id}

## ReleasePreview

GET /rating-release-previews
GET /rating-release-previews/portfolio/statistics
GET /rating-release-previews/{company_guid}
GET /rating-release-previews/{company_guid}/summaries

## Remediations

GET /remediations
POST /remediations
GET /remediations/preferences
PATCH /remediations/preferences
POST /remediations/preferences
GET /remediations/summaries

## Reports

GET /companies/{guid}/reports/company-preview
POST /companies/{guid}/reports/company-preview
GET /companies/{guid}/reports/spi
GET /companies/{guid}/reports/spi/{report_name}/evaluations
POST /companies/{guid}/reports/spi/{report_name}/evaluations
DELETE /companies/{guid}/reports/spi/{report_name}/evaluations/{evaluation_guid}
PATCH /companies/{guid}/reports/spi/{report_name}/evaluations/{evaluation_guid}
GET /companies/{guid}/reports/spi/{spi_report_version}/
GET /reports/dashboards
POST /reports/spi/requests
GET /reports/user-workbooks
POST /reports/user-workbooks
POST /reports/{guid}/share

## Risk Correlations

GET /portfolio/risk-correlations/ransomware-incidents/statistics
GET /portfolio/risk-correlations/security-incidents/risk-vectors/summaries
GET /portfolio/risk-correlations/security-incidents/statistics
GET /tiers/risk-correlations/ransomware-incidents/summaries
GET /tiers/risk-correlations/security-incidents/summaries

## SAML IdPs

GET /idps
Get a List of all SAML IdPs for the current Customer
POST /idps
Add a SAML IdP to the current Customer
GET /idps/config
Get the configuration information about the IdPs for the current customer
DELETE /idps/{guid}
PATCH /idps/{guid}

## Self-Published

GET /companies/{company_guid}/fourth-parties
POST /companies/{company_guid}/fourth-parties
DELETE /companies/{company_guid}/fourth-parties/{fourth_party_guid}
GET /companies/{company_guid}/fourth-parties/{fourth_party_guid}

## Sovereign

GET /countries/{country_guid}/industries/{country_industry_guid}/companies
GET /industries/countries
GET /sovereign/observations
GET /sovereign/observations/companies/kpis
GET /sovereign/observations/counts
GET /sovereign/observations/kpis
GET /territories/{territory_guid}/industries/{industry_guid}/grades

## Standard Underwriting Assessments

## Statistics

POST /diligence/statistics
POST /observations/statistics
POST /user-behavior/statistics

## Subscriptions

GET /subscriptions/
POST /subscriptions/
POST /subscriptions/bulk
GET /subscriptions/companies
POST /subscriptions/companies
GET /subscriptions/company_annotations
GET /subscriptions/expired
GET /subscriptions/{company_guid}
GET /subscriptions/{company_guid}/company_annotations

## Subsidiaries

GET /companies/{guid}/subsidiaries
GET /subsidiaries
GET /subsidiaries/statistics
GET /subsidiaries/{company_guid}/recommendations

## Tiers

GET /tiers
POST /tiers
GET /tiers/configs
PATCH /tiers/configs
GET /tiers/configs/security-risks
POST /tiers/configs/security-risks
DELETE /tiers/configs/security-risks/{config_guid}
GET /tiers/configs/security-risks/{config_guid}
PATCH /tiers/configs/security-risks/{config_guid}
PUT /tiers/configs/security-risks/{config_guid}
GET /tiers/security-risk
GET /tiers/summary
GET /tiers/vendor-action-plan
DELETE /tiers/{tier_guid}
GET /tiers/{tier_guid}
PATCH /tiers/{tier_guid}
PUT /tiers/{tier_guid}
PATCH /tiers/{tier_guid}/companies
GET /tiers/{tier_guid}/graph_data
GET /tiers/{tier_guid}/product-types
GET /tiers/{tier_guid}/products
GET /tiers/{tier_guid}/products/{product_guid}/companies
GET /tiers/{tier_guid}/providers
GET /tiers/{tier_guid}/providers/breaches
GET /tiers/{tier_guid}/providers/breaches/reduced
GET /tiers/{tier_guid}/providers/breaches/{breach_guid}
GET /tiers/{tier_guid}/providers/{provider_guid}/companies
GET /tiers/{tier_guid}/providers/{provider_guid}/products
GET /tiers/{tier_guid}/summary

## UiPreferences

GET /ui-preferences
PATCH /ui-preferences

## Underwriting Assessments

## Underwriting Guidelines

GET /companies/{company_guid}/underwriting-guidelines
GET /underwriting-guidelines
POST /underwriting-guidelines
GET /underwriting-guidelines/defaults
DELETE /underwriting-guidelines/{guid}
PATCH /underwriting-guidelines/{guid}

## Users

GET /customers/current/features
POST /customers/current/features
GET /users
GET /users/current
GET /users/current/beta-features
POST /users/current/beta-features
GET /users/quota
GET /users/{user_guid}
GET /users/{user_guid}/company-views

## UserViewPreferences

GET /view-preferences
POST /view-preferences
DELETE /view-preferences/{guid}
GET /view-preferences/{guid}
PATCH /view-preferences/{guid}

## Vendor Access Requests

GET /access-requests
POST /access-requests
POST /access-requests/bulk
GET /access-requests/config
PATCH /access-requests/config
GET /access-requests/counts
GET /access-requests/received
POST /access-requests/received/mark-all-as-read
GET /access-requests/received/{guid}
PATCH /access-requests/received/{guid}
POST /access-requests/self-access/validate-token
PATCH /access-requests/{guid}

## WFH

GET /findings/wfh
GET /findings/wfh/bulk
POST /findings/wfh/bulk
DELETE /findings/wfh/bulk/{bulk_request_guid}
POST /findings/wfh/bulk/{bulk_request_guid}/rescan

## AppRegions

GET /app-regions
GET /customers/app-regions
POST /customers/app-regions

## Tactical Recovery Plan

POST /companies/{company_guid}/feft/
POST /companies/{company_guid}/feft/{risk_vector}
GET /companies/{company_guid}/tactical-recovery-plans/
POST /companies/{company_guid}/tactical-recovery-plans/
GET /companies/{company_guid}/tactical-recovery-plans/latest/{risk_vector}
GET /companies/{company_guid}/tactical-recovery-plans/{trp_guid}

## Infections

GET /companies/{guid}/infections
POST /companies/{guid}/infections/query

## default

POST /companies/{guid}/iq/assessments/document-collections
GET /company-rankings
GET /geolocation/countries
GET /news
GET /peer-analytics/peer-groups/{guid}/graph-data
GET /portfolio/vulnerabilities
GET /sovereign/network-resources/ips/{ip}
Validate IP
GET /sub-industries/statistics
GET /vulnerabilities

## IQ Assessments

GET /iq/assessments/frameworks

## Threats

GET /threats/attestations
