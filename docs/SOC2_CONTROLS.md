# SOC 2 Type 1 Control Documentation

## Overview

This document maps Valdrics security controls to SOC 2 Trust Service Criteria.
Use this as the foundation for SOC 2 Type 1 audit preparation.

**Organization:** Valdrics AI  
**Audit Scope:** Cloud FinOps Platform  
**Document Version:** 1.0  
**Last Updated:** 2026-01-14

---

## Trust Service Criteria Mapping

### CC1: Control Environment

| Control ID | Description | Implementation | Evidence |
|------------|-------------|----------------|----------|
| CC1.1 | Management commitment to integrity | BSL 1.1 license, code of conduct | LICENSE, README |
| CC1.2 | Board oversight | Founder oversight, quarterly reviews | Meeting notes |
| CC1.3 | Organizational structure | Clear codebase structure, CODEOWNERS | CODEOWNERS file |
| CC1.4 | Competence commitment | Code review process, CI/CD gates | GitHub PR history |

### CC2: Communication and Information

| Control ID | Description | Implementation | Evidence |
|------------|-------------|----------------|----------|
| CC2.1 | Internal communication | Structured logging, alerts | `app/core/logging.py` |
| CC2.2 | External communication | Privacy policy, terms of service | Legal docs |
| CC2.3 | Security policies | DR runbook, security headers | `docs/DR_RUNBOOK.md` |

### CC3: Risk Assessment

| Control ID | Description | Implementation | Evidence |
|------------|-------------|----------------|----------|
| CC3.1 | Risk identification | Technical due diligence audits | `technical_due_diligence.md` |
| CC3.2 | Risk analysis | Threat modeling, dependency scanning | CI/CD Trivy, Bandit |
| CC3.3 | Fraud risk | - | N/A (B2B SaaS) |
| CC3.4 | Change impact | Version control, PR reviews | GitHub history |

### CC4: Monitoring Activities

| Control ID | Description | Implementation | Evidence |
|------------|-------------|----------------|----------|
| CC4.1 | Ongoing monitoring | Health dashboard, job queue status | `/admin/health-dashboard` |
| CC4.2 | Deficiency evaluation | Error logging, dead letter queue | Structlog, background_jobs |

### CC5: Control Activities

| Control ID | Description | Implementation | Evidence |
|------------|-------------|----------------|----------|
| CC5.1 | Risk mitigation | Circuit breakers, rate limiting | `circuit_breaker.py`, `rate_limiter.py` |
| CC5.2 | Technology controls | JWT auth, RLS, encryption | `app/shared/core/auth.py` |
| CC5.3 | Policy deployment | CI/CD automation | `.github/workflows/ci.yml` |

### CC6: Logical and Physical Access

| Control ID | Description | Implementation | Evidence |
|------------|-------------|----------------|----------|
| CC6.1 | Access architecture | Supabase Auth, JWT tokens | `app/shared/core/auth.py` |
| CC6.2 | Access restrictions | RBAC (admin, member roles) | `requires_role()` decorator |
| CC6.3 | Registration/authorization | Supabase user management | Supabase dashboard |
| CC6.4 | Access removal | Manual process via Supabase | Runbook needed |
| CC6.5 | Logical access | Row-Level Security (RLS) | Migration files |
| CC6.6 | Physical access | Cloud providers (Supabase, Koyeb) | Provider SOC 2s |
| CC6.7 | Data transmission | TLS 1.3, HTTPS only | Security headers |
| CC6.8 | Malware prevention | Trivy container scanning | CI/CD |

### CC7: System Operations

| Control ID | Description | Implementation | Evidence |
|------------|-------------|----------------|----------|
| CC7.1 | Vulnerability detection | Trivy, Bandit, Safety | CI pipeline |
| CC7.2 | Security monitoring | Structlog, trace IDs | `app/core/tracing.py` |
| CC7.3 | Security event analysis | Log aggregation | Future: Datadog/Sentry |
| CC7.4 | Incident response | DR runbook | `docs/DR_RUNBOOK.md` |
| CC7.5 | Recovery procedures | DR runbook | `docs/DR_RUNBOOK.md` |

### CC8: Change Management

| Control ID | Description | Implementation | Evidence |
|------------|-------------|----------------|----------|
| CC8.1 | Change authorization | PR reviews, branch protection | GitHub settings |

### CC9: Risk Mitigation

| Control ID | Description | Implementation | Evidence |
|------------|-------------|----------------|----------|
| CC9.1 | Vendor risk | Dependency scanning | Safety, npm audit |
| CC9.2 | Business continuity | DR runbook, backups | Supabase PITR |

---

## Security Controls Summary

### Authentication
- [x] JWT-based authentication (Supabase)
- [x] Token expiration and refresh
- [x] CORS configuration
- [x] Secure headers (CSP, HSTS)

### Authorization
- [x] Role-based access control (RBAC)
- [x] Row-Level Security (RLS) on all tenant tables
- [x] Tenant isolation in all queries

### Data Protection
- [x] Encryption at rest (Supabase)
- [x] Encryption in transit (TLS 1.3)
- [x] Sensitive data masking in logs
- [x] AWS credentials encrypted

### Infrastructure
- [x] Container scanning (Trivy)
- [x] SAST scanning (Bandit)
- [x] Dependency scanning (Safety, npm audit)
- [x] Secret scanning (TruffleHog)

### Operational
- [x] Structured logging
- [x] Distributed tracing (trace IDs)
- [x] Health monitoring endpoints
- [x] DR runbook

---

## Audit Evidence Locations

| Evidence Type | Location |
|---------------|----------|
| Code repository | github.com/Valdrics/valdrics |
| CI/CD history | GitHub Actions logs |
| Security scans | CI artifacts |
| Access logs | Supabase dashboard |
| API logs | Application logs (Koyeb) |
| Change history | Git commit history |

---

## Gap Analysis (Pre-Audit)

### Currently Missing

| Control | Gap | Remediation |
|---------|-----|-------------|
| CC6.4 | Access removal process | Document offboarding procedure |
| CC7.3 | Centralized log analysis | Add Datadog/Sentry integration |
| - | Security awareness training | Document training program |
| - | Formal incident response plan | Expand DR runbook |

### Recommended Pre-Audit Actions

1. **Document access management procedures** - Who can grant/revoke access
2. **Set up log aggregation** - Datadog, Papertrail, or CloudWatch
3. **Create security training record** - Even informal documentation
4. **Expand incident response** - Add communication templates

---

## Compliance Statement

Valdrics AI maintains a security-first approach to software development. 
Our controls are designed to protect customer data and ensure service reliability.
We leverage SOC 2 certified infrastructure providers (Supabase, AWS, Koyeb) 
and implement application-level controls as documented above.

---

*This document should be updated quarterly and before any SOC 2 audit.*
