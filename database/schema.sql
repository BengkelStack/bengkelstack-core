-- PRAGMA configuration
PRAGMA foreign_keys = ON;

-- 1. Motor Models (Master Model Kendaraan)
CREATE TABLE IF NOT EXISTS motor_models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand TEXT NOT NULL,
    model_name TEXT NOT NULL
);

-- 2. Parts (Master Suku Cadang)
CREATE TABLE IF NOT EXISTS parts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    part_code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    cost_price REAL NOT NULL DEFAULT 0,
    retail_price REAL NOT NULL DEFAULT 0,
    default_install_fee REAL NOT NULL DEFAULT 0
);

-- 3. Services (Master Jasa Servis)
CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_name TEXT NOT NULL,
    standard_fee REAL NOT NULL DEFAULT 0
);

-- 4. Part Motor Installations (Matriks Ongkos Pasang Khusus Per Model Motor)
CREATE TABLE IF NOT EXISTS part_motor_installations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    part_id INTEGER NOT NULL,
    motor_model_id INTEGER NOT NULL,
    custom_install_fee REAL NOT NULL DEFAULT 0,
    FOREIGN KEY (part_id) REFERENCES parts(id) ON DELETE CASCADE,
    FOREIGN KEY (motor_model_id) REFERENCES motor_models(id) ON DELETE CASCADE,
    UNIQUE(part_id, motor_model_id)
);

-- 5. Vehicles (Kendaraan Pelanggan)
CREATE TABLE IF NOT EXISTS vehicles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_number TEXT UNIQUE NOT NULL,
    motor_model_id INTEGER NOT NULL,
    customer_name TEXT NOT NULL,
    FOREIGN KEY (motor_model_id) REFERENCES motor_models(id) ON DELETE RESTRICT
);

-- 6. Work Orders (Surat Perintah Kerja / Transaksi Servis)
CREATE TABLE IF NOT EXISTS work_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN',
    total_amount REAL NOT NULL DEFAULT 0,
    payment_method TEXT NOT NULL DEFAULT 'CASH',
    cash_received REAL NOT NULL DEFAULT 0,
    change_amount REAL NOT NULL DEFAULT 0,
    idempotency_key TEXT UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE RESTRICT
);

-- 7. Work Order Items (Rincian Item Transaksi)
CREATE TABLE IF NOT EXISTS work_order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_id INTEGER NOT NULL,
    item_type TEXT NOT NULL CHECK(item_type IN ('part', 'service')),
    item_id INTEGER NOT NULL,
    action_type TEXT NOT NULL CHECK(action_type IN ('takeaway', 'installed')),
    price REAL NOT NULL DEFAULT 0,
    install_fee REAL NOT NULL DEFAULT 0,
    subtotal REAL NOT NULL DEFAULT 0,
    FOREIGN KEY (work_order_id) REFERENCES work_orders(id) ON DELETE CASCADE
);

-- Indexes for fast query lookup
CREATE INDEX IF NOT EXISTS idx_vehicles_plate ON vehicles(plate_number);
CREATE INDEX IF NOT EXISTS idx_vehicles_model ON vehicles(motor_model_id);
CREATE INDEX IF NOT EXISTS idx_pmi_lookup ON part_motor_installations(part_id, motor_model_id);
CREATE INDEX IF NOT EXISTS idx_wo_vehicle ON work_orders(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_woi_order ON work_order_items(work_order_id);

-- 8. Workshop Settings (Multi-Currency & Regional Configurations)
CREATE TABLE IF NOT EXISTS workshop_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    workshop_name TEXT NOT NULL DEFAULT 'BENGKELSTACK WORKSHOP OS',
    currency_symbol TEXT NOT NULL DEFAULT 'Rp',
    currency_code TEXT NOT NULL DEFAULT 'IDR',
    receipt_header TEXT DEFAULT 'SERVICE & REPAIR CENTER',
    receipt_footer TEXT DEFAULT 'Service Warranty 7 Days / 500 KM',
    min_margin_pct REAL NOT NULL DEFAULT 25.0
);

-- 9. Schema Migrations (Pelacak Versi Migrasi)
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
