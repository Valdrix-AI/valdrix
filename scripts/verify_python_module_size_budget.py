"""Guardrail for oversized Python modules in the application package."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


DEFAULT_MAX_LINES = 600

# Transitional exceptions while decomposition work is in progress.
# Budgets pin current module sizes so they cannot silently grow.
MODULE_LINE_BUDGET_OVERRIDES: dict[str, int] = {
    "app/models/enforcement.py": 778,
    "app/modules/enforcement/api/v1/enforcement.py": 668,
    "app/modules/enforcement/domain/gate_evaluation_ops.py": 620,
    "app/modules/enforcement/domain/service_runtime_ops.py": 610,
    "app/modules/governance/api/v1/health_dashboard.py": 694,
    "app/modules/governance/api/v1/scim.py": 742,
    "app/modules/governance/api/v1/settings/notifications.py": 870,
    "app/modules/governance/domain/jobs/handlers/acceptance.py": 741,
    "app/modules/governance/api/v1/audit_evidence.py": 1125,
    "app/modules/governance/domain/security/compliance_pack_bundle.py": 1000,
    "app/modules/reporting/api/v1/costs.py": 797,
    "app/modules/reporting/domain/aggregator.py": 630,
    "app/modules/reporting/domain/attribution_engine.py": 748,
    "app/modules/reporting/domain/persistence.py": 602,
    "app/modules/reporting/domain/reconciliation.py": 1125,
    "app/modules/reporting/domain/savings_proof.py": 720,
    "app/schemas/connections.py": 730,
    "app/shared/adapters/aws_cur.py": 791,
    "app/shared/adapters/hybrid.py": 872,
    "app/shared/adapters/platform.py": 961,
    "app/shared/connections/discovery.py": 883,
    "app/shared/core/config.py": 771,
    "app/shared/core/pricing.py": 804,
    "app/shared/db/session.py": 724,
    "app/shared/llm/analyzer.py": 998,
    "app/shared/llm/budget_fair_use.py": 844,
}


@dataclass(frozen=True)
class ModuleSizeViolation:
    path: str
    lines: int
    max_lines: int


def _line_count(path: Path) -> int:
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for _ in handle)


def collect_module_size_violations(
    root: Path,
    *,
    default_max_lines: int = DEFAULT_MAX_LINES,
    overrides: dict[str, int] | None = None,
) -> tuple[ModuleSizeViolation, ...]:
    normalized_overrides = overrides or MODULE_LINE_BUDGET_OVERRIDES
    app_root = root / "app"
    violations: list[ModuleSizeViolation] = []
    for module_path in sorted(app_root.rglob("*.py")):
        relative = module_path.relative_to(root).as_posix()
        max_lines = int(normalized_overrides.get(relative, default_max_lines))
        lines = _line_count(module_path)
        if lines > max_lines:
            violations.append(
                ModuleSizeViolation(path=relative, lines=lines, max_lines=max_lines)
            )
    return tuple(violations)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fail when Python modules exceed line-count budgets. "
            "Default budget applies to all app modules unless explicitly overridden."
        )
    )
    parser.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Repository root path.",
    )
    parser.add_argument(
        "--default-max-lines",
        type=int,
        default=DEFAULT_MAX_LINES,
        help="Default line budget for app Python modules.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    violations = collect_module_size_violations(
        root,
        default_max_lines=int(args.default_max_lines),
    )
    if not violations:
        print(
            "[python-module-size-budget] ok "
            f"root={root} default_max_lines={args.default_max_lines}"
        )
        return 0

    print(
        "[python-module-size-budget] "
        f"found {len(violations)} oversized module(s):"
    )
    for violation in violations:
        print(
            f" - {violation.path}: {violation.lines} lines "
            f"(budget={violation.max_lines})"
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
