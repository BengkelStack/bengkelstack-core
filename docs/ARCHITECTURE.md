# ARCHITECTURE: BengkelStack Workshop Operating System
**Document Version:** 1.0.0  
**Status:** APPROVED (Gate 3 Passed)  
**System Topology:** Edge-First Hybrid POS with Cloud Staging  

---

## 1. Architectural Philosophy & Layered Topology

BengkelStack dirancang dengan pendekatan **Edge-First / Local-First Resilience**: bengkel harus tetap dapat beroperasi 100% melayani kasir dan mencetak nota meskipun koneksi internet provider mati total. Data lokal disinkronkan secara asinkron ke cluster cloud `bengkelstack.com`.

### Diagram Layer Arsitektur:

```
+-----------------------------------------------------------------------+
|                    PRESENTATION / CLIENT LAYER                        |
|  - BengkelStack POS Web UI (Vanilla JS, Touch-Optimized, Thermal Print)|
|  - bengkelstack.com Landing Site & Invoice OCR Simulator (Tailwind)    |
+-----------------------------------^-----------------------------------+
                                    | HTTP / REST (JSON)
+-----------------------------------v-----------------------------------+
|                     APPLICATION & ROUTING LAYER                       |
|  - app/server.py (Python stdlib http.server + urllib router)           |
|  - Request Validation & Response Serialization                        |
+-----------------------------------^-----------------------------------+
                                    | Direct In-Memory Call
+-----------------------------------v-----------------------------------+
|                     CORE DOMAIN & RULE ENGINE                         |
|  - app/pricing_engine.py (Dual-Tier Pricing: Retail vs Install)       |
|  - app/work_order_service.py (Work Order State Machine & Lifecycle)   |
|  - app/custom_fee_repository.py (Model-Specific Custom Install Logic) |
+-----------------------------------^-----------------------------------+
                                    | Parametric SQL Query
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

1. **`motor_models` (Model Kendaraan):**
   - `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
   - `name` (TEXT NOT NULL UNIQUE) — contoh: "Honda Vario 125/150", "Yamaha NMAX 155", "Honda Beat ESP"
   - `brand` (TEXT NOT NULL) — contoh: "Honda", "Yamaha", "Suzuki", "Kawasaki"
   - `engine_category` (TEXT NOT NULL) — "MATIC", "BEBEK", "SPORT", "BIGBIKE"

2. **`parts` (Katalog Suku Cadang):**
   - `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
   - `sku` (TEXT UNIQUE)
   - `name` (TEXT NOT NULL)
   - `category` (TEXT NOT NULL) — "OIL", "TIRE", "BRAKE", "DRIVE", "ELECTRICAL"
   - `purchase_cost` (REAL DEFAULT 0) — Harga Pokok Penjualan (HPP)
   - `retail_price` (REAL NOT NULL) — Harga Bawa Pulang (Retail)
   - `default_install_fee` (REAL NOT NULL DEFAULT 0) — Default ongkos pasang
   - `stock_qty` (INTEGER NOT NULL DEFAULT 0)
   - `created_at` (TIMESTAMP DEFAULT CURRENT_TIMESTAMP)

3. **`services` (Katalog Jasa Murni):**
   - `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
   - `code` (TEXT UNIQUE)
   - `name` (TEXT NOT NULL) — contoh: "Servis Ringan / Tune Up", "Ganti Ban Luar", "Bongkar CVT"
   - `fee` (REAL NOT NULL)
   - `estimated_minutes` (INTEGER DEFAULT 30)

4. **`model_custom_fees` (Tabel Override Ongkos Model):**
   - `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
   - `motor_model_id` (INTEGER NOT NULL, FK -> `motor_models.id`)
   - `part_id` (INTEGER NOT NULL, FK -> `parts.id`)
   - `custom_install_fee` (REAL NOT NULL)
   - *Constraint:* `UNIQUE(motor_model_id, part_id)`

5. **`vehicles` (Data Kendaraan Pelanggan):**
   - `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
   - `plate_number` (TEXT NOT NULL UNIQUE) — index `idx_plate`
   - `motor_model_id` (INTEGER NOT NULL, FK -> `motor_models.id`)
   - `customer_name` (TEXT NOT NULL)
   - `phone_number` (TEXT)
   - `last_visit_at` (TIMESTAMP)

6. **`work_orders` (Transaksi / Surat Perintah Kerja):**
   - `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
   - `order_number` (TEXT NOT NULL UNIQUE) — format: `WO-YYYYMMDD-XXXX`
   - `vehicle_id` (INTEGER NOT NULL, FK -> `vehicles.id`)
   - `customer_name` (TEXT NOT NULL)
   - `plate_number` (TEXT NOT NULL)
   - `motor_model_id` (INTEGER NOT NULL)
   - `status` (TEXT NOT NULL DEFAULT 'DRAFT') — `DRAFT`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED`
   - `total_parts` (REAL NOT NULL DEFAULT 0)
   - `total_labor` (REAL NOT NULL DEFAULT 0)
   - `grand_total` (REAL NOT NULL DEFAULT 0)
   - `notes` (TEXT)
   - `created_at` (TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
   - `completed_at` (TIMESTAMP)

7. **`work_order_items` (Rincian Item Nota Servis):**
   - `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
   - `work_order_id` (INTEGER NOT NULL, FK -> `work_orders.id` ON DELETE CASCADE)
   - `item_type` (TEXT NOT NULL) — `PART` atau `SERVICE`
   - `item_id` (INTEGER NOT NULL)
   - `item_name` (TEXT NOT NULL)
   - `quantity` (INTEGER NOT NULL DEFAULT 1)
   - `action_type` (TEXT NOT NULL) — `TAKE_AWAY` atau `INSTALL`
   - `unit_price` (REAL NOT NULL)
   - `unit_install_fee` (REAL NOT NULL DEFAULT 0)
   - `subtotal` (REAL NOT NULL)

---

## 3. Work Order State Machine

```
      +---------------+
      |   (Baru)      |
      +-------+-------+
              |
              v
       [    DRAFT     ]  <---+
              |              |
              | Estimasi OK  | Tambah item/revisi
              v              |
       [ IN_PROGRESS  ]  ----+
              |
      +-------+-------+
      |               |
      v               v
 [ COMPLETED ]  [ CANCELLED ]
 (Final & Kunci) (Dibatalkan)
```

- **DRAFT:** Item dapat ditambah/dihapus secara dinamis. Total dikalkulasi oleh pricing engine.
- **IN_PROGRESS:** Mekanik mengambil part dari gudang; stok direservasi.
- **COMPLETED:** Kasir menerima pembayaran (Tunai/Transfer/QRIS); nota dicetak; stok terpotong permanen; entri menjadi immutable.
- **CANCELLED:** Transaksi dibatalkan sebelum kasir; part dikembalikan ke rak.

---

## 4. Staged Cloud Deployment Strategy

1. **Tahap 1 (Lokal Mandiri - Selesai):** Engine berjalan di localhost (port 8089) pada laptop kasir dengan database SQLite WAL.
2. **Tahap 2 (Edge Cloud Hybrid - Staging):** Deploy Landing Page statis ke Cloudflare Pages (`bengkelstack.com`), arahkan DNS dan email (`founder@bengkelstack.com`).
3. **Tahap 3 (Multi-Tenant Cloud Sync - Produksi):** Sync agent asinkron mengirimkan snapshot transaksi harian terenkripsi ke database pusat untuk reporting pemilik bengkel via mobile.
