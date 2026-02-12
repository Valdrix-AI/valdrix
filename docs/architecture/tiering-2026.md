# 2026 Tiering Strategy

## Goal
Package capabilities so entry tiers are affordable, advanced FinOps workflows are monetizable, and enterprise features align to procurement requirements.

## Tier map

### Starter
- Baseline visibility and controls:
  - `dashboards`
  - `cost_tracking`
  - `alerts`
  - `zombie_scan`
  - `greenops`
  - `carbon_tracking`
  - `multi_cloud`
  - `multi_region`
- Q2 value layer:
  - `unit_economics`
  - `ingestion_sla`

### Growth
- Includes Starter, plus advanced optimization and financial workflows:
  - `llm_analysis`
  - `chargeback`
  - `ingestion_backfill`
  - `auto_remediation`
  - `precision_discovery`
  - `owner_attribution`

### Pro
- Includes Growth, plus finance-grade and enterprise controls:
  - `reconciliation`
  - `close_workflow`
  - `carbon_assurance`
  - `compliance_exports`
  - `savings_proof`
  - `sso`
  - `api_access`
  - `audit_logs`
  - `gitops_remediation`

### Enterprise
- Includes all features, plus top-end scope expansion:
  - `cloud_plus_connectors`
  - custom and contractual deployment options

## Roadmap alignment
- Q1 foundations (canonicalization, reconciliation v1, commitment logic): platform-wide trust baseline.
- Q2 productization (chargeback, unit economics, ingestion completeness): split between Starter and Growth.
- Q3 close + Cloud+ (reconciliation v2, close workflow, Cloud+ connectors, carbon assurance): Pro/Enterprise.
- Q4 procurement proof (compliance exports, savings proof, enterprise hardening): Pro/Enterprise, with deeper capabilities in Enterprise.

## Enforcement principle
- Every premium capability must be gated in backend API dependencies.
- Frontend should avoid unnecessary calls for disabled capabilities to reduce compute and API cost.
- Feature flags in `app/shared/core/pricing.py` are the single source of truth.
