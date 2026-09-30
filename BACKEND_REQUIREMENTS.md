# Vaan Vibes Cafe & Restro — Backend Requirements Document (Phase 1 Audit)

## 1. Executive Summary

This document details the comprehensive backend requirements for the **Vaan Vibes Cafe & Restro** platform. It is produced directly from a forensic audit of both existing frontend client applications:
1. **Customer / Public Frontend** (`van-vibes-frontend` located at `/Users/tagline/Desktop/test`, Port `3000`)
2. **Management Frontend** (`vaan-vibes-management` located at `/Users/tagline/Desktop/vaan-vibes-management`, Port `3001`)

The FastAPI backend must act as the **authoritative single source of truth** for both applications, eliminating all static/mock state, enforcing server-side business rules, guaranteeing transactional integrity for orders and billing, and providing real-time synchronization via WebSockets.

---

## 2. Customer Frontend Audit (`/Users/tagline/Desktop/test`)

### 2.1 Pages & Routing
* **Root / Redirects:** \`/\` redirects or loads the digital menu experience.
* **Table Scanned Routes:** \`/cafe/van-vibes/menu?table=T01&token=vv_sec_t01_...\` and \`/cafe/[cafeId]/menu\`.
* **Table QR Validation:** Client validates table ID and QR token upon arrival via \`/api/qr/validate\`.
* **Menu Browsing:** 19 categories rendered horizontally with real-time food name search, category tabs, and dish cards.

### 2.2 Client State & Storage
* **Context:** \`CartContext\` manages:
  * \`cart\`: Array of customized cart items with add-ons and options.
  * \`table\`: Verified \`TableInfo\` object.
  * \`sessionToken\`: Table session identifier (\`sess_t07_...\`).
  * \`customerDetails\`: Name, 10-digit mobile number, special instructions.
  * \`activeOrders\` / \`previousOrders\`: Polled orders for table session.
* **LocalStorage Keys:**
  * \`vv_cart\`: Persists active cart across reloads.
  * \`vv_customer\`: Remembers customer details.
  * \`vv_table\`: Remembers active table session.
  * \`vv_session_token\`: Unique per-browser guest session token.

### 2.3 Order Submission Flow
* Checks valid table token.
* Validates customer name (≥ 2 characters) and mobile number (10 digits).
* Posts order payload:
  \`\`\`json
  {
    "tableId": "T07",
    "token": "vv_sec_t07_...",
    "sessionToken": "sess_t07_1727500000",
    "customerName": "Aarav Sharma",
    "customerMobile": "9825012345",
    "specialInstructions": "Extra hot, no sugar",
    "items": [
      {
        "id": "hc-03-default",
        "menuItemId": "hc-03",
        "name": "Cappuccino",
        "category": "hot-coffee",
        "price": 160,
        "quantity": 2,
        "selectedOptions": { "Milk": "Almond Milk" },
        "selectedAddOns": ["Extra Espresso Shot"],
        "specialInstructions": "Extra hot"
      }
    ]
  }
  \`\`\`
* Clears cart upon HTTP 200, opens \`OrderTrackingModal\`, and polls for order status progression.

---

## 3. Management Frontend Audit (`/Users/tagline/Desktop/vaan-vibes-management`)

### 3.1 Authentication & Role-Based Access Control
* **Unified Entry Point:** \`/login\` for both Admin and Chef staff.
* **Credentials Currently Mocked:**
  * Admin: \`admin@vaanvibes.com\` / \`admin123\` (\`role: "ADMIN"\`)
  * Chef: \`chef@vaanvibes.com\` / \`chef123\` (\`role: "CHEF"\`)
* **Role Permissions Matrix:**
  | Resource / Route | Admin | Chef |
  | :--- | :---: | :---: |
  | \`/login\` | ✅ | ✅ |
  | \`/dashboard\` (KPIs & Overview) | ✅ | ❌ (403 Forbidden) |
  | \`/chef\` (Kitchen Display KDS) | ✅ | ✅ (Primary operational view) |
  | \`/orders\` (Orders Management) | ✅ (Full + Billing) | ✅ (Operational tickets only, no prices) |
  | \`/billing\` (Financial Ledger) | ✅ | ❌ (403 Forbidden) |
  | \`/tables\` (Table QR Standees) | ✅ | ❌ (403 Forbidden) |
  | \`/menu-items\` (Menu Catalog) | ✅ | ❌ (403 Forbidden) |
  | \`/settings\` (Cafe Config) | ✅ | ❌ (403 Forbidden) |
  | \`/profile\` | ✅ | ✅ |

### 3.2 Admin Features & Endpoints
* **Dashboard Summary:**
  * Total Orders count.
  * Kitchen Pending count (\`ORDER_PLACED\`, \`ACCEPTED\`, \`PREPARING\`).
  * Occupied Tables count / Total Tables (12).
  * Settled Revenue amount (₹).
  * Filter pills for Live Orders: \`All Orders\`, \`Placed\`, \`Accepted\`, \`Cancelled\`.
* **Menu Catalog Management:**
  * Category selector (19 categories with emojis and dish counts).
  * Search by food name.
  * Add Item modal (\`name\`, \`category\`, \`price\`, \`description\`, \`isVeg\`, \`popular\`).
  * Three-dot action menu: Edit item, Toggle availability (\`isAvailable\`), and Delete item with confirmation modal.
* **Table QR Standees:**
  * 12 physical cafe tables (\`T01\` to \`T12\`).
  * Table capacities: 2, 4, 6 persons.
  * Status: \`AVAILABLE\`, \`OCCUPIED\`, \`RESERVED\`.
  * Standee card preview with direct scan URL and printable standee.
* **Billing & POS:**
  * Financial metrics: Total Orders, Gross Subtotal, GST (5% — CGST 2.5% + SGST 2.5%), Settled Revenue.
  * Searchable invoice ledger table.
  * Itemized bill modal with GST breakdown and print support.

### 3.3 Chef Features & Endpoints (KDS)
* **Dedicated Operational View (\`/chef\`):**
  * Stage 1: Order Placed (New incoming) — counter & tickets.
  * Stage 2: Order Accepted (In Kitchen) — counter & active prep queue.
  * Stage 3: Completed Today — served tickets.
* **Strict Billing Information Removal:**
  * No item prices, no subtotal, no GST, no total bill amount.
  * Focuses purely on: Table #, Order ID, Items, Quantities, Options, Add-ons, Kitchen Notes, Elapsed time.
* **Rapid Action Lifecycle:**
  * Single tap: \`[ Accept Order ]\` (\`ORDER_PLACED\` → \`ACCEPTED\`).
  * Subsequent taps: \`[ Start Prep ]\` (\`ACCEPTED\` → \`PREPARING\`) → \`[ Mark Ready ]\` (\`READY\`) → \`[ Complete & Served ]\` (\`COMPLETED\`).

---

## 4. Static & Mock Data to be Retired

| Data Set | Current Location | Backend Entity to Replace |
| :--- | :--- | :--- |
| **Menu Categories (19 categories)** | \`src/data/vaan-vibes-menu.ts\` | \`categories\` table |
| **Menu Items (112 dishes)** | \`src/data/vaan-vibes-menu.ts\` | \`menu_items\` & options/add-ons tables |
| **Cafe Tables (12 tables + tokens)** | \`src/lib/cafe-store.ts\` | \`tables\` table |
| **Store Details & Tax** | \`src/lib/cafe-store.ts\` (\`CAFE_INFO\`) | \`cafe_settings\` table |
| **Orders & In-Memory Store** | \`global.__VAAN_VIBES_STORE__\` | \`orders\` & \`order_items\` tables |
| **Demo Users (Admin & Chef)** | \`src/context/AuthContext.tsx\` | \`users\` table with bcrypt hashes |

---

## 5. Backend Status Flow & State Machine

\`\`\`text
                  [ ORDER_PLACED ]
                         │
             ┌───────────────┴───────────────┐
             │                               │
    (Chef / Admin accepts)           (Customer cancels or Admin cancels)
             │                               │
             ▼                               ▼
       [ ACCEPTED ]                     [ CANCELLED ]
             │
     (Chef starts prep)
             │
             ▼
      [ PREPARING ]
             │
     (Chef marks ready)
             │
             ▼
        [ READY ]
             │
    (Waiter / Chef completes)
             │
             ▼
      [ COMPLETED ]
\`\`\`

### Transition Validation Rules:
1. Customer can cancel an order **only** when status is \`ORDER_PLACED\`. Once \`ACCEPTED\` or beyond, customer cancellation is rejected by the backend.
2. Only Chef or Admin can advance to \`ACCEPTED\`, \`PREPARING\`, \`READY\`, and \`COMPLETED\`.
3. Backward transitions (e.g. \`COMPLETED\` → \`PREPARING\`) are strictly forbidden.

---

## 6. Table QR Code Generation Requirement

As requested, the backend must provide automated QR code generation:
* **Endpoint:** \`GET /api/v1/tables/{table_id}/qr\`
* **Format:** Generates direct PNG image or base64 SVG data URI.
* **Payload Encoded in QR:** \`{CUSTOMER_FRONTEND_URL}/cafe/van-vibes/menu?table={table.id}&token={table.token}\`
* **Security Token:** Generated using secure HMAC cryptographic token tied to table ID and cafe secret key.

---

## 7. Real-Time WebSocket Specifications

* **Endpoint:** \`/api/v1/ws/orders\`
* **Authentication:** Query param \`?token=<jwt_token>\` or first handshake message.
* **Broadcast Events:**
  * \`ORDER_CREATED\`: Triggered when customer places order. Pushed to Admin & Chef dashboards.
  * \`ORDER_STATUS_UPDATED\`: Triggered when Chef accepts/prepares/completes order.
  * \`PAYMENT_STATUS_UPDATED\`: Triggered when Admin marks bill settled.
  * \`TABLE_STATUS_UPDATED\`: Triggered when table becomes occupied or vacant.
* **Payload Sanitization:** Chef WebSocket receives operational order payload (no pricing). Admin WebSocket receives full financial payload.
