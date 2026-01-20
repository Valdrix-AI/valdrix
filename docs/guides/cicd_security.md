# CI/CD Security Hardening Guide

## 1. GitHub Actions Security
- **Strict Privileges**: Workflows use `contents: read` and `id-token: write` (for OIDC).
- **Environment Protection**: Deployment jobs require manual approval from a Security Owner.
- **Secret Management**: Secrets are stored in GitHub Environments, not repository-level.

## 2. Scanning Strategy
- **SAST**: Bandit runs on every PR to find common Python vulnerabilities.
- **SCA**: `pip-audit` checks for vulnerable dependencies once a day.
- **Trivy**: Scans Docker images for vulnerabilities before pushing to ECR.
- **Sentinel (Internal)**: Custom checks for hardcoded credentials.

## 3. Supply Chain Security
- **Pinned Versions**: All dependencies are pinned in `requirements.txt` or `pyproject.toml`.
- **Signed Commits**: Only GPG-signed commits are allowed to merge into `main`.

---

# Disaster Recovery Plan

## 1. Backup Schedule
- **Database**: Full daily backup + WAL streaming (5 min).
- **Configuration**: Version-controlled in Git.
- **Logs**: Replicated to Amazon S3 with cross-region replication.

## 2. Disaster Scenarios
