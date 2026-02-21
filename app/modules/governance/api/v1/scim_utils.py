from __future__ import annotations

import re
from uuid import UUID


def normalize_scim_group(value: str) -> str:
    return str(value or "").strip().lower()


def parse_uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        return None


def parse_user_filter(filter_value: str) -> str | None:
    filter_value = (filter_value or "").strip()
    if not filter_value:
        return None
    m = re.match(r'(?i)^userName\s+eq\s+"([^"]+)"\s*$', filter_value)
    if m:
        return m.group(1).strip()
    m = re.match(r"(?i)^userName\s+eq\s+([^\s]+)\s*$", filter_value)
    if m:
        return m.group(1).strip().strip('"')
    return None


def parse_group_filter(filter_value: str) -> tuple[str, str] | None:
    filter_value = (filter_value or "").strip()
    if not filter_value:
        return None

    for attr in ("displayName", "externalId"):
        m = re.match(rf'(?i)^{attr}\s+eq\s+"([^"]+)"\s*$', filter_value)
        if m:
            return (attr, m.group(1).strip())
        m = re.match(rf"(?i)^{attr}\s+eq\s+([^\s]+)\s*$", filter_value)
        if m:
            return (attr, m.group(1).strip().strip('"'))
    return None


def parse_member_filter_from_path(path: str) -> UUID | None:
    path = (path or "").strip()
    m = re.match(r'(?i)^members\[value\s+eq\s+"([^"]+)"\]\s*$', path)
    if not m:
        return None
    return parse_uuid(m.group(1).strip())
