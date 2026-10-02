from datetime import datetime, timezone
from typing import TYPE_CHECKING, List
from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.modules.sessions.models import DiningSession


class Table(Base):
    __tablename__ = "tables"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)  # e.g. "T01"
    table_number: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # "Table 01"
    token: Mapped[str] = mapped_column(String(255), nullable=False)  # HMAC token
    capacity: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="AVAILABLE", nullable=False
    )  # AVAILABLE, OCCUPIED, RESERVED
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    sessions: Mapped[List["DiningSession"]] = relationship(
        "DiningSession", back_populates="table", order_by="DiningSession.created_at.desc()"
    )
