from typing import Optional
from sqlalchemy import Text
from datetime import datetime, timezone
from sqlalchemy import DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.session import Base


class CafeSettings(Base):
    __tablename__ = "cafe_settings"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, default=settings.CAFE_ID)
    name: Mapped[str] = mapped_column(String(255), default=lambda: settings.CAFE_NAME, nullable=False)
    hindi_name: Mapped[str] = mapped_column(String(255), default=lambda: settings.CAFE_HINDI_NAME, nullable=False)
    tagline: Mapped[str] = mapped_column(String(255), default=lambda: settings.CAFE_TAGLINE, nullable=False)
    address: Mapped[str] = mapped_column(
        String(500),
        default=lambda: settings.CAFE_ADDRESS,
        nullable=False,
    )
    phone: Mapped[str] = mapped_column(String(50), default=lambda: settings.CAFE_PHONE, nullable=False)
    gstin: Mapped[str] = mapped_column(String(50), default=lambda: settings.CAFE_GSTIN, nullable=False)
    tax_rate: Mapped[float] = mapped_column(Float, default=lambda: settings.CAFE_TAX_RATE, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default=lambda: settings.CAFE_CURRENCY, nullable=False)
    upi_id: Mapped[Optional[str]] = mapped_column(String(100), default="9773291261@okbizaxis", nullable=True)
    upi_payee_name: Mapped[Optional[str]] = mapped_column(String(255), default="OM DIYORA", nullable=True)
    payment_qr_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
