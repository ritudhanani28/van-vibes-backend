import csv
import io
import json
import zipfile
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.modules.accounts.models import User
from app.modules.export.schemas import ExportFilters, ExportRequest
from app.modules.menu.models import MenuItem
from app.modules.orders.models import Order, OrderItem
from app.modules.sessions.models import BillingInvoice, DiningSession
from app.modules.tables.models import Table

IST = ZoneInfo("Asia/Kolkata")


def sanitize_csv_cell(val: Any) -> str:
    """Format and protect against spreadsheet formula injection (CSV Injection)."""
    if val is None:
        return ""
    if isinstance(val, bool):
        return "Yes" if val else "No"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, datetime):
        if val.tzinfo is None:
            val = val.replace(tzinfo=timezone.utc)
        val_ist = val.astimezone(IST)
        return val_ist.strftime("%Y-%m-%d %H:%M:%S")

    val_str = str(val).strip()
    if val_str and val_str[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + val_str
    return val_str


def build_csv(headers: List[str], rows: List[List[Any]]) -> str:
    """Generate RFC 4180 compliant CSV text with UTF-8 BOM."""
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow([sanitize_csv_cell(h) for h in headers])
    for row in rows:
        writer.writerow([sanitize_csv_cell(cell) for cell in row])
    return output.getvalue()


class ExportService:
    @staticmethod
    def parse_date_range(
        date_range: str,
        start_date_str: Optional[str] = None,
        end_date_str: Optional[str] = None,
    ) -> Tuple[Optional[datetime], Optional[datetime], str]:
        now_ist = datetime.now(IST)

        if date_range == "last_1_day":
            start_date = (now_ist - timedelta(days=1)).date()
            start = datetime.combine(start_date, time.min, tzinfo=IST)
            end = datetime.combine(now_ist.date(), time.max, tzinfo=IST)
            label = "last-1-day"
        elif date_range == "last_7_days":
            start_date = (now_ist - timedelta(days=7)).date()
            start = datetime.combine(start_date, time.min, tzinfo=IST)
            end = datetime.combine(now_ist.date(), time.max, tzinfo=IST)
            label = "last-7-days"
        elif date_range == "last_30_days":
            start_date = (now_ist - timedelta(days=30)).date()
            start = datetime.combine(start_date, time.min, tzinfo=IST)
            end = datetime.combine(now_ist.date(), time.max, tzinfo=IST)
            label = "last-30-days"
        elif date_range == "custom":
            if not start_date_str or not end_date_str:
                raise ValueError("start_date and end_date are required for custom date range")
            s_date = datetime.strptime(start_date_str.strip(), "%Y-%m-%d").date()
            e_date = datetime.strptime(end_date_str.strip(), "%Y-%m-%d").date()
            if s_date > e_date:
                raise ValueError("Start date cannot be after end date")
            start = datetime.combine(s_date, time.min, tzinfo=IST)
            end = datetime.combine(e_date, time.max, tzinfo=IST)
            label = f"{start_date_str}-to-{end_date_str}"
        elif date_range == "all_time":
            start = None
            end = None
            label = "all-time"
        else:
            raise ValueError(f"Unsupported date range: {date_range}")

        return start, end, label

    @classmethod
    def get_category_count(
        cls,
        db: Session,
        category: str,
        start_dt: Optional[datetime],
        end_dt: Optional[datetime],
        filters: Optional[ExportFilters] = None,
    ) -> int:
        if category == "orders":
            q = db.query(func.count(Order.id))
            if start_dt and end_dt:
                q = q.filter(Order.created_at >= start_dt, Order.created_at <= end_dt)
            if filters:
                if filters.order_status and filters.order_status.upper() != "ALL":
                    q = q.filter(Order.status == filters.order_status.upper())
                if filters.order_id:
                    q = q.filter(Order.id == filters.order_id)
                if filters.table_number is not None:
                    q = q.filter(Order.table_number == filters.table_number)
            return q.scalar() or 0

        elif category == "order_items":
            q = db.query(func.count(OrderItem.id)).join(Order, OrderItem.order_id == Order.id)
            if start_dt and end_dt:
                q = q.filter(OrderItem.created_at >= start_dt, OrderItem.created_at <= end_dt)
            if filters:
                if filters.order_id:
                    q = q.filter(OrderItem.order_id == filters.order_id)
                if filters.order_status and filters.order_status.upper() != "ALL":
                    q = q.filter(Order.status == filters.order_status.upper())
                if filters.table_number is not None:
                    q = q.filter(Order.table_number == filters.table_number)
            return q.scalar() or 0

        elif category == "bills":
            q = db.query(func.count(BillingInvoice.id))
            if start_dt and end_dt:
                q = q.filter(BillingInvoice.created_at >= start_dt, BillingInvoice.created_at <= end_dt)
            if filters:
                if filters.bill_payment_status and filters.bill_payment_status.upper() != "ALL":
                    q = q.filter(BillingInvoice.payment_status == filters.bill_payment_status.upper())
                if filters.bill_payment_method and filters.bill_payment_method.upper() != "ALL":
                    q = q.filter(BillingInvoice.payment_method == filters.bill_payment_method.upper())
                if filters.bill_number:
                    q = q.filter(BillingInvoice.invoice_number == filters.bill_number)
            return q.scalar() or 0

        elif category == "payments":
            q = db.query(func.count(BillingInvoice.id))
            if start_dt and end_dt:
                q = q.filter(BillingInvoice.created_at >= start_dt, BillingInvoice.created_at <= end_dt)
            if filters:
                if filters.bill_payment_status and filters.bill_payment_status.upper() != "ALL":
                    q = q.filter(BillingInvoice.payment_status == filters.bill_payment_status.upper())
                if filters.bill_payment_method and filters.bill_payment_method.upper() != "ALL":
                    q = q.filter(BillingInvoice.payment_method == filters.bill_payment_method.upper())
            return q.scalar() or 0

        elif category == "menu_items":
            q = db.query(func.count(MenuItem.id))
            if filters:
                if filters.menu_category and filters.menu_category.lower() != "all":
                    q = q.filter(MenuItem.category_id == filters.menu_category)
                if filters.menu_availability is not None:
                    q = q.filter(MenuItem.is_available == filters.menu_availability)
            return q.scalar() or 0

        elif category == "tables":
            q = db.query(func.count(Table.id))
            if filters:
                if filters.table_status and filters.table_status.upper() != "ALL":
                    q = q.filter(Table.status == filters.table_status.upper())
            return q.scalar() or 0

        elif category == "staff":
            q = db.query(func.count(User.id))
            if filters:
                if filters.staff_role and filters.staff_role.upper() != "ALL":
                    q = q.filter(User.role == filters.staff_role.upper())
            return q.scalar() or 0

        return 0

    @classmethod
    def export_orders_csv(
        cls,
        db: Session,
        start_dt: Optional[datetime],
        end_dt: Optional[datetime],
        filters: Optional[ExportFilters] = None,
    ) -> str:
        q = db.query(Order).options(joinedload(Order.items)).order_by(Order.created_at.desc())
        if start_dt and end_dt:
            q = q.filter(Order.created_at >= start_dt, Order.created_at <= end_dt)
        if filters:
            if filters.order_status and filters.order_status.upper() != "ALL":
                q = q.filter(Order.status == filters.order_status.upper())
            if filters.order_id:
                q = q.filter(Order.id == filters.order_id)
            if filters.table_number is not None:
                q = q.filter(Order.table_number == filters.table_number)

        orders = q.all()
        headers = [
            "Order ID",
            "Date & Time (IST)",
            "Table",
            "Customer Name",
            "Customer Mobile",
            "Status",
            "Payment Status",
            "Items Count",
            "Items Summary",
            "Subtotal (₹)",
            "Tax (₹)",
            "Discount %",
            "Discount (₹)",
            "Extra Charge (₹)",
            "Round Off (₹)",
            "Total (₹)",
            "Special Instructions",
        ]

        rows = []
        for o in orders:
            items_summary = "; ".join(f"{it.quantity}x {it.name}" for it in o.items) if o.items else "None"
            items_count = sum(it.quantity for it in o.items) if o.items else 0
            rows.append([
                o.id,
                o.created_at,
                f"Table {o.table_number}" if o.table_number else (o.table_id or "Takeaway"),
                o.customer_name,
                o.customer_mobile,
                o.status,
                o.payment_status,
                items_count,
                items_summary,
                o.subtotal,
                o.tax,
                o.discount_percentage,
                o.discount_amount,
                o.extra_charge,
                o.round_off,
                o.total,
                o.special_instructions or "",
            ])
        return build_csv(headers, rows)

    @classmethod
    def export_order_items_csv(
        cls,
        db: Session,
        start_dt: Optional[datetime],
        end_dt: Optional[datetime],
        filters: Optional[ExportFilters] = None,
    ) -> str:
        q = db.query(OrderItem).join(Order, OrderItem.order_id == Order.id).order_by(OrderItem.created_at.desc())
        if start_dt and end_dt:
            q = q.filter(OrderItem.created_at >= start_dt, OrderItem.created_at <= end_dt)
        if filters:
            if filters.order_id:
                q = q.filter(OrderItem.order_id == filters.order_id)
            if filters.order_status and filters.order_status.upper() != "ALL":
                q = q.filter(Order.status == filters.order_status.upper())
            if filters.table_number is not None:
                q = q.filter(Order.table_number == filters.table_number)

        items = q.all()
        headers = [
            "Order ID",
            "Item ID",
            "Menu Item ID",
            "Item Name",
            "Category",
            "Quantity",
            "Unit Price (₹)",
            "Line Total (₹)",
            "Selected Options",
            "Selected Add-ons",
            "Special Instructions",
            "Date & Time (IST)",
        ]

        rows = []
        for it in items:
            opts = json.dumps(it.selected_options) if it.selected_options else ""
            addons = ", ".join(it.selected_add_ons) if it.selected_add_ons else ""
            rows.append([
                it.order_id,
                it.id,
                it.menu_item_id or "",
                it.name,
                it.category or "",
                it.quantity,
                it.unit_price,
                it.item_total,
                opts,
                addons,
                it.special_instructions or "",
                it.created_at,
            ])
        return build_csv(headers, rows)

    @classmethod
    def export_bills_csv(
        cls,
        db: Session,
        start_dt: Optional[datetime],
        end_dt: Optional[datetime],
        filters: Optional[ExportFilters] = None,
    ) -> str:
        q = db.query(BillingInvoice).order_by(BillingInvoice.created_at.desc())
        if start_dt and end_dt:
            q = q.filter(BillingInvoice.created_at >= start_dt, BillingInvoice.created_at <= end_dt)
        if filters:
            if filters.bill_payment_status and filters.bill_payment_status.upper() != "ALL":
                q = q.filter(BillingInvoice.payment_status == filters.bill_payment_status.upper())
            if filters.bill_payment_method and filters.bill_payment_method.upper() != "ALL":
                q = q.filter(BillingInvoice.payment_method == filters.bill_payment_method.upper())
            if filters.bill_number:
                q = q.filter(BillingInvoice.invoice_number == filters.bill_number)

        bills = q.all()
        headers = [
            "Invoice Number",
            "Date & Time (IST)",
            "Bill Type",
            "Dining Session ID",
            "Order ID",
            "Subtotal (₹)",
            "CGST (₹)",
            "SGST (₹)",
            "Tax (₹)",
            "Discount %",
            "Discount (₹)",
            "Extra Charge (₹)",
            "Round Off (₹)",
            "Grand Total (₹)",
            "Payment Method",
            "Payment Status",
            "Settled At (IST)",
        ]

        rows = []
        for b in bills:
            rows.append([
                b.invoice_number,
                b.created_at,
                b.bill_type,
                b.dining_session_id or "",
                b.order_id or "",
                b.subtotal,
                b.cgst_amount,
                b.sgst_amount,
                b.tax_amount,
                b.discount_percentage,
                b.discount_amount,
                b.extra_charge,
                b.round_off,
                b.total,
                b.payment_method,
                b.payment_status,
                b.settled_at or "",
            ])
        return build_csv(headers, rows)

    @classmethod
    def export_payments_csv(
        cls,
        db: Session,
        start_dt: Optional[datetime],
        end_dt: Optional[datetime],
        filters: Optional[ExportFilters] = None,
    ) -> str:
        q = db.query(BillingInvoice).order_by(BillingInvoice.created_at.desc())
        if start_dt and end_dt:
            q = q.filter(BillingInvoice.created_at >= start_dt, BillingInvoice.created_at <= end_dt)
        if filters:
            if filters.bill_payment_status and filters.bill_payment_status.upper() != "ALL":
                q = q.filter(BillingInvoice.payment_status == filters.bill_payment_status.upper())
            if filters.bill_payment_method and filters.bill_payment_method.upper() != "ALL":
                q = q.filter(BillingInvoice.payment_method == filters.bill_payment_method.upper())

        payments = q.all()
        headers = [
            "Invoice Number",
            "Date & Time (IST)",
            "Order ID",
            "Session ID",
            "Payment Method",
            "Amount Paid (₹)",
            "Payment Status",
            "Settled At (IST)",
        ]

        rows = []
        for p in payments:
            rows.append([
                p.invoice_number,
                p.created_at,
                p.order_id or "",
                p.dining_session_id or "",
                p.payment_method,
                p.total,
                p.payment_status,
                p.settled_at or "",
            ])
        return build_csv(headers, rows)

    @classmethod
    def export_menu_items_csv(
        cls,
        db: Session,
        filters: Optional[ExportFilters] = None,
    ) -> str:
        q = db.query(MenuItem).order_by(MenuItem.category_id, MenuItem.name)
        if filters:
            if filters.menu_category and filters.menu_category.lower() != "all":
                q = q.filter(MenuItem.category_id == filters.menu_category)
            if filters.menu_availability is not None:
                q = q.filter(MenuItem.is_available == filters.menu_availability)

        items = q.all()
        headers = [
            "Item ID",
            "Name",
            "Category",
            "Price (₹)",
            "Type",
            "Available",
            "Popular",
            "Description",
            "Created At (IST)",
        ]

        rows = []
        for m in items:
            rows.append([
                m.id,
                m.name,
                m.category_id,
                m.price,
                "Vegetarian" if m.is_veg else "Non-Vegetarian",
                "Yes" if m.is_available else "No",
                "Yes" if m.popular else "No",
                m.description or "",
                m.created_at,
            ])
        return build_csv(headers, rows)

    @classmethod
    def export_tables_csv(
        cls,
        db: Session,
        filters: Optional[ExportFilters] = None,
    ) -> str:
        q = db.query(Table).order_by(Table.table_number)
        if filters:
            if filters.table_status and filters.table_status.upper() != "ALL":
                q = q.filter(Table.status == filters.table_status.upper())

        tables = q.all()
        headers = [
            "Table ID",
            "Table Number",
            "Name",
            "Capacity",
            "Status",
            "Active",
        ]

        rows = []
        for t in tables:
            rows.append([
                t.id,
                t.table_number,
                t.name,
                t.capacity,
                t.status,
                "Yes" if t.is_active else "No",
            ])
        return build_csv(headers, rows)

    @classmethod
    def export_staff_csv(
        cls,
        db: Session,
        filters: Optional[ExportFilters] = None,
    ) -> str:
        q = db.query(User).order_by(User.role, User.name)
        if filters:
            if filters.staff_role and filters.staff_role.upper() != "ALL":
                q = q.filter(User.role == filters.staff_role.upper())

        users = q.all()
        headers = [
            "Staff ID",
            "Name",
            "Email",
            "Role",
            "Contact Number",
            "Shift",
            "Assigned Station",
            "Active",
            "Created At (IST)",
        ]

        rows = []
        for u in users:
            rows.append([
                u.id,
                u.name,
                u.email,
                u.role,
                u.contact_number or "",
                u.shift or "",
                u.assigned_station or "",
                "Yes" if u.is_active else "No",
                u.created_at,
            ])
        return build_csv(headers, rows)

    @classmethod
    def generate_export_payload(
        cls,
        db: Session,
        req: ExportRequest,
    ) -> Tuple[bytes, str, str]:
        """
        Returns (content_bytes, media_type, filename).
        Raises ValueError if no valid data or criteria.
        """
        start_dt, end_dt, date_label = cls.parse_date_range(
            req.date_range, req.start_date, req.end_date
        )

        csv_map: Dict[str, str] = {}

        for cat in req.categories:
            c = cat.lower().strip()
            if c == "orders":
                csv_map["orders"] = cls.export_orders_csv(db, start_dt, end_dt, req.filters)
            elif c == "order_items":
                csv_map["order-items"] = cls.export_order_items_csv(db, start_dt, end_dt, req.filters)
            elif c == "bills":
                csv_map["bills"] = cls.export_bills_csv(db, start_dt, end_dt, req.filters)
            elif c == "payments":
                csv_map["payments"] = cls.export_payments_csv(db, start_dt, end_dt, req.filters)
            elif c == "menu_items":
                csv_map["menu-items"] = cls.export_menu_items_csv(db, req.filters)
            elif c == "tables":
                csv_map["tables"] = cls.export_tables_csv(db, req.filters)
            elif c == "staff":
                csv_map["staff"] = cls.export_staff_csv(db, req.filters)

        if not csv_map:
            raise ValueError("No valid categories provided for export")

        # Single category export -> CSV
        if len(csv_map) == 1:
            cat_name, csv_content = next(iter(csv_map.items()))
            filename = f"van-vibes-{cat_name}-{date_label}.csv"
            return csv_content.encode("utf-8-sig"), "text/csv; charset=utf-8", filename

        # Multiple categories export -> ZIP
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for cat_name, csv_content in csv_map.items():
                zf.writestr(f"van-vibes-{cat_name}-{date_label}.csv", csv_content.encode("utf-8-sig"))
        zip_buf.seek(0)
        filename = f"van-vibes-export-{date_label}.zip"
        return zip_buf.getvalue(), "application/zip", filename
