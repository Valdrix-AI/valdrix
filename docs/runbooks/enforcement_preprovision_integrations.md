# Enforcement Pre-Provision Integration Runbook

This runbook defines the production integration contract for:

1. Terraform/CI preflight gate with approval continuation.
2. Kubernetes AdmissionReview webhook integration and failure-policy alignment.

## 1) Terraform preflight and continuation contract

### 1.1 Preflight request

Call:

- `POST /api/v1/enforcement/gate/terraform/preflight`

Persist the following values from the response for retries and continuation:

- `decision_id`
- `request_fingerprint`
- `approval_required`
- `approval_request_id` (when present)
- `continuation.approval_consume_endpoint`
- `continuation.binding` fields:
  - `expected_source`
  - `expected_project_id`
  - `expected_environment`
  - `expected_request_fingerprint`
  - `expected_resource_reference`

Retry contract:

- Reuse the same `idempotency_key` for retry of the same planned change.
- Send `expected_request_fingerprint` on retry; the API rejects mismatched payload replays with `409`.

### 1.2 Approval path

When preflight returns `REQUIRE_APPROVAL`:

1. Obtain approval through:
   - `POST /api/v1/enforcement/approvals/{approval_id}/approve`
2. Collect `approval_token` from the approval response.
3. Continue pipeline only after token consume succeeds.

### 1.3 Token consume request

Call:

- `POST /api/v1/enforcement/approvals/consume`

Provide:

- `approval_token`
- `expected_source`
- `expected_project_id`
- `expected_environment`
- `expected_request_fingerprint`
- `expected_resource_reference`

This enforces one-time token use plus request binding.

### 1.4 Claims and binding checks

The consume path validates token claims and request binding against persisted decision state:

- `tenant_id`
- `project_id`
- `decision_id`
- `approval_id`
- `source`
- `environment`
- `request_fingerprint`
- `resource_reference`
- `max_monthly_delta_usd`
- `max_hourly_delta_usd`
- `exp` / `nbf` / `iat`
- `iss` / `aud`

If any binding check fails, consume returns `401` or `409` and pipeline must stop.

## 2) Kubernetes AdmissionReview and failure policy alignment

Endpoint:

- `POST /api/v1/enforcement/gate/k8s/admission/review`

Payload/response contract uses native AdmissionReview (`admission.k8s.io/v1`).

### 2.1 Failure policy alignment

`failurePolicy` is configured in Kubernetes `ValidatingWebhookConfiguration` (cluster config), not in the API route.

Recommended alignment with enforcement rollout mode:

- `shadow` or early `soft` rollout: `failurePolicy: Ignore` (fail-open on webhook unavailability).
- mature `hard` rollout with proven SLO + HA: `failurePolicy: Fail` (fail-closed).

### 2.2 Webhook baseline example

```yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingWebhookConfiguration
metadata:
  name: valdrix-enforcement-gate
webhooks:
  - name: gate.enforcement.valdrix.io
    failurePolicy: Ignore
    timeoutSeconds: 2
    sideEffects: None
    admissionReviewVersions: ["v1"]
    rules:
      - apiGroups: ["*"]
        apiVersions: ["*"]
        operations: ["CREATE", "UPDATE"]
        resources: ["*/*"]
    clientConfig:
      service:
        namespace: valdrix
        name: valdrix-api
        path: /api/v1/enforcement/gate/k8s/admission/review
```

Change `failurePolicy` only with explicit release sign-off and incident rollback plan.

### 2.3 Helm deployment profile (recommended)

Use chart values to make rollout intent explicit:

```yaml
enforcementWebhook:
  enabled: true
  failurePolicy: Ignore   # soft rollout profile
  timeoutSeconds: 2
  service:
    namespace: valdrix
    name: valdrix-api
    port: 80
  path: /api/v1/enforcement/gate/k8s/admission/review
```

For hard rollout, change only:

```yaml
enforcementWebhook:
  failurePolicy: Fail
  podDisruptionBudget:
    enabled: true
    maxUnavailable: 1
deploymentStrategy:
  type: RollingUpdate
  rollingUpdate:
    maxUnavailable: 0
    maxSurge: 1
```

Guardrails enforced by chart contract:
1. `failurePolicy: Fail` requires `timeoutSeconds <= 5`.
2. `failurePolicy: Fail` requires API HA:
   - either `autoscaling.enabled=true` with `autoscaling.minReplicas >= 2`,
   - or `autoscaling.enabled=false` with `replicaCount >= 2`.
3. `failurePolicy: Fail` requires `podDisruptionBudget.enabled=true`.
4. `failurePolicy: Fail` requires `podDisruptionBudget.maxUnavailable <= 1`.
5. `certManager.enabled=true` requires non-empty `certManager.injectorSecretName`.
6. Do not set `caBundle` when `certManager.enabled=true` (single CA source only).
7. Default `namespaceSelector` excludes `kube-system`, `kube-public`, `kube-node-lease`.
8. `admissionReviewVersions` must include `v1`.
9. `failurePolicy: Fail` requires `deploymentStrategy.type=RollingUpdate`.
10. `failurePolicy: Fail` requires `deploymentStrategy.rollingUpdate.maxUnavailable=0`.
11. `failurePolicy: Fail` requires `deploymentStrategy.rollingUpdate.maxSurge>=1`.
12. `failurePolicy: Fail` requires hard pod anti-affinity across nodes (`topologyKey=kubernetes.io/hostname`).

## 3) Operator checklist

1. Store and reuse idempotency keys/fingerprints for Terraform retries.
2. Treat approval consume failure as a hard stop; never bypass with stale token.
3. Keep webhook timeout low (`<= 2s`) and run API behind HA before using `failurePolicy: Fail`.
4. Monitor gate failure reason distribution; distinguish policy denies from infrastructure reasons (`gate_lock_timeout`, `gate_timeout`, `gate_evaluation_error`).
5. Monitor gate lock contention events (`valdrix_ops_enforcement_gate_lock_events_total`) and alert on sustained `contended`/`timeout` spikes.
6. For audit exports, verify `policy_lineage_sha256` and `policy_lineage` are present so each decision can be tied to its decision-time policy hash.
7. For computed decision determinism audits, verify `computed_context_lineage_sha256` and `computed_context_lineage` are present in export parity/archive artifacts.

## 4) Benchmark profile reference

For standards-aligned deployment profiles tied to benchmark hardening closure (`BENCH-DOC-001`), use:

1. `docs/ops/benchmark_alignment_profiles_2026-02-27.md`
