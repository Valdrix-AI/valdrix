# Licensing Guide

Last updated: February 12, 2026

This project is released under the Business Source License 1.1 (BSL 1.1). The legal source of truth is `LICENSE`. If anything in this guide conflicts with `LICENSE`, the `LICENSE` file wins.

## Plain-English Summary

- You can run Valdrics internally in your own organization.
- You cannot offer Valdrics itself as a competing hosted/managed service to third parties.
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
| Reselling Valdrics as your own hosted SaaS | No | Prohibited competitive hosted offering. |
| Multi-tenant MSP offering Valdrics capabilities as a service | No | Prohibited if customers consume Valdrics as the service. |
| Research, evaluation, and test environments | Yes | Non-production and production internal use allowed. |

## Definitions Used in This Project

- Production use: any environment used to serve real internal business workloads.
- Hosted service: software operated by one party for use by unrelated third parties over a network.
- Competitive offering: hosted use where Valdrics functionality is sold or bundled as a service.

## Licensing FAQ

### Can I self-host Valdrics?

Yes, for your own internal operations.

### Can Valdrix-AI offer an official hosted SaaS?

Yes. The BSL restriction targets third parties offering competing hosted services. It does not block the project owner from operating the official Valdrics SaaS.

### Can I run it for my clients?

You can deploy/support a client-owned instance. You cannot operate a shared hosted Valdrics service for third-party consumption.

### Can I buy rights to run Valdrics as a managed service?

Yes. We provide commercial exceptions for qualified partners and OEM use cases. See `COMMERCIAL_LICENSE.md`.

### Can I resell or white-label it as a hosted platform?

Not under default BSL terms before the change date. This requires a separate commercial agreement.

### When does it become Apache 2.0?

On January 12, 2029, per the change terms in `LICENSE`.

### Does Apache conversion stop Valdrix-AI from making money?

No. Valdrix-AI can continue monetizing through the official SaaS, enterprise features, support, compliance packaging, and commercial agreements.

## Related Policy Documents

- [`LICENSE`](../LICENSE)
- [`COMMERCIAL_LICENSE.md`](../COMMERCIAL_LICENSE.md)
- [`TRADEMARK_POLICY.md`](../TRADEMARK_POLICY.md)
- [`CLA.md`](../CLA.md)
