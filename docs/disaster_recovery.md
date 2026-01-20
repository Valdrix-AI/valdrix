### Scenario A: Region Outage
- **Action**: Follow Multi-Region Failover Architecture.

### Scenario B: Data Corruption / Ransomware
- **Action**: Restore database from the latest point-in-time recovery (PITR) snapshot before the incident.

### Scenario C: Credential Leak
- **Action**: Revoke all compromised tokens, rotate rotation keys using KMS, and re-provision secrets.

## 3. Dry Runs
Valdrix performs a full DR drill every 6 months to ensure the RTO/RPO targets are met.
