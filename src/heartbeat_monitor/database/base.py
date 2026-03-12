import re
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


class PureBase(DeclarativeBase):
    pass


class Base(PureBase):
    __abstract__ = True

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=None,
        onupdate=func.now(),
        nullable=True,
    )

    @declared_attr.directive
    def __tablename__(self) -> str:
        name = re.sub(r"(?<!^)(?=[A-Z])", "_", self.__name__).lower()
        if not name.endswith("s"):
            name += "s"
        return name
