import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.modules.sessions.models import BillingInvoice, DiningSession


class OrderStatus(str, Enum):
    PLACED = "PLACED"
    ACCEPTED = "ACCEPTED"
    IN_KITCHEN = "IN_KITCHEN"
    SERVED = "SERVED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    mobile: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    special_instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    last_visited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)  # "VV-1001"
    cafe_id: Mapped[str] = mapped_column(String(100), default="van-vibes", nullable=False)
    table_id: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("tables.id", ondelete="SET NULL"), nullable=True, index=True
    )
    table_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    dining_session_id: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("dining_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    session_token: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_mobile: Mapped[str] = mapped_column(String(20), nullable=False)
    special_instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(50), default=OrderStatus.PLACED.value, server_default="PLACED", nullable=False, index=True
    )
    payment_status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False, index=True)

    subtotal: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    tax: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    discount_percentage: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", nullable=False)
    discount_amount: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", nullable=False)
    extra_charge: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", nullable=False)
    round_off: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", nullable=False)
    total: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    cancellation_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cancellation_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cancelled_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[List["OrderItem"]] = relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan", order_by="OrderItem.created_at"
    )
    invoice: Mapped[Optional["BillingInvoice"]] = relationship(
        "BillingInvoice", back_populates="order", uselist=False, cascade="all, delete-orphan"
    )
    dining_session: Mapped[Optional["DiningSession"]] = relationship(
        "DiningSession", back_populates="orders"
    )

    @property
    def session_status(self) -> Optional[str]:
        if self.dining_session:
            return self.dining_session.status
        return None

    @property
    def bill_generated(self) -> bool:
        if self.dining_session and self.dining_session.status in ["BILL_GENERATED", "CLOSED"]:
            return True
        if self.dining_session and getattr(self.dining_session, "invoices", None):
            return any(getattr(inv, "bill_type", None) == "SESSION" for inv in self.dining_session.invoices)
        return False

    @property
    def activity_status(self) -> str:
        """
        Determines whether the order lifecycle is 'ACTIVE' or 'INACTIVE'.
        An order is INACTIVE if and only if:
          order_completed = True (status == COMPLETED)
          AND bill_generated = True
          AND payment_status = 'PAID'.
        Otherwise, it is ACTIVE.
        """
        st = (self.status or "").upper()
        if st == OrderStatus.CANCELLED.value:
            return "INACTIVE"
        is_completed = st == OrderStatus.COMPLETED.value
        is_bill_gen = self.bill_generated
        is_paid = (self.payment_status or "").upper() == "PAID"
        if is_completed and is_bill_gen and is_paid:
            return "INACTIVE"
        return "ACTIVE"

    @property
    def is_active(self) -> bool:
        return self.activity_status == "ACTIVE" 


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    order_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("orders.id", ondelete="CASCADE"), index=True, nullable=False
    )
    menu_item_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    item_total: Mapped[float] = mapped_column(Float, nullable=False)
    selected_options: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    selected_add_ons: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    special_instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    order: Mapped["Order"] = relationship("Order", back_populates="items")
