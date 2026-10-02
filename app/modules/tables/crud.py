from typing import List, Optional
from sqlalchemy.orm import Session

from app.core.security import generate_table_token
from app.modules.tables.models import Table
from app.modules.tables.schemas import CreateTableRequest


def get_tables(db: Session, active_only: bool = True) -> List[Table]:
    query = db.query(Table)
    if active_only:
        query = query.filter(Table.is_active == True)
    return query.order_by(Table.table_number.asc()).all()


def get_table_by_id(db: Session, table_id: str, active_only: bool = False) -> Optional[Table]:
    query = db.query(Table).filter(Table.id == table_id)
    if active_only:
        query = query.filter(Table.is_active == True)
    return query.first()


def get_table_by_number(db: Session, table_number: int) -> Optional[Table]:
    return db.query(Table).filter(Table.table_number == table_number).first()


def create_table(db: Session, payload: CreateTableRequest) -> Table:
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
    return new_table


def reactivate_table(db: Session, table: Table, capacity: Optional[int] = 4) -> Table:
    table.is_active = True
    table.capacity = capacity or 4
    table.status = "AVAILABLE"
    table.token = generate_table_token(table.id)
    db.commit()
    db.refresh(table)
    return table


def update_table_status(db: Session, table: Table, status_str: str) -> Table:
    table.status = status_str
    db.commit()
    db.refresh(table)
    return table


def soft_delete_table(db: Session, table: Table) -> None:
    table.is_active = False
    db.commit()


class TableCRUD:
    get_multi = staticmethod(get_tables)
    get_by_id = staticmethod(get_table_by_id)
    get_by_number = staticmethod(get_table_by_number)
    create = staticmethod(create_table)
    reactivate = staticmethod(reactivate_table)
    update_status = staticmethod(update_table_status)
    soft_delete = staticmethod(soft_delete_table)
