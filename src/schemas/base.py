from __future__ import annotations

import uuid

from sqlalchemy import Integer, TIMESTAMP, DateTime, text
from sqlalchemy.sql import func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.dialects import postgresql
from datetime import datetime

class Base(DeclarativeBase):
  pass

class TimestampMixin:
  created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    server_default=func.now(),
    nullable=False
  )
  updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    server_default=func.now(),
    onupdate=func.now(),
    nullable=False
  )
  deleted_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    nullable=True
  )


class BaseSchema(TimestampMixin, Base):
  __abstract__ = True

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, unique=True)
  code: Mapped[uuid.UUID] = mapped_column(
    postgresql.UUID(as_uuid=True),
    unique=True,
    primary_key=True,
    server_default=text("gen_random_uuid()")
  )