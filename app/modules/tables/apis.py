from typing import List, Optional
from fastapi import Depends, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.dependencies import require_admin, require_chef_or_admin
from app.db.session import get_db
from app.modules.accounts.models import User
from app.modules.tables.schemas import (
    TableTransferRequest,
    TableTransferResponse,
    CreateTableRequest,
    StandeeResponse,
    TableResponse,
    TableStatusUpdate,
    ValidateQRRequest,
    ValidateQRResponse,
)
from app.modules.tables.service import TableService, format_table


def get_tables(
    request: Request,
    frontend_url: Optional[str] = None,
    db: Session = Depends(get_db),
) -> List[TableResponse]:
    """List all cafe tables with status, scan URLs, and active dining session info."""
    return TableService.list_tables(db, request=request, frontend_url=frontend_url)


def get_table(
    table_id: str,
    request: Request,
    frontend_url: Optional[str] = None,
    db: Session = Depends(get_db),
) -> TableResponse:
    """Get single table details."""
    return TableService.get_table(db, table_id, request=request, frontend_url=frontend_url)


async def create_table(
    payload: CreateTableRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> TableResponse:
    """Create a new table with backend-generated cryptographic QR token (Admin only)."""
    return await TableService.create_table(db, payload, request=request)


async def validate_table_qr(
    payload: ValidateQRRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> ValidateQRResponse:
    """Public endpoint to validate table QR scan and token, joining or creating OPEN session."""
    return await TableService.validate_qr(db, payload, request=request)


async def update_table_status(
    table_id: str,
    payload: TableStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_chef_or_admin),
) -> TableResponse:
    """Update table status (AVAILABLE, OCCUPIED, RESERVED) and broadcast real-time update."""
    return await TableService.update_status(db, table_id, payload, request=request)


def generate_table_qr_code(
    table_id: str,
    request: Request,
    frontend_url: Optional[str] = None,
    db: Session = Depends(get_db),
) -> Response:
    """Dynamically generates high-res PNG QR code encoding the secure cafe menu URL."""
    return TableService.generate_qr_code(db, table_id, request=request, frontend_url=frontend_url)


def get_table_standee_data(
    table_id: str,
    request: Request,
    frontend_url: Optional[str] = None,
    db: Session = Depends(get_db),
) -> StandeeResponse:
    """Return complete standee metadata with Base64 QR code for instant standee printing."""
    return TableService.get_standee_data(db, table_id, request=request, frontend_url=frontend_url)


def scan_table_redirect(
    table_id: str,
    request: Request,
    token: Optional[str] = None,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Public dynamic redirect for table QR codes."""
    return TableService.scan_redirect(db, table_id, request=request, token=token)


async def delete_table(
    table_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict:
    """Delete a table (Admin only)."""
    return await TableService.delete_table(db, table_id)


async def swipe_table_endpoint(
    payload: TableTransferRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> TableTransferResponse:
    """
    Table Swipe / Transfer operation (Admin only):
    Atomically moves an active dining session and its associated orders from source table to destination table.
    """
    from app.modules.sessions.service import SessionService
    from app.modules.sessions.schemas import DiningSessionResponse

    session, source_tbl, dest_tbl, order_ids = await SessionService.transfer_table_session(
        db, payload.source_table_id, payload.destination_table_id
    )

    dest_session_resp = DiningSessionResponse(
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
        table_status="OCCUPIED",
    )

    return TableTransferResponse(
        message=f"Successfully swiped Table {source_tbl.table_number:02d} to Table {dest_tbl.table_number:02d}",
        sessionId=session.id,
        sourceTable=format_table(source_tbl, active_session=None, request=request),
        destinationTable=format_table(dest_tbl, active_session=dest_session_resp, request=request),
        orderIds=order_ids,
    )
