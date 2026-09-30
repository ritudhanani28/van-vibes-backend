from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import require_admin
from app.db.session import get_db
from app.models.settings import CafeSettings
from app.models.user import User
from app.schemas.settings import CafeSettingsResponse, CafeSettingsUpdate

router = APIRouter(prefix="/settings", tags=["Cafe Settings"])


@router.get("", response_model=CafeSettingsResponse)
def get_cafe_settings(db: Session = Depends(get_db)):
    """Get cafe public details and tax rates."""
    record = db.query(CafeSettings).first()
    if not record:
        record = CafeSettings(id="van-vibes")
        db.add(record)
        db.commit()
        db.refresh(record)
    return CafeSettingsResponse.model_validate(record)


@router.put("", response_model=CafeSettingsResponse)
def update_cafe_settings(
    payload: CafeSettingsUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Update cafe configuration (Admin only)."""
    record = db.query(CafeSettings).first()
    if not record:
        record = CafeSettings(id="van-vibes")
        db.add(record)

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

    db.commit()
    db.refresh(record)
    return CafeSettingsResponse.model_validate(record)
