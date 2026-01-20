# Data Retention & Purge Policy

**Scope:** All Valdrix Tenant Data

## 1. Purpose
To ensure compliance with GDPR and other data protection regulations by defining how long data is stored and how it is purged.

## 2. Retention Periods
| Data Category | Retention Period | Reason |
|---------------|------------------|--------|
| Authentication Logs | 90 Days | Security Auditing |
| Cost/Billing Data | 7 Years | Financial Compliance |
| Zombie Scan Results| 1 Year | Trend Analysis |
| LLM Analysis | 30 Days | Privacy Minimization |
| Remediation Logs | 7 Years | Operational Accountability|
| Tenant Metadata | Period of Service + 30 Days | Operational |

## 3. Purging Mechanism
1. **Automated Cleanup**: A background job runs daily to delete records older than their retention period.
2. **Account Deletion**: When a tenant deletes their account, all associated data is hard-deleted within 30 days.
3. **Backup Purge**: Backups are rotated every 30 days. Data purged from the primary DB will be gone from all backups after 30 days.

## 4. Compliance
Tenants can request a "Data Purge Report" to verify that their data has been removed according to this policy.
