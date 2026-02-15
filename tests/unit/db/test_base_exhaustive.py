from unittest.mock import patch
from app.shared.db.base import get_partition_args


def test_get_partition_args_sqlite():
    """Verify empty dict for SQLite/Testing."""
    with patch.dict(
        "os.environ", {"DATABASE_URL": "sqlite:///test.db", "TEST_DATABASE_URL": ""}
    ):
        assert get_partition_args("daily") == {}


def test_get_partition_args_postgres():
    """Verify postgres args when not in SQLite."""
    with patch.dict(
        "os.environ", {"DATABASE_URL": "postgresql://h/d", "TEST_DATABASE_URL": ""}
    ):
        assert get_partition_args("daily") == {"postgresql_partition_by": "daily"}
