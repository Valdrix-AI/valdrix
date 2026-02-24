from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Iterable

import structlog
from fastapi import HTTPException

logger = structlog.get_logger()


SUPPORTED_COMPLIANCE_PROVIDERS: frozenset[str] = frozenset(
    {"aws", "azure", "gcp", "hybrid", "license", "platform", "saas"}
)

_REFERENCE_DOC_PATHS: tuple[tuple[str, str], ...] = (
    ("scim_doc", "docs/integrations/scim.md"),
    ("idp_reference_doc", "docs/integrations/idp_reference_configs.md"),
    ("sso_doc", "docs/integrations/sso.md"),
    ("teams_doc", "docs/integrations/microsoft_teams.md"),
    ("compliance_pack_doc", "docs/compliance/compliance_pack.md"),
    ("focus_doc", "docs/compliance/focus_export.md"),
    ("acceptance_doc", "docs/ops/acceptance_evidence_capture.md"),
    ("close_runbook_doc", "docs/runbooks/month_end_close.md"),
    ("tenant_lifecycle_doc", "docs/runbooks/tenant_data_lifecycle.md"),
    ("partition_maintenance_doc", "docs/runbooks/partition_maintenance.md"),
    ("licensing_doc", "docs/licensing.md"),
    ("license_text", "LICENSE"),
    ("trademark_policy_doc", "TRADEMARK_POLICY.md"),
    ("commercial_license_doc", "COMMERCIAL_LICENSE.md"),
)


def _project_root() -> Path:
    """
    Best-effort project root discovery.

    Compliance pack exports should not depend on the current working directory,
    especially in containerized deployments.
    """
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return Path.cwd()


def _read_doc(*, root: Path, rel_path: str) -> str | None:
    try:
        return (root / rel_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        logger.warning("compliance_pack_doc_read_failed", path=rel_path, error=str(exc))
        return None


def load_reference_documents() -> tuple[dict[str, str | None], list[str]]:
    root = _project_root()
    docs: dict[str, str | None] = {}
    included_files: list[str] = []
    for key, rel_path in _REFERENCE_DOC_PATHS:
        content = _read_doc(root=root, rel_path=rel_path)
        docs[key] = content
        if content is not None:
            included_files.append(rel_path)
    return docs, included_files


def normalize_optional_provider(
    *,
    provider: str | None,
    provider_name: str,
    supported_providers: Iterable[str] = SUPPORTED_COMPLIANCE_PROVIDERS,
) -> str | None:
    if provider is None:
        return None
    candidate = provider.strip().lower()
    if not candidate:
        return None
    supported_values = set(str(item) for item in supported_providers)
    if candidate not in supported_values:
        supported = ", ".join(sorted(supported_values))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported {provider_name} '{provider}'. Use one of: {supported}",
        )
    return candidate


def resolve_window(
    *,
    start: date | None,
    end: date | None,
    default_start: date,
    default_end: date,
    error_detail: str,
) -> tuple[date, date]:
    resolved_start = start or default_start
    resolved_end = end or default_end
    if resolved_start > resolved_end:
        raise HTTPException(status_code=400, detail=error_detail)
    return resolved_start, resolved_end
