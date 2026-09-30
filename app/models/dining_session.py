import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.billing import BillingInvoice
    from app.models.order import Order
    from app.models.table import Table


class SessionStatus(str, Enum):
    OPEN = "OPEN"
    BILL_GENERATED = "BILL_GENERATED"
    CLOSED = "CLOSED"


class DiningSession(Base):
    __tablename__ = "dining_sessions"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)  # e.g. "DS-1001"
    table_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("tables.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    table_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default=SessionStatus.OPEN.value, server_default="OPEN", nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    table: Mapped["Table"] = relationship("Table", foreign_keys=[table_id])
    orders: Mapped[List["Order"]] = relationship(
        "Order", back_populates="dining_session", cascade="all, delete-orphan", order_by="Order.created_at"
    )
    invoices: Mapped[List["BillingInvoice"]] = relationship(
        "BillingInvoice", back_populates="dining_session", order_by="BillingInvoice.created_at"
    )
