# Logic & Performance Audit

**Date:** 2026-02-15  
**Scope:** Logic correctness, null/type handling, N+1 and blocking patterns, performance hotspots.

---

## 1. Completed in This Pass

### 1.1 Formatting
- **Ruff format:** Applied to `app`, `tests`, `scripts` (675 files reformatted). Style is now consistent.

### 1.2 Type fixes (mypy)
- **app/main.py:** CsrfSettings `secret_key` default (`or ""`), `app` redef `# type: ignore[no-redef]`, redundant casts removed.
- **app/modules/governance/api/v1/audit.py:** `cast(UUID, user.tenant_id)` for export/Focus/SavingsProof/close_package/AuditLogger; loop variables renamed (`factor_set_row`, `factor_update_row`, `focus_row`) so mypy infers correct types; `realized_stmt` and `realized_csv_writer` to avoid variable reuse; `close_service` for CostReconciliationService.
- **app/modules/governance/api/v1/settings/identity.py:** `cast(UUID, current_user.tenant_id)` for AuditLogger in update and rotate-scim-token.
- **app/modules/optimization:** `raw_type is not None and hasattr(raw_type, "value")` and `scheduled_execution_at is not None` / `focus_row_dict` for focus export row.

### 1.3 Logic / null safety
- **Optimization service/strategies/zombies:** Guarded `.value` and `.isoformat()` on possibly-None values so logic is correct and mypy is satisfied.

---

## 2. Logic & Type Issues (Remaining or Follow-up)

### 2.1 Mypy (other modules)
- **app/modules/reporting/domain/savings_proof.py:** Assignment/return type mismatch (`SavingsProofDrilldownResponse` vs `SavingsProofResponse`), `.buckets`/`.truncated` on wrong type.
- **app/modules/reporting/domain/carbon_factors.py:** Returning `Any` from function declared to return `CarbonFactorSet | None`.
- **app/modules/reporting/domain/focus_export.py:** `Result` vs `AsyncResult`, missing `await`, `type[Base]` has no `id`/`vendor`.
- **app/modules/reporting/domain/persistence.py:** Incompatible assignment (str vs KeyedColumnElement).
- **app/shared/core/auth.py:** JWT key argument `str | None` where key is required (validator ensures set in prod; consider assert or cast at use site).
- **app/modules/governance/api/v1/scim.py:** `ScimGroup | None` assigned to variable typed as `ScimGroup`.
- **app/modules/reporting/api/v1/costs.py:** `Row` type mismatch in provider breakdown assignment.
- **app/modules/optimization/domain/strategies/baseline_commitment.py:** `float(Any | None)` argument type.

These are type-correctness and null-safety follow-ups; fixing them will reduce runtime risk and improve maintainability.

### 2.2 Logic / conditions
- **Tenant_id in protected routes:** Several handlers use `user.tenant_id` or `current_user.tenant_id` where the type is `UUID | None`. Dependency layers (e.g. `requires_feature`, `require_tenant_access`) effectively guarantee tenant_id for those routes. Using `cast(UUID, user.tenant_id)` at the call site is a pragmatic fix; a stricter approach is to have a dependency that returns a type with `tenant_id: UUID` (non-optional) for tenant-scoped routes.

---

## 3. Performance

### 3.1 N+1 and per-item DB work
- **app/modules/reporting/domain/attribution_engine.py — `apply_rules_to_tenant`:**
  - For each cost record: `await self.db.execute(delete(CostAllocation)...)` then `await self.apply_rules(record, rules)` then `self.db.add(allocation)` for each allocation.
  - **Risk:** Many round-trips when `records` is large.
  - **Recommendation:** Batch deletes (e.g. one delete per record batch or a single bulk delete with `in_`), and/or batch inserts of allocations (e.g. `add_all` + periodic flush/commit) instead of per-record commit.

### 3.2 Loops over connections/tenants
- **app/modules/reporting/domain/service.py — `ingest_costs_for_tenant`:** Loop over `connections` with per-connection adapter work and `persistence.save_records_stream`. This is sequential per connection; acceptable if connection count is small. Consider capping parallelism (e.g. semaphore) if connection count grows.
- **app/modules/governance/domain/jobs/handlers/finops.py:** Loop over `connections` with adapter and LLM calls. Per-connection work is expected; ensure timeouts and limits are in place (already noted in .cursorrules for scan endpoints).
- **app/modules/optimization/domain/service.py — `scan_for_tenant`:** Loop over AWS/Azure/GCP models with `_scoped_query` and `db.execute`. Three queries total (one per provider); not N+1.

### 3.3 Large result sets
- **app/modules/reporting/domain/aggregator.py:** `MAX_AGGREGATION_ROWS`, `MAX_DETAIL_ROWS`, `STATEMENT_TIMEOUT_MS` and truncation logging are in place. Good.
- **app/modules/governance/api/v1/audit.py — compliance pack:** Audit log export limited to 10000; focus/savings/realized/close use windows and limits. Reasonable.

### 3.4 Blocking in async
- No `time.sleep` or synchronous HTTP/DB in async paths found; `asyncio.sleep` and async DB are used. Good.

---

## 4. Summary

| Area | Status |
|------|--------|
| **Ruff format** | Done (675 files). |
| **Mypy (main, audit, identity, optimization, zombies)** | Fixed (tenant_id casts, loop variable names, close_service, realized_stmt, realized_csv_writer, main app redef). |
| **Mypy (savings_proof, focus_export, carbon_factors, auth, scim, costs, persistence, baseline_commitment)** | Remaining; see §2.1. |
| **Logic / nulls** | Addressed in optimization and audit loop variables; remaining in other modules as above. |
| **N+1** | One clear case: attribution `apply_rules_to_tenant`; recommendation: batch deletes/inserts. |
| **Blocking in async** | None found. |
| **Large result sets** | Aggregator and audit export already use limits and timeouts. |

---

## 5. Recommended Next Steps

1. **Mypy:** Fix remaining errors in savings_proof, focus_export, carbon_factors, auth, scim, costs, persistence, baseline_commitment (and run `uv run mypy app` in CI).
2. **Attribution N+1:** Refactor `apply_rules_to_tenant` to batch deletes and batch-add allocations with periodic flush/commit.
3. **Optional:** Introduce a tenant-scoped user type (e.g. `TenantUser` with `tenant_id: UUID`) so routes that require tenant context don’t rely on `cast(UUID, user.tenant_id)`.

This audit was produced after applying ruff format, targeted mypy fixes, and a pass over logic and performance patterns.
