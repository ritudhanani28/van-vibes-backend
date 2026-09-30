import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.billing import BillingInvoice
    from app.models.dining_session import DiningSession


class OrderStatus(str, Enum):
    PLACED = "PLACED"
    ACCEPTED = "ACCEPTED"
    IN_KITCHEN = "IN_KITCHEN"
    SERVED = "SERVED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


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
    
    # PLACED, ACCEPTED, SERVED, COMPLETED
    status: Mapped[str] = mapped_column(String(50), default=OrderStatus.PLACED.value, server_default="PLACED", nullable=False, index=True)
    
    # PENDING, PAID, REFUNDED
    payment_status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False, index=True)
    
    subtotal: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    tax: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)  # 5% GST
    discount_percentage: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", nullable=False)
    discount_amount: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", nullable=False)
    extra_charge: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", nullable=False)
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

    items: Mapped[List["OrderItem"]] = relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan", order_by="OrderItem.created_at"
    )
    invoice: Mapped[Optional["BillingInvoice"]] = relationship(
        "BillingInvoice", back_populates="order", uselist=False, cascade="all, delete-orphan"
    )
    dining_session: Mapped[Optional["DiningSession"]] = relationship(
        "DiningSession", back_populates="orders"
    )


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
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)  # Historical freeze
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    item_total: Mapped[float] = mapped_column(Float, nullable=False)
    selected_options: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    selected_add_ons: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    special_instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    order: Mapped["Order"] = relationship("Order", back_populates="items")
