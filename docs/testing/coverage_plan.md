# Coverage Plan: Optimization, Reporting, and LLM Orchestration

Last updated: February 12, 2026

## Scope

This plan defines the modules covered by the focused CI coverage gate:

- Optimization scope: `app/modules/optimization/*`
- Reporting scope: `app/modules/reporting/*`
- LLM orchestration scope: `app/shared/llm/hybrid_scheduler.py`

## Focused Test Suites

- Optimization tests: `tests/unit/optimization`
- Reporting tests: `tests/unit/modules/reporting`
- LLM scheduler tests: `tests/unit/llm/test_hybrid_scheduler.py`

## Required Scenarios

The focused suites must include both happy-path and failure-path coverage:

1. Missing CUR data path:
- Reporting ingestion must safely handle empty upstream data without crashing.

2. Invalid tenant configuration path:
- Optimization/reporting path must fail safely with clear error propagation and no cross-tenant leakage.

3. LLM provider timeout/failure path:
- Hybrid scheduler must be tested against provider timeout/failure using mocked provider/analyzer calls.

## CI Gate

CI enforces minimum coverage floors:

- Optimization: 85%
- Reporting: 85%
- LLM scheduler (`hybrid_scheduler.py`): 90%

If any threshold is not met, CI fails.
