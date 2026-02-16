# Disaster Recovery Runbook

## Overview
This runbook documents recovery procedures for Valdrix infrastructure.

**RTO (Recovery Time Objective):** 4 hours  
**RPO (Recovery Point Objective):** 24 hours (Supabase daily backups)

---

## 1. Supabase Database Failure

### Detection
- `/health` endpoint returns 500
- Job queue processing stops
- Users cannot login

### Recovery Steps

1. **Check Supabase Status**
   ```bash
   # Check https://status.supabase.com
   curl https://your-project.supabase.co/rest/v1/ -H "apikey: $SUPABASE_ANON_KEY"
   ```

2. **If Supabase Region Outage**
   - Supabase handles failover automatically
   - Wait for status page update
   - ETA: 15-60 minutes

3. **If Data Corruption**
   - Contact Supabase support immediately
   - Request point-in-time recovery (PITR)
   - Supabase retains 7 days of backups

4. **Post-Recovery**
   - Verify job queue resumed: `GET /jobs/status`
   - Run manual job processing: `POST /jobs/process`
   - Check tenant subscriptions are intact

---

## 2. Koyeb Backend Failure

### Detection
- All API endpoints return 502/503
- Health checks fail

### Recovery Steps

1. **Check Koyeb Status**
   ```bash
   # Koyeb dashboard: https://app.koyeb.com
   koyeb service list
   ```

2. **Restart Service**
   ```bash
   koyeb service redeploy valdrix-api
   ```

3. **If Persistent Failure**
   - Check logs: `koyeb logs valdrix-api`
   - Verify DATABASE_URL is correct
   - Redeploy from latest commit

4. **Failover to Backup Region** (if configured)
   ```bash
   # Promote backup instance
   koyeb service scale valdrix-api-backup --instances 1
   # Update DNS/load balancer
   ```

---

## 3. Vercel Frontend Failure

### Detection
- Dashboard returns 500
- Static assets not loading

### Recovery Steps

1. **Check Vercel Status**
   - https://www.vercel-status.com

2. **Redeploy**
   ```bash
   vercel deploy --prod
   ```

3. **Rollback**
   ```bash
   vercel rollback
   ```

---

## 4. Paystack Webhook Failures

### Detection
- `GET /jobs/status` shows dead letter webhooks
- Subscriptions not activating

### Recovery Steps

1. **Check Dead Letter Queue**
   ```bash
   curl -X GET https://api.valdrix.ai/jobs/list?status=dead_letter
   ```

2. **Reprocess Failed Webhooks**
   ```sql
   -- In Supabase SQL Editor
   UPDATE background_jobs 
   SET status = 'pending', attempts = 0 
   WHERE status = 'dead_letter' 
     AND job_type = 'webhook_retry';
   ```

3. **Trigger Processing**
   ```bash
   curl -X POST https://api.valdrix.ai/jobs/process
   ```

---

## 5. LLM Provider Outage

### Detection
- Analysis endpoints timeout
- Logs show provider errors

### Recovery Steps

The system automatically falls back through providers:
1. Groq → Gemini → OpenAI

**Manual Override:**
```bash
# Set preferred provider temporarily
export LLM_PROVIDER=google  # or openai
# Restart service
koyeb service redeploy valdrix-api
```

---

## 6. AWS Rate Limiting

### Detection
- Cost data returns stale/empty
- Logs show "ThrottlingException"

### Recovery Steps

1. The RateLimiter handles this automatically
2. Wait 5-10 minutes for backoff
3. If persistent, check tenant's IAM role permissions

---

## Contact Escalation

| Issue | Primary Contact | Backup |
|-------|----------------|--------|
| Supabase | support@supabase.io | - |
| Koyeb | support@koyeb.com | - |
| Vercel | - | - |
| Paystack | support@paystack.com | - |

---

## Backup Verification Schedule

| Backup Type | Frequency | Last Verified |
|-------------|-----------|---------------|
| Supabase auto | Daily | Check monthly |
| Tenant export | Weekly | - |
| Config backup | On change | - |

---

## Post-Incident

After any incident:
1. Update this runbook if needed
2. Create post-mortem (5 Whys)
3. Add monitoring/alerting for the failure mode
