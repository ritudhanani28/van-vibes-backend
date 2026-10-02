from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    pass


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)  # slug e.g. "hot-coffee"
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    icon: Mapped[str] = mapped_column(String(50), nullable=True, default="🍽️")
    page: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    items: Mapped[List["MenuItem"]] = relationship(
        "MenuItem", back_populates="category_rel", cascade="all, delete-orphan"
    )


class MenuItem(Base):
    __tablename__ = "menu_items"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)  # e.g. "hc-01"
    category_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("categories.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_veg: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    image: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    popular: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    options: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSON, nullable=True)
    add_ons: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    category_rel: Mapped["Category"] = relationship("Category", back_populates="items")

    @property
    def category(self) -> str:
        return self.category_id

    @property
    def isVeg(self) -> bool:
        return self.is_veg

    @property
    def isAvailable(self) -> bool:
        return self.is_available

    @property
    def addOns(self) -> Optional[List[Dict[str, Any]]]:
        return self.add_ons
