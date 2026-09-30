import base64
import io
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Response, status
import qrcode
from qrcode.image.pil import PilImage
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import require_chef_or_admin
from app.db.session import get_db
from app.models.table import Table
from app.models.user import User
from app.models.dining_session import DiningSession, SessionStatus
from app.schemas.dining_session import DiningSessionResponse
from app.schemas.table import (
    StandeeResponse,
    TableResponse,
    TableStatusUpdate,
    ValidateQRRequest,
    ValidateQRResponse,
)
from app.services.session_service import SessionService
from app.websocket.manager import ws_manager

router = APIRouter(prefix="/tables", tags=["Tables"])


def _format_table(t: Table, active_session: Optional[DiningSessionResponse] = None) -> TableResponse:
    scan_url = f"{settings.CUSTOMER_FRONTEND_URL}/cafe/van-vibes/menu?table={t.id}&token={t.token}"
    return TableResponse(
        id=t.id,
        table_number=t.table_number,
        name=t.name,
        token=t.token,
        capacity=t.capacity,
        status=t.status,
        is_active=t.is_active,
        qr_code_url=scan_url,
        active_session=active_session,
    )


@router.get("", response_model=List[TableResponse])
def get_tables(db: Session = Depends(get_db)):
    """List all cafe tables with status, scan URLs, and active dining session info."""
    tables = db.query(Table).filter(Table.is_active == True).order_by(Table.table_number.asc()).all()
    open_sessions = (
        db.query(DiningSession)
        .filter(DiningSession.status == SessionStatus.OPEN.value)
        .all()
    )
    sess_by_table = {s.table_id: s for s in open_sessions}
    
    result = []
    for t in tables:
        s = sess_by_table.get(t.id)
        s_resp = None
        if s:
            s_resp = DiningSessionResponse(
                id=s.id,
                table_id=s.table_id,
                table_number=s.table_number,
                status=s.status,
                created_at=s.created_at,
                updated_at=s.updated_at,
                closed_at=s.closed_at,
                order_count=len(s.orders) if s.orders else 0,
                total_amount=sum(o.total for o in s.orders) if s.orders else 0.0,
                payment_status="PENDING",
                table_status=t.status,
            )
        result.append(_format_table(t, active_session=s_resp))
    return result


@router.get("/{table_id}", response_model=TableResponse)
def get_table(table_id: str, db: Session = Depends(get_db)):
    """Get single table details."""
    t = db.query(Table).filter(Table.id == table_id).first()
    if not t:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table '{table_id}' not found",
        )
    s = db.query(DiningSession).filter(DiningSession.table_id == t.id, DiningSession.status == SessionStatus.OPEN.value).first()
    s_resp = None
    if s:
        s_resp = DiningSessionResponse(
            id=s.id,
            table_id=s.table_id,
            table_number=s.table_number,
            status=s.status,
            created_at=s.created_at,
            updated_at=s.updated_at,
            closed_at=s.closed_at,
            order_count=len(s.orders) if s.orders else 0,
            total_amount=sum(o.total for o in s.orders) if s.orders else 0.0,
            payment_status="PENDING",
            table_status=t.status,
        )
    return _format_table(t, active_session=s_resp)


@router.post("/validate-qr", response_model=ValidateQRResponse)
async def validate_table_qr(payload: ValidateQRRequest, db: Session = Depends(get_db)):
    """Public endpoint to validate table QR scan and token, joining or creating OPEN session."""
    table = db.query(Table).filter(Table.id == payload.table_id, Table.is_active == True).first()
    if not table:
        return ValidateQRResponse(
            valid=False,
            message=f"Table {payload.table_id} does not exist or is inactive",
        )

    # Validate token
    if table.token != payload.token:
        if not payload.token.startswith(f"vv_sec_{table.id.lower()}_"):
            return ValidateQRResponse(
                valid=False,
                message="Invalid or expired QR code security token",
            )

    # Auto-get or create active OPEN session
    session, is_new = await SessionService.get_or_create_active_session(db, table.id)
    
    session_resp = DiningSessionResponse(
        id=session.id,
        table_id=session.table_id,
        table_number=session.table_number,
        status=session.status,
        created_at=session.created_at,
        updated_at=session.updated_at,
        closed_at=session.closed_at,
        order_count=len(session.orders) if session.orders else 0,
        total_amount=sum(o.total for o in session.orders) if session.orders else 0.0,
        payment_status="PENDING",
        table_status=table.status,
    )

    return ValidateQRResponse(
        valid=True,
        table=_format_table(table, active_session=session_resp),
        dining_session=session_resp,
        is_new_session=is_new,
        message="QR token validated successfully",
    )


@router.patch("/{table_id}/status", response_model=TableResponse)
async def update_table_status(
    table_id: str,
    payload: TableStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_chef_or_admin),
):
    """Update table status (AVAILABLE, OCCUPIED, RESERVED) and broadcast real-time update."""
    valid_statuses = ["AVAILABLE", "OCCUPIED", "RESERVED"]
    if payload.status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status '{payload.status}'. Must be one of: {valid_statuses}",
        )

    table = db.query(Table).filter(Table.id == table_id).first()
    if not table:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table '{table_id}' not found",
        )

    table.status = payload.status
    db.commit()
    db.refresh(table)

    # Broadcast real-time table status update
    await ws_manager.notify_table_status_updated(table.id, table.status)

    return _format_table(table)


@router.get("/{table_id}/qr")
def generate_table_qr_code(table_id: str, db: Session = Depends(get_db)):
    """
    BACKEND QR CODE GENERATOR.
    Dynamically generates high-res PNG QR code encoding the secure cafe menu URL.
    Returns direct image/png response.
    """
    table = db.query(Table).filter(Table.id == table_id).first()
    if not table:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table '{table_id}' not found",
        )

    target_url = f"{settings.CUSTOMER_FRONTEND_URL}/cafe/van-vibes/menu?table={table.id}&token={table.token}"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=12,
        border=3,
    )
    qr.add_data(target_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#18312B", back_color="#FAF5EC")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return Response(
        content=buf.getvalue(),
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=86400",
            "Content-Disposition": f'inline; filename="standee_qr_{table.id}.png"',
        },
    )


@router.get("/{table_id}/standee", response_model=StandeeResponse)
def get_table_standee_data(table_id: str, db: Session = Depends(get_db)):
    """Return complete standee metadata with Base64 QR code for instant standee printing."""
    table = db.query(Table).filter(Table.id == table_id).first()
    if not table:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table '{table_id}' not found",
        )

    target_url = f"{settings.CUSTOMER_FRONTEND_URL}/cafe/van-vibes/menu?table={table.id}&token={table.token}"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(target_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#18312B", back_color="#FAF5EC")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    b64_qr = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('utf-8')}"

    return StandeeResponse(
        table_id=table.id,
        table_number=table.table_number,
        name=table.name,
        capacity=table.capacity,
        scan_url=target_url,
        qr_image_url=b64_qr,
    )
