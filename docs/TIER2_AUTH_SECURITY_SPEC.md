# SPESIFIKASI ARSITEKTUR KEAMANAN: TIER 2 CLOUD MULTI-TENANT AUTH & ACCESS CONTROL
**Sistem:** BengkelStack (bengkelstack.com)  
**Dokumen:** Spesifikasi Arsitektur Keamanan & Otentikasi Tier 2  
**Standar Kepatuhan:** OWASP ASVS v4.0, OWASP Password Storage Cheat Sheet, NIST SP 800-63B  
**Status:** APPROVED (Zero Heavy Dependencies - Python Standard Library Engine)

---

## 1. PASSWORD HASHING SPECIFICATION

### 1.1 Algoritma & Konfigurasi OWASP
- **Algoritma:** PBKDF2-HMAC-SHA256 (`hashlib.pbkdf2_hmac`).
- **Iterasi:** Minimal 600.000 iterasi (sesuai rekomendasi resmi OWASP Password Storage Cheat Sheet).
- **Garam (Salt):** 16 bytes (128 bits) salt dinamis per user yang dihasilkan oleh CSPRNG (`secrets.token_bytes(16)`). Salt unik untuk setiap password mencegah attacks berbasis Rainbow Table.
- **Key Length:** 32 bytes (256 bits).
- **Format Penyimpanan DB:**
  ```text
  $pbkdf2-sha256$i=600000$s=<salt_hex>$h=<digest_hex>
  ```
  - `i`: Jumlah iterasi (mendukung upgrade migrasi transparan).
  - `s`: Salt dalam format hex (32 karakter).
  - `h`: Digest dalam format hex (64 karakter).

### 1.2 Verifikasi Aman & Migrasi Transparan
- **Timing Attack Immunity:** Verifikasi hash wajib menggunakan `secrets.compare_digest(candidate, expected_hash)` pada representasi biner.
- **Transparent Rehash:** Saat user login dengan iterasi lama (misal legacy < 600.000 iterasi), sistem mengecek `needs_rehash()` dan melakukan hash ulang ke target 600.000 iterasi secara otomatis tanpa disrupsi user.
- **Upgrade Path:** *ponytail:* Menggunakan stdlib `hashlib.pbkdf2_hmac` agar portabel 100% tanpa compiler C. Migrasi ke Argon2id direkomendasikan ketika lingkungan runtime cloud mengizinkan dependensi pustaka C eksternal (`argon2-cffi`).

---

## 2. TOKEN & SESSION MANAGEMENT

### 2.1 Arsitektur Session Cookie vs Bearer Token
BengkelStack memisahkan dua kanal antarmuka klien:
1. **Web Cloud Dashboard (Browser Manusia):**
   - Menggunakan Session Cookie berbasis HTTPOnly.
   - Atribut Cookie: `HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=86400`.
   - Di lingkungan produksi HTTPS menggunakan prefix `__Host-BengkelStack-Session`.
   - Mengeliminasi risiko pencurian token via serangan Cross-Site Scripting (XSS).
2. **Edge POS & Mobile App (Mesin / Client Native):**
   - Menggunakan HTTP Header: `Authorization: Bearer <opaque_token>`.

### 2.2 Evaluasi JWT vs Opaque Random Token
| Parameter Evaluasi | Stateless JWT | Opaque Random Token (BengkelStack) |
| :--- | :--- | :--- |
| **Penyimpanan di Server** | Tidak ada (stateless) | Hash SHA-256 tersimpan di database/cache |
| **Pencabutan Seketika (Revocation)** | Sulit (butuh denylist stateful) | **Seketika (Instant)** — hapus/flag di DB |
| **Resiko Kompromi Database** | Token aktif dapat dipalsukan jika secret bocor | Aman — DB hanya menyimpan SHA-256 hash |
| **Resiko Parsing / Kriptografi** | Rentan salah config (`alg: none`, key confusion) | **Nol resiko parsing crypto** |
| **Ukuran Payload Jaringan** | Besar (~500–1000 bytes) | Sangat hemat (~44 karakter URL-safe) |

**Keputusan Arsitektur:** BengkelStack mengadopsi **Opaque Random Token** berukuran 256-bit entropy (`secrets.token_urlsafe(32)`).
- Raw token hanya dikirim 1 kali ke klien saat pembuatan sesi.
- Database hanya menyimpan nilai `token_hash = sha256(raw_token).hexdigest()`.
- Saat request datang: server menghitung hash dari header Bearer dan mencocokkan ke database. Jika user menekan "Logout" atau token dicabut, record di DB langsung dihapus.

---

## 3. EDGE-TO-CLOUD SYNC SECURITY (PAIRING CREDENTIALS)

### 3.1 Masalah Keamanan & Ancaman
Terminal POS di bengkel fisik beroperasi di komputer kasir yang rentan diakses mekanik atau kasir. Password pemilik toko (**TENANT_OWNER**) **DILARANG KERAS** disimpan di terminal POS offline. Jika komputer kasir dicuri atau diakses pihak ketiga, akun utama pemilik tidak boleh terkompromi.

### 3.2 Alur Pairing Terminal POS
1. Pemilik bengkel login ke Cloud Dashboard BengkelStack via browser.
2. Membuka menu **Pengaturan Perangkat & POS** -> **Pairing Perangkat Baru**.
3. Cloud Dashboard menghasilkan sepasang kredensial mesin:
   - `Device ID`: `dev_<hex_16>` (Publik identifier perangkat)
   - `Device Secret`: `bs_sec_<token_urlsafe_32>` (Kunci simetris mesin)
4. Cloud Dashboard hanya menyimpan `sha256(Device Secret)` dengan metadata `tenant_id`, `device_id`, `created_at`, dan status `ACTIVE`.
5. Device Secret diinput satu kali ke POS lokal (disimpan dalam file aman `.env` / SQLite lokal).

### 3.3 Protokol Request Signing (HMAC-SHA256)
Setiap transaksi yang disinkronisasi dari POS lokal ke Cloud Gateway dikirim dengan signature kriptografis:
- **HTTP Headers:**
  - `X-Bengkel-Tenant-Id`: `<tenant_id>`
  - `X-Bengkel-Device-Id`: `<device_id>`
  - `X-Bengkel-Timestamp`: `<unix_epoch_seconds>`
  - `X-Bengkel-Nonce`: `<random_hex_16>`
  - `X-Bengkel-Signature`: `<hmac_sha256_hex>`
- **Payload Kanonikal yang Ditandatangani:**
  ```text
  METHOD
  REQUEST_PATH
  TIMESTAMP
  NONCE
  SHA256(REQUEST_BODY)
  ```
- **Formula Signature:**
  ```text
  Signature = HMAC-SHA256(DeviceSecret, CanonicalPayload)
  ```

### 3.4 Aturan Validasi Cloud Gateway
1. **Pemeriksaan Clock Drift:** Selisih `abs(ServerTime - Timestamp)` harus $\le 300$ detik (toleransi 5 menit). Melebihi batas langsung ditolak (`401 Unauthorized`).
2. **Mitigasi Serangan Replay (Nonce Deduplication):** Nonce dicatat dalam cache anti-replay. Nonce yang sama yang dikirim berulang dalam window 5 menit langsung ditolak.
3. **Verifikasi Hash Body:** Mencegah manipulasi transaksi (Man-in-the-Middle) di perjalanan jaringan.
4. **Constant-Time Verification:** Signature divalidasi dengan `secrets.compare_digest`.
5. **Instant Revocation:** Jika mesin kasir hilang/dicuri, pemilik toko cukup mengklik **"Revoke Device"** di Cloud Dashboard. Cloud mematikan status perangkat seketika tanpa mengubah password akun pemilik.

---

## 4. ROLE-BASED ACCESS CONTROL (RBAC)

### 4.1 Definisi Peran (Roles)
1. **`SUPERADMIN`**: Platform Engineer / Operator BengkelStack Cloud. Mengelola isolasi multi-tenant, billing tier, dan operasional infrastruktur. Tidak mengintip data privat transaksi bengkel tanpa izin audit.
2. **`TENANT_OWNER`**: Pemilik bengkel fisik. Kontrol penuh atas seluruh aspek bisnis bengkel miliknya: laporan laba bersih, HPP/COGS, tarif jasa, akun karyawan, dan pairing POS.
3. **`TENANT_OPERATOR`**: Kasir dan Service Advisor di bengkel. Melayani konsumen harian: pencarian sparepart, pembuatan nota (Work Order), checkout pembayaran, cetak struk termal.
4. **`DEVICE_AGENT`**: Identitas mesin POS lokal yang tersambung via pairing key. Terbatas untuk sinkronisasi transaksi.

### 4.2 Matriks Izin Granular (Permissions Matrix)

| Kode Izin (*Permission*) | Deskripsi Operasional | SUPERADMIN | TENANT_OWNER | TENANT_OPERATOR | DEVICE_AGENT |
| :--- | :--- | :---: | :---: | :---: | :---: |
| `tenant:manage` | Buat, blokir, hapus profil tenant | :white_check_mark: | :x: | :x: | :x: |
| `tenant:billing` | Kelola paket langganan SaaS Cloud | :white_check_mark: | :white_check_mark: | :x: | :x: |
| `device:pair` | Generate pairing key terminal POS | :x: | :white_check_mark: | :x: | :x: |
| `device:revoke` | Cabut akses terminal POS yang hilang | :white_check_mark: | :white_check_mark: | :x: | :x: |
| `user:manage` | Buat/kelola akun operator & kasir | :x: | :white_check_mark: | :x: | :x: |
| `catalog:read` | Lihat katalog sparepart & tarif jasa | :x: | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| `catalog:write_price` | Ubah harga jual ritel & ongkos pasang | :x: | :white_check_mark: | :x: | :x: |
| `catalog:write_cost` | Lihat & edit harga modal (COGS / HPP) | :x: | :white_check_mark: | :x: | :x: |
| `pos:transact` | Buat nota, edit draft, bayar nota kasir | :x: | :white_check_mark: | :white_check_mark: | :x: |
| `pos:void_completed` | Batalkan nota yang sudah berstatus LUNAS | :x: | :white_check_mark: | :x: | :x: |
| `reports:financial_margin` | Rekapitulasi laba-rugi & margin kotor | :x: | :white_check_mark: | :x: | :x: |
| `sync:push` | Unggah stream transaksi dari terminal | :x: | :white_check_mark: | :x: | :white_check_mark: |

### 4.3 Invarian Anti-Fraud Bengkel
- **Larangan Pembatalan Sepihak (`pos:void_completed`):** Kasir/Operator dilarang membatalkan transaksi yang sudah berstatus `COMPLETED`. Tindakan ini mencegah kecurangan kasir mengambil uang tunai konsumen lalu membatalkan transaksi di sistem.
- **Isolasi Kerahasiaan Margin (`catalog:write_cost` & `reports:financial_margin`):** Kasir hanya melihat harga jual eceran. Informasi margin keuntungan dan harga modal kulakan distributor hanya bisa diakses oleh `TENANT_OWNER`.

---

## 5. MITIGASI ANCAMAN (THREAT MITIGATION)

### 5.1 Proteksi Brute-Force & Credential Stuffing
- **Mekanisme:** Dual-layer tracking (kombinasi IP Address klien dan identifier akun/username).
- **Ambang Batas (Threshold):** Maksimal 5 kali kegagalan otentikasi berturut-turut dalam jendela 15 menit (900 detik).
- **Hukuman:** Akun/IP dikunci sementara (*temporary lockout*) selama 15 menit dengan status `429 Too Many Requests` dan header `Retry-After: 900`.
- **Anti-User-Enumeration:** Respon kegagalan login selalu menggunakan pesan generik: `"Email atau password salah"` dengan durasi komputasi yang seragam.

### 5.2 Proteksi Cross-Site Request Forgery (CSRF)
- Cookie sesi dikonfigurasi dengan `SameSite=Lax` (atau `Strict`).
- Untuk request mutasi state (`POST`, `PUT`, `DELETE`):
  - Validasi header standar: Verifikasi bahwa `Origin` atau `Referer` sesuai dengan whitelist domain `bengkelstack.com`.
  - Double Submit Cookie / Header Token: Request wajib menyertakan header `X-CSRF-Token` yang dicocokkan dengan cookie anti-CSRF.

### 5.3 Proteksi Timing Attacks
- Semua operasi perbandingan string sensitif wajib menggunakan `secrets.compare_digest`:
  1. Verifikasi digest password PBKDF2.
  2. Verifikasi opaque session token hash.
  3. Verifikasi signature HMAC pada sinkronisasi POS.
  4. Verifikasi API Key eksternal.

### 5.4 Pencegahan Kebocoran Isolasi Multi-Tenant (Anti-IDOR)
1. **Scoped Context Invariant:** Nilai `tenant_id` **TIDAK PERNAH** dipercayai dari URL parameter, query string, atau request body klien. `tenant_id` diekstrak murni dari token sesi yang sudah terverifikasi secara kriptografis di sisi server.
2. **Klausul SQL Wajib (Row-Level Tenancy):** Setiap query ke database wajib memuat klausul `tenant_id = ?` dengan parameter binding:
   ```sql
   SELECT * FROM work_orders WHERE tenant_id = ? AND id = ?;
   ```
3. **Compound Unique Constraints:** Mencegah tabrakan nomor faktur antar bengkel yang berbeda:
   ```sql
   UNIQUE(tenant_id, order_number)
   UNIQUE(tenant_id, plate_number)
   ```
4. **Runtime Enforcement Barrier:** Framework aplikasi mengeksekusi assertion `enforce_tenant_predicate` pada handler data untuk menggagalkan eksekusi jika klausul `tenant_id` tidak disertakan.

---

## 6. KESIMPULAN ARSITEKTUR
Arsitektur Tier 2 BengkelStack memenuhi standar industri keamanan OWASP dengan memanfaatkan keunggulan Python Standard Library murni (`hashlib`, `hmac`, `secrets`, `time`). Solusi ini menjamin efisiensi performa tinggi tanpa overhead ketergantungan paket pihak ketiga yang rentan terhadap supply-chain vulnerability.
