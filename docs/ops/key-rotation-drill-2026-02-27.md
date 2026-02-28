# Enforcement Key Rotation Drill Evidence (2026-02-27)

This document records the staged enforcement key-rotation drill with fallback and rollback validation.

## Metadata

- drill_id: KRD-2026-02-27-ENF-001
- executed_at_utc: 2026-02-27T08:10:00Z
- environment: staging
- owner: security-oncall
- approver: platform-oncall
- next_drill_due_on: 2026-05-28

## Scope

Secrets rotated during the drill:

1. `ENFORCEMENT_APPROVAL_TOKEN_SECRET`
2. `ENFORCEMENT_APPROVAL_TOKEN_FALLBACK_SECRETS`
3. `ENFORCEMENT_EXPORT_SIGNING_SECRET`

## Validation Outcomes

- pre_rotation_tokens_accepted: true
- post_rotation_new_tokens_accepted: true
- post_rotation_old_tokens_rejected: true
- fallback_verification_passed: true
- rollback_validation_passed: true
- replay_protection_intact: true
- alert_pipeline_verified: true
- post_drill_status: PASS

## Evidence Anchors

1. Enforcement token fallback/rotation tests:
   - `tests/unit/enforcement/test_enforcement_service.py::test_consume_approval_token_accepts_valid_fallback_secret`
   - `tests/unit/enforcement/test_enforcement_service.py::test_consume_approval_token_rejects_when_rotation_fallback_absent`
2. Emergency runbook:
   - `docs/runbooks/secret_rotation_emergency.md`
3. Release-gate contract:
   - `scripts/verify_key_rotation_drill_evidence.py`
   - `scripts/run_enterprise_tdd_gate.py`

## External Benchmarks

1. NIST SP 800-57 (key management lifecycle and operational controls):  
   https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final
2. AWS KMS rotation guidance (operational rotation patterns and cadence):  
   https://docs.aws.amazon.com/kms/latest/developerguide/rotate-keys.html
