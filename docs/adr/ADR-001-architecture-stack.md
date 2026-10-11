# ADR-001: Architectural Stack & Zero-Dependency Engine
**Status:** ACCEPTED  
**Date:** 2026-10-10  
**Deciders:** PM Lead, Architect, Core Backend Engineer  

---

## Konteks
Bengkel motor mandiri di Indonesia beroperasi dalam lingkungan ritel fisik yang keras: seringkali fluktuasi koneksi internet, perangkat kasir berspesifikasi terbatas (laptop kantor atau PC kasir lawas), dan operator (kasir/mekanik) yang membutuhkan respons instan tanpa hambatan loading lambat. Framework Python yang gemuk (seperti Django atau instalasi dependensi pip ratusan megabyte) rentan terhadap problem 'dependency hell' saat instalasi offline dan boros memory working set.

## Keputusan
1. **Python 3 Standard Library First (Clean Routing & HTTP Server):**
   - Menggunakan `http.server.HTTPServer` dan routing berbasis `urllib.parse` bawaan Python.
   - Tidak ada ketergantungan runtime pip (zero external runtime dependencies).
   - Memangkas memory working set backend menjadi < 25 MB RAM.
2. **SQLite 3 dengan Mode WAL (Write-Ahead Logging):**
   - Menjamin isolasi transaksi ACID penuh tanpa perlu menginstal service RDBMS terpisah (PostgreSQL/MySQL) di PC bengkel.
   - Mengaktifkan `PRAGMA journal_mode = WAL;` dan `PRAGMA busy_timeout = 5000;` untuk menangani pembacaan multi-koneksi paralel tanpa lock error.
3. **Dual-Tier Dynamic Pricing Engine:**
   - Menetapkan pemisahan eksplisit harga item menjadi `retail_price` (bawa pulang) dan `install_fee` (ongkos pasang).
   - Menyediakan fallback hierarki: Model-Specific Custom Fee -> Default Part Install Fee -> Flat Zero.
4. **Staged Deployment Model:**
   - Menyimpan landing page publik `bengkelstack-site` secara independen untuk deploy ke edge CDN gratis (Cloudflare Pages), sementara backend POS berjalan lokal di LAN bengkel.

## Konsekuensi
- **Positif:**
  - Startup server instan (< 0.2 detik).
  - Portabilitas penuh: sistem dapat dijalankan di Windows, Linux, maupun Raspberry Pi hanya dengan runtime Python bawaan OS.
  - Sangat tahan terhadap gangguan internet (offline-first).
- **Negatif / Mitigasi:**
  - Tanpa ORM pihak ketiga (seperti SQLAlchemy), kueri ditulis menggunakan SQL mentah.  
    *Mitigasi:* Wajib 100% parameterized queries (`?`) dan repository abstraction teruji unit test.
  - Server thread bawaan `http.server` sederhana.  
    *Mitigasi:* Menggunakan `ThreadingHTTPServer` untuk menangani konkurensi request kasir secara simultan tanpa blocking.
