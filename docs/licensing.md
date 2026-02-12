# Licensing Guide

Last updated: February 12, 2026

This project is released under the Business Source License 1.1 (BSL 1.1). The legal source of truth is `LICENSE`. If anything in this guide conflicts with `LICENSE`, the `LICENSE` file wins.

## Plain-English Summary

- You can run Valdrix internally in your own organization.
- You cannot offer Valdrix itself as a competing hosted/managed service to third parties.
- On the change date, the code converts to Apache 2.0.

## Change Terms

- Change Date: January 12, 2029
- Change License: Apache License 2.0

## Allowed and Prohibited Use Matrix

| Scenario | Allowed | Notes |
| --- | --- | --- |
| Internal self-hosting for your own company | Yes | Includes production internal usage. |
| Internal use by subsidiaries under same corporate control | Yes | Treated as internal use. |
| Consulting/professional services deploying a customer-owned instance | Yes | Customer controls the instance and data plane. |
| Reselling Valdrix as your own hosted SaaS | No | Prohibited competitive hosted offering. |
| Multi-tenant MSP offering Valdrix capabilities as a service | No | Prohibited if customers consume Valdrix as the service. |
| Research, evaluation, and test environments | Yes | Non-production and production internal use allowed. |

## Definitions Used in This Project

- Production use: any environment used to serve real internal business workloads.
- Hosted service: software operated by one party for use by unrelated third parties over a network.
- Competitive offering: hosted use where Valdrix functionality is sold or bundled as a service.

## FAQ

### Can I self-host Valdrix?

Yes, for your own internal operations.

### Can I run it for my clients?

You can deploy/support a client-owned instance. You cannot operate a shared hosted Valdrix service for third-party consumption.

### Can I resell or white-label it as a hosted platform?

No, not under BSL terms before the change date.

### When does it become Apache 2.0?

On January 12, 2029, per the change terms in `LICENSE`.
