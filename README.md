# bengkelstack-core

[![CI](https://github.com/BengkelStack/bengkelstack-core/actions/workflows/ci.yml/badge.svg)](https://github.com/BengkelStack/bengkelstack-core/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Self-hosted point-of-sale and parts pricing engine for motorcycle repair workshops. Runs on the Python 3 standard library with SQLite WAL storage and zero pip runtime dependencies.

---

## Features

- **Dual-Tier Dynamic Pricing:** Splits parts retail price from vehicle-specific installation labor (e.g. Honda Beat vs Yamaha NMAX CVT disassemblies).
- **Plate Number Lookup:** Regex normalization for vehicle registration numbers, retrieving customer ownership and chronological repair history.
- **Multimodal Invoice Ingestion:** Parser for OEM parts distributor invoices (Astra Otoparts, Yamaha, Denso) with mathematical determinism checks (`sum(subtotal) == grand_total`).
- **Fuzzy Catalog Matcher:** SequenceMatcher-backed catalog mapper that flags cost inflation and enforces an automated minimum 25% gross retail margin.
- **Thermal Receipt Formatter:** Generates clean 40-column monospaced receipts compatible with ESC/POS 58mm and 80mm thermal printers.
- **Idempotency Guard:** Protects against duplicate checkout submissions and double-billing via unique transaction tokens.
- **Local Network Isolation:** Defaults to localhost loopback access (`127.0.0.1`), with constant-time Bearer token verification (`secrets.compare_digest`) required for external IP requests.

---

## Architecture

```text
+-------------------------------------------------------------------------+
|                      PRESENTATION / CLIENT LAYER                        |
|  - BengkelStack POS Web UI (Vanilla JS, Touch-Optimized, Thermal Print) |
|  - Public Simulator & Ingestion Gateway (bengkelstack.com)              |
+-----------------------------------^-------------------------------------+
                                    | HTTP / REST (JSON)
+-----------------------------------v-------------------------------------+
|                     APPLICATION & ROUTING LAYER                         |
|  - app/server.py (Python ThreadingHTTPServer + urllib Router)           |
|  - app/security.py (Token Auth, Rate Limiter, Security Headers)         |
+-----------------------------------^-------------------------------------+
                                    | Direct In-Memory Call
+-----------------------------------v-------------------------------------+
|                      DOMAIN & VISION AI ENGINES                         |
|  - app/pricing_engine.py (Dual-Tier Pricing & Model Overrides)          |
|  - app/work_order_service.py (Work Order State Machine & Receipt Engine)|
|  - app/invoice_vision.py (Deterministic OEM Receipt Parser)             |
|  - app/catalog_matcher.py (Fuzzy SKU Matcher & 25% Margin Guard)        |
+-----------------------------------^-------------------------------------+
                                    | Parametric SQL Query (?)
+-----------------------------------v-------------------------------------+
|                      PHYSICAL PERSISTENCE LAYER                         |
|  - SQLite 3 (WAL Mode, synchronous=NORMAL, busy_timeout=5000ms)         |
|  - database/workshop.db (Zero external RDBMS overhead)                  |
+-------------------------------------------------------------------------+
```

An interactive SVG topology diagram is available at [`docs/bengkelstack-architecture.html`](docs/bengkelstack-architecture.html).

---

## ⏱️ Quickstart (30 Seconds)

BengkelStack runs on **pure Python 3 standard library**. Zero `pip install` required for core runtime.

```bash
# 1. Clone the repository
git clone https://github.com/BengkelStack/bengkelstack-core.git
cd bengkelstack-core

# 2. Run the application
python run.py
```

Open your browser at **`http://localhost:8089`** to access the live workshop POS interface.

---

## Testing

The project maintains 88 unit and integration test cases covering domain logic, concurrent writes, API endpoints, pentest security, data migrations, and boundary white-box edge cases.

```bash
python -m unittest discover -s tests -v
```

All tests execute against an isolated in-memory or temporary SQLite database in approximately 1.7 seconds without network calls.

---

## Specifications & Architecture Records

Engineering documentation and formal decision records:

| Document | Path | Description |
| :--- | :--- | :--- |
| **Product Requirements** | [`docs/PRD.md`](docs/PRD.md) | Problem analysis (5 Whys), user personas, and scope boundary. |
| **Engineering Requirements** | [`docs/SRS.md`](docs/SRS.md) | IEEE 830 / ISO 25010 specification (FR-01 to FR-08, NFRs). |
| **System Architecture** | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 3NF relational data model and work order state machine. |
| **API Contract** | [`docs/api/openapi.yaml`](docs/api/openapi.yaml) | OpenAPI 3.0.3 specification for all REST endpoints. |
| **ADR-001** | [`docs/adr/ADR-001-architecture-stack.md`](docs/adr/ADR-001-architecture-stack.md) | Zero-dependency standard library and SQLite WAL storage. |
| **ADR-002** | [`docs/adr/ADR-002-multi-currency-and-payments.md`](docs/adr/ADR-002-multi-currency-and-payments.md) | Dynamic multi-currency configuration and cash change tracking. |

### Technical Reports (PDF)
- [Comprehensive SDLC Audit & Master Report (PDF)](docs/BengkelStack_Comprehensive_SDLC_Audit_Report.pdf)
- [System Architecture Specification (PDF)](docs/BengkelStack_Architecture_Report.pdf)
- [Institutional Security & OWASP Audit (PDF)](docs/BengkelStack_Institutional_Security_Report.pdf)
- [NVIDIA Inception Edge AI Technical Pitch (PDF)](docs/BengkelStack_NVIDIA_Inception_Report.pdf)
- [Consumer Trust & Pentest Security Report (PDF)](docs/BengkelStack_Consumer_Security_Report.pdf)

---

## Edge AI Roadmap (NVIDIA Inception)

For edge deployments in areas with intermittent connectivity, the repository includes a roadmap for local hardware acceleration:

1. **On-Premise TensorRT Inferencing:** Quantized INT8/FP16 Vision Transformer models on low-power NVIDIA Jetson Orin Nano hardware.
2. **Local Processing:** Invoices and proprietary wholesale purchase agreements are parsed locally without transmitting supplier pricing over public networks.
3. **Continuous Catalog Alignment:** Discrepancies between physical OEM packing slips and digital catalogs are reconciled in real time at the edge.

Reviewer technical pitch documentation: [`docs/NVIDIA_INCEPTION_PITCH.md`](docs/NVIDIA_INCEPTION_PITCH.md).

---

## Security

Please report vulnerabilities directly via email to `founder@bengkelstack.com`. Do not disclose security vulnerabilities through public GitHub issues. See [`SECURITY.md`](SECURITY.md) for details.

---

## License

BengkelStack Core is licensed under the [MIT License](LICENSE).  
Copyright (c) 2026 BengkelStack / Rahmad Riyadi.
