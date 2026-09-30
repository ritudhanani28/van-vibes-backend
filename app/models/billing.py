import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional
from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.dining_session import DiningSession
    from app.models.order import Order


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
    cgst_rate: Mapped[float] = mapped_column(Float, default=0.025, nullable=False)  # 2.5%
    cgst_amount: Mapped[float] = mapped_column(Float, nullable=False)
    sgst_rate: Mapped[float] = mapped_column(Float, default=0.025, nullable=False)  # 2.5%
    sgst_amount: Mapped[float] = mapped_column(Float, nullable=False)
    tax_amount: Mapped[float] = mapped_column(Float, nullable=False)  # 5% total
    discount_percentage: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", nullable=False)
    discount_amount: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", nullable=False)
    total: Mapped[float] = mapped_column(Float, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(50), default="CASH", nullable=False)  # CASH, UPI, CARD
    payment_status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False)  # PENDING, PAID
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    order: Mapped[Optional["Order"]] = relationship("Order", back_populates="invoice")
    dining_session: Mapped[Optional["DiningSession"]] = relationship("DiningSession", back_populates="invoices")
