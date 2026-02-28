from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import structlog

logger = structlog.get_logger()


async def iter_aws_paginator_pages(
    paginator: Any,
    *,
    operation_name: str,
    paginate_kwargs: dict[str, Any],
    max_pages: int | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Stream AWS paginator pages with optional deterministic page bounds.

    `max_pages` provides a hard stop for protection against unbounded scans in
    misconfigured accounts while preserving native paginator semantics.
    """
    if max_pages is not None and max_pages <= 0:
        raise ValueError("max_pages must be > 0 when provided")

    pages_seen = 0
    async for page in paginator.paginate(**paginate_kwargs):
        pages_seen += 1
        yield page
        if max_pages is not None and pages_seen >= max_pages:
            logger.warning(
                "aws_paginator_page_cap_reached",
                operation=operation_name,
                max_pages=max_pages,
            )
            break
