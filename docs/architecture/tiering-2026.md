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
  - `multi_region`
- Operational KPIs:
  - `unit_economics`
  - `ingestion_sla`

### Growth
- Includes Starter, plus advanced optimization and financial workflows:
  - `multi_cloud`
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

## Delivery tracking
Delivery milestones live in `roadmap.md`. Keep this document time-agnostic and aligned with current entitlements in `app/shared/core/pricing.py`.

## Enforcement principle
- Every premium capability must be gated in backend API dependencies.
- Frontend should avoid unnecessary calls for disabled capabilities to reduce compute and API cost.
- Feature flags in `app/shared/core/pricing.py` are the single source of truth.
