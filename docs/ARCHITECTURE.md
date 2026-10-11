# ARCHITECTURE: BengkelStack Workshop Operating System

**Document Version:** 1.0.0  
**Status:** APPROVED (Gate 3 Passed)  
**System Topology:** Edge-First Hybrid POS with Cloud Staging  

---

## 1. Architectural Philosophy & Layered Topology

BengkelStack is engineered around an **Edge-First / Local-First Resilience** paradigm: physical workshops must remain 100% operational for counter checkout and thermal printing even during total ISP internet outages. Local records synchronize asynchronously with the `bengkelstack.com` cloud gateway.

### Architectural Layer Topology:

```text
+-----------------------------------------------------------------------+
|                    PRESENTATION / CLIENT LAYER                        |
|  - BengkelStack POS Web UI (Vanilla JS, Touch-Optimized, Thermal Print)|
|  - bengkelstack.com Landing Site & Invoice OCR Simulator (Tailwind)    |
+-----------------------------------^-----------------------------------+
                                    | HTTP / REST (JSON)
+-----------------------------------v-----------------------------------+
|                     APPLICATION & ROUTING LAYER                       |
|  - app/server.py (Python stdlib ThreadingHTTPServer + urllib router)  |
|  - Request Validation & Response Serialization                        |
+-----------------------------------^-----------------------------------+
                                    | Direct In-Memory Call
+-----------------------------------v-----------------------------------+
|                     CORE DOMAIN & RULE ENGINE                         |
|  - app/pricing_engine.py (Dual-Tier Pricing: Retail vs Installed)     |
|  - app/work_order_service.py (Work Order State Machine & Lifecycle)   |
|  - app/custom_fee_repository.py (Model-Specific Custom Install Logic) |
+-----------------------------------^-----------------------------------+
                                    | Parametric SQL Query (?)
+-----------------------------------v-----------------------------------+
|                    DATA ACCESS & REPOSITORIES                         |
|  - app/repositories.py (Motor Models, Parts Catalog, Services)        |
|  - database/db.py (Connection Pool, Migration Manager)                |
+-----------------------------------^-----------------------------------+
                                    | C-Level Engine Driver
+-----------------------------------v-----------------------------------+
|                    PHYSICAL PERSISTENCE LAYER                         |
|  - SQLite 3 (WAL Mode, synchronous=NORMAL, busy_timeout=5000ms)       |
|  - database/workshop.db (Local Storage)                               |
+-----------------------------------------------------------------------+
```

---

## 2. Third Normal Form (3NF) Data Model & Schemas

### Relational Schema Definitions:

1. **`motor_models` (Vehicle Models):**
   - `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
   - `name` (TEXT NOT NULL UNIQUE) — e.g. "Honda Vario 125/150", "Yamaha NMAX 155", "Honda Beat ESP"
   - `brand` (TEXT NOT NULL) — e.g. "Honda", "Yamaha", "Suzuki", "Kawasaki"
   - `engine_category` (TEXT NOT NULL) — "MATIC", "MOPED", "SPORT", "BIGBIKE"

2. **`parts` (Parts Catalog):**
   - `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
   - `sku` (TEXT UNIQUE)
   - `name` (TEXT NOT NULL)
   - `category` (TEXT NOT NULL) — "OIL", "TIRE", "BRAKE", "DRIVE", "ELECTRICAL"
   - `purchase_cost` (REAL DEFAULT 0) — Cost of Goods Sold (COGS)
   - `retail_price` (REAL NOT NULL) — Takeaway retail price
   - `default_install_fee` (REAL NOT NULL DEFAULT 0) — Default installation labor fee
   - `stock_qty` (INTEGER NOT NULL DEFAULT 0)
   - `created_at` (TIMESTAMP DEFAULT CURRENT_TIMESTAMP)

3. **`services` (Labor Services Catalog):**
   - `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
   - `code` (TEXT UNIQUE)
   - `name` (TEXT NOT NULL) — e.g. "Routine Tune-Up", "Tire Replacement", "CVT Overhaul"
   - `fee` (REAL NOT NULL)
   - `estimated_minutes` (INTEGER DEFAULT 30)

4. **`model_custom_fees` (Model-Specific Custom Labor Overrides):**
   - `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
   - `motor_model_id` (INTEGER NOT NULL, FK -> `motor_models.id`)
   - `part_id` (INTEGER NOT NULL, FK -> `parts.id`)
   - `custom_install_fee` (REAL NOT NULL)
   - *Constraint:* `UNIQUE(motor_model_id, part_id)`

5. **`vehicles` (Customer Vehicle Fleet):**
   - `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
   - `plate_number` (TEXT NOT NULL UNIQUE) — index `idx_plate`
   - `motor_model_id` (INTEGER NOT NULL, FK -> `motor_models.id`)
   - `customer_name` (TEXT NOT NULL)
   - `phone_number` (TEXT)
   - `last_visit_at` (TIMESTAMP)

6. **`work_orders` (Work Orders & Billing):**
   - `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
   - `order_number` (TEXT NOT NULL UNIQUE) — format: `WO-YYYYMMDD-XXXX`
   - `vehicle_id` (INTEGER NOT NULL, FK -> `vehicles.id`)
   - `customer_name` (TEXT NOT NULL)
   - `plate_number` (TEXT NOT NULL)
   - `motor_model_id` (INTEGER NOT NULL)
   - `status` (TEXT NOT NULL DEFAULT 'DRAFT') — `DRAFT`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED`
   - `payment_method` (TEXT NOT NULL DEFAULT 'CASH')
   - `cash_received` (REAL NOT NULL DEFAULT 0)
   - `change_amount` (REAL NOT NULL DEFAULT 0)
   - `idempotency_key` (TEXT UNIQUE)
   - `total_parts` (REAL NOT NULL DEFAULT 0)
   - `total_labor` (REAL NOT NULL DEFAULT 0)
   - `grand_total` (REAL NOT NULL DEFAULT 0)
   - `notes` (TEXT)
   - `created_at` (TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
   - `completed_at` (TIMESTAMP)

7. **`work_order_items` (Work Order Line Items):**
   - `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
   - `work_order_id` (INTEGER NOT NULL, FK -> `work_orders.id` ON DELETE CASCADE)
   - `item_type` (TEXT NOT NULL) — `PART` or `SERVICE`
   - `item_id` (INTEGER NOT NULL)
   - `item_name` (TEXT NOT NULL)
   - `quantity` (INTEGER NOT NULL DEFAULT 1)
   - `action_type` (TEXT NOT NULL) — `TAKE_AWAY` or `INSTALL`
   - `unit_price` (REAL NOT NULL)
   - `unit_install_fee` (REAL NOT NULL DEFAULT 0)
   - `subtotal` (REAL NOT NULL)

---

## 3. Work Order State Machine

```text
      +---------------+
      |    (New)      |
      +-------+-------+
              |
              v
       [    DRAFT     ]  <---+
              |              |
              | Estimate OK  | Item updates/revisions
              v              |
       [ IN_PROGRESS  ]  ----+
              |
      +-------+-------+
      |               |
      v               v
 [ COMPLETED ]  [ CANCELLED ]
(Locked & Paid)   (Voided)
```

- **DRAFT:** Line items can be dynamically added or modified. Totals calculated in real-time by pricing engine.
- **IN_PROGRESS:** Mechanic retrieves parts from store; inventory reserved.
- **COMPLETED:** Cashier receives payment (Cash, Card, QR); thermal receipt formatted; inventory deducted; record locked immutable.
- **CANCELLED:** Transaction voided before checkout; reserved inventory released back to shelves.

---

## 4. Staged Cloud Deployment Strategy

1. **Stage 1 (Autonomous Edge - Implemented):** Core engine runs on localhost (port 8089) on the workshop cashier computer with local SQLite WAL database.
2. **Stage 2 (Edge Cloud Hybrid - Staging):** Deploy static landing page to Cloudflare Pages (`bengkelstack.com`), configure DNS and founder communications (`founder@bengkelstack.com`).
3. **Stage 3 (Multi-Tenant Cloud Sync - Production):** Lightweight sync agent asynchronously streams encrypted daily transaction snapshots to the central database for mobile owner dashboards.
