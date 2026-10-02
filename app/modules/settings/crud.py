from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session

from app.modules.settings.models import CafeSettings
from app.modules.settings.schemas import CafeSettingsUpdate


class SettingsCRUD:
    @staticmethod
    def get(db: Session) -> Optional[CafeSettings]:
        return db.query(CafeSettings).first()

    @staticmethod
    def get_or_create(db: Session) -> CafeSettings:
        record = db.query(CafeSettings).first()
        if not record:
            record = CafeSettings(id="van-vibes")
            db.add(record)
            db.commit()
            db.refresh(record)
        return record

    @staticmethod
    def update(db: Session, record: CafeSettings, payload: CafeSettingsUpdate) -> CafeSettings:
        if payload.name is not None:
            record.name = payload.name
        if payload.hindi_name is not None:
            record.hindi_name = payload.hindi_name
        if payload.tagline is not None:
            record.tagline = payload.tagline
        if payload.address is not None:
            record.address = payload.address
        if payload.phone is not None:
            record.phone = payload.phone
        if payload.gstin is not None:
            record.gstin = payload.gstin
        if payload.tax_rate is not None:
            record.tax_rate = payload.tax_rate

        record.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(record)
        return record
