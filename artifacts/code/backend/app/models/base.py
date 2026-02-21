"""SQLAlchemy declarative base and common mixins."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import event, func, inspect as sa_inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


@event.listens_for(Base, "init", propagate=True)
def _apply_column_defaults(target: object, args: tuple, kwargs: dict) -> None:
    """Apply mapped_column(default=...) values at Python object init time.

    SQLAlchemy 2.0's mapped_column(default=X) only applies the default at
    INSERT time (DB-level), not when constructing a Python object without a
    session.  This listener fills in scalar and callable defaults immediately
    so that unit tests can assert on freshly constructed model instances
    without touching the database.
    """
    mapper = sa_inspect(type(target), raiseerr=False)
    if mapper is None:
        return
    for col_attr in mapper.column_attrs:
        col = col_attr.columns[0]
        attr_name = col_attr.key
        if attr_name in kwargs or col.default is None:
            continue
        default = col.default
        if default.is_scalar:
            kwargs[attr_name] = default.arg
        elif default.is_callable:
            # callable defaults receive a context argument; pass None for
            # Python-level initialisation (no execution context available)
            try:
                kwargs[attr_name] = default.arg(None)
            except Exception:
                pass


class TimestampMixin:
    """Mixin that adds created_at and updated_at timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        default=func.now(),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
    )
