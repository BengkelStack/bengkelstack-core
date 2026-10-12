# BengkelStack Security Incident & Threat Response Standard Operating Procedure (SOP)

**Document Classification:** Standard Operating Procedure (SOP)  
**Security Baseline:** ISO/IEC 27001 / OWASP Top 10 API Security / NIST SP 800-61  
**Version:** 2.0.0  
**Effective Date:** October 2026  

---

## 1. Overview & Objective
This Standard Operating Procedure (SOP) defines the concrete protocols and operational countermeasures enforced by BengkelStack to protect workshop data, financial transactions, and multi-tenant cloud infrastructure against physical, network, and application-layer security threats.

---

## 2. Threat Scenarios & Standard Response Procedures

### 2.1 Threat Scenario 1: Physical Theft of Workshop Counter Laptop
- **Context:** An adversary gains physical access to the cashier computer at a physical workshop.
- **Risk Assessment:** Potential attempt to extract master workshop credentials or access competitor data.
- **Architectural Defense:**
  1. **Zero Master Password Storage:** Cashier terminals NEVER store the workshop owner's account password.
  2. **Machine Isolation:** The counter computer only stores a paired `device_id` (`dev_<hex>`) and local `device_secret`.
- **Immediate Response SOP:**
  1. The workshop owner logs into `app.bengkelstack.com` from their smartphone or home computer.
  2. Navigate to **Workshop Portal -> Physical Cashier Terminal Pairing**.
  3. Click **Regenerate New Key** (or SuperAdmin executes **Revoke Device Key** in Master Admin).
  4. The cloud gateway immediately marks the old key hash as `is_revoked = 1`.
  5. Any subsequent sync attempts from the stolen laptop are rejected with **HTTP 403 Forbidden**.
  6. The adversary gains ZERO access to other workshops or cloud owner data.

### 2.2 Threat Scenario 2: Network Eavesdropping & Replay Attacks
- **Context:** An adversary sniffs network packets on an insecure workshop Wi-Fi network and attempts to replay past synchronization packets to inflate transaction revenue.
- **Architectural Defense:**
  1. **HMAC-SHA256 Cryptographic Request Signing:** Every packet is signed over `Method + Path + Timestamp + Nonce + BodyHash`.
  2. **Timestamp Drift Guard:** Packets with a timestamp deviation exceeding 300 seconds (5 minutes) from the server clock are dropped with HTTP 401.
  3. **Sliding Window Nonce Cache:** The cloud gateway maintains an in-memory nonce cache (`ReplayGuard`). Re-submitting a previously recorded nonce is rejected immediately with `Replay rejection: Nonce already used`.

### 2.3 Threat Scenario 3: Compromised Workshop Owner Account
- **Context:** An owner's password is leaked via credential stuffing from an external third-party breach.
- **Immediate Response SOP:**
  1. SuperAdmin detects anomalous logins or the owner reports unauthorized activity.
  2. In Master Admin Dashboard (`admin.bengkelstack.com`), SuperAdmin clicks **Suspend Tenant**.
  3. The cloud gateway immediately invalidates all active session tokens in `user_sessions` where `user_id = ?`.
  4. SuperAdmin triggers an authenticated password reset link.
  5. The owner creates a new password hashed with **PBKDF2-HMAC-SHA256 (600,000 iterations)**.
  6. Once verified, SuperAdmin re-activates the tenant status to `ACTIVE`.

### 2.4 Threat Scenario 4: Edge Offline Resilience & Database Corruption Defense
- **Context:** A power outage or sudden shutdown occurs during an active cashier transaction.
- **Architectural Defense:**
  1. **SQLite WAL Mode (`Write-Ahead Logging`):** Transactions commit append-only to `-wal` file. Incomplete writes roll back cleanly upon restart.
  2. **Idempotency Key Engine:** Transactions carry `idempotency_key TEXT UNIQUE` preventing accidental double billing when cashiers retry checkouts after power restoration.
  3. **Atomic Vacuum Backup:** Routine offsite backups execute via `VACUUM INTO '<backup_path>'` guaranteeing 100% consistent point-in-time snapshots without locking POS operations.

---

## 3. Security Verification Checklist & Audit Evidence

| Security Domain | Implemented Invariant | Test Suite Verification |
| :--- | :--- | :--- |
| **SQL Injection** | 100% Parameterized queries (`?`), zero string interpolation | `tests/test_adversarial_fuzzing.py` (Passed) |
| **Cross-Tenant IDOR** | Strict `WHERE tenant_id = ?` query isolation | `tests/test_adversarial_fuzzing.py` (Passed) |
| **Password Storage** | PBKDF2-HMAC-SHA256 (600,000 iterations), salt 16-byte | `tests/test_tier2_auth.py` (Passed) |
| **HMAC Fail-Closed** | Empty secret/signature/nonce rejected immediately | `tests/test_tier2_auth.py` (Passed) |
| **Rate Limiting** | Sliding window 120 req/min, 1MB max body (HTTP 413) | `tests/test_security_hardening.py` (Passed) |
| **DOM XSS** | Zero unescaped innerHTML, safe textContent mutation | `tests/test_cloud_frontend_whitebox.js` (Passed) |
| **Edge Sync Invariant**| Offline local buffering, HMAC signing, exponential backoff| `tests/test_sync_daemon.py` (Passed) |

---

## 4. Certification & Contact
- **Auditor:** BengkelStack Security Sentinel & QA Lead  
- **Vulnerability Reporting Policy:** Responsible disclosure via `founder@bengkelstack.com` or `SECURITY.md`.
