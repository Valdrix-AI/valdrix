from datetime import datetime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import MetaData, func
from sqlalchemy.types import TIMESTAMP

# Recommended naming convention for constraints (required for Alembic with SQLite/Postgres)
class Base(DeclarativeBase):
    pass
