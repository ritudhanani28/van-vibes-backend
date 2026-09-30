# Vaan Vibes Cafe & Restro — FastAPI Backend

Production-ready, asynchronous backend service built with **FastAPI**, **SQLAlchemy ORM (v2)**, **Pydantic (v2)**, and **PostgreSQL**, acting as the authoritative single source of truth for both the Customer Ordering Frontend (`http://localhost:3000`) and the Cafe Management / Kitchen KDS Frontend (`http://localhost:3001`).

---

## 🚀 Key Features

* **Authoritative Server-Side Pricing & Billing**: All prices, subtotal, and 5% GST (2.5% CGST + 2.5% SGST) are computed directly from the menu database. Client-submitted prices are never trusted.
* **Role-Based Access Control (RBAC)**: Secure JWT authentication with Bcrypt password hashing. Admin enjoys full operational control, while Chef receives strictly sanitized operational tickets (no prices, revenue, or billing data).
* **State Machine Lifecycle Enforcement**: Order transitions (`ORDER_PLACED` $\rightarrow$ `ACCEPTED` $\rightarrow$ `PREPARING` $\rightarrow$ `READY` $\rightarrow$ `SERVED` $\rightarrow$ `COMPLETED`) are validated by the backend. Invalid/backward transitions are rejected.
* **On-the-Fly Dynamic QR Code Generator**: Backend generates high-resolution PNG QR codes directly at `/api/v1/tables/{table_id}/qr` encoding cryptographic standee tokens.
* **Real-Time WebSocket Gateway**: Publishes `ORDER_CREATED`, `ORDER_STATUS_UPDATED`, `PAYMENT_SETTLED`, and `TABLE_STATUS_UPDATED` events at `/api/v1/ws/orders` with role-based payload filtering.

---

## 📁 Repository Structure

```text
vaan-vibes-backend/
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── endpoints/
│   │       │   ├── auth.py         # Login, /me profile, logout
│   │       │   ├── categories.py   # Category listing & counts
│   │       │   ├── menu.py         # Menu CRUD & dish availability
│   │       │   ├── tables.py       # Table management & QR generator
│   │       │   ├── orders.py       # Order lifecycle & state machine
│   │       │   ├── billing.py      # GST billing & UPI/Cash settlement
│   │       │   ├── dashboard.py    # Live SQL aggregated KPIs
│   │       │   ├── settings.py     # Cafe details & tax configuration
│   │       │   └── ws.py           # Real-time WebSocket endpoint
│   │       └── router.py           # API v1 consolidated routing
│   ├── core/
│   │   ├── config.py               # Pydantic v2 application settings
│   │   ├── security.py             # Bcrypt hashing & PyJWT tokens
│   │   └── dependencies.py         # RBAC dependencies (require_admin, etc.)
│   ├── db/
│   │   ├── session.py              # SQLAlchemy engine & session factory
│   │   ├── seed.py                 # Initial data seeder (19 categories, 112 dishes, 12 tables)
│   │   └── seed_menu.json          # Canonical menu JSON data
│   ├── models/                     # SQLAlchemy 2.0 ORM Models
│   │   ├── user.py
│   │   ├── category.py
│   │   ├── menu.py
│   │   ├── table.py
│   │   ├── order.py
│   │   ├── billing.py
│   │   └── settings.py
│   ├── schemas/                    # Pydantic Request & Response DTOs
│   │   ├── auth.py
│   │   ├── category.py
│   │   ├── menu.py
│   │   ├── table.py
│   │   ├── order.py
│   │   ├── billing.py
│   │   ├── dashboard.py
│   │   └── settings.py
│   ├── websocket/
│   │   └── manager.py              # WebSocket ConnectionManager
│   └── main.py                     # Application entry point
├── tests/
│   ├── test_vaan_vibes_api.py      # Core unit & RBAC test suite
│   └── test_e2e_realtime.py        # Real-time WebSocket E2E integration test
├── BACKEND_REQUIREMENTS.md         # Phase 1 Discovery & Audit documentation
├── ARCHITECTURE.md                 # Phase 2 System Architecture & ERD
├── requirements.txt
├── .env.example
└── .env
```

---

## 🛠️ Quick Start

### 1. Activate Virtual Environment
```bash
source venv/bin/activate
```

### 2. Seed Initial Database
Populates the 19 canonical categories, 112 dishes, 12 tables, admin/chef accounts, and store settings:
```bash
python -m app.db.seed
```

### 3. Run Development Server
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

---

## 🔑 Default Staff Credentials

| Role | Email | Password | Allowed Capabilities |
| :--- | :--- | :--- | :--- |
| **Admin** | `admin@vaanvibes.com` | `admin123` | Full access: Dashboard, Orders, Billing, Menu Catalog, Tables, Settings |
| **Chef** | `chef@vaanvibes.com` | `chef123` | Kitchen operational access only: KDS, Orders queue (no prices) |

---

## 🧪 Running Tests

```bash
# Run unit & RBAC test suite
pytest tests/test_vaan_vibes_api.py -v

# Run real-time WebSocket end-to-end integration test
pytest tests/test_e2e_realtime.py -v -s
```

---

## 📖 Interactive API Documentation

* **Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
* **ReDoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
