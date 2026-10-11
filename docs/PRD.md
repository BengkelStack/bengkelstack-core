# Product Requirements Document (PRD): BengkelStack Core

**Document Version:** 1.0.0  
**Status:** APPROVED (Gate 1 Passed)  
**Author:** PM Lead / System Architect  
**Domain:** bengkelstack.com  

---

## 1. Problem Statement (5 Whys Analysis)

Independent motorcycle repair shops lose 15% to 28% of monthly gross margins due to inconsistent labor pricing versus parts retail markup, combined with manual paper receipt friction.

1. **Why 1:** Why do independent workshops suffer profit leakage?  
   *Because cashiers and mechanics estimate installation fees arbitrarily without standardized flat-rate matrices.*
2. **Why 2:** Why is installation pricing arbitrary?  
   *Because generic retail POS systems only support single-price retail items and do not separate Takeaway (Retail/DIY) from In-Shop Installation (Retail + Model-Specific Labor).*
3. **Why 3:** Why not use authorized OEM dealer software (Honda AHASS / Yamaha DDS)?  
   *Because independent workshops service multi-brand fleets (Honda, Yamaha, Suzuki, Kawasaki, Vespa) with aftermarket replacement parts not indexed in closed dealer catalogs.*
4. **Why 4:** Why do mechanics avoid logging repair histories?  
   *Because manual desktop keyboard input takes 3 to 5 minutes per vehicle during peak rush hours when hands are soiled with oil.*
5. **Why 5 (Root Cause):**  
   *Lack of an edge-first, lightweight workshop operating system that provides instant plate number lookups (< 1s), model-tiered flat-rate labor calculation, and invoice vision OCR without costly proprietary hardware.*

---

## 2. Target KPIs & Success Metrics

| Metric | Manual Industry Baseline | BengkelStack Target (Local & Cloud) |
| :--- | :--- | :--- |
| **Plate History Lookup** | 180 - 300s (Paper logbook search) | **< 1.0s** (Instant indexed search) |
| **Checkout Time per Order** | 120s | **< 20s** (Auto retail vs installed toggle) |
| **Pricing Accuracy** | ~72% (Frequent unbilled labor) | **100% deterministic** via rule engine |
| **API Response Latency (P95)** | N/A | **< 50 ms** on local SQLite WAL |
| **Runtime Dependency Overhead** | 100+ MB npm/pip bloat | **0 MB extra pip runtime** (Python 3 stdlib) |

---

## 3. User Personas

### Persona A: Dimas (38) — Workshop Owner & Store Manager
- **Context:** Operates an independent 4-bay motorcycle repair shop with 6 mechanics, generating $3,000 - $6,000 monthly turnover.
- **Pain Points:**
  - Suspects unrecorded labor charges go into mechanic pockets due to manual paper notes.
  - Inability to track parts inventory turns because paper distributor invoices pile up unindexed.
  - Wants computing infrastructure without paying high monthly SaaS subscription fees.
- **Goals:**
  - One-click POS checkout separating retail takeaway from in-shop installation.
  - Persistent customer repair logs searchable by license plate.

### Persona B: Budi (27) — Senior Mechanic & Operational Cashier
- **Context:** Lead technician servicing 15 to 25 bikes daily; manages POS checkout when the primary cashier is away.
- **Pain Points:**
  - Forgets exact installation fee formulas for complex assemblies (e.g. CVT clutch replacement vs basic oil change).
  - Customers dispute prices claiming "last week you charged less".
- **Goals:**
  - Instant vehicle lookup showing last service date, odometer reading, and parts replaced.
  - Automatic tiered labor fee calculation matching motorcycle class (Automatic Scooter, Moped, Sport).

---

## 4. Scope Boundary

### In-Scope (Core Engine & MVP):
- **Core Engine (`bengkel_pricing_engine`):**
  - Instant Vehicle & Customer Lookup via license plate regex.
  - Dynamic Dual-Tier Pricing: Retail (Takeaway) vs Retail + Vehicle-Specific Labor.
  - Work Order Service & Lifecycle (Draft -> In Progress -> Completed -> Cancelled).
  - Master Data CRUD: Parts, Services, Motorcycle Models, Custom Model Labor Overrides.
  - Direct Receipt Formatting for 58mm/80mm ESC/POS thermal printers.
  - Multimodal Supplier Invoice Parser with financial determinism validation.
  - Idempotency guard for atomic checkout transactions.
- **Frontend / Presentation (`bengkelstack-site` & Web POS):**
  - Responsive POS Interface (Touch-optimized, dark mode high contrast).
  - Public Gateway (bengkelstack.com) with interactive pricing simulator and invoice intake demo.
- **Architecture Standards:**
  - 5-Gate Enterprise SDLC compliance.
  - Zero-dependency runtime (Python stdlib HTTP server & SQLite WAL mode).

### Out-of-Scope (Post-MVP Phases):
- Dynamic bank QR payment gateway integrations (staged for Cloud sync phase).
- Multi-branch consolidated general ledger accounting.
- Proprietary biometric fingerprint attendance hardware.
