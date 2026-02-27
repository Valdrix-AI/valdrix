# SSDF Traceability Matrix (2026-02-25)

This document tracks repository evidence for the NIST SSDF baseline:

1. Baseline: NIST SP 800-218 v1.1 (Final, February 2022).
2. Forward watch: NIST SP 800-218 Rev.1 v1.2 IPD (December 2025).

Machine-readable source of truth:

1. `docs/security/ssdf_traceability_matrix_2026-02-25.json`

Validation gate:

1. `scripts/verify_ssdf_traceability_matrix.py`

Release integration:

1. `scripts/run_enterprise_tdd_gate.py` runs SSDF matrix verification as part of the release-blocking gate.

## Notes

1. This matrix is a traceability artifact for engineering governance and evidence management.
2. It is not a certification statement.
3. Practice statuses are intentionally conservative (`implemented_baseline`, `partial`, `planned`) and should be updated as controls evolve.
