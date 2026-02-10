# Change Categorization Report

Generated: 2026-02-10
Branch: `main`
Working tree entries: `364`

## 1) Snapshot Summary

- Modified tracked files: heavy concentration in `app/` and `tests/`
- Untracked files: significant; includes new tests, terraform files, and many generated local artifacts
- Deleted tracked files: at least `terraform/valdrix-role.tf`, `tests/analysis/test_greenops_2.py`

## 2) Counts By Top-Level Area

From tracked diffs (`git diff --name-only`):
- `tests`: 127
- `app`: 95
- `scripts`: 6
- `.github`: 3
- `docs`: 2
- `cloudformation`: 2
- `dashboard`: 1
- `docker-compose.yml`: 1
- `docker-compose.observability.yml`: 1
- `migrations`: 1
- `prometheus`: 1
- `pyproject.toml`: 1
- `terraform`: 1
- `uv.lock`: 1

From untracked files (`git ls-files --others --exclude-standard`):
- `tests`: 56
- `terraform`: 22
- `app`: 6
- Generated local test/db/log artifacts: many (`test_*.sqlite`, `tmp_*.sqlite`, `test_output*.txt`, etc.)

## 3) Categorized Buckets

### A. Core Backend + Security/Architecture
Scope:
- `app/` (governance, optimization, reporting, shared core/db, schedulers, adapters)

Risk:
- High (behavioral and security-sensitive paths changed)

### B. Test Suite Expansion + Coverage Work
Scope:
- `tests/` modified and new files across unit/integration/security/governance/optimization/reporting

Risk:
- Medium/High (can destabilize CI signal if mixed with production changes)

### C. Infra/Runtime/Platform
Scope:
- `.github/workflows/`, `docker-compose*`, `prometheus/`, `cloudformation/`, `terraform/`, `migrations/`

Risk:
- High (deployment, CI, observability, and IaC blast radius)

### D. Tooling/Dependency/Docs/UI
Scope:
- `pyproject.toml`, `uv.lock`, `scripts/`, `docs/`, `dashboard/`

Risk:
- Medium

### E. Generated/Transient Local Artifacts (should not ship)
Scope:
- `test_*.sqlite`, `tmp_*.sqlite`, `test_output*.txt`, `analyzer_error.txt`, etc.

Risk:
- High hygiene risk (pollutes PR and can hide real changes)

## 4) Recommended GitHub Issue Breakdown

1. `repo-stabilization/core-backend-security`
- Track all production runtime/security/architecture changes under `app/`

2. `repo-stabilization/test-suite-consolidation`
- Track all added/modified tests, dedup, and coverage gate strategy

3. `repo-stabilization/infra-ci-observability-iac`
- Track workflows, compose, prometheus, cloudformation, terraform, migrations

4. `repo-stabilization/tooling-deps-docs-ui`
- Track scripts, dependencies, docs, dashboard

5. `repo-stabilization/transient-artifact-cleanup`
- Remove/ignore generated local artifacts and tighten `.gitignore`

## 5) Release Hygiene Gate (required before merge)

- Ensure GitHub auth is valid for `gh` commands
- Remove transient artifacts from proposed PR scope
- Split commits by category (A-E)
- Run category-specific tests before merge
- Require PR checks green before merge to `main`
