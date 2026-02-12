# Open-Core Boundary

Last updated: February 12, 2026

This document defines licensing boundaries for Valdrix components.

## Current State

All code in this repository is licensed under BSL 1.1 unless stated otherwise.

## Boundary Policy

| Component Area | License | Boundary Decision |
| --- | --- | --- |
| Control plane APIs, schedulers, policy engine, reconciliation, billing workflows | BSL 1.1 | Core proprietary control-plane logic. |
| Dashboard/UI and admin experiences | BSL 1.1 | Product surface and workflow IP. |
| Production connector implementations in this repo | BSL 1.1 | Operated as part of control-plane product. |
| Future public SDKs/agents (separate repos, when published) | Apache 2.0 (planned) | Intended for ecosystem adoption and integrations. |
| Public schemas/spec helpers (separate repos, when published) | Apache 2.0 (planned) | Intended to ease integration by customers/partners. |

## Contribution Policy

- Contributions to this repository are accepted under BSL 1.1.
- We use DCO-style sign-off for contributions (see `CONTRIBUTING.md`).
- If permissive components are split into separate repositories, they will define their own license files and contribution terms.

## Notes

- This document is a product policy summary, not a replacement for the legal license text.
- Legal terms are defined in `LICENSE`.
