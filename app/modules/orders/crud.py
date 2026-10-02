from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session

from app.modules.orders.models import Customer, Order, OrderItem, OrderStatus


class OrderCRUD:
    @staticmethod
    def get_by_id(db: Session, order_id: str) -> Optional[Order]:
        return db.query(Order).filter(Order.id == order_id).first()

    @staticmethod
    def get_multi(
        db: Session,
        status: Optional[str] = None,
        table_id: Optional[str] = None,
        dining_session_id: Optional[str] = None,
        session_token: Optional[str] = None,
        start_dt: Optional[datetime] = None,
        end_dt: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Order]:
        query = db.query(Order)
        if status and status.upper() != "ALL":
            query = query.filter(Order.status == status.upper())
        if table_id:
            query = query.filter(Order.table_id == table_id)
        if dining_session_id:
            query = query.filter(Order.dining_session_id == dining_session_id)
        if session_token:
            query = query.filter(Order.session_token == session_token)
        if start_dt and end_dt:
            query = query.filter(Order.created_at >= start_dt, Order.created_at <= end_dt)
        return query.order_by(Order.created_at.desc()).limit(limit).all()

    @staticmethod
    def next_order_id(db: Session) -> str:
        all_ids = db.query(Order.id).filter(Order.id.like("VV-%")).all()
        max_num = 1000
        for (oid,) in all_ids:
            try:
                num = int(oid.replace("VV-", ""))
                if num > max_num:
                    max_num = num
            except (ValueError, TypeError):
                continue
        return f"VV-{max_num + 1}"

    @staticmethod
    def create(db: Session, order: Order, items: List[OrderItem]) -> Order:
        db.add(order)
        for it in items:
            db.add(it)
        db.commit()
        db.refresh(order)
        return order

    @staticmethod
    def update_status(db: Session, order: Order, new_status: str) -> Order:
        order.status = new_status
        order.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(order)
        return order


class CustomerCRUD:
    @staticmethod
    def get_by_mobile(db: Session, mobile: str) -> Optional[Customer]:
        return db.query(Customer).filter(Customer.mobile == mobile).first()

    @staticmethod
    def upsert(db: Session, name: str, mobile: str) -> Customer:
        customer = CustomerCRUD.get_by_mobile(db, mobile)
        now = datetime.now(timezone.utc)
        if not customer:
            customer = Customer(name=name, mobile=mobile, last_visited_at=now)
            db.add(customer)
        else:
            customer.name = name
            customer.last_visited_at = now
        return customer
