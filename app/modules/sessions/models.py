import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.modules.orders.models import Order
    from app.modules.tables.models import Table


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


class BillingInvoice(Base):
    __tablename__ = "billing_invoices"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    order_id: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("orders.id", ondelete="CASCADE"), unique=True, index=True, nullable=True
    )
    dining_session_id: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("dining_sessions.id", ondelete="SET NULL"), index=True, nullable=True
    )
    bill_type: Mapped[str] = mapped_column(
        String(50), default="SESSION", server_default="SESSION", nullable=False
    )
    invoice_number: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    subtotal: Mapped[float] = mapped_column(Float, nullable=False)
    cgst_rate: Mapped[float] = mapped_column(Float, default=0.025, nullable=False)
    cgst_amount: Mapped[float] = mapped_column(Float, nullable=False)
    sgst_rate: Mapped[float] = mapped_column(Float, default=0.025, nullable=False)
    sgst_amount: Mapped[float] = mapped_column(Float, nullable=False)
    tax_amount: Mapped[float] = mapped_column(Float, nullable=False)
    discount_percentage: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", nullable=False)
    discount_amount: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", nullable=False)
    extra_charge: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", nullable=False)
    round_off: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", nullable=False)
    total: Mapped[float] = mapped_column(Float, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(50), default="CASH", nullable=False)
    payment_status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False)
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    order: Mapped[Optional["Order"]] = relationship("Order", back_populates="invoice")
    dining_session: Mapped[Optional["DiningSession"]] = relationship("DiningSession", back_populates="invoices")
