import json
import os
import sys
from datetime import datetime, timezone

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.core.security import hash_password
from app.db.session import Base, SessionLocal, engine
from app.models.category import Category
from app.models.menu import MenuItem
from app.models.settings import CafeSettings
from app.models.table import Table
from app.models.user import User


def seed_database():
    print("Cleaning database tables...")
    Base.metadata.create_all(bind=engine)

    # Delete existing data across all tables in reverse topological order, keeping alembic_version intact
    with engine.begin() as conn:
        for tbl in reversed(Base.metadata.sorted_tables):
            conn.execute(tbl.delete())

    db = SessionLocal()

    try:
        # 1. Cafe Settings (1)
        print("Seeding Cafe Settings (1)...")
        settings_record = CafeSettings(
            id="van-vibes",
            name="Vaan Vibes Cafe & Restro",
            hindi_name="वन VIBES",
            tagline="Cafe & Restro • Taste the Vibe",
            address="Main Promenade, Serenita Arts Quarter, Surat, Gujarat - 395007",
            phone="+91 98765 43210",
            gstin="24AAAAA0000A1Z5",
            tax_rate=0.05,
            currency="₹",
        )
        db.add(settings_record)
        db.flush()

        # 2. Staff Users (2: Admin & Chef)
        print("Seeding Staff Users (2)...")
        admin_user = User(
            id="user-admin-01",
            email="admin@vaanvibes.com",
            name="Admin Manager",
            password_hash=hash_password("admin123"),
            role="ADMIN",
            shift="All-Day",
            assigned_station="Control Desk",
            is_active=True,
        )
        chef_user = User(
            id="user-chef-01",
            email="chef@vaanvibes.com",
            name="Head Chef Vikram",
            password_hash=hash_password("chef123"),
            role="CHEF",
            shift="Morning",
            assigned_station="Hot Kitchen",
            is_active=True,
        )
        db.add_all([admin_user, chef_user])
        db.flush()

        # 3. Tables (12 Cafe Tables, all AVAILABLE)
        print("Seeding Tables (12)...")
        for i in range(1, 13):
            pad = f"{i:02d}"
            table_id = f"T{pad}"
            token = f"vv_sec_{table_id.lower()}_{(i * 7393 + 19283):x}"
            capacity = 2 if i <= 4 else (4 if i <= 8 else 6)
            t = Table(
                id=table_id,
                table_number=i,
                name=f"Table {pad}",
                token=token,
                capacity=capacity,
                status="AVAILABLE",
                is_active=True,
            )
            db.add(t)
        db.flush()

        # 4. Categories (19) & Menu Items (112) from seed_menu.json
        print("Seeding Categories (19) & Menu Items (112) from seed_menu.json...")
        json_path = os.path.join(os.path.dirname(__file__), "seed_menu.json")
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Insert categories (excluding 'all' which is a virtual filter)
            cats = [c for c in data.get("categories", []) if c.get("id") != "all"]
            for idx, c in enumerate(cats):
                cat_obj = Category(
                    id=c["id"],
                    name=c["name"],
                    slug=c.get("slug", c["id"]),
                    icon=c.get("icon", "🍽️"),
                    page=c.get("page", 2),
                    display_order=idx + 1,
                    is_active=True,
                )
                db.add(cat_obj)
            db.flush()

            # Insert menu items
            for item in data.get("items", []):
                m_obj = MenuItem(
                    id=item["id"],
                    category_id=item["category"],
                    name=item["name"],
                    price=float(item["price"]),
                    description=item.get("description"),
                    is_veg=bool(item.get("isVeg", True)),
                    image=item.get("image"),
                    popular=bool(item.get("popular", False)),
                    is_available=True,
                    options=item.get("options"),
                    add_ons=item.get("addOns"),
                )
                db.add(m_obj)
            db.flush()
        else:
            print("Warning: seed_menu.json not found!")

        db.commit()
        print("Database seeding completed successfully! Only requested tables populated.")
    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
