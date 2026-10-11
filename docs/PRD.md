# PRD: BengkelStack Workshop Operating System (OS)
**Document Version:** 1.0.0  
**Status:** APPROVED (Gate 1 Passed)  
**Author:** PM Lead / Architect (Jarvis Team)  
**Domain:** bengkelstack.com  

---

## 1. Problem Statement (5 Whys Analysis)

Bengkel motor mandiri di Indonesia (UMKM) kehilangan 15-28% margin kotor bulanan akibat inkonsistensi penetapan harga jasa vs part dan friksi manual pencatatan riwayat nota servis.

1. **Why 1:** Mengapa margin kotor bengkel mandiri sering bocor?  
   *Karena kasir dan montir sering menetapkan tarif ongkos pasang secara arbitrer/kira-kira tanpa acuan standar baku.*
2. **Why 2:** Mengapa penetapan ongkos pasang dilakukan secara arbitrer?  
   *Karena sistem POS umum hanya mengenal harga jual barang tunggal (retail) dan tidak memisahkan struktur harga Bawa Pulang (DIY/Retail) vs Pasang di Tempat (Retail + Ongkos Pasang Model-Spesifik).*
3. **Why 3:** Mengapa tidak menggunakan software bengkel pabrikan (AHASS/Yamaha DDS)?  
   *Karena bengkel mandiri melayani ragam multi-brand (Honda, Yamaha, Suzuki, Kawasaki, Vespa) dengan part aftermarket (aspira, federal, kawahara) yang tidak tercakup dalam catalog tertutup ATPM.*
4. **Why 4:** Mengapa mekanik enggan mencatat riwayat perbaikan pelanggan?  
   *Karena input manual lewat keyboard/mouse memakan waktu 3-5 menit per kendaraan di saat antrean servis sedang ramai dan tangan mekanik berlumuran oli.*
5. **Why 5 (Root Cause):**  
   *Ketiadaan OS bengkel ringan berbasis web yang mampu lookup riwayat kendaraan instan via plat nomor (< 2 detik), kalkulasi ongkos pasang otomatis berbasis model motor (flat-rate tiered), serta intake nota faktur distributor via AI OCR tanpa ketergantungan hardware proprietary mahal.*

---

## 2. Target KPIs & Goals

| Metrik Keberhasilan | Baseline Industri Manual | Target BengkelStack (Lokal & Cloud) |
| :--- | :--- | :--- |
| **Lookup Waktu Riwayat Plat** | 180 - 300 detik (buku fisik / cari nota) | **< 1.0 detik** (instant plate lookup) |
| **Waktu Checkout Kasir per Motor** | 120 detik | **< 20 detik** (toggle retail vs pasang otomatis) |
| **Akurasi Pricing Jasa vs Part** | ~72% (rentan lupa tagih ongkos) | **100% deterministik** via rule engine |
| **API Response Latency (P95)** | N/A | **< 50 ms** pada mode lokal SQLite WAL |
| **Overhead Dependensi Runtime** | 100+ MB node_modules / venv gemuk | **0 MB extra pip runtime** (Python 3 stdlib first) |

---

## 3. User Personas

### Persona A: Dimas (38 th) — Pemilik Bengkel Mandiri & Kepala Toko
- **Latar Belakang:** Mengelola bengkel servis & sparepart motor di area ruko, 4 stall servis, 6 mekanik, omzet 45jt - 80jt/bulan.
- **Pain Points:** 
  - Sering curiga mekanik pasang part tapi ongkos pasangnya masuk kantong pribadi karena nota manual.
  - Sulit melacak part fast-moving vs slow-moving karena nota kulakan distributor menumpuk tanpa digitasi.
  - Mau sistem komputer tapi tidak mau langganan software mahal jutaan rupiah per bulan.
- **Goals:** 
  - POS kasir yang sekali klik langsung bedakan bawa pulang vs pasang di tempat.
  - Histori kendaraan konsumen tersimpan rapi berdasarkan plat nomor motor.

### Persona B: Budi (27 th) — Mekanik Senior & Kasir Operasional
- **Latar Belakang:** Mekanik handal, melayani 15-25 motor per hari, bertanggung jawab input transaksi kasir saat kasir utama istirahat.
- **Pain Points:**
  - Lupa besaran ongkos pasang part rumit (contoh: ganti kampas ganda NMAX vs ganti oli Beat).
  - Pelanggan sering komplain "minggu lalu harganya gak segini mas!".
- **Goals:**
  - Ketik plat motor langsung tahu riwayat ganti oli terakhir dan kilometer servis.
  - Tinggal pilih item part, ongkos pasang otomatis terhitung sesuai tipe motor (Matic 150cc, Bebek, Sport).

---

## 4. Scope Boundary

### In-Scope (MVP & Arsitektur Inti):
- **Core Engine (bengkel_pricing_engine):**
  - Instant Vehicle & Customer Lookup via Plat Nomor (regex nomor polisi Indonesia).
  - Dynamic Dual-Tier Pricing: Retail (Bawa Pulang) vs Retail + Ongkos Pasang spesifik model motor.
  - Work Order Service & Transaction Lifecycle (Draft -> In Progress -> Completed -> Cancelled).
  - Master Data CRUD: Part, Service, Motor Models, Custom Install Fee per Model.
  - Direct Receipt Printing format struk thermal 58mm/80mm (ESC/POS & plain text).
- **Frontend / Landing (`bengkelstack-site` & Web POS):**
  - POS Interface responsive (Touch-friendly, dark mode high contrast).
  - Public Landing Page (bengkelstack.com) dengan interactive pricing simulator & invoice intake demo.
- **Enterprise Standards:**
  - 5-Gate Enterprise SDLC compliance.
  - Zero-dependency runtime (Python stdlib HTTP server & SQLite WAL mode).

### Out-of-Scope (Fase Pasca-MVP):
- Integrasi Payment Gateway QRIS Dinamis Bank Indonesia (akan ditambahkan di Fase Staging Cloud).
- Accounting General Ledger multi-cabang (fokus utama adalah operasional bengkel tunggal terlebih dahulu).
- Manajemen absensi fingerprint mekanik hardware proprietary.
