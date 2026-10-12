# Product Requirements Document (PRD) — BengkelStack Cloud Platform (Tier 2)

**Document Version:** 2.0.0  
**Status:** Approved / Engineering Ready  
**Date:** 2026-10-12  
**Target Architecture:** Multi-Tenant Cloud Operating System & Central Administration  
**Compliance Standard:** ISO/IEC 25010 / OWASP ASVS v4.0 Level 2  

---

## 1. Executive Summary & Problem Statement

### 1.1 Background
BengkelStack Tier 1 (`bengkelstack-core`) successfully establishes a zero-dependency, edge-first Point of Sale (POS) and pricing appliance designed for local motorcycle repair workshops. It operates 100% offline with zero external cloud dependencies.

However, to support commercial software operations, global customer acquisition, and remote fleet management, BengkelStack requires a centralized cloud tier (**Tier 2**) that provides:
1. Multi-tenant customer onboarding and billing management.
2. Centralized administration for system operators (SuperAdmin).
3. Secure pairing and bidirectional synchronization between offline edge terminals and cloud backends.
4. Business analytics and revenue tracking accessible remotely via mobile browsers.

### 1.2 Problem Statement
- **Lack of Multi-Tenant Identity:** Workshop owners cannot register, manage subscriptions, or invite staff online.
- **Operator Blind Spot:** BengkelStack HQ administrators lack global visibility into tenant health, active licenses, aggregate transaction volumes, and terminal sync latencies.
- **Unmanaged Edge Terminals:** Offline POS terminals operate in isolation without an automated, authenticated channel for offsite backup, telemetry reporting, or subscription verification.

---

## 2. User Personas & Role-Based Access Control (RBAC)

| Persona | Role Code | Authentication Method | Primary Interface | Key Capabilities |
| :--- | :--- | :--- | :--- | :--- |
| **SuperAdmin (HQ)** | `SUPERADMIN` | Email + 600k PBKDF2 + Opaque Session | `admin.bengkelstack.com` | Global tenant directory, account suspension, aggregate revenue analytics, sync error monitoring, manual quota override. |
| **Workshop Owner** | `OWNER` | Email + 600k PBKDF2 + Opaque Session | `app.bengkelstack.com` | Tenant onboarding, subscription selection, terminal pairing key generation, multi-branch revenue telemetry. |
| **Workshop Cashier** | `CASHIER` | Local PIN (6-digit) / Edge Appliance | Edge POS (`localhost:8089`) | Daily checkout, work order management, thermal receipt printing, local part catalog lookup. No cloud portal access. |
| **Workshop Mechanic**| `MECHANIC`| Local PIN (4-digit) / Edge Appliance | Edge POS (`localhost:8089`) | Work order status update, checklist verification, bay assignment. No financial margin or cloud access. |
| **Edge Appliance** | `DEVICE_AGENT`| HMAC-SHA256 Signed API Key | Headless Background Daemon | Automated WAL delta synchronization, inventory heartbeat, offline buffer flush. |

---

## 3. Subscription & Licensing Tier Matrix

| Dimension | Community Tier | Pro Sync Tier | Enterprise Fleet Tier |
| :--- | :--- | :--- | :--- |
| **Monthly Pricing** | **$0 / Month** (Free Forever) | **$19 / Month** (Rp 299,000) | **$49 / Month** (Rp 749,000) |
| **License Type** | MIT Open-Core | Commercial SaaS Subscription | Commercial Dedicated Fleet |
| **Terminal Quota** | 1 Edge POS Terminal | Up to 3 Terminals per Branch | Unlimited Terminals / Multi-Branch |
| **Cloud Sync** | Manual CSV/JSON export | Automated SQLite WAL Delta (15s) | Continuous Real-Time Streaming |
| **Historical Data Retention** | 30 Days Cloud Buffer | 1 Year Cloud Analytics | 5 Years Immutable Cloud Archive |
| **Invoice Vision OCR** | Local Manual Input Only | 500 Scans / Month | 2,500 Scans / Month |
| **Support SLA** | Community GitHub Discussions | 24-Hour Email / WhatsApp | 4-Hour Dedicated Engineering SLA |

---

## 4. User Journeys & Critical Workflows

### 4.1 Workshop Owner Onboarding (Self-Service)
1. Owner navigates to `bengkelstack.com/register`.
2. Step 1: Owner fills out full name, business email, and WhatsApp contact number.
3. Step 2: Owner inputs workshop trading name, country (ID, VN, TH, PH, MY, IN, US, GB), and preferred currency.
4. Step 3: Owner selects license tier (Community Free or 14-Day Pro Trial) and creates a secure password.
5. System provisions `tenants` and `users` records in a single atomic transaction and issues an authenticated session.

### 4.2 Edge Terminal Pairing Workflow (Zero Password Exposure)
1. Workshop owner logs into Cloud Portal (`/owner`) and navigates to **Terminal Pairing**.
2. Owner clicks **Generate Terminal Key**.
3. System outputs a unique device credential:
   - `Device Prefix`: 8-character hex string (e.g., `bk_sync_a1b2c3d4`).
   - `API Key Secret`: 32-byte cryptographically secure random token (e.g., `bk_sync_a1b2c3d4_x9...`).
4. System stores only `SHA-256(API Key Secret)` in database table `tenant_sync_keys`.
5. Owner downloads `bengkel.config.json` or copies `.env` snippet directly into the local POS appliance directory.
6. The edge daemon reads the key and initiates authenticated handshake with cloud gateway via HMAC-SHA256 headers.

### 4.3 SuperAdmin Fleet Oversight & Kill-Switch
1. SuperAdmin logs into `bengkelstack.com/admin`.
2. Overview cards display real-time global health metrics: Total Tenants, Active Subscribers, Churn Rate, and Aggregate GMV.
3. SuperAdmin searches tenant table by name, slug, country, or subscription state.
4. In case of fraudulent usage or overdue invoice, SuperAdmin toggles tenant status to `SUSPENDED`.
5. Cloud gateway immediately invalidates all active sessions and rejects all incoming edge sync requests with HTTP 403 Forbidden.

---

## 5. Non-Functional Requirements (NFR)

1. **Security & Cryptography:** Zero plaintext credential storage. PBKDF2-HMAC-SHA256 with minimum 600,000 iterations for passwords. Constant-time digest comparison (`secrets.compare_digest`) for all auth verifications.
2. **Availability & Zero-Interruption Invariant:** Disruption or maintenance of Cloud Tier 2 MUST NEVER interrupt local POS checkout at physical workshops (Edge-First Independence).
3. **Multi-Tenant Isolation:** Zero data bleed across tenants. Strict row-level tenancy (`WHERE tenant_id = ?`) enforced at SQL query boundary.
4. **Zero-Build Frontend:** Clean Vanilla JavaScript ES modules and responsive Tailwind CSS. Compatible with instant deployment on Cloudflare Pages or Netlify Edge without Node/npm compilation dependencies.
