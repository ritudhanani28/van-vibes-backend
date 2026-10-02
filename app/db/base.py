# Central database Base and model registry for Alembic and application metadata
from app.db.session import Base

# Import all SQLAlchemy models to register them on Base.metadata
from app.modules.accounts.models import User  # noqa: F401
from app.modules.menu.models import Category, MenuItem  # noqa: F401
from app.modules.tables.models import Table  # noqa: F401
from app.modules.orders.models import Customer, Order, OrderItem, OrderStatus  # noqa: F401
from app.modules.sessions.models import BillingInvoice, DiningSession, SessionStatus  # noqa: F401
from app.modules.settings.models import CafeSettings  # noqa: F401

__all__ = ["Base"]
