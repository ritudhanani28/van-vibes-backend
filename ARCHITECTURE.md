# Vaan Vibes Cafe — Backend Architecture Specification

## 1. System Architecture & High-Level Design

The **Vaan Vibes Cafe Backend** is a high-performance, asynchronous REST & WebSocket service built on **FastAPI**, **SQLAlchemy ORM**, **Pydantic v2**, and **PostgreSQL** (with zero-configuration SQLite fallback for local development testing). It serves as the single source of truth for both customer-facing ordering and kitchen/administrative management.

```
                    ┌────────────────────────────────────────────────────────┐
                    │               FastAPI Single Source of Truth           │
                    │                                                        │
                    │  ┌──────────────────┐  ┌─────────────────────────────┐  │
                    │  │ REST APIs (/v1)  │  │ WebSocket Gateway (/ws/..) │  │
                    │  │  • Auth / RBAC   │  │  • Order State Broadcast    │  │
                    │  │  • Menu & Cat    │  │  • Role-filtered Events     │  │
                    │  │  • Tables & QR   │  │  • Live KDS Dispatch        │  │
                    │  │  • Orders & POS  │  │  • Auto-reconnect Support   │  │
                    │  │  • Billing & GST │  └─────────────────────────────┘  │
                    │  │  • Dashboard KPIs│                                  │
                    │  └──────────────────┘                                  │
                    │                   ▲                                    │
                    │                   │                                    │
                    │  ┌────────────────┴─────────────────────────────┐      │
                    │  │ Core Service Layer & State Transition Engine  │      │
                    │  │  • Server-Side Pricing & Bill Calculation    │      │
                    │  │  • Cryptographic QR Token Verification       │      │
                    │  │  • Transactional Multi-Item Processing       │      │
                    │  └────────────────┬─────────────────────────────┘      │
                    │                   │                                    │
                    │                   ▼                                    │
                    │  ┌──────────────────────────────────────────────┐      │
                    │  │ PostgreSQL / SQLite (SQLAlchemy ORM Models)  │      │
                    │  │  • Users (Bcrypt)   • Categories & Items     │      │
                    │  │  • Tables (Tokens)  • Orders & OrderItems    │      │
                    │  │  • Customers        • Invoices & Tax Ledger  │      │
                    │  └──────────────────────────────────────────────┘      │
                    └───────────────────┬────────────────────────────────────┘
                                        │
                 ┌──────────────────────┴──────────────────────┐
                 │                                             │
      ┌──────────▼────────────┐                     ┌──────────▼────────────┐
      │   Customer Frontend   │                     │  Management Frontend  │
      │   (Next.js Port 3000) │                     │  (Next.js Port 3001)  │
      ├───────────────────────┤                     ├───────────────────────┤
      │ • Table QR Validation │                     │ • Admin Dashboard     │
      │ • Category & Dish Menu│                     │ • Chef KDS (No price) │
      │ • Real-time Food Search                     │ • Orders Queue & POS  │
      │ • Cart & Customization│                     │ • Menu Catalog CRUD   │
      │ • Order Placement     │                     │ • Table QR Standees   │
      │ • Live Order Status   │                     │ • Billing / GST Bills │
      └───────────────────────┘                     └───────────────────────┘
```

---

## 2. Database Schema & Entity Relationship Diagram (ERD)

```mermaid
erDiagram
    USERS ||--o{ ORDERS : updates
    CATEGORIES ||--|{ MENU_ITEMS : contains
    TABLES ||--o{ ORDERS : hosts
    CUSTOMERS ||--o{ ORDERS : places
    ORDERS ||--|{ ORDER_ITEMS : includes
    ORDERS ||--o| BILLING_INVOICES : generates

    USERS {
        uuid id PK
        string email UK
        string name
        string password_hash
        string role "ADMIN | CHEF"
        string shift
        string assigned_station
        boolean is_active
        timestamp created_at
        timestamp updated_at
    }

    CATEGORIES {
        string id PK "slug e.g. hot-coffee"
        string name "Hot Coffee"
        string icon "☕"
        int page
        int display_order
        boolean is_active
        timestamp created_at
    }

    MENU_ITEMS {
        string id PK "e.g. hc-01"
        string category_id FK
        string name
        decimal price
        string description
        boolean is_veg
        string image
        boolean popular
        boolean is_available
        json options "milk, roast, size variations"
        json add_ons "extra shots, syrups"
        timestamp created_at
        timestamp updated_at
    }

    TABLES {
        string id PK "T01 to T12"
        int table_number UK
        string name "Table 1"
        int capacity
        string status "AVAILABLE | OCCUPIED | RESERVED"
        string token "HMAC secret token"
        boolean is_active
        timestamp updated_at
    }

    CUSTOMERS {
        uuid id PK
        string name
        string mobile "10-digit unique/indexed"
        string special_instructions
        timestamp created_at
        timestamp last_visited_at
    }

    ORDERS {
        string id PK "VV-1001, VV-1002..."
        string table_id FK
        int table_number
        string session_token
        uuid customer_id FK
        string customer_name
        string customer_mobile
        string special_instructions
        string status "ORDER_PLACED | ACCEPTED | PREPARING | READY | SERVED | COMPLETED | CANCELLED"
        string payment_status "PENDING | PAID | REFUNDED"
        decimal subtotal
        decimal tax
        decimal total
        timestamp created_at
        timestamp updated_at
    }

    ORDER_ITEMS {
        uuid id PK
        string order_id FK
        string menu_item_id FK
        string name
        decimal unit_price "Historical freeze"
        int quantity
        decimal item_total
        json selected_options
        json selected_add_ons
        string special_instructions
    }

    BILLING_INVOICES {
        string id PK "INV-1001"
        string order_id FK UK
        string invoice_number UK
        decimal subtotal
        decimal cgst_rate "0.025 (2.5%)"
        decimal cgst_amount
        decimal sgst_rate "0.025 (2.5%)"
        decimal sgst_amount
        decimal total_tax
        decimal grand_total
        string payment_method "CASH | UPI | CARD"
        string payment_status "PENDING | SETTLED"
        timestamp settled_at
        timestamp created_at
    }

    CAFE_SETTINGS {
        string id PK "singleton"
        string name "Vaan Vibes Cafe & Restro"
        string name_hindi "वन VIBES"
        string tagline "Where Coffee Meets Wilderness"
        string address
        string phone
        string gstin "24AAAAA0000A1Z5"
        decimal tax_rate "0.05"
        timestamp updated_at
    }
```

---

## 3. REST API Specification

### 3.1 Authentication & Profile (`/api/v1/auth`)
* `POST /api/v1/auth/login`: Form/JSON with `username` (`email`) and `password`. Returns JWT token, token type, expiry, and user profile (`id`, `name`, `email`, `role`, `assigned_station`).
* `GET /api/v1/auth/me`: Validates JWT token and returns current user details.
* `POST /api/v1/auth/logout`: Invalidates client session.

### 3.2 Menu & Categories (`/api/v1/menu` & `/api/v1/categories`)
* `GET /api/v1/categories`: List all 19 active categories in sorted order.
* `GET /api/v1/menu`: List all active menu dishes. Supports query filters: `?category=hot-coffee`, `?search=cappuccino`, `?is_veg=true`.
* `GET /api/v1/menu/{item_id}`: Retrieve single dish specification including available options and add-ons.
* `POST /api/v1/menu` *(Admin only)*: Create a new dish in the catalog.
* `PUT /api/v1/menu/{item_id}` *(Admin only)*: Update dish pricing, description, veg flag, or tags.
* `PATCH /api/v1/menu/{item_id}/availability` *(Admin only)*: Instantly toggle dish availability (`is_available: true/false`).
* `DELETE /api/v1/menu/{item_id}` *(Admin only)*: Soft-delete/deactivate or remove dish from catalog.

### 3.3 Tables & QR Standees (`/api/v1/tables`)
* `GET /api/v1/tables`: List all 12 cafe tables with real-time status and active session info.
* `POST /api/v1/tables/validate-qr`: Public endpoint used by customer QR scanner. Validates `table_id` and cryptographic `token`.
* `PATCH /api/v1/tables/{table_id}/status` *(Admin/Staff)*: Update table status (`AVAILABLE`, `OCCUPIED`, `RESERVED`).
* `GET /api/v1/tables/{table_id}/qr`: **Backend QR Generation Endpoint**. Generates high-res PNG image or SVG stream encoding `{CUSTOMER_FRONTEND_URL}/cafe/van-vibes/menu?table={table_id}&token={token}`.
* `GET /api/v1/tables/{table_id}/standee-data`: Return standee metadata for print preview (table number, capacity, scan URL, direct QR base64 image).

### 3.4 Orders & Lifecycle (`/api/v1/orders`)
* `POST /api/v1/orders`: Public customer order placement. Validates table session, freezes item prices from database, creates transactional order + order items, updates table status to `OCCUPIED`, and broadcasts `ORDER_CREATED` event via WebSocket.
* `GET /api/v1/orders`: List orders with pagination & filters (`?status=ORDER_PLACED`, `?table_id=T07`, `?session_token=...`).
  * If requested by **Chef**: Response fields are automatically sanitized (price, subtotal, tax, and revenue fields stripped).
  * If requested by **Admin**: Full order with financial breakdown returned.
  * If requested by **Customer** (via `session_token` header/param): Returns customer's active and historical orders.
* `GET /api/v1/orders/{order_id}`: Single order details (sanitized if Chef role).
* `PATCH /api/v1/orders/{order_id}/status`: Transitions order state (`ORDER_PLACED` $\rightarrow$ `ACCEPTED` $\rightarrow$ `PREPARING` $\rightarrow$ `READY` $\rightarrow$ `SERVED` $\rightarrow$ `COMPLETED` or `CANCELLED`). Enforces state transition validation rules and broadcasts `ORDER_STATUS_UPDATED`.
* `POST /api/v1/orders/{order_id}/cancel`: Customer or Admin cancellation with strict status check (cannot cancel after preparation has begun).

### 3.5 Billing & POS (`/api/v1/billing`) *(Admin only)*
* `GET /api/v1/billing/ledger`: List all financial order invoices with subtotal, CGST (2.5%), SGST (2.5%), and grand total.
* `GET /api/v1/billing/{order_id}`: Full itemized receipt with tax breakdown and store details.
* `POST /api/v1/billing/{order_id}/settle`: Mark bill as settled (`payment_method`: `CASH` | `UPI` | `CARD`, `payment_status`: `PAID`). Releases table back to `AVAILABLE` if no further pending orders exist.

### 3.6 Dashboard & Metrics (`/api/v1/dashboard`) *(Admin only)*
* `GET /api/v1/dashboard/summary`: Real-time aggregated statistics calculated directly from SQL:
  * `total_orders`: Total orders count today.
  * `kitchen_pending`: Count of orders in `ORDER_PLACED`, `ACCEPTED`, `PREPARING`.
  * `occupied_tables`: Number of occupied tables / Total tables (12).
  * `settled_revenue`: Total revenue collected from paid orders today.
  * `recent_orders`: Top 10 most recent live orders.

---

## 4. WebSocket Real-Time Event Architecture

* **WebSocket Route:** `/api/v1/ws/orders`
* **Authentication:** Query parameter `?token=<jwt>` or initial `AUTH` handshake.
* **Broadcaster Channels:**
  * `admin`: Receives all events with full financial data.
  * `chef`: Receives operational events with price sanitization.
  * `public_table_{id}`: Customer live tracking for their table's orders.

### Event Catalog

| Event Name | Trigger | Target Audience | Payload Summary |
| :--- | :--- | :--- | :--- |
| `ORDER_CREATED` | Customer places order | Admin, Chef, Table | Order ID, Table #, Items, Quantities, Instructions |
| `ORDER_STATUS_UPDATED` | Chef/Admin updates state | Admin, Chef, Table | Order ID, Previous Status, New Status, Updated At |
| `PAYMENT_SETTLED` | Admin settles bill | Admin, Table | Order ID, Invoice #, Payment Method, Settled At |
| `TABLE_STATUS_UPDATED` | Table status changes | Admin, Staff | Table ID, New Status (`OCCUPIED` / `AVAILABLE`) |
| `MENU_AVAILABILITY_CHANGED`| Admin toggles dish | Admin, Chef, Customer | Item ID, `is_available` |

---

## 5. Security & Role-Based Access Control (RBAC)

1. **Password Hashing:** Passwords hashed with standard **Bcrypt** (`passlib[bcrypt]`). Plaintext passwords never stored or logged.
2. **JWT Authentication:** Signed with HMAC-SHA256 (`HS256`) using server secret key. Token claims:
   ```json
   {
     "sub": "user_uuid",
     "email": "admin@vaanvibes.com",
     "role": "ADMIN",
     "station": "MAIN_KITCHEN",
     "exp": 1727600000
   }
   ```
3. **Role Authorization Dependencies:**
   * `get_current_user`: Verifies valid JWT token.
   * `require_admin`: Enforces `role == "ADMIN"`, raises HTTP 403 Forbidden otherwise.
   * `require_chef_or_admin`: Permits operational actions for both `CHEF` and `ADMIN`.
4. **Data Isolation:**
   * The backend strips all financial fields (`unit_price`, `item_total`, `subtotal`, `tax`, `total`) from schemas when the requester is a Chef.

---

## 6. Table QR Code Generation Specification

The backend generates high-quality standard QR codes using the Python `qrcode` library with `PIL` (Pillow).
* **Target Scanned URL Format:**
  `{CUSTOMER_FRONTEND_URL}/cafe/van-vibes/menu?table={table_id}&token={token}`
* **Security Token:** Generated per-table using `HMAC-SHA256(secret_key, table_id)` ensuring client requests cannot spoof arbitrary tables.
* **Image Response:**
  * Returns `Content-Type: image/png` with browser cache headers for crisp, scalable rendering on physical standees or digital screens.
  * Standee metadata endpoint provides SVG/Base64 options for printable table tents.

---

## 7. Migration & Seeding Plan

* **Alembic:** Database schema managed via automated migrations (`alembic revision --autogenerate`).
* **Initial Seed Data:**
  * **19 Canonical Categories**: Hot Coffee, Iced Coffee, Non Coffee, Manual Brew, Shake, Frappe, Toastie, Appetizers, Pasta, Pizza, Rice, Soup, Starters, Asian Indo, Sizzlers, Signature Punjabi, Bread, Accompaniment, Desserts.
  * **112 Dishes**: Complete dish catalog with Indian pricing, veg/non-veg flags, descriptions, and custom options/add-ons imported directly from `src/data/vaan-vibes-menu.ts`.
  * **12 Cafe Tables**: `T01` to `T12` with secure tokens and capacities (2, 4, 6 seats).
  * **Default Staff Users**:
    * Admin: `admin@vaanvibes.com` / `admin123`
    * Chef: `chef@vaanvibes.com` / `chef123`
  * **Store Settings**: GSTIN `24AAAAA0000A1Z5`, 5% GST (2.5% CGST + 2.5% SGST), store address, and phone numbers.
