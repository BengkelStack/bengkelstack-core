# Software Requirements Specification (SRS): BengkelStack Core

**Document Version:** 1.0.0  
**Status:** APPROVED (Gate 2 Passed)  
**Standard:** IEEE Std 830-1998 / ISO/IEC 25010:2023  
**System:** BengkelStack Workshop Operating System  

---

## 1. Introduction & Purpose

This document defines the software engineering requirements for the BengkelStack system. The system is engineered to run autonomously on on-premise workshop workstations (offline-capable edge execution) and interface with the cloud gateway at `bengkelstack.com`.

---

## 2. Functional Requirements (FR)

### FR-01: Plate Number Sanitization & Vehicle Lookup
- **Description:** The system must accept vehicle registration plate input strings (e.g. `B 1234 XYZ`, `TX 9988 USA`, `DK 9901 AA`).
- **Input:** Query string `plate`.
- **Business Rules:** 
  - Extra whitespace must be stripped, letters capitalized, and format normalized.
  - If the plate is registered, return vehicle model (`motor_model_id`, `motor_name`), last registered owner, phone number, and total visit count.
  - If the plate is unregistered, return `not_found` with an instant registration flag without interrupting cashier checkout flow.

### FR-02: Dual-Tier Dynamic Pricing Engine
- **Description:** Every catalog item has two dynamic price calculations:
  1. **Retail Mode (`TAKE_AWAY` / Retail):** Base retail sales price only (`price`).
  2. **Install Mode (`INSTALL` / Workshop):** Base retail price + installation labor (`price + install_fee`).
- **Business Rules:**
  - Pure labor services (`item_type = 'SERVICE'`) always have `price = 0` and charge only `install_fee` (service labor).
  - Default installation fees are sourced from the parts master table but can be overridden per motorcycle model.

### FR-03: Model-Specific Custom Installation Fee
- **Description:** Mechanical assembly complexity varies by vehicle model (e.g. body disassembly on a Honda PCX is more demanding than on a Honda Supra).
- **Business Rules:**
  - If an entry exists in `model_custom_fees` for the pair `(motor_model_id, part_id)`, this value overrides `default_install_fee`.
  - If no override exists, fallback to `default_install_fee` in `parts`.

### FR-04: Work Order Lifecycle Management
- **Description:** Service visits and billing are managed via the Work Order entity (`work_orders`).
- **State Machine:**
  - `DRAFT`: Vehicle entered bay, tentative parts and service estimate.
  - `IN_PROGRESS`: Technician actively servicing the vehicle.
  - `COMPLETED`: Work order settled at cashier, inventory deducted, invoice locked.
  - `CANCELLED`: Service order voided before payment.
- **Invariant:** Completed work orders are immutable snapshots.

### FR-05: Historical Service Record Audit by Plate
- **Description:** Cashiers and mechanics can inspect all chronological past visits by license plate number.
- **Output:** Chronological list of service dates, replaced parts, performed services, and settled grand totals.

### FR-06: Master Catalog Management
- **Description:** Management of spare parts and standardized service operations.
- **Attributes:** SKU code, item name, barcode/OEM code, wholesale cost (COGS), retail price, default labor fee, and physical inventory stock.

### FR-07: In-Memory Cart Pricing Calculation API
- **Description:** Low-latency pricing calculation endpoint prior to final checkout (`/api/calculate`).
- **Input:** `motor_model_id` (integer) and `items` array (`[item_type, item_id, quantity, action_type]`).
- **Output:** Parts subtotal, installation labor total, discount, grand total, and itemized tier breakdown.

### FR-08: Thermal Receipt Formatting
- **Description:** Generates formatted monospaced output for 58mm and 80mm ESC/POS thermal receipt printers.
- **Format:** Workshop header, plate number, timestamp, itemized lines, parts subtotal, labor total, cash tender, change due, and warranty footer.

---

## 3. Non-Functional Requirements (NFR)

### NFR-01: Performance Efficiency & Latency
- **Target Latency (P95):** API queries `/api/calculate`, `/api/parts`, and `/api/vehicle-lookup` must respond within `<= 50ms` on local workstations.
- **Throughput:** Capable of handling a minimum of 200 requests per second locally without UI frame drops.

### NFR-02: Reliability & Data Concurrency
- **Database Engine:** SQLite 3 with Write-Ahead Logging (`WAL`) mode enabled.
- **Connection Isolation:** Thread-scoped database connections with `busy_timeout = 5000ms` to prevent database lock contention.

### NFR-03: Architectural Footprint & Zero-Dependency (Ponytail Standard)
- **Runtime Backend:** 100% Python Standard Library (`http.server`, `sqlite3`, `urllib.parse`, `json`, `os`, `sys`).
- **Zero PIP Overhead:** Requires zero third-party pip dependencies for core runtime execution.

### NFR-04: Security & Input Sanitation (ISO/IEC 27001 Alignment)
- **SQL Injection Prevention:** 100% parameterized queries (`?`). String interpolation for SQL execution is strictly forbidden.
- **Timing-Attack Immune Auth:** External API token verification uses constant-time string comparison (`secrets.compare_digest`).
- **Network Boundaries:** Untrusted non-loopback IPs receive `403 Forbidden` unless authorized. Sliding-window rate limiting (120 req/min) and 1MB payload ceilings enforced.
