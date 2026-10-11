# Security Policy

BengkelStack takes the security and privacy of automotive workshops, mechanics, and vehicle owners seriously. We implement an **Edge-First, Local-First Architecture** designed to minimize attack surfaces and protect sensitive Personally Identifiable Information (PII) and wholesale parts pricing data.

## Supported Versions

| Version | Supported          | Security Maintenance Status |
| ------- | ------------------ | ---------------------------- |
| 1.0.x   | :white_check_mark: | Active Security Updates      |

## Core Security Invariants

1. **Local Loopback Isolation:** By default, all unauthenticated API requests from external/non-loopback network interfaces are rejected (`403 Forbidden`). External network access requires an explicitly configured Bearer token (`BENGKELSTACK_API_KEY`).
2. **Timing Attack Protection:** Token verification enforces constant-time string comparison (`secrets.compare_digest`).
3. **Database Parameterization:** 100% of SQL queries utilize parameterized placeholders (`?`). String interpolation, concatenation, and raw SQL queries are strictly forbidden.
4. **Denial of Service (DoS) Controls:**
   - Ingestion payload sizes are strictly capped at 1 MB (`413 Payload Too Large`).
   - Global sliding-window rate limiting is enforced (120 requests/minute per client IP).
5. **Deterministic Financial Audit:** All invoice ingestion and work order transactions require mathematical reconciliation (`sum(subtotal) == grand_total`).

## Reporting a Vulnerability

If you discover a potential security vulnerability within BengkelStack, please do **NOT** open a public issue.

Instead, please report it via encrypted or direct email:
- **Contact:** `founder@bengkelstack.com`
- **Subject:** `[SECURITY] BengkelStack Vulnerability Report - <Component>`

### What to Include in Your Report:
- Detailed description of the vulnerability and potential impact.
- Step-by-step reproduction instructions or a minimal Proof of Concept (PoC).
- Affected files, functions, or endpoints.

### Our Commitment:
- We acknowledge receipt within **24 hours**.
- We provide a preliminary assessment and remediation plan within **72 hours**.
- We credit security researchers in release notes upon coordinated public disclosure.
