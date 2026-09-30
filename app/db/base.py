# This file is intentional so that Alembic/DB utils can import 'Base' and all models from one place
from app.db.session import Base
import app.models  # noqa: F401

__all__ = ["Base"]
