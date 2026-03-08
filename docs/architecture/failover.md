# Failover and Availability Architecture

## Current State

The checked-in configuration provides in-region high availability, not automatic
cross-region failover.

The repository does include a scheduled rebuild-and-verify disaster recovery
drill workflow (`.github/workflows/disaster-recovery-drill.yml`) so the manual
regional recovery path is exercised regularly instead of remaining a paper-only
procedure.

## Availability Building Blocks

- Edge/frontend: Cloudflare Pages or ingress fronting the API surface
- API: multi-replica Helm deployment with anti-affinity and rolling updates
- Database: AWS RDS with Multi-AZ enabled
- Cache/rate-limit coordination: ElastiCache replication group with Multi-AZ enabled

## Failure Handling Model

### In-Region Failures

- RDS and Redis are expected to fail over inside the provisioned region.
- API replicas are expected to survive node-level failures through Kubernetes scheduling and anti-affinity.

### Cross-Region Failures

Cross-region recovery is currently manual:

1. Restore data from backups or snapshots into the target region.
2. Apply infrastructure and deploy the application stack in that region.
3. Update Cloudflare or other edge routing to direct traffic to the recovered stack.

## What This Document Does Not Claim

- No DNS-provider-driven automatic failover is defined in the checked-in infrastructure.
- No automatic cross-region database replica promotion is defined in the checked-in infrastructure.
