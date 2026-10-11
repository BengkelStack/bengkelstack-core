# SRS: Software Requirements Specification
**Document Version:** 1.0.0  
**Status:** APPROVED (Gate 2 Passed)  
**Standard:** IEEE Std 830-1998 / ISO/IEC 25010:2023  
**System:** BengkelStack Workshop Operating System  

---

## 1. Introduction & Purpose

Dokumen ini mendefinisikan spesifikasi rekayasa perangkat lunak sistem BengkelStack. Sistem ini dirancang untuk beroperasi secara mandiri di workstation bengkel (offline-capable lokal) dan siap di-deploy secara bertahap menuju cloud multi-tenant di domain `bengkelstack.com`.

---

## 2. Functional Requirements (FR)

### FR-01: Plate Number Sanitization & Vehicle Lookup
- **Deskripsi:** Sistem harus menerima input string nomor plat kendaraan Indonesia (contoh: `B 1234 XYZ`, `D 5678 AB`, `DK 9901 AA`).
- **Input:** String query `plate`.
- **Aturan Bisnis:** 
  - Whitespace ekstra harus dibersihkan, huruf dikonversi menjadi huruf kapital seragam.
  - Jika plat terdaftar, sistem mengembalikan model motor (`motor_model_id`, `motor_name`), nama pemilik terakhir, nomor telepon, dan total kunjungan.
  - Jika plat belum terdaftar, kembalikan status `not_found` dengan flag pendaftaran instan tanpa memblokir alur kasir.

### FR-02: Dual-Tier Dynamic Pricing Engine
- **Deskripsi:** Setiap item sparepart memiliki dua harga kalkulasi:
  1. **Retail Mode (`TAKE_AWAY` / Bawa Pulang):** Hanya harga jual eceran part (`price`).
  2. **Install Mode (`INSTALL` / Pasang di Bengkel):** Harga part + ongkos pasang (`price + install_fee`).
- **Aturan Bisnis:**
  - Jasa murni (`item_type = 'SERVICE'`) selalu memiliki `price = 0` dan hanya mengenakan `install_fee` (ongkos pengerjaan).
  - Ongkos pasang default diambil dari tabel master part, namun dapat dioverride oleh model motor kendaraan terkait.

### FR-03: Model-Specific Custom Installation Fee
- **Deskripsi:** Kerumitan pemasangan berbeda per motor (contoh: bongkar body Honda PCX lebih rumit dibanding Honda Supra).
- **Aturan Bisnis:**
  - Jika terdapat entri pada `model_custom_fees` untuk pasangan `(motor_model_id, part_id)`, nilai ini menggantikan `default_install_fee`.
  - Jika tidak ada, gunakan `default_install_fee` dari tabel master `parts`.

### FR-04: Work Order Lifecycle Management
- **Deskripsi:** Transaksi servis dikelola melalui entitas Work Order (`work_orders`).
- **State Machine Status:**
  - `DRAFT`: Kendaraan masuk stall, rincian part/jasa masih tentatif.
  - `IN_PROGRESS`: Mekanik sedang mengeksekusi pengerjaan.
  - `COMPLETED`: Transaksi dibayar di kasir, stok terpotong, faktur terkunci.
  - `CANCELLED`: Servis dibatalkan sebelum pembayaran.
- **Invarian:** Work order yang berstatus `COMPLETED` tidak boleh dimutasi itemnya (immutable snapshot).

### FR-05: Historical Service Record Audit by Plate
- **Deskripsi:** Kasir atau mekanik dapat melihat seluruh histori kunjungan masa lalu kendaraan berdasarkan plat nomor.
- **Output:** Urutan kronologis tanggal servis, daftar part yang diganti, jasa yang dikerjakan, dan total biaya.

### FR-06: Master Part & Service Catalog Management
- **Deskripsi:** Manajemen data master suku cadang dan jasa servis bengkel.
- **Atribut Part:** Kode part/SKU, nama, barcode/kode pabrikan, harga beli (HPP), harga eceran retail, default ongkos pasang, stok fisik.

### FR-07: In-Memory Cart Pricing Calculation API
- **Deskripsi:** Endpoint kalkulasi cepat sebelum finalisasi transaksi (`/api/calculate`).
- **Input:** `motor_model_id` (integer) dan array `items` (`[item_type, item_id, quantity, action_type]`).
- **Output:** Subtotal part, total ongkos pasang, diskon, grand total, dan rincian tier per item.

### FR-08: Thermal Receipt Printing Support
- **Deskripsi:** Menghasilkan payload struk siap cetak untuk printer thermal lebar 58mm / 80mm.
- **Format:** Header nama bengkel, plat nomor, tanggal/jam, tabel baris part/jasa, subtotal, ongkos pasang, total bayar, dan footer garansi pengerjaan.

---

## 3. Non-Functional Requirements (NFR)

### NFR-01: Performance Efficiency & Latency
- **Target Latensi P95:** API query `/api/calculate`, `/api/parts`, dan `/api/vehicle-lookup` wajib merespons dalam `<= 50ms` pada workstation lokal.
- **Throughput:** Sanggup menangani minimal 200 request per detik secara lokal tanpa frame drop UI.

### NFR-02: Reliability & Data Concurrency
- **Database Engine:** SQLite 3 dengan mode `WAL` (Write-Ahead Logging) diaktifkan secara otomatis.
- **Connection Isolation:** Setiap HTTP request thread membuka koneksi independen dengan `busy_timeout = 5000ms` untuk mencegah disk lock crash.

### NFR-03: Architectural Footprint & Zero-Dependency (Ponytail Standard)
- **Runtime Backend:** 100% Python Standard Library (`http.server`, `sqlite3`, `urllib.parse`, `json`, `os`, `sys`).
- **Zero PIP Overhead:** Tidak memerlukan instalasi runtime pip tambahan untuk menjalankan backend inti (YAGNI / stdlib first).

### NFR-04: Security & Input Sanitation (ISO/IEC 27001 Alignment)
- **SQL Injection Prevention:** Seluruh interaksi database 100% menggunakan parameterized queries (`?`). Dilarang keras f-string SQL execution.
- **XSS & CORS:** API header menyertakan sanitasi MIME `application/json; charset=utf-8` dan restriksi origin terkontrol.
- **Validation:** Validasi tipe data ketat pada parsing JSON sebelum memanggil layer database.
