
# Multi-Region Failover Architecture

## 1. Strategy
Valdrix uses an **Active-Passive** multi-region strategy for high availability.

## 2. Components
- **Primary Region**: AWS `us-east-1`.
- **Secondary Region (Failover)**: AWS `eu-west-1`.
- **Global DNS**: Route 53 with Health Checks.
- **Database**: Supabase (PostgreSQL) with cross-region read replicas.

## 3. Failover Procedure
1. **Detection**: Route 53 health check fails for the primary region.
2. **Switch**: DNS is updated to point to the secondary region endpoint.
3. **Database Promotion**: If the primary DB is down, promote the secondary replica to primary.
4. **Validation**: Automated smoke tests run in the secondary region.

## 4. RTO / RPO
- **Recovery Time Objective (RTO)**: 15 minutes.
- **Recovery Point Objective (RPO)**: 5 minutes (data loss limit).
