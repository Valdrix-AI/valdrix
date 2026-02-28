from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest

from app.shared.adapters.aws_pagination import iter_aws_paginator_pages


class _AsyncPaginator:
    def __init__(self, pages: list[dict[str, object]]) -> None:
        self._pages = pages

    def paginate(self, **_kwargs: object) -> AsyncIterator[dict[str, object]]:
        async def _iter() -> AsyncIterator[dict[str, object]]:
            for page in self._pages:
                yield page

        return _iter()


@pytest.mark.asyncio
async def test_iter_aws_paginator_pages_streams_all_pages_when_unbounded() -> None:
    paginator = _AsyncPaginator([{"idx": 1}, {"idx": 2}, {"idx": 3}])

    pages: list[dict[str, object]] = []
    async for page in iter_aws_paginator_pages(
        paginator,
        operation_name="s3.list_objects_v2",
        paginate_kwargs={"Bucket": "b", "Prefix": "p"},
    ):
        pages.append(page)

    assert pages == [{"idx": 1}, {"idx": 2}, {"idx": 3}]


@pytest.mark.asyncio
async def test_iter_aws_paginator_pages_enforces_max_pages_cap() -> None:
    paginator = _AsyncPaginator([{"idx": 1}, {"idx": 2}, {"idx": 3}])

    pages: list[dict[str, object]] = []
    with patch("app.shared.adapters.aws_pagination.logger.warning") as warning:
        async for page in iter_aws_paginator_pages(
            paginator,
            operation_name="resource-explorer-2.search",
            paginate_kwargs={"QueryString": "*"},
            max_pages=2,
        ):
            pages.append(page)

    assert pages == [{"idx": 1}, {"idx": 2}]
    warning.assert_called_once()


@pytest.mark.asyncio
async def test_iter_aws_paginator_pages_rejects_non_positive_cap() -> None:
    paginator = _AsyncPaginator([{"idx": 1}])
    with pytest.raises(ValueError, match="max_pages must be > 0"):
        async for _ in iter_aws_paginator_pages(
            paginator,
            operation_name="resource-explorer-2.search",
            paginate_kwargs={"QueryString": "*"},
            max_pages=0,
        ):
            pass
