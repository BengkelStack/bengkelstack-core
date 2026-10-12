# ADR-003: Cloud Multi-Tenant Architecture & Edge Synchronization
**Status:** ACCEPTED  
**Date:** 2026-10-12  
**Deciders:** PM Lead, System Architect, Security & Auth Engineer, Core Backend Engineer  

---

## 1. Context & Business Drivers
BengkelStack Tier 1 (`bengkelstack-core`) provides an offline-first POS engine running locally inside workshops. To support commercial software operations, global customer acquisition, and remote fleet management, BengkelStack requires a centralized cloud tier (**Tier 2**) that provides:
1. Multi-tenant customer onboarding and billing management.
2. Centralized administration for system operators (SuperAdmin).
3. Secure pairing and bidirectional synchronization between offline edge terminals and cloud backends.
4. Business analytics and revenue tracking accessible remotely via mobile browsers.

Key constraints:
- **Zero-Interruption Invariant:** Workshop POS operations must never freeze if cloud services are offline or unreachable.
- **Zero-Dependency Core:** Maintain standard library simplicity without heavyweight framework lock-in.
- **Strict Multi-Tenant Isolation:** Zero data bleed across different workshop organizations.

---

## 2. Decision & Architecture Strategy

### 2.1 Hybrid Multi-Tenancy (Master Catalog + Row-Level Ingestion)
- **Central Master Database (`cloud_master.db`):** Shared schema utilizing SQLite WAL mode.
- **Tenancy Boundary:** Enforce strict row-level isolation using `tenant_id` on all operational and analytics tables.
- **Foreign Key Constraints:** `PRAGMA foreign_keys = ON;` with cascading deletions for clean tenant lifecycles.
- **Compound Uniqueness:** Enforce `UNIQUE(tenant_id, payload_hash)` in event logs to guarantee idempotency across edge sync attempts.

### 2.2 Standard Library Cryptography & Authentication
- **Password Hashing:** `PBKDF2-HMAC-SHA256` with 600,000 iterations and 16-byte cryptographically secure salts via `secrets.token_bytes(16)`.
- **Session Tokens:** 256-bit entropy opaque URL-safe tokens (`secrets.token_urlsafe(32)`). Only `SHA-256(token)` is stored in the database.
- **Constant-Time Verification:** All secret comparisons execute via `secrets.compare_digest` to prevent timing-attack side-channel leaks.

### 2.3 Edge-to-Cloud Pairing Protocol (Zero Password Exposure)
- **Credential Separation:** The workshop owner's login credentials are never stored on physical POS cashier computers.
- **Pairing Key Pair:** Cloud portal issues a unique `Device ID` (`prefix`) and `API Secret Key`.
- **HMAC-SHA256 Signatures:** Edge synchronization daemons authenticate delta batches using cryptographic request signing:
  `Signature = HMAC-SHA256(SecretKey, Method + "\n" + Path + "\n" + Timestamp + "\n" + Nonce + "\n" + SHA256(Body))`.
- **Replay Protection:** 300-second maximum clock drift tolerance and nonce caching.

---

## 3. Consequences & Trade-Offs

### Positive
1. **Security Isolation:** Even if an edge cash register is physically stolen, the attacker gains zero access to the owner's cloud account or other workshops' data.
2. **High Concurrency & Low Latency:** SQLite WAL handles concurrent reads effortlessly with sub-millisecond query responses.
3. **Audit Trail:** Every synchronization packet is logged immutably with payload hashes, enabling instant deduplication and transaction audits.

### Negative & Mitigations
1. **Row-Level Tenancy Risks:** Inadvertent exclusion of `WHERE tenant_id = ?` in raw queries could leak data.
   - *Mitigation:* Strict repository pattern and automated query validation test suite (`tests/test_cloud_multi_tenant.py`).
2. **Key Rotation Overhead:** If a device is compromised, keys must be manually regenerated.
   - *Mitigation:* One-click 1-second instant revocation in Owner Portal and SuperAdmin Dashboard.
