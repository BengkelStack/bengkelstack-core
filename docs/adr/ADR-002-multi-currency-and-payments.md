# ADR-002: Multi-Currency Configuration & Cash Tender Invariant
**Status:** ACCEPTED  
**Date:** 2026-10-11  
**Deciders:** PM Lead, Architect, Core Backend Engineer  

---

## Konteks
BengkelStack diposisikan untuk melayani pasar bengkel motor mandiri di Asia Tenggara dan negara berkembang (Indonesia, Vietnam, India, Filipina, Thailand) serta kualifikasi program startup global (NVIDIA Inception). Sebelumnya, simbol mata uang (`Rp`) dan format struk bersifat hardcoded dalam kode, dan transaksi work order hanya menyimpan nominal tagihan kotor tanpa mencatat metode bayar (`CASH`, `QRIS`, `TRANSFER`, `CARD`) atau menghitung nominal uang kembalian kasir.

## Keputusan
1. **Tabel Pengaturan Bengkel Dinamis (`workshop_settings`):**
   - Mengisolasi konfigurasi toko ke tabel tunggal (`id = 1` constraint): `workshop_name`, `currency_symbol`, `currency_code`, `receipt_header`, `receipt_footer`, dan `min_margin_pct`.
   - Format nominal pada antarmuka kasir dan struk thermal 40-kolom mengacu dinamis pada simbol mata uang aktif (contoh: `Rp` untuk IDR, `₫` untuk VND, `$` untuk USD, `₹` untuk INR).
2. **Kalkulasi Kembalian & Metode Pembayaran Deterministik:**
   - Menambahkan kolom `payment_method`, `cash_received`, dan `change_amount` pada tabel `work_orders`.
   - Invarian Transaksi:
     - Jika `payment_method == 'CASH'`, `change_amount = max(0.0, cash_received - total_amount)`.
     - Jika metode non-tunai (QRIS / Transfer / Card), `cash_received = total_amount` dan `change_amount = 0.0`.
3. **Penyelarasan Kontrak API (OpenAPI 3.0):**
   - Membuka endpoint `GET /api/settings` dan `POST /api/settings` untuk mutasi konfigurasi toko secara live dari modal GUI kasir.
   - Memperluas payload `POST /api/work-orders` agar mencakup `payment_method` dan `cash_received`.

## Konsekuensi
- **Positif:**
  - Siap diekspansi ke bengkel di negara mana pun tanpa refactor database (currency-agnostic).
  - Kasir tidak lagi menghitung kembalian uang fisik secara manual.
  - Struk thermal mencatat metode pembayaran, nominal tunai diterima, dan kembalian secara transparan.
- **Negatif / Mitigasi:**
  - Perlu migrasi skema tabel `work_orders` yang sudah ada di workstation lama.
  - *Mitigasi:* Menambahkan pelacak versi `schema_migrations` di `database/db.py` dengan fallback `ALTER TABLE` otomatis.
