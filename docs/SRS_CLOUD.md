# Software Requirements Specification (SRS) — BengkelStack Cloud Platform (Tier 2)

**Standard:** IEEE 830-1998 / ISO/IEC/IEEE 29148:2018  
**Quality Model:** ISO/IEC 25010:2011  
**Security Standard:** OWASP Top 10 API Security / ASVS v4.0 Level 2  
**Version:** 2.0.0  
**Date:** 2026-10-12  

---

## 1. Introduction

### 1.1 Purpose
This Software Requirements Specification (SRS) delineates the complete functional, interface, security, and performance requirements for the BengkelStack Cloud Multi-Tenant Platform and Master Administration Subsystem (Tier 2).

### 1.2 Scope of Software
The software comprises:
1. Multi-Tenant Identity and Authentication Gateway (`/api/v1/auth/*`).
2. Central Administration REST Interface (`/api/v1/admin/*`).
3. Workshop Owner Management Interface (`/api/v1/owner/*`).
4. Edge-to-Cloud Ingestion Engine (`/api/v1/sync/*`).
5. Client-Side Single Page Application (SPA) surfaces (`login.html`, `register.html`, `admin.html`, `owner.html`).

---

## 2. Functional Requirements (FR)

### 2.1 Multi-Tenant Authentication (Module FR-AUTH)
- **FR-AUTH-001 (Registration):** The system shall expose `POST /api/v1/auth/register`. The endpoint shall validate payload schemas (`tenant_name`, `email`, `password`, `country_code`, `currency`), generate a unique URL-safe tenant slug, hash the password using PBKDF2-HMAC-SHA256 (600,000 iterations), persist the tenant and owner user records atomically, and return an opaque session token.
- **FR-AUTH-002 (Authentication):** The system shall expose `POST /api/v1/auth/login`. Given valid credentials, the system shall return an opaque 256-bit bearer token and store its SHA-256 digest in the session table with a default time-to-live (TTL) of 24 hours.
- **FR-AUTH-003 (Session Invalidation):** The system shall expose `POST /api/v1/auth/logout`. The endpoint shall delete the matching session token hash from the database, rendering subsequent requests unauthenticated.
- **FR-AUTH-004 (Tenant Isolation Barrier):** Every authenticated request shall extract `tenant_id` exclusively from the verified session claims. Requests attempting to supply or override `tenant_id` via request body or query parameters shall be strictly rejected or ignored.

### 2.2 SuperAdmin Administration (Module FR-ADMIN)
- **FR-ADMIN-001 (Tenant Directory):** The system shall expose `GET /api/v1/admin/tenants` with pagination (`page`, `limit`), status filter (`ACTIVE`, `SUSPENDED`, `TRIAL`), and full-text keyword search across tenant names and slugs.
- **FR-ADMIN-002 (Tenant Status Mutation):** The system shall expose `PATCH /api/v1/admin/tenants/{id}/status`. Only actors possessing `SUPERADMIN` authority shall be permitted to transition tenant status between `ACTIVE` and `SUSPENDED`.
- **FR-ADMIN-003 (Fleet Telemetry Summary):** The system shall expose `GET /api/v1/admin/metrics/overview`, aggregating total registered workshops, active subscriptions, total synchronized transactions, and 30-day gross merchandise volume (GMV).

### 2.3 Workshop Owner Terminal Management (Module FR-OWNER)
- **FR-OWNER-001 (Pairing Key Generation):** The system shall expose `POST /api/v1/owner/sync-key/generate`. The system shall generate a 32-byte cryptographically secure random token, return the plaintext key once to the client, and persist only its SHA-256 hash.
- **FR-OWNER-002 (Terminal Revocation):** The system shall expose `DELETE /api/v1/owner/sync-key/{key_id}`. Revoked keys shall immediately be rejected upon subsequent sync attempts.
- **FR-OWNER-003 (Configuration Export):** The client application shall provide automated generation of `bengkel.config.json` containing `tenant_id`, `api_key`, and target endpoint URLs without requiring external round-trips.

### 2.4 Edge-to-Cloud Ingestion Protocol (Module FR-SYNC)
- **FR-SYNC-001 (HMAC-SHA256 Verification):** The cloud gateway shall verify every incoming sync request against the formula:  
  `Signature = HMAC-SHA256(SecretKey, Method + "\n" + Path + "\n" + Timestamp + "\n" + Nonce + "\n" + SHA256(Body))`.
- **FR-SYNC-002 (Clock Drift Tolerance):** Requests with timestamp deviation greater than 300 seconds from server clock shall be rejected with HTTP 401 Unauthorized.
- **FR-SYNC-003 (Idempotency Guarantee):** The system shall reject duplicate payloads matching `(tenant_id, payload_hash)` with HTTP 409 Conflict or return existing receipt status without mutating records.

---

## 3. External Interface Requirements

### 3.1 Software Interfaces & Protocols
- **Transport Security:** Strict Transport Security (HSTS) over TLS 1.3. Plain HTTP connections shall be refused or redirected.
- **Data Serialization:** Standard UTF-8 JSON (`application/json`).
- **Database Engine:** SQLite 3 WAL Mode (`PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON; PRAGMA busy_timeout = 5000;`).

---

## 4. Non-Functional Attributes (ISO/IEC 25010)

| Metric | Threshold / Target | Verification Method |
| :--- | :--- | :--- |
| **Response Time (p95)** | < 80 ms for Auth/Admin queries | Automated load probe (`tests/test_perf_auth.py`) |
| **Password Storage Security** | PBKDF2-HMAC-SHA256, 600,000 iterations | Unit test assertion on hash metadata |
| **Timing Attack Resistance** | Constant-time string comparison | `secrets.compare_digest` enforcement |
| **Brute-Force Lockout** | 5 consecutive failures = 15-minute freeze | Integration test on rate-limit middleware |
| **Browser Compatibility** | Chrome, Edge, Safari, Firefox (Latest 2 versions) | Headless Chrome CDP black-box test |
