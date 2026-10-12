# BengkelStack Cloud Multi-Tenant Architecture & API Specification

**Dokumen Versi:** 2.0.0  
**Status:** DRAFT / REVIEW  
**Fokus:** Tier 2 Cloud Master Admin, Multi-Tenancy Data Model, Edge-to-Cloud Sync & REST API  

---

## 1. Skema Database Multi-Tenant (SQLite 3 WAL)

Arsitektur database dirancang dalam 3NF relasional dengan integritas referensial penuh (`PRAGMA foreign_keys = ON`).

### DDL SQL

```sql
PRAGMA foreign_keys = ON;

-- 1. Master Tenants
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

-- 2. Cloud Users & Identity
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

-- 3. Tenant Subscriptions & Billing
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

-- 4. Edge-to-Cloud Sync API Keys
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

-- 5. Sync Events Log & Audit Trail
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

-- Indexes
CREATE INDEX IF NOT EXISTS idx_tenants_slug ON tenants(slug);
CREATE INDEX IF NOT EXISTS idx_tenants_status ON tenants(status);
CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_subscriptions_tenant ON tenant_subscriptions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_sync_keys_tenant ON tenant_sync_keys(tenant_id);
CREATE INDEX IF NOT EXISTS idx_sync_keys_hash ON tenant_sync_keys(api_key_hash);
CREATE INDEX IF NOT EXISTS idx_sync_events_tenant_status ON sync_events_log(tenant_id, sync_status);
CREATE INDEX IF NOT EXISTS idx_sync_events_hash ON sync_events_log(tenant_id, payload_hash);
```

---

## 2. Evaluasi Strategi Isolasi Tenant (Python + SQLite WAL)

| Parameter | Opsi A: Shared DB / Shared Schema (Row-Level Tenancy) | Opsi B: DB-per-Tenant (Isolated File Sharding) |
| :--- | :--- | :--- |
| **Penyimpanan Fisik** | 1 file SQLite (`cloud_master.db`) untuk semua tenant. | 1 Master Catalog DB (`catalog.db`) + 1 file per tenant (`tenants/{id}.db`). |
| **Isolasi Data** | Logikal via kolom `tenant_id` pada tiap query. | Fisik total di level berkas OS. Zero cross-tenant SQL risk. |
| **Manajemen Koneksi** | 1 connection pool sederhana di Python stdlib. | Router dinamis: pool file handle on-demand via tenant identifier. |
| **Kueri SuperAdmin / Cross-Tenant** | Sangat cepat & trivial (`SELECT ... GROUP BY tenant_id`). | Butuh agregasi bertahap, loop file, atau `ATTACH DATABASE`. |
| **Backup & Restore** | Parsial SQL dump (sulit restore 1 tenant secara terpisah). | Trivial: copy/backup/restore file SQLite `.db` tunggal milik bengkel. |
| **Sync Alignment Edge-to-Cloud** | Edge mem-push JSON event delta ke tabel tunggal. | Edge bisa rsync/stream WAL file snapshot langsung per tenant. |
| **Batas Skalabilitas SQLite** | Batas write lock WAL tunggal jika traffic serentak tinggi. | Concurrency write terisolasi per file; disk IO paralel. |

### Rekomendasi BengkelStack Tier 2:
Gunakan **Pola Hibrida Terdistribusi (Hybrid Master + Row-Level Cloud Ingestion)**:
1. **Master DB (`cloud_master.db`)**: Menggunakan **Shared DB / Shared Schema** untuk tabel `tenants`, `users`, `tenant_subscriptions`, `tenant_sync_keys`, dan `sync_events_log`. Ini memastikan otentikasi login, pengelolaan langganan, dan pemantauan status bengkel oleh SuperAdmin tetap cepat, terpusat, dan minim overhead operasional.
2. **Operational Mirroring (Opsional untuk Tier 3)**: Event log diolah ke agregat dashboard owner. Jika tenant membutuhkan audit forensik mandiri, snapshot SQLite lokal (`workshop.db`) diunggah sebagai blob file backup independen.

---

## 3. Kontrak API Endpoints Inti (Draft REST API)

### 3.1. POST `/api/v1/auth/register`
Mendaftarkan tenant bengkel baru beserta akun Owner pertama.
- **Access:** Public
- **Request Body:**
  ```json
  {
    "tenant_name": "Bengkel Berkah Mandiri",
    "slug": "berkah-mandiri",
    "owner_name": "Ahmad Fauzi",
    "email": "ahmad@berkahmandiri.com",
    "password": "PasswordKuat123!",
    "country_code": "ID",
    "currency": "IDR"
  }
  ```
- **Responses:**
  - `201 Created`:
    ```json
    {
      "status": "success",
      "data": {
        "tenant": {
          "id": 1,
          "slug": "berkah-mandiri",
          "name": "Bengkel Berkah Mandiri",
          "plan": "FREE",
          "status": "ACTIVE"
        },
        "user": {
          "id": 1,
          "email": "ahmad@berkahmandiri.com",
          "full_name": "Ahmad Fauzi",
          "role": "OWNER"
        },
        "tokens": {
          "access_token": "bk_jwt_eyJhbGciOi...",
          "refresh_token": "bk_ref_9f8e7d6c...",
          "expires_in": 3600
        }
      }
    }
    ```
  - `400 Bad Request`: Validasi gagal (misal slug duplikat, format email salah).

### 3.2. POST `/api/v1/auth/login`
Autentikasi kredensial pengguna (Owner, SuperAdmin, Staff).
- **Access:** Public
- **Request Body:**
  ```json
  {
    "email": "ahmad@berkahmandiri.com",
    "password": "PasswordKuat123!"
  }
  ```
- **Responses:**
  - `200 OK`:
    ```json
    {
      "status": "success",
      "data": {
        "user": {
          "id": 1,
          "tenant_id": 1,
          "email": "ahmad@berkahmandiri.com",
          "full_name": "Ahmad Fauzi",
          "role": "OWNER"
        },
        "tokens": {
          "access_token": "bk_jwt_eyJhbGciOi...",
          "refresh_token": "bk_ref_9f8e7d6c...",
          "expires_in": 3600
        }
      }
    }
    ```
  - `401 Unauthorized`: Kredensial tidak valid atau akun dinonaktifkan.
  - `403 Forbidden`: Tenant dalam status `SUSPENDED`.

### 3.3. POST `/api/v1/auth/refresh`
Memperbarui Access Token menggunakan Refresh Token valid.
- **Access:** Public
- **Request Body:**
  ```json
  {
    "refresh_token": "bk_ref_9f8e7d6c..."
  }
  ```
- **Responses:**
  - `200 OK`:
    ```json
    {
      "status": "success",
      "data": {
        "access_token": "bk_jwt_new_token...",
        "expires_in": 3600
      }
    }
    ```
  - `401 Unauthorized`: Token kedaluwarsa atau tidak valid.

### 3.4. GET `/api/v1/admin/tenants`
Mengambil daftar seluruh tenant untuk kebutuhan SuperAdmin.
- **Access:** SuperAdmin Only (`Authorization: Bearer <superadmin_token>`)
- **Query Parameters:**
  - `page` (integer, default: 1)
  - `limit` (integer, default: 20)
  - `status` (string, optional: ACTIVE|SUSPENDED|TRIAL|CANCELLED)
  - `search` (string, optional)
- **Responses:**
  - `200 OK`:
    ```json
    {
      "status": "success",
      "data": {
        "items": [
          {
            "id": 1,
            "slug": "berkah-mandiri",
            "name": "Bengkel Berkah Mandiri",
            "country_code": "ID",
            "currency": "IDR",
            "plan": "FREE",
            "status": "ACTIVE",
            "owner_email": "ahmad@berkahmandiri.com",
            "created_at": "2026-10-12T10:00:00Z"
          }
        ],
        "pagination": {
          "page": 1,
          "limit": 20,
          "total_records": 1,
          "total_pages": 1
        }
      }
    }
    ```
  - `403 Forbidden`: Role bukan `SUPERADMIN`.

### 3.5. PATCH `/api/v1/admin/tenants/{id}/status`
Mengubah status tenant (Suspend / Activate).
- **Access:** SuperAdmin Only (`Authorization: Bearer <superadmin_token>`)
- **Request Body:**
  ```json
  {
    "status": "SUSPENDED",
    "reason": "Pembayaran langganan gagal lebih dari 14 hari"
  }
  ```
- **Responses:**
  - `200 OK`:
    ```json
    {
      "status": "success",
      "data": {
        "id": 1,
        "slug": "berkah-mandiri",
        "status": "SUSPENDED",
        "updated_at": "2026-10-12T10:15:00Z"
      }
    }
    ```
  - `404 Not Found`: Tenant tidak ditemukan.

### 3.6. POST `/api/v1/owner/sync-key/generate`
Membuat kredensial sync API baru untuk mesin POS lokal Edge.
- **Access:** Owner Only (`Authorization: Bearer <owner_token>`)
- **Request Body:**
  ```json
  {
    "label": "Kasir PC Front Desk"
  }
  ```
- **Responses:**
  - `201 Created`:
    ```json
    {
      "status": "success",
      "data": {
        "id": 1,
        "prefix": "3a8b4f1c",
        "api_key": "bk_sync_3a8b4f1c_x7k9Pq2L...67",
        "label": "Kasir PC Front Desk",
        "created_at": "2026-10-12T10:20:00Z",
        "warning": "Simpan API Key ini sekarang. Nilai token rahasia tidak dapat ditampilkan kembali."
      }
    }
    ```
  - `403 Forbidden`: Role bukan `OWNER`.

---

## 4. Prinsip Ponytail Ladder & Clean Architecture

Implementasi mengikuti prinsip *Zero External Dependencies*:
1. **Security & Cryptography:** Python stdlib `hashlib.pbkdf2_hmac` (100.000 iterasi SHA-256) dengan garam acak (`secrets.token_bytes(16)`). Verifikasi token konstan waktu via `hmac.compare_digest`.
2. **Token Format:** API Key format `bk_sync_{prefix}_{entropy}`. Hash SHA-256 disimpan di database; plaintext hanya ditampilkan 1x saat generate.
3. **Clean Architecture:**
   - **Domain / Entity Layer:** Entitas `Tenant`, `User`, `Subscription`, `SyncKey`, `SyncEvent`.
   - **Repository Layer:** Parametric query SQLite, row-level isolation via parameterized `tenant_id`.
   - **Service / Use Case Layer:** Business rules (validasi limit tenant, transisi status akun, verifikasi hashing).
   - **Interface / Delivery Layer:** Dispatcher routing HTTP berbasis Python stdlib `http.server` & `urllib.parse`.
