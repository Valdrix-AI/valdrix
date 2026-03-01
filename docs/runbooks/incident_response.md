# Valdrics Operational Runbooks

This document provides step-by-step procedures for handling common operational scenarios and incidents.

## 1. Database Connectivity Failure
**Symptom**: `/health` returns 503, logs show `asyncpg.exceptions`.

1. **Verify Connection String**: Check `DATABASE_URL` in environment variables.
2. **Check Neon/Supabase Status**: Verify if the upstream provider is having an outage.
3. **Connection Pooling**: If `Too many connections` is seen, verify if Supavisor is active or increase `DB_MAX_OVERFLOW`.
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
2. **Token Validity**: Verify `SLACK_BOT_TOKEN`.
3. **Channel ID**: Ensure the bot is a member of the channel specified in `SLACK_CHANNEL_ID`.

## 4. Security Incident: Key Compromise
**Symptom**: Suspected leak of `ENCRYPTION_KEY`.

1. **Generate New Key**: `Fernet.generate_key()`.
2. **Shift Keys**: Move the compromised key to `ENCRYPTION_KEY_FALLBACKS`.
3. **Set New Key**: Set the new key as `ENCRYPTION_KEY`.
4. **Monitor**: Verify that data can still be decrypted (fallback logic).
5. **Re-encrypt**: (Scheduled) Run a background job to re-encrypt all sensitive records with the new primary key.
