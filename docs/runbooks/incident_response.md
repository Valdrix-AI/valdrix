# Valdrics Operational Runbooks

This document provides step-by-step procedures for handling common operational scenarios and incidents.

## 1. Database Connectivity Failure
**Symptom**: `/health` returns 503, logs show `asyncpg.exceptions`.

1. **Verify Connection String**: Check `DATABASE_URL` in environment variables.
2. **Check Database Provider Status**: Verify if the managed PostgreSQL or AWS RDS backend is having an outage.
3. **Connection Pooling**: If `Too many connections` is seen, review `WEB_CONCURRENCY`, `DB_POOL_SIZE`, and `DB_MAX_OVERFLOW` against the active database connection budget.
4. **Restart Service**: Restart the backend service to clear stale connection pools.

## 2. Slow API Responses
**Symptom**: Logs show `slow_query_detected` (duration > 200ms).

1. **Identify the Query**: Check the log entry for the SQL statement.
2. **Analyze Execution Plan**: Run `EXPLAIN ANALYZE` on the query in the DB console.
3. **Add Indexes**: If a sequential scan is detected on a large table (e.g., `audit_logs`), add a missing index.
4. **Cache Check**: Verify if Redis is hit properly for rate limiting and frequent metadata lookups.

## 3. Slack Notification Failure
**Symptom**: Alerts are not appearing in Slack, logs show `Slack API error`.

1. **Rate Limiting**: If `ratelimited` is seen, the `AsyncWebClient` will auto-retry. Check if volume is excessively high.
2. **Shared Bot Validity**: Verify the platform-managed `SLACK_BOT_TOKEN`.
3. **Tenant Routing**: Confirm the affected tenant has a Slack channel configured in **Settings -> Notifications**. In strict SaaS mode, env channel routing is blocked and `SLACK_CHANNEL_ID` must remain unset.
4. **Workspace Membership**: Ensure the shared bot is invited to the tenant-selected Slack channel.

## 4. Security Incident: Key Compromise
**Symptom**: Suspected leak of `ENCRYPTION_KEY`.

1. **Generate New Key**: `Fernet.generate_key()`.
2. **Shift Keys**: Move the compromised key to `ENCRYPTION_KEY_FALLBACKS`.
3. **Set New Key**: Set the new key as `ENCRYPTION_KEY`.
4. **Monitor**: Verify that data can still be decrypted (fallback logic).
5. **Re-encrypt**: (Scheduled) Run a background job to re-encrypt all sensitive records with the new primary key.
