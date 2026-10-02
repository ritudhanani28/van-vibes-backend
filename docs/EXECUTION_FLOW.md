# System Execution Flows

## 1. Customer Order Placement & Authoritative Price Computation Flow

```mermaid
sequenceDiagram
    autonumber
    actor Customer as Guest Customer
    participant API as Order API (/api/v1/orders)
    participant Svc as OrderService
    participant SessSvc as SessionService
    participant DB as PostgreSQL DB
    participant WS as WebSocket Manager (ws_manager)
    actor Chef as Kitchen Chef Display
    actor Admin as Admin POS Panel

    Customer->>API: POST /api/v1/orders (table_id, token, items, session_token)
    API->>Svc: create_order(db, payload)
    Svc->>DB: Verify Table & Security Token
    Svc->>SessSvc: attach_order_to_session(table_id)
    SessSvc->>DB: Get or Create OPEN DiningSession
    Svc->>DB: Upsert Customer record (name, mobile)
    Note over Svc,DB: Server-side authoritative price recalculation<br/>(Freeze item unit price + add-ons)
    Svc->>DB: Create Order (status=PLACED) & OrderItems
    Svc->>DB: Create Draft BillingInvoice (bill_type=ORDER)
    Svc->>DB: Set Table status = OCCUPIED
    Svc->>DB: COMMIT Transaction
    Svc->>WS: notify_order_placed(admin_order, chef_order, table_id)
    par Real-Time Broadcast
        WS-->>Chef: Event ORDER_PLACED (prices stripped)
        WS-->>Admin: Event ORDER_PLACED (full financial breakdown)
        WS-->>Customer: WebSocket update to active Table stream
    end
    API-->>Customer: HTTP 201 Created (OrderResponse)
```

---

## 2. Order Lifecycle & Kitchen State Machine Flow

```mermaid
stateDiagram-v2
    [*] --> PLACED: Customer scans QR & places order
    PLACED --> ACCEPTED: Admin / Chef accepts order
    PLACED --> CANCELLED: Customer cancels (only allowed in PLACED stage)
    ACCEPTED --> IN_KITCHEN: Chef taps 'Done' / starts prep
    ACCEPTED --> SERVED: Order served directly
    ACCEPTED --> COMPLETED: Order finalized
    IN_KITCHEN --> COMPLETED: Cooking finished & fulfilled
    SERVED --> COMPLETED: Dining complete
    COMPLETED --> [*]
    CANCELLED --> [*]

    note right of PLACED
        Initial status on creation.
        Editable / Cancellable by guest.
    end note

    note right of IN_KITCHEN
        Kitchen prep active.
        Order locked from guest cancellation.
    end note

    note right of COMPLETED
        Final state.
        Included in settled session billing.
    end note
```

---

## 3. Dining Session Billing, Ledger & Immediate Table Release Flow

```mermaid
sequenceDiagram
    autonumber
    actor Admin as Admin Cashier
    participant API as Billing API (/api/v1/billing/sessions/{id}/generate)
    participant Svc as SessionService
    participant DB as PostgreSQL DB
    participant WS as WebSocket Manager
    actor Guest as Table Guests

    Admin->>API: POST /sessions/{id}/generate (discountPercentage)
    API->>Svc: generate_final_bill(session_id, discount_percentage)
    Svc->>DB: Fetch all non-cancelled orders for session
    Svc->>Svc: Aggregate subtotal, compute discount & taxes
    Svc->>DB: Upsert BillingInvoice (bill_type=SESSION, status=PENDING)
    Svc->>DB: Update Session status = BILL_GENERATED
    critical Immediate Physical Table Release
        Svc->>DB: Table status = AVAILABLE
        Svc->>DB: COMMIT Transaction
        Svc->>WS: notify_table_status_updated(table_id, "AVAILABLE")
    end
    WS-->>Admin: Table visual marker turns Green (AVAILABLE)
    WS-->>Guest: Bill is ready for payment
    API-->>Admin: BillReceiptResponse (printable receipt)

    Note over Admin,DB: Later: Guest pays cash / UPI
    Admin->>API: POST /sessions/{id}/settle (payment_method=CASH)
    API->>Svc: settle_session_bill(session_id, payment_method)
    Svc->>DB: BillingInvoice payment_status = PAID
    Svc->>DB: Session status = CLOSED
    Svc->>DB: Orders payment_status = PAID
    Svc->>DB: Check if table has another active OPEN session
    Svc->>DB: COMMIT Transaction
    Svc->>WS: notify_payment_settled(order_id, invoice_number, "PAID")
    API-->>Admin: InvoiceResponse (settled)
```
