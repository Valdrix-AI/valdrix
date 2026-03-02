# Benchmark Alignment Profiles (2026-02-27)

This document closes `BENCH-DOC-001` by publishing concrete operational profiles for the three benchmark rows that were previously tracked as documentation hardening.

## Scope

Profiles covered:

1. Kubernetes webhook production guidance profile.
2. CEL portability profile for enforcement policy-as-code.
3. Terraform ordering profile for preflight decision stages.

## 1) Kubernetes Webhook Production Guidance Profile

Primary source:

1. Kubernetes admission webhook good practices:
   - https://kubernetes.io/docs/concepts/cluster-administration/admission-webhooks-good-practices/

Runtime/Helm contract in repository:

1. `helm/valdrics/templates/enforcement-validating-webhook.yaml`
2. `helm/valdrics/templates/enforcement-webhook-pdb.yaml`
3. `helm/valdrics/values.schema.json`
4. `docs/runbooks/enforcement_preprovision_integrations.md`

Production profile requirements:

1. `failurePolicy: Fail` only when API HA is configured (replicas or HPA min replicas >= 2).
2. `timeoutSeconds <= 5` for fail-closed mode.
3. PDB must be enabled with `maxUnavailable <= 1`.
4. Rolling update strategy must enforce `maxUnavailable=0`, `maxSurge>=1`.
5. Hard pod anti-affinity across nodes must be enabled.
6. AdmissionReview contract must stay on `admission.k8s.io/v1`.
7. Namespace/request filtering must be enabled to avoid system-namespace lockouts.

Validation evidence:

1. `uv run pytest --no-cov -q tests/unit/ops/test_enforcement_webhook_helm_contract.py`
2. `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_api.py -k "admission_review"`

## 2) CEL Portability Profile

Primary sources:

1. ValidatingAdmissionPolicy (CEL): https://kubernetes.io/docs/reference/access-authn-authz/validating-admission-policy/
2. MutatingAdmissionPolicy (CEL): https://kubernetes.io/docs/reference/access-authn-authz/mutating-admission-policy/

Current engine baseline:

1. Internal formal policy document schema:
   - `app/modules/enforcement/domain/policy_document.py`
2. API schema integration:
   - `app/modules/enforcement/api/v1/schemas.py`

CEL portability profile (required constraints):

1. Keep policy semantics deterministic and side-effect free.
2. Restrict comparisons to scalar values and bounded lists (`environments`, `action_prefixes`, `risk_levels`, roles).
3. Keep numeric thresholds explicit and non-negative (`*_monthly_delta_usd`, ceiling fields).
4. Preserve stable canonicalization + digest (`policy_document_sha256`) for parity across internal and CEL-rendered representations.
5. Disallow dynamic code execution and non-deterministic sources inside policy evaluation contract.

Portability mapping baseline:

1. `mode_matrix` -> source/environment mode selectors.
2. `approval.routing_rules` -> predicate clauses (`env`, `action prefix`, `risk`, threshold bounds).
3. `entitlements` -> threshold predicates and short-circuit deny/approval constraints.
4. `execution` -> bounded operational policy parameters (TTL/retry/lease).

Validation evidence:

1. `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_service_helpers.py -k "policy_document"`

## 3) Terraform Ordering Profile

Primary sources:

1. Run tasks integration contract:
   - https://developer.hashicorp.com/terraform/enterprise/api-docs/run-tasks/run-tasks-integration
2. Policy enforcement ordering/results:
   - https://developer.hashicorp.com/terraform/cloud-docs/policy-enforcement/view-results

Runtime contract in repository:

1. Endpoint:
   - `POST /api/v1/enforcement/gate/terraform/preflight`
2. Schemas:
   - `TerraformPreflightRequest`, `TerraformPreflightResponse`
   - `TerraformPreflightContinuation.binding`
3. Implementation:
   - `app/modules/enforcement/api/v1/enforcement.py`

Ordering profile requirements:

1. Pre-plan/pre-apply stage must call preflight gate before apply continuation.
2. Retries for the same planned change must reuse `idempotency_key`.
3. Retries must include `expected_request_fingerprint`; mismatches must fail (`409`).
4. Approval-required decisions must enforce consume binding before continuation:
   - source/project/environment/fingerprint/resource_reference.
5. Gate outcome must remain deterministic for stable payload + snapshot context.

Validation evidence:

1. `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_api.py -k "terraform_preflight"`
2. `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_endpoint_wrapper_coverage.py::test_enforcement_endpoint_wrappers_cover_preflight_and_k8s_review_branches`

## Closure Statement

`BENCH-DOC-001` is now documentation-complete for benchmark alignment profiles. Remaining non-documentary work stays tracked under commercial and financial backlogs (`PKG-*`, `FIN-*`), not benchmark profile documentation.
