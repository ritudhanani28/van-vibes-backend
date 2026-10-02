from sqlalchemy.orm import Session

from app.modules.settings.crud import SettingsCRUD
from app.modules.settings.models import CafeSettings
from app.modules.settings.schemas import CafeSettingsResponse, CafeSettingsUpdate


class SettingsService:
    @staticmethod
    def get_settings(db: Session) -> CafeSettings:
        return SettingsCRUD.get_or_create(db)

    @staticmethod
    def update_settings(db: Session, payload: CafeSettingsUpdate) -> CafeSettings:
        record = SettingsCRUD.get_or_create(db)
        return SettingsCRUD.update(db, record, payload)
