# Incident Response Runbook (SOC2 CC7.4)

**Version:** 1.0 (Audit Remediation)
**Status:** Operational
**Scope:** Valdrics Valdrics-AI Platform

## 1. Detection and Analysis

### Initial Indicators
- **Security Alerts**: Monitoring systems (Prometheus/Grafana) trigger on `rls_enforcement_violation_detected`.
- **Anomalous Activity**: Drastic spikes in LLM usage or remediation actions.
- **Budget Breaches**: `budget_hard_cap_breached` logs in `SafetyGuardrailService`.

### Severity Levels
| Level | Description | Example |
|-------|-------------|---------|
| SEV-1 | Critical data breach or platform compromise | RLS failure detected in production |
| SEV-2 | High impact service disruption | Budget hard cap reached for Enterprise tenant |
| SEV-3 | Medium impact anomaly | Repeated remediation failures (Circuit Breaker) |

---

## 2. Containment and Neutralization

### Emergency Disconnect
If an AWS connection is compromised or performing unauthorized deletions:
```bash
python3 scripts/emergency_disconnect.py --tenant-id <UUID> --provider aws
```
*This attaches an inline 'Deny All' policy to the Valdrics IAM role.*

### Global Kill Switch
To stop all remediation actions globally (if a systemic bug is suspected):
1. Update `.env` or Kubernetes ConfigMap:
   `REMEDIATION_KILL_SWITCH_THRESHOLD=0.1`
2. Restart API/Worker pods.

### Database Session Cutoff
To terminate all sessions for a suspected compromised tenant:
```sql
SELECT pg_terminate_backend(pid) 
FROM pg_stat_activity 
WHERE query LIKE '%set_config(''app.current_tenant_id'', ''<TENANT_ID>'', true)%';
```

---

## 3. Investigation and Eradication

### Log Analysis
- **Audit Logs**: Query `audit_events` table for actor actions.
- **Structured Logs**: Search for `correlation_id` in centralized logging (Loki/CloudWatch).
- **Traces**: Use Jaeger/Honeycomb to trace the request lifecycle.

---

## 4. Recovery and Post-Mortem

1. **Restore Data**: If resources were accidentally deleted, use the backup identified in the `RemediationRequest` (`backup_resource_id`).
2. **Review RLS**: Analyze `rls_context_missing` metrics to identify code-level isolation gaps.
3. **Draft PIR**: Complete a Post-Incident Report within 48 hours for SOC2 compliance.
