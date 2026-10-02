from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session

from app.modules.sessions.models import BillingInvoice, DiningSession, SessionStatus


class SessionCRUD:
    @staticmethod
    def get_by_id(db: Session, session_id: str) -> Optional[DiningSession]:
        return db.query(DiningSession).filter(DiningSession.id == session_id).first()

    @staticmethod
    def get_active_by_table(db: Session, table_id: str) -> Optional[DiningSession]:
        return (
            db.query(DiningSession)
            .filter(DiningSession.table_id == table_id, DiningSession.status == SessionStatus.OPEN.value)
            .first()
        )

    @staticmethod
    def get_multi(
        db: Session,
        status: Optional[str] = None,
        table_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[DiningSession]:
        query = db.query(DiningSession).order_by(DiningSession.created_at.desc())
        if status:
            query = query.filter(DiningSession.status == status)
        if table_id:
            query = query.filter(DiningSession.table_id == table_id)
        return query.limit(limit).all()

    @staticmethod
    def next_session_id(db: Session) -> str:
        all_sessions = db.query(DiningSession.id).filter(DiningSession.id.like("DS-%")).all()
        max_num = 1000
        for (sid,) in all_sessions:
            try:
                num = int(sid.replace("DS-", ""))
                if num > max_num:
                    max_num = num
            except (ValueError, TypeError):
                continue
        return f"DS-{max_num + 1}"

    @staticmethod
    def create(db: Session, session: DiningSession) -> DiningSession:
        db.add(session)
        db.commit()
        db.refresh(session)
        return session


class BillingCRUD:
    @staticmethod
    def get_invoice_by_id(db: Session, invoice_id: str) -> Optional[BillingInvoice]:
        return db.query(BillingInvoice).filter(BillingInvoice.id == invoice_id).first()

    @staticmethod
    def get_invoice_by_order(db: Session, order_id: str) -> Optional[BillingInvoice]:
        return db.query(BillingInvoice).filter(BillingInvoice.order_id == order_id).first()

    @staticmethod
    def get_invoice_by_session(db: Session, session_id: str, bill_type: str = "SESSION") -> Optional[BillingInvoice]:
        return (
            db.query(BillingInvoice)
            .filter(BillingInvoice.dining_session_id == session_id, BillingInvoice.bill_type == bill_type)
            .first()
        )

    @staticmethod
    def get_ledger(db: Session) -> List[BillingInvoice]:
        return db.query(BillingInvoice).order_by(BillingInvoice.created_at.desc()).all()

    @staticmethod
    def next_invoice_number(db: Session) -> str:
        all_invs = db.query(BillingInvoice.invoice_number).all()
        max_num = 1000
        for (inv_no,) in all_invs:
            try:
                parts = inv_no.split("-")
                num = int(parts[-1])
                if num > max_num:
                    max_num = num
            except (ValueError, TypeError, IndexError):
                continue
        return f"INV-2026-{max_num + 1}"
