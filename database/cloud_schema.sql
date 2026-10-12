-- ============================================================================
-- BengkelStack Cloud Master & Multi-Tenant Database Schema
-- Dialect: SQLite 3 (WAL Mode Compatible)
-- Standards: 3NF Relational, Foreign Keys Enforced, Zero External Dependency
-- ============================================================================

PRAGMA foreign_keys = ON;

-- 1. Tenants (Master Bengkel / Pelanggan SaaS)
CREATE TABLE IF NOT EXISTS tenants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    country_code TEXT NOT NULL DEFAULT 'ID',
    currency TEXT NOT NULL DEFAULT 'IDR',
    plan TEXT NOT NULL DEFAULT 'FREE' CHECK(plan IN ('FREE', 'STARTER', 'PRO', 'ENTERPRISE')),
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE', 'SUSPENDED', 'TRIAL', 'CANCELLED')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 2. Users (Pengguna Cloud: SuperAdmin, Owner Bengkel, Staff Kasir/Mekanik)
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'STAFF' CHECK(role IN ('SUPERADMIN', 'OWNER', 'CASHIER', 'MECHANIC', 'STAFF')),
    full_name TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);

-- 3. Tenant Subscriptions (Siklus Penagihan & Lisensi)
CREATE TABLE IF NOT EXISTS tenant_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    plan_id TEXT NOT NULL CHECK(plan_id IN ('FREE', 'STARTER', 'PRO', 'ENTERPRISE')),
    billing_cycle TEXT NOT NULL DEFAULT 'MONTHLY' CHECK(billing_cycle IN ('MONTHLY', 'ANNUAL', 'LIFETIME')),
    valid_until TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);

-- 4. Tenant Sync Keys (Kredensial API Sync Edge-to-Cloud POS Lokal)
CREATE TABLE IF NOT EXISTS tenant_sync_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    api_key_hash TEXT NOT NULL UNIQUE,
    prefix TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT 'Edge Terminal',
    last_sync_at TIMESTAMP,
    is_revoked INTEGER NOT NULL DEFAULT 0 CHECK(is_revoked IN (0, 1)),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);

-- 5. Sync Events Log (Audit Trail & Idempotent Event Log Transaksi Edge)
CREATE TABLE IF NOT EXISTS sync_events_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    event_type TEXT NOT NULL CHECK(event_type IN (
        'WORK_ORDER_CREATED',
        'WORK_ORDER_COMPLETED',
        'INVENTORY_ADJUSTED',
        'PRICE_UPDATED',
        'SNAPSHOT_UPLOAD',
        'HEARTBEAT'
    )),
    payload_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    sync_status TEXT NOT NULL DEFAULT 'PENDING' CHECK(sync_status IN ('PENDING', 'PROCESSED', 'FAILED', 'REJECTED')),
    error_message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
    UNIQUE(tenant_id, payload_hash)
);

-- 6. Sessions (Opaque Bearer Token Storage)
CREATE TABLE IF NOT EXISTS user_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Indexes for Fast Scoped Queries & Tenant Isolation Enforcement
CREATE INDEX IF NOT EXISTS idx_tenants_slug ON tenants(slug);
CREATE INDEX IF NOT EXISTS idx_tenants_status ON tenants(status);
CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_subscriptions_tenant ON tenant_subscriptions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_sync_keys_tenant ON tenant_sync_keys(tenant_id);
CREATE INDEX IF NOT EXISTS idx_sync_keys_hash ON tenant_sync_keys(api_key_hash);
CREATE INDEX IF NOT EXISTS idx_sync_events_tenant_status ON sync_events_log(tenant_id, sync_status);
CREATE INDEX IF NOT EXISTS idx_sync_events_hash ON sync_events_log(tenant_id, payload_hash);
CREATE INDEX IF NOT EXISTS idx_sessions_hash ON user_sessions(token_hash);
