# Workstream Categorization: All Local Changes (2026-03-02)

This document categorizes the full local working-tree delta at capture time.

## Inventory Source of Truth
- File-level inventory: `docs/ops/evidence/all_changes_inventory_2026-03-02.txt`
- Total changed paths: `383`
  - Modified: `348`
  - Deleted: `22`
  - Added (untracked): `13`

## Top-Level Distribution
- `tests`: 121
- `app`: 63
- `reports`: 38
- `dashboard`: 35
- `docs`: 33
- `scripts`: 21
- `helm`: 14
- `terraform`: 11
- `cloudformation`: 4
- `.github`: 4
- `migrations`: 3
- `loadtest`: 3
- `grafana`: 3
- `prometheus`: 2
- `ops`: 2
- `data`: 2
- `assets`: 2
- root/config singletons: 20

## Categorized Tracks

### Track K: Platform/backend hardening and migration contracts
- Issue: https://github.com/Valdrics/valdrics/issues/212
- File count: 66
- Coverage patterns:
  - `app/**`
  - `migrations/**`

### Track L: Frontend product surfaces and landing UX rollout
- Issue: https://github.com/Valdrics/valdrics/issues/213
- File count: 37
- Coverage patterns:
  - `dashboard/**`
  - `assets/**`

### Track M: Infra/deploy/observability platform alignment
- Issue: https://github.com/Valdrics/valdrics/issues/214
- File count: 48
- Coverage patterns:
  - `terraform/**`
  - `helm/**`
  - `cloudformation/**`
  - `.github/workflows/**`
  - `grafana/**`
  - `prometheus/**`
  - `ops/**`
  - `loadtest/**`
  - `docker-compose*.yml`
  - `koyeb.yaml`
  - `prod.env.template`

### Track N: Docs/reports/legal-governance evidence synchronization
- Issue: https://github.com/Valdrics/valdrics/issues/215
- File count: 79
- Coverage patterns:
  - `docs/**`
  - `reports/**`
  - `README.md`
  - `DEPLOYMENT.md`
  - `CHANGELOG.md`
  - `CLA.md`
  - `COMMERCIAL_LICENSE.md`
  - `CONTRIBUTING.md`
  - `LICENSE`
  - `TRADEMARK_POLICY.md`

### Track O: QA/tooling/script verification hardening
- Issue: https://github.com/Valdrics/valdrics/issues/216
- File count: 153
- Coverage patterns:
  - `tests/**`
  - `scripts/**`
  - `pyproject.toml`
  - `uv.lock`
  - `.pre-commit-config.yaml`
  - `coverage-enterprise-gate.xml`
  - `codealike.json`
  - `.cursorrules`
  - `.env.example`
  - `Makefile`
  - `Dockerfile`
  - `data/**`

## Merge Intent
- Merge as one full-batch PR referencing Tracks K-O.
- Auto-close issues `#212`-`#216` via PR closing keywords.
