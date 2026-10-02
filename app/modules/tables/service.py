import base64
from datetime import datetime, timezone
import io
from typing import Any, List, Optional
from urllib.parse import urlparse

from fastapi import HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
import qrcode
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.tables import crud
from app.modules.tables.models import Table
from app.modules.tables.schemas import (
    CreateTableRequest,
    StandeeResponse,
    TableResponse,
    TableStatusUpdate,
    ValidateQRRequest,
    ValidateQRResponse,
)
from app.modules.notifications.manager import ws_manager


def resolve_customer_frontend_url(
    request: Optional[Request] = None,
    frontend_url: Optional[str] = None,
) -> str:
    """
    Dynamically resolves customer-facing frontend URL (port 4000).
    Guarantees production links & QR codes point to the real host/domain.
    """
    # 1. Direct explicit param override
    if frontend_url and frontend_url.strip():
        clean_url = frontend_url.strip().rstrip("/")
        if not any(h in clean_url for h in ("localhost", "127.0.0.1")):
            return clean_url

    # 2. Configured production setting (if not localhost)
    configured = (settings.CUSTOMER_FRONTEND_URL or "").strip().rstrip("/")
    if configured and not any(h in configured for h in ("localhost", "127.0.0.1")):
        return configured

    # 3. Dynamic resolution from incoming HTTP request headers
    if request:
        custom_hdr = request.headers.get("x-customer-frontend-url")
        if custom_hdr and not any(h in custom_hdr for h in ("localhost", "127.0.0.1")):
            return custom_hdr.strip().rstrip("/")

        proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "http"

        origin = request.headers.get("origin") or request.headers.get("referer")
        if origin:
            try:
                parsed = urlparse(origin)
                if parsed.hostname and parsed.hostname not in ("backend", "van_vibes_backend", "localhost", "127.0.0.1"):
                    return f"{parsed.scheme or proto}://{parsed.hostname}:4000"
            except Exception:
                pass

        raw_host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
        if raw_host:
            hostname = raw_host.split(":")[0].strip()
            if hostname and hostname not in ("backend", "van_vibes_backend", "localhost", "127.0.0.1"):
                return f"{proto}://{hostname}:4000"

    return configured or "http://localhost:4000"


def format_table(
    t: Table,
    active_session: Optional[Any] = None,
    request: Optional[Request] = None,
    frontend_url: Optional[str] = None,
) -> TableResponse:
    base_url = resolve_customer_frontend_url(request, frontend_url)
    scan_url = f"{base_url}/cafe/van-vibes/menu?table={t.id}&token={t.token}"
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


class TableService:
    @staticmethod
    def list_tables(db: Session, request: Optional[Request] = None) -> List[TableResponse]:
        from app.modules.sessions.models import DiningSession, SessionStatus
        from app.modules.sessions.schemas import DiningSessionResponse

        tables = crud.get_tables(db, active_only=True)
        open_sessions = (
            db.query(DiningSession)
            .filter(DiningSession.status == SessionStatus.OPEN.value)
            .all()
        )
        sess_by_table = {s.table_id: s for s in open_sessions}

        result = []
        for t in tables:
            s = sess_by_table.get(t.id) if t.status == "OCCUPIED" else None
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
            result.append(format_table(t, active_session=s_resp, request=request))
        return result

    @staticmethod
    def get_table(db: Session, table_id: str, request: Optional[Request] = None) -> TableResponse:
        from app.modules.sessions.models import DiningSession, SessionStatus
        from app.modules.sessions.schemas import DiningSessionResponse

        t = crud.get_table_by_id(db, table_id)
        if not t:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Table '{table_id}' not found",
            )
        s = db.query(DiningSession).filter(DiningSession.table_id == t.id, DiningSession.status == SessionStatus.OPEN.value).first() if t.status == "OCCUPIED" else None
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
        return format_table(t, active_session=s_resp, request=request)

    @staticmethod
    async def create_table(db: Session, payload: CreateTableRequest, request: Optional[Request] = None) -> TableResponse:
        if payload.table_number <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Table number must be greater than 0.",
            )

        existing = crud.get_table_by_number(db, payload.table_number)
        if existing:
            if not existing.is_active:
                reactivated = crud.reactivate_table(db, existing, payload.capacity)
                await ws_manager.notify_table_status_updated(reactivated.id, "AVAILABLE")
                await ws_manager.broadcast_event(
                    event_type="TABLE_CREATED",
                    admin_payload={"tableId": reactivated.id, "tableNumber": reactivated.table_number},
                    chef_payload={"tableId": reactivated.id, "tableNumber": reactivated.table_number},
                    table_id=reactivated.id,
                )
                return format_table(reactivated, request=request)
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Table number {payload.table_number} already exists.",
                )

        new_table = crud.create_table(db, payload)
        await ws_manager.notify_table_status_updated(new_table.id, "AVAILABLE")
        await ws_manager.broadcast_event(
            event_type="TABLE_CREATED",
            admin_payload={"tableId": new_table.id, "tableNumber": new_table.table_number},
            chef_payload={"tableId": new_table.id, "tableNumber": new_table.table_number},
            table_id=new_table.id,
        )
        return format_table(new_table, request=request)

    @staticmethod
    async def validate_qr(db: Session, payload: ValidateQRRequest, request: Optional[Request] = None) -> ValidateQRResponse:
        from app.modules.sessions.schemas import DiningSessionResponse
        from app.modules.sessions.service import SessionService

        table = crud.get_table_by_id(db, payload.table_id, active_only=True)
        if not table:
            return ValidateQRResponse(
                valid=False,
                message=f"Table {payload.table_id} does not exist or is inactive",
            )

        if table.token != payload.token:
            if not payload.token.startswith(f"vv_sec_{table.id.lower()}_"):
                return ValidateQRResponse(
                    valid=False,
                    message="Invalid or expired QR code security token",
                )

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
            table=format_table(table, active_session=session_resp, request=request),
            dining_session=session_resp,
            is_new_session=is_new,
            message="QR token validated successfully",
        )

    @staticmethod
    async def update_status(
        db: Session, table_id: str, payload: TableStatusUpdate, request: Optional[Request] = None
    ) -> TableResponse:
        from app.modules.sessions.models import DiningSession, SessionStatus
        from app.modules.sessions.service import SessionService
        from app.modules.orders.models import OrderStatus

        valid_statuses = ["AVAILABLE", "OCCUPIED", "RESERVED"]
        if payload.status not in valid_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status '{payload.status}'. Must be one of: {valid_statuses}",
            )

        table = crud.get_table_by_id(db, table_id)
        if not table:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Table '{table_id}' not found",
            )

        now = datetime.now(timezone.utc)

        if payload.status == "AVAILABLE":
            open_sess = (
                db.query(DiningSession)
                .filter(
                    DiningSession.table_id == table.id,
                    DiningSession.status == SessionStatus.OPEN.value,
                )
                .first()
            )
            if open_sess:
                has_active_orders = any(
                    o.status not in [OrderStatus.CANCELLED.value, OrderStatus.COMPLETED.value]
                    for o in open_sess.orders
                )
                if has_active_orders:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Cannot mark table AVAILABLE while it has an active session with open orders. Please generate a bill or cancel the orders first.",
                    )
                open_sess.status = SessionStatus.CLOSED.value
                open_sess.closed_at = now
                open_sess.updated_at = now
            table.status = "AVAILABLE"

        elif payload.status == "OCCUPIED":
            table.status = "OCCUPIED"
            open_sess = (
                db.query(DiningSession)
                .filter(
                    DiningSession.table_id == table.id,
                    DiningSession.status == SessionStatus.OPEN.value,
                )
                .first()
            )
            if not open_sess:
                await SessionService.get_or_create_active_session(db, table.id)

        elif payload.status == "RESERVED":
            table.status = "RESERVED"

        table.updated_at = now
        db.commit()
        db.refresh(table)
        await ws_manager.notify_table_status_updated(table.id, table.status)
        return TableService.get_table(db, table.id, request=request)

    @staticmethod
    def generate_qr_code(
        db: Session, table_id: str, request: Optional[Request] = None, frontend_url: Optional[str] = None
    ) -> Response:
        table = crud.get_table_by_id(db, table_id)
        if not table:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Table '{table_id}' not found",
            )

        base_url = resolve_customer_frontend_url(request, frontend_url)
        target_url = f"{base_url}/cafe/van-vibes/menu?table={table.id}&token={table.token}"

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
                "Cache-Control": "public, max-age=60",
                "Content-Disposition": f'inline; filename="standee_qr_{table.id}.png"',
            },
        )

    @staticmethod
    def get_standee_data(
        db: Session, table_id: str, request: Optional[Request] = None, frontend_url: Optional[str] = None
    ) -> StandeeResponse:
        table = crud.get_table_by_id(db, table_id)
        if not table:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Table '{table_id}' not found",
            )

        base_url = resolve_customer_frontend_url(request, frontend_url)
        target_url = f"{base_url}/cafe/van-vibes/menu?table={table.id}&token={table.token}"

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

    @staticmethod
    def scan_redirect(
        db: Session, table_id: str, request: Optional[Request] = None, token: Optional[str] = None
    ) -> RedirectResponse:
        table = crud.get_table_by_id(db, table_id)
        if not table:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Table '{table_id}' not found",
            )

        base_url = resolve_customer_frontend_url(request)
        target_token = token or table.token
        target_url = f"{base_url}/cafe/van-vibes/menu?table={table.id}&token={target_token}"
        return RedirectResponse(url=target_url, status_code=status.HTTP_302_FOUND)

    @staticmethod
    async def delete_table(db: Session, table_id: str) -> dict:
        from app.modules.sessions.models import DiningSession, SessionStatus

        table = crud.get_table_by_id(db, table_id, active_only=True)
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

        crud.soft_delete_table(db, table)
        await ws_manager.broadcast_event(
            event_type="TABLE_DELETED",
            admin_payload={"tableId": table_id, "tableNumber": table.table_number},
            chef_payload={"tableId": table_id, "tableNumber": table.table_number},
            table_id=table_id,
        )
        return {"message": f"Table {table.table_number} deleted successfully", "id": table_id}
