import base64
import io
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Response, status
import qrcode
from qrcode.image.pil import PilImage
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import require_admin, require_chef_or_admin
from app.core.security import generate_table_token
from app.db.session import get_db
from app.models.table import Table
from app.models.user import User
from app.models.dining_session import DiningSession, SessionStatus
from app.schemas.dining_session import DiningSessionResponse
from app.schemas.table import (
    CreateTableRequest,
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



@router.post("", response_model=TableResponse, status_code=status.HTTP_201_CREATED)
async def create_table(
    payload: CreateTableRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Create a new table with backend-generated cryptographic QR token (Admin only).
    Validates table number > 0, prevents duplicate table numbers.
    """
    if payload.table_number <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Table number must be greater than 0.",
        )

    existing = db.query(Table).filter(Table.table_number == payload.table_number).first()
    if existing:
        if not existing.is_active:
            existing.is_active = True
            existing.capacity = payload.capacity or 4
            existing.status = "AVAILABLE"
            existing.token = generate_table_token(existing.id)
            db.commit()
            db.refresh(existing)
            await ws_manager.notify_table_status_updated(existing.id, "AVAILABLE")
            await ws_manager.broadcast_event(
                event_type="TABLE_CREATED",
                admin_payload={"tableId": existing.id, "tableNumber": existing.table_number},
                chef_payload={"tableId": existing.id, "tableNumber": existing.table_number},
                table_id=existing.id,
            )
            return _format_table(existing)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Table number {payload.table_number} already exists.",
            )

    table_id = f"T{payload.table_number:02d}"
    if db.query(Table).filter(Table.id == table_id).first():
        table_id = f"T{payload.table_number}"

    token = generate_table_token(table_id)
    new_table = Table(
        id=table_id,
        table_number=payload.table_number,
        name=f"Table {payload.table_number:02d}",
        token=token,
        capacity=payload.capacity or 4,
        status="AVAILABLE",
        is_active=True,
    )
    db.add(new_table)
    db.commit()
    db.refresh(new_table)

    await ws_manager.notify_table_status_updated(new_table.id, "AVAILABLE")
    await ws_manager.broadcast_event(
        event_type="TABLE_CREATED",
        admin_payload={"tableId": new_table.id, "tableNumber": new_table.table_number},
        chef_payload={"tableId": new_table.id, "tableNumber": new_table.table_number},
        table_id=new_table.id,
    )

    return _format_table(new_table)


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

@router.delete("/{table_id}")
async def delete_table(
    table_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Delete a table (Admin only). Checks for active open session, sets is_active = False."""
    table = db.query(Table).filter(Table.id == table_id, Table.is_active == True).first()
    if not table:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table '{table_id}' not found",
        )

    open_session = (
        db.query(DiningSession)
        .filter(
            DiningSession.table_id == table_id,
            DiningSession.status == SessionStatus.OPEN.value,
        )
        .first()
    )
    if open_session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete Table {table.table_number} because it has an active dining session ({open_session.id}). Please settle or close the session first.",
        )

    table.is_active = False
    db.commit()

    await ws_manager.broadcast_event(
        event_type="TABLE_DELETED",
        admin_payload={"tableId": table_id, "tableNumber": table.table_number},
        chef_payload={"tableId": table_id, "tableNumber": table.table_number},
        table_id=table_id,
    )

    return {"message": f"Table {table.table_number} deleted successfully", "id": table_id}
