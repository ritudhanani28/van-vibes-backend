from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.dependencies import require_admin
from app.db.session import get_db
from app.modules.accounts.models import User
from app.modules.settings.schemas import CafeSettingsResponse, CafeSettingsUpdate
from app.modules.settings.service import SettingsService


def get_cafe_settings_endpoint(db: Session = Depends(get_db)) -> CafeSettingsResponse:
    """Get cafe public details and tax rates."""
    record = SettingsService.get_settings(db)
    return CafeSettingsResponse.model_validate(record)


def update_cafe_settings_endpoint(
    payload: CafeSettingsUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> CafeSettingsResponse:
    """Update cafe configuration (Admin only)."""
    record = SettingsService.update_settings(db, payload)
    return CafeSettingsResponse.model_validate(record)
