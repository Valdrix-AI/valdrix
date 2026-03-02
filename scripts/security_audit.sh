#!/bin/bash
# Valdrics Security Audit Automation Script
# Runs SAST, Dependency Scanning, Secret Checks, and Leak Detection

set -e # Fail-fast: Stop on any error for CI integration (SEC-01)

echo "--- Starting Valdrics Security Audit ---"

# 1. Python SAST (Bandit)
echo "Running Bandit SAST..."
uv run bandit -r app/ -ll

# 2. Dependency Audit (pip-audit)
echo "Running Python Dependency Audit..."
uv run pip-audit

# 3. Secret Leak Detection (Gitleaks)
# BE-SEC-01: Proactive secret detection in CI
if command -v gitleaks &> /dev/null; then
    echo "Running Gitleaks secret scan..."
    gitleaks detect --source . --verbose --redact
else
    echo "WARNING: gitleaks not found. Using fallback grep check..."
    grep -rE "(password|secret|key|token|auth|pwd)\s*=\s*['\"][^'\"]+['\"]" app/ || echo "No obvious hardcoded secrets found."
fi

# 3b. Local .env hygiene check (never prints secret values)
if [ -f ".env" ]; then
    echo "Running local .env live-secret pattern scan..."
    uv run python scripts/security/check_local_env_for_live_secrets.py
fi

# 4. Frontend Audit
if [ -d "dashboard" ]; then
    echo "Running Frontend Dependency Audit..."
    cd dashboard && pnpm audit && cd ..
fi

echo "--- Audit Complete (PASSED) ---"
