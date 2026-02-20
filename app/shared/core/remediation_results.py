import re
from dataclasses import dataclass
from typing import Any

_FAILED_ERROR_PATTERN = re.compile(
    r"^\[(?P<code>[^\]]+)\]\s*(?P<message>.*)\s+\(Status:\s*(?P<status>\d+)\)\s*$"
)


@dataclass(frozen=True)
class RemediationFailure:
    reason: str
    message: str
    status_code: int | None = None


def normalize_remediation_status(status_obj: Any) -> str:
    return status_obj.value if hasattr(status_obj, "value") else str(status_obj or "")


def parse_remediation_execution_error(
    execution_error: str | None,
    *,
    default_reason: str = "remediation_execution_failed",
    default_message: str = "Remediation execution failed.",
) -> RemediationFailure:
    raw_error = (execution_error or "").strip()
    if not raw_error:
        return RemediationFailure(
            reason=default_reason,
            message=default_message,
            status_code=None,
        )

    match = _FAILED_ERROR_PATTERN.match(raw_error)
    if match:
        return RemediationFailure(
            reason=match.group("code"),
            message=match.group("message"),
            status_code=int(match.group("status")),
        )

    return RemediationFailure(
        reason=default_reason,
        message=raw_error,
        status_code=None,
    )
