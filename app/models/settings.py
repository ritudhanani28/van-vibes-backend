from datetime import datetime, timezone
from sqlalchemy import DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class CafeSettings(Base):
    __tablename__ = "cafe_settings"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, default="van-vibes")
    name: Mapped[str] = mapped_column(String(255), default="Vaan Vibes Cafe & Restro", nullable=False)
    hindi_name: Mapped[str] = mapped_column(String(255), default="वन VIBES", nullable=False)
    tagline: Mapped[str] = mapped_column(String(255), default="Cafe & Restro • Taste the Vibe", nullable=False)
    address: Mapped[str] = mapped_column(
        String(500),
        default="Main Promenade, Serenita Arts Quarter, Surat, Gujarat - 395007",
        nullable=False,
    )
    phone: Mapped[str] = mapped_column(String(50), default="+91 98765 43210", nullable=False)
    gstin: Mapped[str] = mapped_column(String(50), default="24AAAAA0000A1Z5", nullable=False)
    tax_rate: Mapped[float] = mapped_column(Float, default=0.05, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="₹", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
