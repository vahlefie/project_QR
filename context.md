# Project Context

## Tujuan Project

Aplikasi web berbasis Python Flask untuk mengelola data tamu berbasis role:
- `super_admin`: mengelola admin, user, dan seluruh data tamu.
- `admin`: mengelola user dan seluruh data tamu.
- `user`: mengelola data tamu miliknya sendiri.
- `staff`: mengelola data tamu milik client yang menambahkannya.

Fokus utama project saat ini adalah autentikasi, manajemen user/admin/staff, upload Excel data tamu, data cleaning, validasi format, tabel data tamu, edit status, hapus baris, tambah tamu manual, download data Excel dari backend admin, chart dashboard client, dan kesiapan deploy VPS.

Standar dokumentasi kode: setiap fungsi Python diberi komentar `#` tepat di atas baris `def` untuk menjelaskan kegunaan atau peruntukannya.

## Tech Stack

- Backend: Python Flask
- Database: SQLAlchemy dengan SQLite `users.db` pada environment development
- Data processing: Pandas
- Export Excel: Pandas ExcelWriter dengan `openpyxl`
- Frontend: Template Jinja HTML dan CSS custom di `static/style.css`
- Development server: Flask local development server
- Production server: Gunicorn di belakang Nginx reverse proxy
- Process manager production: `systemd` service `project_qr`
- SSL production: Certbot/Nginx untuk domain `vlf.my.id`

## Struktur Utama Aplikasi

- `app.py`: app factory `create_app()`, instance kompatibilitas `app`, wrapper helper bersama, dan bootstrap service aplikasi.
- `config.py`: konfigurasi Flask default, database URL, secret key, cookie session, proxy fix, dan GeoIP path.
- `constants.py`: konstanta bersama untuk role, validasi tamu/user, session, staff, attendance, brute force, dan path log.
- `exceptions.py`: exception aplikasi bersama, termasuk `UploadValidationError` untuk validasi upload Excel.
- `extensions.py`: objek ekstensi shared seperti `db = SQLAlchemy()` untuk menghindari circular import saat model dipisah.
- `models.py`: model database `User`, `BillingPayment`, `EventArchive`, `Guests`, `DemoGuest`, `GuestShortUrl`, `AttendanceVerificationRequest`, `AttendanceVerificationDismissal`, `WhatsappSetting`, `WhatsappTemplate`, `Staff`, `StaffAccess`, dan `LoginThrottle`.
- `run.py`: entry point ringan untuk menjalankan server development Flask.
- `blueprints/registry.py`: registry pendaftaran Blueprint dan daftar dependency eksplisit per Blueprint.
- `services/account_service.py`: service helper akun untuk normalisasi nomor HP, nama tampilan, periode akhir/status aktivasi, validasi form user/admin, generate username client, dan daftar akun manageable.
- `services/attendance_service.py`: service token verifikasi kehadiran, token QR tamu, generator QR SVG, format waktu kehadiran, logging attendance, pencarian tamu attendance, dan proses verifikasi nomor HP/QR.
- `services/auth_service.py`: service autentikasi untuk normalisasi identifier, throttle login, session login, validasi password, hash password, dan lookup user aktif.
- `services/guest_service.py`: service upload Excel tamu, validasi format, data cleaning, duplicate detection, save/replace rows, pending upload, dan helper data tamu/staff.
- `services/event_archive_service.py`: service arsip final event client, export final dari CSV, pemindahan upload lama, dan kompresi arsip event `tar.gz`.
- `services/listing_service.py`: service redirect halaman, guard akses tamu, query/filter/sorting/pagination data tamu, context halaman data user/staff/admin, dan context daftar user.
- `services/logging_service.py`: service logging request, auth, activity, system error, request id, tracking session id, GeoIP lookup, dan parser log harian.
- `services/log_backup_service.py`: service backup log bulanan ke arsip `tar.gz`, verifikasi isi arsip, dan cleanup file log lama.
- `services/request_service.py`: service lifecycle request Flask, helper form, timeout session login, access log, error handler, dan decorator login/role.
- `services/schema_service.py`: service bootstrap database, migrasi ringan schema SQLite, normalisasi status tamu tersimpan, default super admin, dan seed fallback data demo dashboard.
- `services/staff_service.py`: service token akses staff, PIN, cookie session staff, idle timeout, revoke/block/unblock akses, current staff dari cookie, logging aktivitas staff, context halaman staff, status staff, validasi form staff, dan parser log staff.
- `services/whatsapp_service.py`: service konfigurasi WhatsApp, template pesan WhatsApp, short URL QR tamu, masking token API, dan helper URL pendek `/q/<short_code>`.
- `blueprints/auth/routes.py`: Blueprint autentikasi untuk route `/`, `/login`, `/reset-password`, `/password/new`, dan `/logout`.
- `blueprints/attendance/routes.py`: Blueprint verifikasi kehadiran publik untuk route `/kehadiran/<attendance_token>`, `/kehadiran/<attendance_token>/qr.png`, `/kehadiran/<attendance_token>/qr.svg` sebagai redirect kompatibilitas, `/kehadiran/<attendance_token>/verify`, `/kehadiran/<attendance_token>/request/<request_id>/status`, `/kehadiran/<attendance_token>/request/<request_id>/result`, `/q/<short_code>`, `/qr/<guest_token>`, `/qr/<guest_token>/image.svg`, dan `/qr/<guest_token>/status`.
- `blueprints/dashboard/routes.py`: Blueprint dashboard dan profile untuk route `/admin/dashboard`, `/super-admin/dashboard`, `/user/dashboard`, dan `/profile`.
- `blueprints/client_staff/routes.py`: Blueprint pengelolaan staff dari sisi client untuk route `/user/staff...`.
- `blueprints/staff/routes.py`: Blueprint session staff, dashboard staff, dan pengelolaan data tamu staff untuk route `/staff...`.
- `blueprints/guests/routes.py`: Blueprint update/hapus baris tamu bersama untuk route `/guests/<guest_id>/status` dan `/guests/<guest_id>/delete`.
- `blueprints/user/routes.py`: Blueprint data tamu user untuk route `/user/data`, `/user/upload`, `/user/upload-confirm`, `/user/guests/new`, `/user/scan`, `/user/scan/verify`, dan `/user/delete-data`.
- `blueprints/admin/routes.py`: Blueprint admin/super-admin untuk manajemen client, admin, upload/export/hapus data tamu admin.
- `templates/`: halaman login, layout role, dashboard, user management, dan data tamu.
- `static/style.css`: tema UI utama, tabel, form, popup/modal, tombol, dropdown.
- `static/sidebar_toggle.js`: toggle sidebar, penyimpanan state sidebar, dan auto-close sidebar pada mobile setelah klik menu.
- `static/action_toggle.js`: helper global untuk mengubah action button lebih dari satu menjadi tombol `Show`/`Hide` dengan popup action.
- `static/password_toggle.js`: toggle tampil/sembunyi password.
- `static/indonesia_regions.js`: data wilayah Indonesia untuk form user.
- `scripts/backup_monthly_logs.py`: CLI backup log bulan sebelumnya.
- `scripts/log_backup.cron`: contoh jadwal cron tanggal 1 jam 00:01, 12:00, dan 18:00.
- `scripts/backup_expired_events.py`: CLI backup final data tamu client setelah melewati `period_end`.
- `scripts/event_archive.cron`: contoh cron harian jam 00:05 untuk backup final event expired.
- `instance/uploads/`: folder runtime untuk file Excel asli yang diupload client/admin. Folder `instance/`, `logs/`, dan `backup/` tidak ikut Git/deploy source; folder dibuat dan diisi oleh server saat runtime.
- `context.md`: dokumen konteks aktif project dan wajib diperbarui setiap ada perubahan fitur, format, deploy, atau spesifikasi.
- `rules.txt`: aturan kerja aktif project; file ini tetap berada di root dan tidak dipindah ke `archieve/`.

## Model Database

### User

Model `User` dipakai untuk akun `super_admin`, `admin`, dan `user`.

Kolom penting:
- `id`
- `username`
- `nama`
- `no_hp`
- `email`
- `perusahaan`
- `alamat`
- `kota`
- `provinsi`
- `aktivasi`
- `paket`
- `tgl_daftar`
- `tgl_expired` sebagai nama kolom database lama untuk `periode_akhir`
- `password`
- `role`
- `must_reset_password`
- `active_session_token`
- `is_blocked`
- `blocked_at`
- `attendance_token_nonce`
- `attendance_token_generated_at`

Catatan:
- `attendance_token_nonce` dan `attendance_token_generated_at` pada `User` adalah field legacy dari URL publik per client. Mekanisme aktif sekarang memakai field token pada `Staff`.

### Guests

Model `Guests` dipakai untuk data tamu.

Kolom:
- `id`
- `no`
- `nama`
- `no_hp`
- `email`
- `status`
- `added_by`
- `kehadiran`
- `verified_by_staff_id`
- `verified_by_staff_name`
- `user_id`

Relasi:
- `Guests.user_id` mengarah ke `User.id`.
- User role `user` hanya boleh mengakses data tamu miliknya.
- Role `admin` dan `super_admin` boleh mengakses data tamu semua user.
- Staff hanya boleh mengakses data tamu milik client pemilik staff.
- `added_by` menyimpan label sumber penambah tamu. Upload client/admin untuk client memakai `username` client, tambah manual client memakai nama client, dan tambah manual staff memakai nama staff.

### GuestShortUrl

Model `GuestShortUrl` dipakai untuk URL pendek halaman QR tamu.

Kolom:
- `id`
- `guest_id`
- `short_code`
- `created_at`
- `updated_at`

Aturan:
- Satu tamu hanya memiliki satu short URL.
- `short_code` unik secara global.
- Format dasar `short_code`: `<user_id>_<nama_tamu_slug>`, contoh `3_Ajin_Ajojing`.
- Jika format dasar sudah dipakai tamu lain, suffix angka ditambahkan mulai dari `_2`.

### WhatsappSetting

Model `WhatsappSetting` dipakai untuk konfigurasi global WhatsApp dari super admin.

Kolom:
- `id`
- `send_mode`
- `phone_number`
- `api_token`
- `api_phone_number_id`
- `active_template_id`
- `updated_at`

### WhatsappTemplate

Model `WhatsappTemplate` dipakai untuk menyimpan template pesan WhatsApp.

Kolom:
- `id`
- `name`
- `body`
- `is_default`
- `created_at`
- `updated_at`

### Staff

Model `Staff` dipakai untuk akun staff yang dibuat oleh client.

Kolom:
- `id`
- `owner_user_id`
- `nama`
- `no_hp`
- `created_at`
- `is_blocked`
- `blocked_at`
- `block_reason`
- `attendance_token_nonce`
- `attendance_token_generated_at`

Relasi:
- `Staff.owner_user_id` mengarah ke `User.id` client.
- Kombinasi `owner_user_id` dan `no_hp` unik, sehingga satu client tidak bisa menambahkan nomor staff yang sama dua kali.
- Staff memiliki banyak `StaffAccess`.
- Setiap staff dapat memiliki satu URL publik/QR Client sendiri melalui `attendance_token_nonce`.

### AttendanceVerificationRequest

Model `AttendanceVerificationRequest` dipakai untuk antrean konfirmasi kehadiran oleh staff.

Kolom penting:
- `owner_user_id`
- `target_staff_id`
- `guest_id`
- `no_hp`
- `status`
- `source`
- `message`
- `expires_at`
- `confirmed_by_staff_id`
- `confirmed_by_staff_name`

Aturan:
- `target_staff_id` diisi untuk request yang berasal dari Link publik/QR Client milik staff.
- Popup staff hanya menampilkan request dengan `target_staff_id` sesuai staff login, atau request lama/global yang `target_staff_id` kosong.

### StaffAccess

Model `StaffAccess` dipakai untuk URL random dan PIN login staff.

Kolom:
- `id`
- `staff_id`
- `token_hash`
- `pin_hash`
- `failed_pin_attempts`
- `is_active`
- `created_at`
- `last_activity_at`
- `revoked_at`
- `revoked_by`
- `revoked_reason`

Aturan keamanan:
- Token URL mentah tidak disimpan di database; database hanya menyimpan hash SHA-256.
- PIN disimpan sebagai hash password.
- PIN maksimal salah 3 kali.
- Jika PIN salah 3 kali, staff otomatis diblokir dan semua akses aktif staff dicabut.
- Akses staff aktif dicabut saat client logout staff, staff logout, staff diblokir, akses diganti oleh login baru, atau idle 2 jam.

### EventArchive

Model `EventArchive` dipakai untuk mencatat arsip final event client setelah melewati tanggal periode akhir.

Kolom:
- `id`
- `user_id`
- `event_name`
- `package_name`
- `period_start`
- `period_end`
- `csv_path`
- `tar_path`
- `guest_count`
- `status`
- `created_at`
- `archived_at`

Aturan:
- `csv_path` menunjuk file final `<nama_event>_Final_YYYY.csv` di `backup/event/<user_id>/`.
- `tar_path` menunjuk arsip `<nama_event>_YYYY.tar.gz` saat event lama sudah dikompresi pada proses reaktivasi.
- Backup final harus selesai sebelum data tamu pada tabel `Guests` dihapus.
- Export final untuk client nonaktif membaca CSV final, lalu mengubahnya ke `.xlsx` saat download.

### DemoGuest

Model `DemoGuest` dipakai sebagai sumber data dummy dashboard client mode Demo.

Kolom:
- `id`
- `no`
- `nama`
- `no_hp`
- `email`
- `status`
- `kehadiran`
- `verifikasi`
- `source_file`

Aturan:
- Tabel dibuat saat bootstrap database lewat `services/schema_service.py`.
- Jika file Excel demo `data_dummy_1000_baris.xlsx` tersedia di `DEMO_GUEST_EXCEL_PATH`, data demo dibaca dari file tersebut.
- Jika file Excel demo tidak tersedia, server membuat fallback 1000 baris demo deterministik lewat `build_fallback_demo_guest_rows()`.
- Fallback demo memakai `source_file = generated_demo_seed`, kombinasi status `Reguler`/`VIP`, jam kehadiran bertahap, dan label verifikasi staff dummy.
- Fallback ini penting untuk VPS karena file Excel lokal `~/Downloads/data_dummy_1000_baris.xlsx` tidak ikut GitHub/deploy.

## Format Excel Data Tamu

Format kolom Excel wajib sama persis:

```text
no | nama | no_hp | email | status
```

Jika format tidak sesuai, upload dibatalkan dan UI menampilkan popup:

```text
Format data excel tidak sesuai
```

Popup memiliki tombol `Tutup`.

## Aturan Data Cleaning Tamu

Cleaning dijalankan setelah klik upload file dan sebelum data disimpan.

### nama

- Tipe data dianggap string.
- Maksimal 30 karakter.
- Awalan setiap kata dibuat huruf kapital.
- Karakter spesial dihapus.
- Spasi di awal dihapus.
- Wajib diisi.
- Jika kosong atau `N/A`, baris dihapus.

### no_hp

- Wajib diisi.
- Minimal 8 digit.
- Angka desimal ditolak.
- Angka negatif ditolak.
- Jika diawali `0`, angka awal diganti menjadi `62`.
- Jika diawali `8`, ditambahkan `62` di awal.
- Jika hasil tidak valid atau `N/A`, baris dihapus.

### email

- Tipe data dianggap string.
- Maksimal 30 karakter.
- Harus mengandung `@` dan `.`.
- Jika tidak valid, email dikosongkan dan ditampilkan sebagai `N/A`.

### status

- Pilihan valid: `Reguler` atau `VIP`.
- Jika kosong atau tidak valid, default menjadi `Reguler`.

### kehadiran

- Format tampilan timestamp: `dd-MMM HH:mm`, contoh `05-Jun 18:00`.
- Jika belum ada nilai, tampil sebagai `N/A`.

## Verifikasi Kehadiran Tamu

Route utama:
- `GET /kehadiran/<attendance_token>`
- `GET /kehadiran/<attendance_token>/qr.png`
- `GET /kehadiran/<attendance_token>/qr.svg` redirect ke PNG
- `POST /kehadiran/<attendance_token>/verify`
- `GET /kehadiran/<attendance_token>/request/<request_id>/status`
- `GET /kehadiran/<attendance_token>/request/<request_id>/result`

Perilaku:
- Link verifikasi memakai token bertanda tangan berdasarkan `Staff.id`, `Staff.owner_user_id`, dan `Staff.attendance_token_nonce`, sehingga satu staff memiliki satu URL publik/QR Client sendiri.
- `Staff.attendance_token_nonce` dibuat/diperbarui oleh client dari halaman `/user/staff` pada kolom `URL Client`.
- Saat URL staff digenerate ulang, nonce lama diganti sehingga URL publik/QR staff lama otomatis tidak valid.
- Kartu `Verifikasi Kehadiran` di dashboard client tetap dipertahankan tanpa tombol; kontrol `Buka`, `Generate`, dan `QR Client` dipindahkan ke halaman Staff client.
- Tombol `QR Client` pada halaman Staff client mengunduh QR PNG resolusi sekitar 2400 px yang berisi URL halaman verifikasi `/kehadiran/<attendance_token>`. Jika discan device tamu, halaman verifikasi langsung terbuka di device tamu.
- Halaman publik menampilkan UI input nomor HP dengan prefix visual `+62`.
- Kolom input setelah prefix menerima angka minimal 8 digit yang diawali `08` atau `8`; frontend mengirim hidden value canonical `62...`.
- Jika nomor ditemukan dan `kehadiran` masih kosong, backend membuat `AttendanceVerificationRequest` status `pending`; halaman tamu berubah menjadi status tunggu `Harap Tunggu Sebentar, Data Sedang Diverifikasi` dengan spinner dan polling status tiap 3 detik.
- Popup verifikasi kehadiran hanya muncul di sisi staff pemilik QR jika request memiliki `target_staff_id`. Staff lain hanya menerima request dari QR/link miliknya masing-masing.
- Staff dapat klik `Konfirmasi` untuk mengisi `Guests.kehadiran` dan `verified_by_staff_name`, atau klik `Tolak/Tutup` untuk menutup request bagi staff tersebut.
- Jika staff klik `Konfirmasi`, halaman tamu otomatis redirect ke halaman hasil dan menampilkan `Selamat Datang Bpk/Ibu (nama tamu)`.
- Jika request habis karena timeout 1 menit tanpa konfirmasi, halaman tamu menampilkan `Waktu Habis, Nomor Tidak Berhasil Diverifikasi`.
- Jika staff target klik `Tolak/Tutup`, halaman tamu menampilkan `Nomor Tidak Berhasil Diverifikasi, Harap Hubungi Staff`. Untuk request global tanpa `target_staff_id`, pesan ini muncul jika semua staff aktif menutup request.
- Jika tamu mencoba verifikasi kembali saat request masih pending, halaman menampilkan `Silahkan dicoba kembali setelah beberapa saat lagi`.
- Jika nomor tidak ditemukan, request notifikasi staff status `not_registered` dibuat dan halaman tamu menampilkan pesan nomor tidak terdaftar setelah proses selesai.
- Jika nomor ditemukan tetapi `kehadiran` sudah terisi, request notifikasi staff status `already_verified` dibuat dan halaman tamu menampilkan pesan sudah terverifikasi setelah proses selesai.
- Tombol merah `Tutup Halaman` tetap tersedia pada halaman hasil. Jika browser menolak `window.close()`, halaman menampilkan hint untuk menutup tab secara manual.
- Saat request awal berjalan atau koneksi tidak stabil, halaman menampilkan spinner loading dan teks koneksi tidak stabil jika response belum diterima.
- Jika server mengembalikan error atau link tidak valid, halaman menampilkan pesan error tanpa menampilkan `Request ID` dan `Kode pemeriksaan` pada UI tamu.

Logging:
- Event verifikasi ditulis ke kategori log `ATTENDANCE` dengan event `GUEST_ATTENDANCE_PENDING_STAFF_CONFIRMATION`, `GUEST_ATTENDANCE_CONFIRMED_BY_STAFF`, `GUEST_ATTENDANCE_NOT_FOUND`, `GUEST_ATTENDANCE_ALREADY_VERIFIED`, `GUEST_ATTENDANCE_INVALID_LINK`, atau `GUEST_ATTENDANCE_SERVER_ERROR`.
- Access log menyimpan header `X-Client-Request-ID` pada field `client_request_id`.
- Pemeriksaan log tetap bisa dilakukan dari file `logs/activity_YYYY-MM-DD.log` menggunakan access log, `request_id`, atau `client_request_id` yang tersimpan di log server.

## QR Code Kehadiran Tamu Premium

Route publik:
- `GET /q/<short_code>`
- `GET /qr/<guest_token>`
- `GET /qr/<guest_token>/image.svg`
- `GET /qr/<guest_token>/status`

Route scan client:
- `GET /user/scan`
- `POST /user/scan/verify`

Perilaku:
- QR Code hanya tersedia untuk tamu milik client dengan `User.paket == "premium"`.
- Token QR memakai serializer bertanda tangan dengan salt `guest-qr-attendance` dan payload `guest_id`, `owner_user_id`, serta scope `guest_qr`.
- Link `/qr/<guest_token>` boleh diberikan ke tamu. Halaman ini hanya menampilkan QR/status dan tidak dapat mengisi `Guests.kehadiran` sendiri.
- Link pendek `/q/<short_code>` redirect ke `/qr/<guest_token>`. Short code dibuat dari `<user_id>_<nama_tamu_slug>`, contoh `3_Ajin_Ajojing`; jika duplicate, tamu terbaru mendapat suffix seperti `_2`.
- Gambar QR SVG berisi komposisi `<guest_id><user_id><guest_token><no_hp>` tanpa delimiter, bukan URL halaman QR. Endpoint scan tetap memvalidasi `guest_token`, mencocokkan metadata `guest_id`, `user_id`, dan `no_hp`, serta masih dapat membaca URL `/qr/<guest_token>` atau token mentah sebagai fallback.
- Halaman publik QR melakukan polling ke `/qr/<guest_token>/status` setiap 3 detik saat belum terverifikasi.
- Halaman publik QR menampilkan countdown `05:00` berwarna merah di bawah nama tamu. Setelah waktu habis, QR disembunyikan, polling dihentikan, dan halaman menampilkan status expired sampai link QR dibuka ulang.
- Setelah panitia scan QR dan backend mengisi `Guests.kehadiran`, halaman QR yang sedang terbuka reload ke `?verified=1` dan menampilkan `Selamat Datang Bpk/Ibu (nama tamu).` lalu baris baru `Terima Kasih Atas Kehadiran dan Partisipasinya.` serta teks kecil `Silahkan untuk menutup browser ini`.
- Jika tamu membuka link QR setelah sudah terverifikasi, halaman menampilkan `Kode QR Sudah Terverifikasi Sebelumnya.` lalu baris baru `Harap Hubungi Staff Reservasi Jika Terdapat Kendala.`
- Endpoint `/user/scan/verify` wajib login role `user`, wajib paket Premium, dan hanya menerima QR tamu milik client yang sedang login.
- Scan ulang tidak overwrite `Guests.kehadiran`.
- Event scan dicatat di kategori `ATTENDANCE` dengan event `GUEST_QR_ATTENDANCE_VERIFIED`, `GUEST_QR_ATTENDANCE_ALREADY_VERIFIED`, atau `GUEST_QR_ATTENDANCE_INVALID`.
- Halaman `/user/scan` menyediakan dua mode: `Kamera` untuk tablet/webcam via `BarcodeDetector`, dan `Scanner` untuk alat scanner fisik yang mengisi input token seperti keyboard.
- Mode `Scanner` tidak memiliki tombol verifikasi; input scanner auto-submit setelah kode terbaca atau saat scanner mengirim Enter.

## Setting WhatsApp Super Admin

Route utama:
- `GET /super-admin/settings/whatsapp`
- `POST /super-admin/settings/whatsapp/mode`
- `POST /super-admin/settings/whatsapp/phone`
- `POST /super-admin/settings/whatsapp/api-token`
- `POST /super-admin/settings/whatsapp/api-phone-number-id`
- `POST /super-admin/settings/whatsapp/template`

Perilaku:
- Menu `Setting > WhatsApp` aktif hanya pada layout super admin.
- Mode `development` memakai `wa.me` untuk testing lokal; pengiriman tetap manual dari WhatsApp.
- Mode `production` disiapkan untuk WhatsApp API setelah aplikasi deploy.
- Nomor WhatsApp memakai UI prefix `+62` dan disimpan canonical `62...`.
- API token ditampilkan tersensor dengan `*` dan menyisakan 4 karakter terakhir.
- Field `Phone Number ID` disediakan untuk kebutuhan WhatsApp Cloud API production.
- Template pesan memiliki mode readonly opacity abu-abu 50%, tombol `Edit`, lalu tombol `Simpan` dan `Batal` saat diedit.
- Format pesan yang tersedia: Tebal `*teks*`, Miring `_teks_`, Coret `~teks~`, dan Monospace ```teks```.
- Variabel template yang disediakan: `{nama_tamu}`, `{no_hp}`, `{qr_url}`, `{short_qr_url}`, dan `{nama_client}`.
- Template bisa disimpan dan dimuat ulang dari dropdown `Load Template`; template terakhir disimpan menjadi default.

Route kirim undangan QR:
- `GET /guests/<guest_id>/whatsapp-invite`

Perilaku kirim:
- Route wajib login role `user`, `admin`, atau `super_admin` dan tetap memakai guard akses tamu.
- Data Tamu client/admin/superadmin menampilkan kolom `WhatsApp` dengan tombol `Kirim` untuk tamu Premium yang memiliki QR.
- Backend membuat short URL QR jika belum ada, merender template aktif, lalu pada mode `development` redirect ke `https://wa.me/<no_hp_tamu>?text=<pesan>`.
- Jika belum ada template tersimpan, sistem memakai fallback template development berisi `{nama_tamu}` dan `{short_qr_url}`.
- Mode `production` belum mengirim API pada development lokal; route mengembalikan error jika konfigurasi API belum lengkap atau integrasi production belum aktif.
- Event pembukaan link WhatsApp dicatat sebagai `OPEN_GUEST_WHATSAPP_INVITE`.

## URL Client Per Staff

Route utama:
- `POST /user/staff/<staff_id>/attendance-url/generate`
- `POST /admin/users/<user_id>/attendance-url/generate` hanya kompatibilitas endpoint lama dan mengembalikan status `410 moved`.

Halaman `/user/staff` client memiliki kolom `URL Client` di sebelah kanan kolom `Action`:
- Setiap baris staff aktif menampilkan tombol `Generate` warna abu-abu dan tombol biru `QR Client`.
- Tombol `Generate` membuat/memperbarui URL publik milik staff pada baris tersebut.
- Tombol `QR Client` mengunduh QR PNG dari `/kehadiran/<attendance_token>/qr.png`. Isi QR adalah URL halaman verifikasi kehadiran milik staff, bukan token mentah.
- Jika staff belum pernah generate URL, tombol `QR Client` tampil disabled sampai `Generate` berhasil.
- Jika URL belum pernah dibuat, klik `Generate` langsung membuat URL dan menampilkan popup notifikasi `URL publik sudah dibuat.`.
- Jika URL sudah pernah dibuat, klik `Generate` membuka popup peringatan `Terakhir generate pada (tanggal terakhir generate).` lalu baris baru `Apakah akan membuat ulang URL?`.
- Popup konfirmasi memiliki tombol `Ya` warna biru dan `Batal` warna merah.
- Klik `Ya` membuat atau memperbarui `Staff.attendance_token_nonce`, mengisi `Staff.attendance_token_generated_at`, dan mengembalikan URL publik baru.
- Response JSON generate juga mengembalikan `attendance_qr_url`; frontend memakai value ini untuk mengaktifkan tombol `QR Client` tanpa reload halaman.
- Setelah sukses, popup menampilkan `URL publik sudah dibuat.` dengan tombol `Buka` warna biru dan `Tutup` warna merah.
- Tombol `Buka` membuka halaman verifikasi kehadiran dengan token staff terbaru pada tab baru.
- Staff yang diblokir tidak dapat generate URL; QR/link staff yang diblokir juga dianggap tidak valid pada route publik.
- Event generate dicatat sebagai `GENERATE_STAFF_ATTENDANCE_URL` pada log activity.
- Halaman `/users` admin/super admin tidak lagi menampilkan kolom `URL Client`.

## Upload Data Tamu Role User

Route utama:
- `GET /user/data`
- `POST /user/upload`
- `POST /user/upload-confirm`

Perilaku upload:
- File Excel dibaca dengan Pandas.
- Format kolom divalidasi sebelum cleaning.
- Setelah file berhasil dibaca dan format kolom valid, file Excel asli disimpan ke `instance/uploads/`.
- Nama file upload memakai format `<nama_event>_<username_client>_YYYY-MM-DD.xlsx`.
- `nama_event` diambil dari `BillingPayment.event_name` terbaru milik client, fallback ke `User.perusahaan`, lalu `User.nama`, lalu `event`.
- Bagian nama file dibersihkan menjadi karakter alfanumerik dan underscore.
- Jika client/admin upload lebih dari satu kali pada tanggal yang sama dengan nama dasar yang sama, suffix nomor urut ditambahkan: `_2`, `_3`, dan seterusnya.
- Data yang tidak valid dihapus saat cleaning.
- Data valid ditampilkan dalam ringkasan popup.
- Popup `Konfirmasi Upload Data Tamu` menampilkan tabel `Data tamu yang dihapus saat cleaning` jika ada baris yang terhapus.
- Tabel data yang dihapus menampilkan `Baris`, `No`, `Nama`, `No HP`, `Email`, `Status`, dan `Alasan`.
- Alasan saat ini mencakup `Nama kosong/tidak valid` dan `No HP kosong/tidak valid`.
- Jika tidak ada data yang sama, data langsung disimpan dan popup hanya menampilkan ringkasan dengan tombol `Tutup`.
- Jika ada data yang sama, popup menampilkan daftar duplicate dan pertanyaan:

```text
Apakah akan memperbarui data yang sama?
```

Pilihan:
- `Ya`: data yang sama akan di-replace dengan data baru, tanpa membuat duplikasi.
- `Tidak`: data yang sama tidak dimasukkan.

Duplicate dicocokkan terhadap data tersimpan dan baris lain di file upload berdasarkan nilai yang sama pada `no_hp` atau `email`. `nama` tetap wajib dan dibersihkan, tetapi tidak dipakai sebagai kunci unique saat upload.
Setiap tamu yang masuk lewat upload client/admin untuk client mengisi kolom `Ditambahkan` dengan `username` client pemilik data.

## Data Tamu Role User

Halaman menu `Data` user menampilkan:
- Upload Excel.
- Search.
- Sorting: terbaru, nama A-Z, nama Z-A, kehadiran terbaru.
- Pagination: 10, 50, 100.
- Tombol `Tambah Tamu` di sebelah kanan tombol `Apply`.
- Tabel data tamu.

Jika client sudah tidak aktif setelah periode event berakhir:
- Informasi event, paket, periode mulai, dan periode akhir tetap ditampilkan dari payment terakhir, bukan `N/A`.
- Tabel data tamu, upload, tambah tamu, edit status, WhatsApp invite, dan hapus baris tidak ditampilkan atau ditolak backend.
- Fitur yang tetap tersedia hanya `Ekspor Data`.
- Route `/user/data` hanya merender halaman Data dan tidak boleh otomatis mengunduh file; download hanya terjadi saat client klik tombol `Ekspor Data`.
- Jika backup final belum ada, export menjalankan backup final terlebih dahulu; setelah backup berhasil, data tamu aktif di tabel `Guests` dihapus.

Kolom tabel:
- `No`
- `Nama`
- `No HP`
- `Email`
- `Status`
- `Ditambahkan`
- `Kehadiran`
- `Verifikasi`
- `QR Code`
- `WhatsApp`
- `Action`

Action per baris:
- `View` pada kolom `QR Code`: membuka halaman QR publik tamu Premium di tab baru. Jika client bukan Premium, nilai kolom `QR Code` adalah `N/A`.
- `Edit`: pada backend client mengubah kolom `Nama`, `No HP`, `Email`, dan `Status` menjadi field edit inline, lalu tombol berubah menjadi `Simpan` warna biru.
- Saat mode edit aktif, tombol `Hapus` berubah menjadi `Batal` dengan warna merah yang sama seperti tombol `Hapus`; klik `Batal` membatalkan edit, mengembalikan field ke nilai awal, dan tidak menghapus data.
- Selama mode edit aktif, tombol `Simpan` dan `Batal` tetap ditampilkan sampai salah satunya diklik, termasuk saat user klik area lain di halaman.
- `Hapus`: menghapus baris data tamu terpilih saat row tidak sedang dalam mode edit.

Fitur `Hapus Semua Data` untuk role user sudah dihilangkan dari UI. Route lama `/user/delete-data` tetap ada sebagai fallback, tetapi sudah dinonaktifkan dan tidak menghapus data.

## Tambah Tamu Manual Role User

Route:
- `POST /user/guests/new`

Tombol `Tambah Tamu` membuka popup input:
- `nama`
- `no_hp` memakai UI prefix `+62` dengan input lokal angka minimal 8 digit yang diawali `08` atau `8`
- `email`
- `status`

Tombol popup:
- `Simpan`
- `Batal`

Data dari popup tetap melewati cleaning yang sama:
- `nama` dibersihkan dan dibuat title case.
- `no_hp` divalidasi unik per pemilik data tamu dan dinormalisasi ke format canonical `62...`.
- `email` invalid menjadi `N/A`.
- `status` default `Reguler` jika kosong/tidak valid.
- `Ditambahkan` diisi dengan nama client yang sedang login, fallback ke username jika nama kosong.

Jika `nama` atau `no_hp` tidak valid, data tidak disimpan dan popup tetap terbuka dengan pesan error.

## Staff Role Client

Route utama client:
- `GET /user/staff`
- `POST /user/staff`
- `POST /user/staff/<staff_id>/login`
- `POST /user/staff/<staff_id>/logout`
- `POST /user/staff/<staff_id>/block`
- `POST /user/staff/<staff_id>/unblock`
- `GET /user/staff/status`

Menu client:
- Menu `Scan` muncul di bawah menu `Data` hanya untuk client Premium.
- Menu `Staff` muncul di bawah menu `Data`.

Halaman `Staff` client menampilkan:
- Form tambah staff dengan input `Nomor HP`, `Nama`, dan tombol `Tambah Staff`.
- Input nomor HP staff memakai UI prefix `+62` yang sama dengan halaman `Tambah Client` role admin.
- Tabel daftar staff tanpa search, sort, paging, dan total staff.
- Kolom tabel staff: `No`, `Nomor HP`, `Nama`, `Action`.
- Kolom paling kanan `Log` berisi tombol `View`.
- Action staff:
  - `Login`: membuka tab baru berisi URL random login staff dan PIN 6 digit.
  - `Logout`: mencabut akses aktif staff dari dashboard client.
  - `Block`: membuka popup peringatan dengan tombol `Ya` dan `Batal`, lalu memblokir staff dan mencabut semua akses aktifnya.
  - `Unblock`: melepas blokir staff.
- Tombol `View` pada kolom `Log` membuka popup log aktivitas staff terpilih dengan tombol `Tutup`.
- Popup log hanya menampilkan aktivitas staff pada baris terpilih untuk hari ini.
- Header popup log memakai format `Log Aktivitas Staff - Hari ini`.
- Format waktu log memakai jam, menit, dan detik.
- Isi log diformat sebagai timeline informatif agar mudah dibaca orang awam.
- Tombol `Login` memakai warna biru tema utama.
- Tombol `Logout` memakai warna hijau tema.
- Tombol `View` memakai warna abu-abu tema.
- Tombol `Unblock` memakai warna abu-abu tema.
- Popup log memiliki tombol `Download` berwarna abu-abu untuk mengunduh log dalam format `.txt`.
- Tombol `Tutup` pada popup log memakai warna merah tema.

Staff login tidak memakai session Flask utama. Session staff memakai cookie terpisah:

```text
staff_session
```

Perilaku session staff:
- Cookie staff ditandatangani dengan serializer Flask/itsdangerous.
- Session staff tidak mengubah session client di tab lama.
- Session staff diperpanjang setiap request staff aktif.
- Session staff berakhir setelah idle 2 jam.
- Jika session staff invalid, expired, staff diblokir, atau akses sudah dicabut, staff diarahkan ke halaman pesan session staff.
- Halaman pesan session staff tidak menampilkan kalimat `Session staff berakhir karena idle 2 jam.`; pesan default hanya meminta staff menghubungi client untuk membuka akses kembali.
- Jika client menekan tombol `Logout` staff dari menu Staff saat staff masih membuka halaman staff, halaman staff menampilkan `Logout staff berhasil.` tanpa pesan idle.
- Tombol `Login` pada halaman Staff client berubah menjadi `Logout` selama staff memiliki akses aktif.
- Tombol kembali menjadi `Login` setelah staff logout, client logout staff, staff idle 2 jam, atau akses dicabut.

Route utama staff:
- `GET /staff/access/<access_token>`
- `POST /staff/access/<access_token>`
- `GET /staff/data`
- `POST /staff/guests/new`
- `POST /staff/guests/<guest_id>/status`
- `POST /staff/guests/<guest_id>/delete`
- `GET /staff/logout`

Area staff langsung membuka menu `Data` setelah PIN login berhasil. Layout sidebar staff hanya berisi:
- `Data`
- `Logout`

Halaman `Data` staff memakai tampilan data tamu yang sama dengan client, tetapi tanpa upload Excel.
Popup `Tambah Tamu` staff memakai format input nomor HP yang sama dengan manual user: UI prefix `+62`, input lokal minimal 8 digit yang diawali `08` atau `8`, lalu backend menyimpan canonical `62...`.
Tamu yang ditambahkan dari area staff mengisi kolom `Ditambahkan` dengan nama staff, fallback ke nomor HP staff jika nama kosong.

Fitur Data staff:
- Search.
- Sorting otomatis memakai `Kehadiran` terbaru, sehingga waktu kehadiran paling baru muncul teratas.
- Pagination.
- Tambah tamu manual.
- Edit status.
- Hapus baris.

Staff hanya dapat menambah, mengedit status, dan menghapus data tamu dengan `Guests.user_id` yang sama dengan `owner_user_id` staff.

## Data Tamu Role Admin dan Super Admin

Route utama:
- `GET /admin/guests`
- `POST /admin/upload-guests`
- `POST /admin/upload-guests-confirm`
- `GET /admin/guests/download`
- `POST /admin/delete-guests`

Menu sidebar admin yang sebelumnya tampil sebagai `Guests` sekarang tampil sebagai `Data`. URL route tetap `/admin/guests`.

Halaman admin menampilkan:
- Upload Excel untuk user pemilik data yang dipilih.
- Upload admin menyimpan file Excel asli ke `instance/uploads/` memakai event terbaru dan username client pemilik data yang dipilih.
- Data tamu yang masuk lewat upload admin tetap mengisi `Ditambahkan` dengan `username` client pemilik data, bukan username admin.
- Setelah upload, admin/super admin melihat popup `Konfirmasi Upload Data Tamu` yang sama dengan client.
- Popup admin/super admin menampilkan ringkasan `Data valid`, `Data yang sama`, `Dihapus saat cleaning`, tabel data yang dihapus saat cleaning, dan tabel duplicate jika ada.
- Jika duplicate ditemukan, popup admin/super admin menampilkan pertanyaan `Apakah akan memperbarui data yang sama?`.
- Pada popup duplicate admin/super admin, `Ya` memperbarui data yang sama tanpa duplikasi, sedangkan `Tidak` menyimpan hanya data yang tidak duplicate.
- Duplicate upload admin/super admin memakai aturan yang sama dengan client: hanya `no_hp` dan `email` yang menjadi kunci data sama, bukan `nama`.
- Filter owner user.
- Search.
- Sorting: terbaru, nama A-Z, nama Z-A, kehadiran terbaru.
- Pagination.
- Tombol `Ekspor Data`.
- Tabel data tamu semua user.

Kolom tabel admin:
- `No`
- `Owner`
- `Nama`
- `No HP`
- `Email`
- `Status`
- `Kehadiran`
- `QR Code`
- `Action`

Action per baris:
- `View` pada kolom `QR Code`: membuka halaman QR publik tamu dari client Premium di tab baru. Jika owner bukan Premium atau data tidak punya owner, nilai kolom `QR Code` adalah `N/A`.
- `Edit`: mengubah status dengan dropdown `Reguler` / `VIP`, lalu tombol berubah menjadi `Simpan` warna biru.
- Saat mode edit aktif, tombol `Hapus` berubah menjadi `Batal` dengan warna merah yang sama seperti tombol `Hapus`; klik `Batal` membatalkan edit, mengembalikan dropdown ke nilai awal, dan tidak menghapus data.
- `Hapus`: menghapus baris terpilih saat row tidak sedang dalam mode edit.

Fitur hapus massal admin tetap tersedia untuk user terpilih:
- `Hapus Data User Terpilih`

## Ekspor Data Admin

Route:
- `GET /admin/guests/download`

Download mengikuti filter yang sedang dipakai:
- `search`
- `owner_user_id`
- `sort_by`

File Excel berisi kolom:

```text
no | nama | no_hp | email | status | kehadiran
```

Nama file:

```text
<nama_event>_YYYY-MM-DD.xlsx
```

`nama_event` diambil dari `BillingPayment.event_name` terverifikasi terbaru milik client yang dipilih. Jika event kosong atau `N/A`, fallback ke `User.perusahaan`, lalu `User.nama`. Jika tidak ada client, fallback menjadi `data_tamu`.

Jika client yang dipilih sudah tidak aktif karena melewati `period_end`, export admin membaca backup final CSV dan nama file menjadi:

```text
<nama_event>_Final_YYYY-MM-DD.xlsx
```

Nilai kosong:
- `email`: `N/A`
- `no_hp`: `N/A`
- `kehadiran`: `N/A`; jika ada nilai memakai format `dd-MMM HH:mm`
- `status`: default `Reguler`

## Ekspor Data Client

Route:
- `GET /user/guests/download`

Download mengikuti filter yang sedang dipakai:
- `search`
- `sort_by`

File Excel berisi kolom:

```text
no | nama | no_hp | email | status | kehadiran | verifikasi
```

Nama file:

```text
<nama_event>_YYYY-MM-DD.xlsx
```

`nama_event` diambil dari `BillingPayment.event_name` terverifikasi terbaru milik client yang sedang login. Jika event kosong atau `N/A`, fallback ke `User.perusahaan`, lalu `User.nama`.

Jika client sudah melewati `period_end`, export membaca file final CSV di `backup/event/<user_id>/<nama_event>_Final_YYYY.csv` dan nama file download menjadi:

```text
<nama_event>_Final_YYYY-MM-DD.xlsx
```

Tanggal pada nama file final adalah tanggal download, bukan tanggal pembuatan CSV.

## Arsip Final Event Client

Backup final event dibuat setelah client melewati `period_end`.

Perilaku:
- Job otomatis dijadwalkan melalui cron `scripts/event_archive.cron` pada jam 00:05 setiap hari.
- Script `scripts/backup_expired_events.py` mencari client dengan payment terverifikasi terbaru yang sudah melewati `period_end`.
- File CSV final disimpan ke `backup/event/<user_id>/<nama_event>_Final_YYYY.csv`.
- File upload Excel event lama di `instance/uploads/` ikut dipindahkan ke `backup/event/<user_id>/` setelah client melewati `period_end`.
- Mode manual `scripts/backup_expired_events.py --uploads-only` hanya memindahkan file upload client expired tanpa membuat CSV final dan tanpa menghapus data tamu.
- Setelah CSV berhasil dibuat dan diverifikasi, data tamu client tersebut dihapus dari tabel `Guests`.
- Export final client/admin memakai CSV final tersebut lalu mengubahnya menjadi `.xlsx`.

Saat client reaktivasi atau membuat event baru:
- Sistem membackup event sebelumnya terlebih dahulu jika `period_end` event lama sudah lewat.
- Semua file lama di folder backup event tersebut dikompresi menjadi `backup/event/<user_id>/<nama_event>_YYYY.tar.gz`.
- Setelah arsip `tar.gz` berhasil dibuat dan diverifikasi, file CSV final dan file upload Excel lama yang sudah masuk arsip dihapus.
- Event aktif berikutnya memakai nama event dari payment terbaru.

## Tambah Client Backend

Route:
- `GET /admin/users/new`
- `POST /admin/users/new`

Perilaku form:
- Menu Tambah Client tersedia untuk admin dan super admin.
- Form tidak menampilkan `Tgl Daftar`, `Tgl Expired`/`Periode Akhir`, `Paket`, dan `Aktivasi`; nilai operasional dibuat atau diubah lewat proses backend/payment.
- `Tgl Daftar` otomatis diisi saat client dibuat.
- Kolom `Nama Lengkap`, `No HP`, `Email`, dan `Password` wajib diisi dan diberi tanda `*`.
- `Nama Lengkap` hanya menerima huruf dan spasi.
- `No HP` memakai UI prefix visual `+62`; frontend mengirim hidden value canonical `62...` dan backend tetap menormalisasi sebelum simpan.
- `Email` wajib mengandung `@` dan `.`.
- Password minimal 8 karakter dan dapat dibuat lewat tombol `Generate`; hasil generate tampil di field read-only agar bisa disalin.
- Generator password membuat kombinasi huruf, angka, dan karakter spesial.
- Kolom `Provinsi` memakai dropdown custom yang bisa diketik untuk pencarian.
- Kolom `Kota / Kabupaten` memakai dropdown custom yang bisa diketik untuk pencarian, aktif setelah provinsi valid dipilih, dan isinya mengikuti provinsi terpilih.
- Data wilayah diambil dari `static/indonesia_regions.js`.
- Tombol `Batal` pada form memakai warna merah.

## Payment Client

Route admin/super admin:
- `GET /admin/payment`
- `POST /admin/payment/input`
- `GET /admin/payment-history`

Route client:
- `GET /user/payment`

Perilaku:
- Istilah lama `Billing` sudah diganti menjadi `Payment` pada URL, sidebar, judul halaman, dan label UI.
- Sidebar client memiliki menu `Payment`; tombol `Billing` pada halaman Profile client sudah dihapus.
- Sidebar admin dan super admin pada submenu `Client` menampilkan `Payment`, lalu `Payment History` tepat di bawahnya.
- Halaman `/admin/payment` khusus untuk input payment client.
- Halaman `/admin/payment-history` khusus untuk histori pembayaran client.
- Admin dan super admin mencatat pembayaran manual lewat tombol/form `Input Payment` pada halaman `Payment`.
- Total kas masuk dihitung dari payment yang sudah tersimpan dan ditampilkan pada halaman `Payment History`.
- Histori payment pada halaman `Payment History` dapat difilter berdasarkan client.
- Input `Akuntansi` sudah dihapus dari form dan tidak dipakai lagi sebagai kolom pencatatan payment.
- Migrasi ringan di `services/schema_service.py` menghapus kolom lama `accounting_entry` pada tabel `billing_payment` jika kolom tersebut masih ada dan SQLite mendukung operasi `DROP COLUMN`.
- Field wajib input payment: `Client`, `Tanggal Payment`, `Waktu Payment`, `Nominal`, `Jenis Bayar`, `Paket`, `Periode Mulai`, `Periode Akhir`, dan `Nama Event`.
- `Waktu Payment` memakai format `HH:MM` dan ditampilkan sebagai kolom `Waktu` di sebelah kanan kolom `Tanggal`.
- `Metode` hanya berisi `Transfer`, `Cash`, `QRIS`, dan `Virtual Account`; opsi `Lainnya` sudah dihapus.
- Jika metode `Transfer`, `Bank Asal` dan `Nomor Rekening` wajib diisi.
- Jika metode bukan `Transfer`, `Bank Asal` dan `Nomor Rekening` otomatis menjadi `N/A`, disabled, dan memakai tampilan disabled yang konsisten.
- Saat metode `Transfer`, opsi bank `N/A` disembunyikan.
- Pilihan `Bank Asal` berasal dari daftar bank umum Indonesia yang diurutkan alfabet.
- `Nomor Rekening` harus 10 sampai 16 digit angka dan boleh diawali angka `0`.
- `Jenis Bayar` berisi `Lunas`, `Sebagian`, dan `DP`.
- Pilihan `Paket` hanya berisi paket valid aplikasi; opsi `Tidak dicatat` sudah dihapus.
- `Periode Mulai` dapat memilih tanggal kapan saja.
- `Periode Akhir` harus lebih dari hari ini dan tidak boleh lebih awal dari `Periode Mulai`; tanggal yang sama dengan `Periode Mulai` diperbolehkan selama tetap lebih dari hari ini.
- Field lama `Catatan` untuk event diganti menjadi `Nama Event`; field `Catatan` baru tersedia untuk keterangan opsional.
- Payment tersimpan dengan status `verified`, memperbarui paket/periode akhir client, dan mensinkronkan status aktivasi client.

## Autentikasi dan Role

Login menggunakan:
- Admin/super admin: `username`
- User: email atau no HP

Format input nomor HP di semua form:
- Harus angka.
- Minimal 8 digit.
- Menggunakan UI prefix visual `+62`.
- Kolom setelah prefix harus diawali `08` atau `8`.
- Frontend mengirim hidden value canonical `62...`; backend juga menormalisasi nomor valid ke canonical `62...` untuk penyimpanan dan pencarian.
- Nomor akun admin/client unik secara global, nomor staff unik per client, dan nomor tamu manual unik per pemilik data tamu.

Password disimpan dalam bentuk hash.

Popup gagal login:
- Jika password salah, halaman login menampilkan popup dengan pesan `Password salah!` lalu baris baru `Harap hubungi petugas untuk informasi lebih lanjut.`.
- Jika email/no HP tidak ditemukan, halaman login menampilkan popup dengan pesan `Email/No HP tidak ditemukan!` lalu baris baru `Harap hubungi petugas untuk informasi lebih lanjut.`.
- Popup gagal login memiliki tombol `Tutup` warna merah.

Block akun:
- Admin dan super admin dapat memblokir/membuka blokir client dari halaman Manage Client.
- Super admin dapat memblokir/membuka blokir admin dari halaman Manage Admin.
- Aksi block/unblock wajib melewati popup peringatan, lalu konfirmasi password akun yang sedang login.
- Akun yang diblokir tidak dapat login dan session aktifnya diputus melalui `active_session_token = NULL`.

Role yang dikenal:
- `super_admin`
- `admin`
- `user`
- `staff` sebagai session staff terpisah, bukan role pada tabel `User`

Ada mekanisme `must_reset_password` untuk memaksa reset password setelah login.

## UI dan Tema

UI menggunakan tema custom dengan:
- Layout sidebar per role.
- Card/panel transparan.
- Button primary, secondary, danger.
- Popup/modal untuk konfirmasi dan form.
- Dropdown mengikuti gaya global `select`.
- Tabel responsif dengan horizontal scroll.
- Tombol aksi lebih dari satu dalam `.action-group` otomatis diringkas oleh `static/action_toggle.js` menjadi tombol `Show`/`Hide`.
- Saat tombol `Show` diklik, action lain ditampilkan dalam popup kecil yang diposisikan relatif terhadap tombol dan tetap berada dalam viewport.
- Popup action ditambahkan ke `document.body` agar posisinya tidak bergeser oleh parent dengan efek visual seperti `backdrop-filter`.
- Hanya satu popup action boleh terbuka dalam satu waktu; klik di luar popup, scroll, atau resize akan menutup/menyesuaikan posisi popup.
- Tombol `Batal` di form dan popup memakai warna merah/danger.
- Pada mobile, sidebar memakai layout menu vertikal yang lebih ringkas agar semua menu utama tetap terlihat tanpa scroll.
- Pada mobile, setelah user klik menu sidebar dan halaman baru selesai load, sidebar otomatis tertutup.
- Dashboard client pada kartu `Verifikasi Kehadiran` tidak lagi menampilkan tombol; teks mengarahkan pengelolaan URL publik dan QR Client ke menu Staff.

Saat menambah fitur UI, gunakan class dan pola yang sudah ada di `static/style.css`.

## Waktu dan Timestamp

Semua timestamp pencatatan aplikasi menggunakan GMT+7:
- Payload JSON log memakai ISO-8601 dengan offset `+07:00`.
- Prefix waktu pada log harian memakai jam GMT+7.
- Nama file log harian dihitung berdasarkan tanggal GMT+7.
- Waktu kehadiran tamu dan timestamp aktivitas staff/login memakai GMT+7.

## Backup Log Bulanan

Script:
- `scripts/backup_monthly_logs.py`

Service:
- `services/log_backup_service.py`

Jadwal cron:
- `scripts/log_backup.cron`
- Tanggal 1 setiap bulan jam `00:01`.
- Retry terjadwal pada jam `12:00` dan `18:00`.
- Retry aman/idempotent: jika backup pertama berhasil, run berikutnya menjadi no-op karena log bulan sebelumnya sudah bersih.

Perilaku:
- Target default adalah bulan sebelumnya dari tanggal eksekusi.
- Sumber log default: `logs/activity_YYYY-MM-DD.log`.
- Arsip dibuat di folder `backup/log/<tahun>/`.
- Contoh untuk backup Mei 2026: `backup/log/2026/mei.tar.gz`.
- Isi arsip ditempatkan dalam folder bulan, contoh `mei/activity_2026-05-22.log`.
- File log bulan sebelumnya dihapus dari `logs` hanya setelah arsip `tar.gz` berhasil dibuat dan diverifikasi.
- Folder `logs` menyisakan log bulan terbaru setelah backup bulanan selesai.

## Deploy VPS dan Runtime Production

Status deploy:
- Repository GitHub production: `https://github.com/vahlefie/project_QR.git`.
- Branch production aktif: `main`.
- Domain production: `vlf.my.id`.
- IP VPS: `202.10.47.177`.
- Path project VPS: `/var/www/project_qr`.
- Virtualenv VPS: `/var/www/project_qr/.venv`.
- Environment file VPS: `/var/www/project_qr/.env`.

Aturan source dan runtime:
- Source code yang masuk GitHub hanya file aplikasi, template, static, tests, scripts, dan konfigurasi development.
- File runtime seperti `instance/`, `logs/`, `backup/`, `.venv/`, `.env`, file `.db`, file `.xlsx`, dan file `.log` tidak ikut Git.
- Folder `archieve/` hanya untuk arsip lokal laptop dan tidak ikut GitHub.
- `context.md` dan `rules.txt` adalah dokumen aktif root project, bukan arsip. Keduanya harus tetap di root agar aturan update dokumentasi tetap berjalan.
- `app.py` memastikan `instance_path` dibuat saat startup agar SQLite production bisa membuat database di server baru.

Konfigurasi environment VPS:
- `SECRET_KEY` wajib diset kuat di `.env`.
- `DATABASE_URL` production saat ini memakai SQLite, contoh `sqlite:////var/www/project_qr/instance/users.db`.
- `ENABLE_PROXY_FIX=true` dipakai karena aplikasi berjalan di belakang Nginx reverse proxy.
- `TRUSTED_PROXY_COUNT=1` cukup untuk topologi Nginx -> Gunicorn.

Service aplikasi:
- Nama service: `project_qr.service`.
- Lokasi service di VPS: `/etc/systemd/system/project_qr.service`.
- Process manager: `systemd`.
- Server WSGI production: Gunicorn.
- Bind internal yang direkomendasikan: `127.0.0.1:8000`.
- Bentuk `ExecStart` yang direkomendasikan:

```ini
ExecStart=/var/www/project_qr/.venv/bin/gunicorn --workers 3 --bind 127.0.0.1:8000 app:app
```

Nginx:
- Nginx menerima request publik domain `vlf.my.id` pada port 80/443.
- Nginx meneruskan request ke Gunicorn internal melalui `proxy_pass http://127.0.0.1:8000;`.
- Jangan memakai IP publik VPS sebagai upstream internal, misalnya `proxy_pass http://202.10.47.177:8000;`, karena pernah menyebabkan 502 dan log upstream salah.
- Setelah mengubah konfigurasi Nginx, wajib jalankan `sudo nginx -t` lalu `sudo systemctl reload nginx`.

SSL:
- SSL domain `vlf.my.id` dipasang dengan Certbot plugin Nginx.
- Command pemasangan SSL: `sudo certbot --nginx -d vlf.my.id`.
- Auto-renew Certbot dikelola oleh paket Certbot di server. Verifikasi renew memakai `sudo certbot renew --dry-run`.

Masalah deploy yang pernah terjadi:
- Push GitHub ke `main` pernah ditolak karena history lokal lama berisi database, log, backup, Excel, dan cache. Solusi yang dipakai adalah branch clean `deploy-clean`, PR #1 ke `main`, lalu local `main` disinkronkan ulang ke `origin/main`.
- Service VPS pernah gagal karena syntax Python lama `except TypeError, ValueError:` di `services/guest_service.py`. Fix dipush pada commit `6e4e7b2`.
- Dashboard Demo di VPS pernah kosong karena file Excel demo tidak ikut deploy. Fix fallback seed demo dipush pada commit `9d85101`.
- Nginx pernah 502 karena upstream masih menunjuk `202.10.47.177:8000`; upstream harus `127.0.0.1:8000`.

## Job Otomatis

Job otomatis yang berjalan atau disiapkan project:

1. `systemd` service aplikasi
- Nama service: `project_qr`.
- Fungsi: menjaga aplikasi Flask/Gunicorn tetap berjalan dan otomatis start saat VPS reboot.
- Trigger: boot server dan restart manual via `sudo systemctl restart project_qr`.
- Log: `sudo journalctl -u project_qr -n 100 --no-pager`.
- Health check manual: `sudo systemctl status project_qr --no-pager` dan `curl -I http://127.0.0.1:8000/`.

2. Nginx reverse proxy
- Fungsi: menerima traffic publik `vlf.my.id`, terminasi HTTP/HTTPS, lalu proxy ke Gunicorn.
- Trigger: service Nginx aktif terus sebagai daemon systemd.
- Config project: `/etc/nginx/sites-available/project_qr` dengan symlink di `/etc/nginx/sites-enabled/`.
- Log error: `/var/log/nginx/error.log`.
- Validasi config: `sudo nginx -t`.

3. Certbot SSL renew
- Fungsi: memperpanjang sertifikat TLS/SSL otomatis.
- Trigger: timer/cron bawaan Certbot sesuai instalasi server.
- Domain: `vlf.my.id`.
- Validasi manual: `sudo certbot renew --dry-run`.

4. Cron backup log bulanan
- Definisi repo: `scripts/log_backup.cron`.
- Command: `.venv/bin/python scripts/backup_monthly_logs.py`.
- Jadwal:
  - `1 0 1 * *`: backup bulan sebelumnya tanggal 1 jam 00:01.
  - `0 12 1 * *`: retry tanggal 1 jam 12:00.
  - `0 18 1 * *`: retry tanggal 1 jam 18:00.
- Output log cron: `logs/log_backup_cron.log`.
- Hasil arsip: `backup/log/<tahun>/<bulan>.tar.gz`.
- Sifat job: idempotent; retry aman jika backup pertama sudah selesai.

5. Cron arsip event expired
- Definisi repo: `scripts/event_archive.cron`.
- Command: `.venv/bin/python scripts/backup_expired_events.py`.
- Jadwal: `5 0 * * *`, setiap hari jam 00:05.
- Output log cron: `logs/event_archive_cron.log`.
- Fungsi: membuat backup final CSV untuk client yang payment terverifikasi terbarunya sudah melewati `period_end`, memindahkan file upload lama, dan menjaga data event lama siap diekspor.
- Hasil arsip: `backup/event/<user_id>/`.
- Mode manual tambahan: `scripts/backup_expired_events.py --uploads-only`.

Catatan operasional job:
- Pada VPS, path cron harus disesuaikan dari `/path/to/project_qr` menjadi `/var/www/project_qr`.
- Cron harus dijalankan oleh user yang punya akses tulis ke `/var/www/project_qr/logs`, `/var/www/project_qr/backup`, dan `/var/www/project_qr/instance`.
- Untuk melihat cron user aktif: `crontab -l`.
- Untuk memasang cron dari repo: edit file cron agar path benar, lalu jalankan `crontab scripts/log_backup.cron` atau gabungkan manual agar tidak menimpa job lain.

## Testing Terakhir yang Sudah Dilakukan

Testing yang pernah dijalankan setelah update terbaru:
- Unit test auth dasar ditambahkan di `tests/test_auth.py` memakai `unittest` stdlib untuk helper autentikasi dan endpoint dasar auth.
- Unit test attendance dasar ditambahkan di `tests/test_attendance.py` untuk validasi token publik yang tidak valid.
- Unit test dashboard dasar ditambahkan di `tests/test_dashboard.py` untuk memastikan route dashboard/profile wajib login.
- Unit test client staff dasar ditambahkan di `tests/test_client_staff.py` untuk memastikan route `/user/staff...` wajib login.
- Unit test staff dasar ditambahkan di `tests/test_staff.py` untuk session expired, akses invalid, proteksi session staff, dan logout staff.
- Unit test guest route dasar ditambahkan di `tests/test_guest_routes.py` untuk proteksi route update/hapus tamu.
- Unit test user route dasar ditambahkan di `tests/test_user_routes.py` untuk proteksi route data/upload user.
- Unit test admin route dasar ditambahkan di `tests/test_admin_routes.py` untuk proteksi route admin/super-admin.
- Route auth dipindahkan bertahap ke Flask Blueprint `auth` tanpa memindahkan modul lain.
- Route attendance dipindahkan bertahap ke Flask Blueprint `attendance` setelah test baseline lulus.
- Route dashboard/profile dipindahkan bertahap ke Flask Blueprint `dashboard` setelah test baseline lulus.
- Route pengelolaan staff client dipindahkan bertahap ke Flask Blueprint `client_staff` setelah test baseline lulus.
- Route session/dashboard/data staff dipindahkan bertahap ke Flask Blueprint `staff` setelah test baseline lulus.
- Route update/hapus tamu bersama dipindahkan bertahap ke Flask Blueprint `guests` setelah test baseline lulus.
- Route data/upload tamu user dipindahkan bertahap ke Flask Blueprint `user` setelah test baseline lulus.
- Route admin/super-admin dipindahkan bertahap ke Flask Blueprint `admin` setelah test baseline lulus.
- Cleanup import route lama di `app.py` setelah seluruh route fitur pindah ke Blueprint.
- Ekstensi SQLAlchemy dipisahkan ke `extensions.py`; `app.py` memanggil `db.init_app(app)`.
- Model database dipindahkan dari `app.py` ke `models.py`.
- Konfigurasi Flask dipindahkan dari `app.py` ke `config.py`; `SECRET_KEY` dan `DATABASE_URL` bisa diambil dari environment dengan default development lama.
- Entry point `run.py` ditambahkan untuk menjalankan development server tanpa menaruh bootstrap server sebagai tanggung jawab utama `app.py`.
- Konstanta bersama dipindahkan dari `app.py` ke `constants.py`; default model `User.role` dan `Guests.status` sekarang memakai konstanta yang sama.
- Verifikasi refactor constants: `.venv\Scripts\python.exe -m unittest discover` berhasil menjalankan 26 test.
- Verifikasi compile refactor constants: `.venv\Scripts\python.exe -m py_compile app.py constants.py models.py config.py extensions.py` berhasil.
- Verifikasi formatter/linter refactor constants: Black dan Flake8 berhasil untuk `constants.py`, modul terpisah, Blueprints, dan tests; cek Flake8 fatal/import untuk `app.py` juga berhasil.
- Logic logging dipindahkan ke `services/logging_service.py`; `app.py` menyisakan wrapper tipis agar kontrak fungsi Blueprint tetap stabil.
- Unit test logging service ditambahkan di `tests/test_logging_service.py`.
- Verifikasi refactor logging service: `.venv\Scripts\python.exe -m unittest discover` berhasil menjalankan 28 test.
- Verifikasi compile refactor logging service: `.venv\Scripts\python.exe -m py_compile app.py services\__init__.py services\logging_service.py tests\test_logging_service.py` berhasil.
- Verifikasi formatter/linter refactor logging service: Black dan Flake8 berhasil untuk `services`, modul terpisah, Blueprints, dan tests; cek Flake8 fatal/import untuk `app.py` juga berhasil.
- Logic autentikasi dipindahkan ke `services/auth_service.py`; `app.py` menyisakan wrapper tipis agar kontrak fungsi Blueprint tetap stabil.
- Unit test auth service ditambahkan di `tests/test_auth_service.py`.
- Verifikasi refactor auth service: `.venv\Scripts\python.exe -m unittest discover` berhasil menjalankan 31 test.
- Verifikasi compile refactor auth service: `.venv\Scripts\python.exe -m py_compile app.py services\auth_service.py tests\test_auth_service.py` berhasil.
- Verifikasi formatter/linter refactor auth service: Black dan Flake8 berhasil untuk `services`, modul terpisah, Blueprints, dan tests; cek Flake8 fatal/import untuk `app.py` juga berhasil.
- Logic attendance dipindahkan ke `services/attendance_service.py`; `app.py` menyisakan wrapper tipis agar kontrak fungsi Blueprint tetap stabil.
- Unit test attendance service ditambahkan di `tests/test_attendance_service.py`.
- Verifikasi refactor attendance service: `.venv\Scripts\python.exe -m unittest discover` berhasil menjalankan 34 test.
- Verifikasi compile refactor attendance service: `.venv\Scripts\python.exe -m py_compile app.py services\attendance_service.py tests\test_attendance_service.py` berhasil.
- Verifikasi formatter/linter refactor attendance service: Black dan Flake8 berhasil untuk `services`, modul terpisah, Blueprints, dan tests; cek Flake8 fatal/import untuk `app.py` juga berhasil.
- Logic session/access staff dipindahkan ke `services/staff_service.py`; helper context/form staff tetap di `app.py` untuk commit terpisah.
- Unit test staff service ditambahkan di `tests/test_staff_service.py`.
- Verifikasi refactor staff service: `.venv\Scripts\python.exe -m unittest discover` berhasil menjalankan 38 test.
- Verifikasi compile refactor staff service: `.venv\Scripts\python.exe -m py_compile app.py services\staff_service.py tests\test_staff_service.py` berhasil.
- Verifikasi formatter/linter refactor staff service: Black dan Flake8 berhasil untuk `services`, modul terpisah, Blueprints, dan tests; cek Flake8 fatal/import untuk `app.py` juga berhasil.
- Logic context halaman staff, status staff, validasi form staff, dan parser log staff dipindahkan ke `services/staff_service.py`.
- Unit test staff service diperluas untuk payload log dan format pesan log staff.
- Verifikasi refactor staff page/log service: `.venv\Scripts\python.exe -m unittest discover` berhasil menjalankan 50 test.
- Verifikasi compile refactor staff page/log service: `.venv\Scripts\python.exe -m py_compile app.py services\staff_service.py tests\test_staff_service.py` berhasil.
- Verifikasi formatter/linter refactor staff page/log service: Black dan Flake8 berhasil untuk `services`, modul terpisah, Blueprints, dan tests; cek Flake8 fatal/import untuk `app.py` juga berhasil.
- Logic upload/cleaning data tamu dipindahkan ke `services/guest_service.py`; `UploadValidationError` dipindahkan ke `exceptions.py`.
- Unit test guest service ditambahkan di `tests/test_guest_service.py`.
- Verifikasi refactor guest service: `.venv\Scripts\python.exe -m unittest discover` berhasil menjalankan 43 test.
- Verifikasi compile refactor guest service: `.venv\Scripts\python.exe -m py_compile app.py exceptions.py services\guest_service.py tests\test_guest_service.py` berhasil.
- Verifikasi formatter/linter refactor guest service: Black dan Flake8 berhasil untuk `services`, modul terpisah, Blueprints, dan tests; cek Flake8 fatal/import untuk `app.py` juga berhasil.
- Logic helper akun/user/admin dipindahkan ke `services/account_service.py`.
- Unit test account service ditambahkan di `tests/test_account_service.py`.
- Verifikasi refactor account service: `.venv\Scripts\python.exe -m unittest discover` berhasil menjalankan 48 test.
- Verifikasi compile refactor account service: `.venv\Scripts\python.exe -m py_compile app.py services\account_service.py tests\test_account_service.py` berhasil.
- Verifikasi formatter/linter refactor account service: Black dan Flake8 berhasil untuk `services`, modul terpisah, Blueprints, dan tests; cek Flake8 fatal/import untuk `app.py` juga berhasil.
- Logic redirect, query, pagination, context halaman data tamu, context daftar user, dan guard akses tamu dipindahkan ke `services/listing_service.py`.
- Unit test listing service ditambahkan di `tests/test_listing_service.py`.
- Verifikasi refactor listing service: `.venv\Scripts\python.exe -m unittest discover` berhasil menjalankan 52 test.
- Verifikasi compile refactor listing service: `.venv\Scripts\python.exe -m py_compile app.py services\listing_service.py tests\test_listing_service.py` berhasil.
- Verifikasi formatter/linter refactor listing service: Black dan Flake8 berhasil untuk `services`, modul terpisah, Blueprints, dan tests; cek Flake8 fatal/import untuk `app.py` juga berhasil.
- Logic bootstrap database, migrasi ringan schema SQLite, dan default super admin dipindahkan ke `services/schema_service.py`.
- Unit test schema service ditambahkan di `tests/test_schema_service.py`.
- Verifikasi refactor schema service: `.venv\Scripts\python.exe -m unittest discover` berhasil menjalankan 53 test.
- Verifikasi compile refactor schema service: `.venv\Scripts\python.exe -m py_compile app.py services\schema_service.py tests\test_schema_service.py` berhasil.
- Verifikasi formatter/linter refactor schema service: Black dan Flake8 berhasil untuk `services`, modul terpisah, Blueprints, dan tests; cek Flake8 fatal/import untuk `app.py` juga berhasil.
- Logic lifecycle request Flask, helper form, timeout session login, access log, error handler, dan decorator login/role dipindahkan ke `services/request_service.py`.
- Unit test request service ditambahkan di `tests/test_request_service.py`.
- Verifikasi refactor request service: `.venv\Scripts\python.exe -m unittest discover` berhasil menjalankan 57 test.
- Verifikasi compile refactor request service: `.venv\Scripts\python.exe -m py_compile app.py services\request_service.py tests\test_request_service.py` berhasil.
- Verifikasi formatter/linter refactor request service: Black dan Flake8 berhasil untuk `services`, modul terpisah, Blueprints, dan tests; cek Flake8 fatal/import untuk `app.py` juga berhasil.
- Logic parsing tanggal expired dan sinkronisasi status aktivasi user dipindahkan ke `services/account_service.py`.
- Unit test account service diperluas untuk parsing tanggal, status aktivasi, dan commit sinkronisasi.
- Verifikasi refactor account date/activation service: `.venv\Scripts\python.exe -m unittest discover` berhasil menjalankan 60 test.
- Verifikasi compile refactor account date/activation service: `.venv\Scripts\python.exe -m py_compile app.py services\account_service.py tests\test_account_service.py` berhasil.
- Verifikasi formatter/linter refactor account date/activation service: Black dan Flake8 berhasil untuk `services`, modul terpisah, Blueprints, dan tests; cek Flake8 fatal/import untuk `app.py` juga berhasil.
- Registrasi Blueprint dan dependency per Blueprint dipindahkan ke `blueprints/registry.py`; `app.py` sekarang hanya membangun namespace dependency aplikasi dan memanggil registry.
- Unit test registry Blueprint ditambahkan di `tests/test_blueprint_registry.py`.
- Verifikasi refactor Blueprint registry: `.venv\Scripts\python.exe -m unittest discover` berhasil menjalankan 62 test.
- Verifikasi compile refactor Blueprint registry: `.venv\Scripts\python.exe -m py_compile app.py blueprints\registry.py tests\test_blueprint_registry.py` berhasil.
- Verifikasi formatter/linter refactor Blueprint registry: Black dan Flake8 berhasil untuk `services`, modul terpisah, Blueprints, dan tests; cek Flake8 fatal/import untuk `app.py` juga berhasil.
- App factory `create_app()` ditambahkan di `app.py`; instance global `app = create_app()` tetap tersedia agar test dan entry point lama kompatibel.
- Unit test app factory ditambahkan di `tests/test_app_factory.py` untuk memastikan filter template dan hook lifecycle request terpasang.
- Verifikasi refactor app factory: `.venv\Scripts\python.exe -m unittest discover` berhasil menjalankan 64 test.
- Verifikasi compile refactor app factory: `.venv\Scripts\python.exe -m py_compile app.py tests\test_app_factory.py` berhasil.
- Verifikasi formatter/linter refactor app factory: Black dan Flake8 berhasil untuk `services`, modul terpisah, Blueprints, dan tests; cek Flake8 fatal/import untuk `app.py` juga berhasil.
- Verifikasi refactor admin route: `.venv\Scripts\python.exe -m unittest discover` berhasil menjalankan 26 test.
- Verifikasi refactor user route: `.venv\Scripts\python.exe -m unittest discover` berhasil menjalankan 24 test.
- Verifikasi refactor guest route: `.venv\Scripts\python.exe -m unittest discover` berhasil menjalankan 22 test.
- Verifikasi refactor staff: `.venv\Scripts\python.exe -m unittest discover` berhasil menjalankan 20 test.
- Verifikasi refactor client staff: `.venv\Scripts\python.exe -m unittest discover` berhasil menjalankan 15 test.
- Verifikasi refactor dashboard/profile: `.venv\Scripts\python.exe -m unittest discover` berhasil menjalankan 13 test.
- Cleanup kode mati: `GUEST_REQUIRED_COLUMNS`, `validate_required_columns`, dan `get_optional_string` dihapus karena tidak memiliki referensi aktif.
- Konfigurasi formatter/linter ditambahkan: `pyproject.toml` untuk Black, `setup.cfg` untuk Flake8, dan `requirements-dev.txt` untuk dependency development.
- Black dan Flake8 sudah terinstall di `.venv`; verifikasi terbatas modul baru berhasil: `.venv\Scripts\python.exe -m black --check blueprints tests` dan `.venv\Scripts\python.exe -m flake8 blueprints tests`.
- Verifikasi refactor attendance: `.venv\Scripts\python.exe -m unittest discover` berhasil menjalankan 11 test.
- Verifikasi compile refactor attendance: `.venv\Scripts\python.exe -m py_compile app.py blueprints\auth\routes.py blueprints\attendance\routes.py tests\test_auth.py tests\test_attendance.py` berhasil.
- Verifikasi refactor auth: `.venv\Scripts\python.exe -m unittest discover` berhasil menjalankan 8 test.
- Verifikasi compile refactor auth: `.venv\Scripts\python.exe -m py_compile app.py blueprints\auth\routes.py tests\test_auth.py` berhasil.
- `py_compile app.py`
- Flask test client untuk render user/admin.
- Verifikasi tombol `Tambah Tamu` muncul pada halaman Data user.
- Verifikasi mode edit Data Tamu user/admin: tombol `Simpan` berubah menjadi biru, tombol `Hapus` berubah menjadi `Batal` tetap merah, dan tombol `Batal` membatalkan edit tanpa submit hapus.
- Verifikasi form `Hapus Semua Data` tidak muncul untuk user.
- Verifikasi route lama `/user/delete-data` tidak menghapus data.
- Verifikasi alur staff URL+PIN: client login, tambah staff, buat URL random dan PIN 6 digit, buka URL dari test client berbeda tanpa session client, input PIN benar, langsung masuk Data staff tanpa upload Excel, logout staff.
- Verifikasi PIN staff salah 3 kali otomatis mencabut akses dan memblokir staff.
- Verifikasi block/unblock staff dari dashboard client.
- Verifikasi status staff client berubah aktif/nonaktif setelah login dan logout staff.
- Verifikasi endpoint log staff hari ini hanya mengembalikan log untuk staff terpilih dan memakai format waktu dengan detik.
- Verifikasi halaman Staff menampilkan kolom `Log`, tombol `View`, dan popup log dengan tombol `Tutup`.
- Verifikasi popup log tidak menampilkan keyword sumber log, memiliki tombol `Download` `.txt`, dan tombol `Tutup` berwarna merah.
- Verifikasi `app.py` bersih dari 23 diagnostics Pyright/Pylance setelah type-check cleanup: hasil `pyright app.py` adalah 0 error, 0 warning.
- Verifikasi staff setelah PIN login diarahkan langsung ke `/staff/data` dan route `/staff/dashboard` sudah tidak terdaftar.
- Verifikasi popup `Tambah Tamu` pada layout staff memakai UI No HP prefix `+62` dengan hidden value `62...`.
- Verifikasi semua template input No HP utama (`Tambah Client`, `Tambah Admin`, `Staff`, `Tambah Tamu`, `Kehadiran`) kembali memakai UI prefix `+62`.
- Verifikasi form `Tambah Client` dan `Tambah Admin` merender UI No HP prefix `+62` lewat test template.
- Verifikasi `python -m unittest discover` lulus 66 test.
- Verifikasi timestamp log memakai GMT+7 dengan offset `+07:00`.
- Verifikasi halaman Data client tetap menampilkan upload Excel dan endpoint client setelah template Data dibuat reusable.
- Verifikasi tambah tamu manual membersihkan:
  - nama menjadi title case
  - no HP menjadi `62...`
  - email invalid menjadi `N/A`
  - status tersimpan sesuai pilihan
- Verifikasi tombol `Ekspor Data` muncul pada halaman admin.
- Verifikasi sidebar admin memakai label `Data`, bukan `Guests`.
- Verifikasi export Excel admin dapat dibaca kembali dengan Pandas.
- Verifikasi `py_compile app.py` berhasil dengan interpreter `.venv`.
- Verifikasi route publik `/kehadiran/<attendance_token>` render halaman input nomor HP.
- Verifikasi API kehadiran publik sekarang membuat request pending konfirmasi staff, menampilkan status tunggu di halaman tamu, dan memproses hasil konfirmasi/timeout/tolak tanpa menampilkan `Request ID` atau `Kode pemeriksaan`.
- Verifikasi terbaru Manage Client tidak lagi memiliki kolom `URL Client`.
- Verifikasi URL Client per staff: halaman Staff client memiliki kolom `URL Client`, endpoint generate staff memperbarui nonce/timestamp pada `Staff`, menghasilkan URL/QR staff, dan endpoint admin lama mengembalikan status `410 moved`.
- Verifikasi terbaru: `.venv\Scripts\python.exe -m unittest discover` berhasil menjalankan 81 test.
- Verifikasi compile terbaru: `.venv\Scripts\python.exe -m py_compile app.py constants.py models.py services\account_service.py services\attendance_service.py services\schema_service.py services\listing_service.py services\staff_service.py services\logging_service.py services\guest_service.py blueprints\registry.py blueprints\admin\routes.py tests\test_attendance_service.py tests\test_admin_routes.py` berhasil.
- Verifikasi formatter/linter terbaru: Black dan Flake8 berhasil untuk file yang disentuh pada fitur QR Code dan Scan Premium.
- Backup log bulanan ditambahkan dengan script `scripts/backup_monthly_logs.py`, service `services/log_backup_service.py`, contoh cron `scripts/log_backup.cron`, dan unit test `tests/test_log_backup_service.py`.
- Verifikasi backup log: `.venv\Scripts\python.exe -m unittest tests.test_log_backup_service` berhasil menjalankan 3 test.
- Verifikasi backup log full suite: `.venv\Scripts\python.exe -m unittest discover` berhasil menjalankan 90 test.
- Verifikasi backup log compile: `.venv\Scripts\python.exe -m py_compile services\log_backup_service.py scripts\backup_monthly_logs.py tests\test_log_backup_service.py` berhasil.
- Verifikasi backup log format: `.venv\Scripts\python.exe -m black --check services\log_backup_service.py scripts\backup_monthly_logs.py tests\test_log_backup_service.py` berhasil.
- Backup aktual Mei 2026 sudah dijalankan: arsip dibuat di `backup/log/2026/mei.tar.gz`, berisi folder `mei/`, dan file `activity_2026-05-*.log` sudah dibersihkan dari `logs`.
- Upload data tamu client/admin sekarang menyimpan file Excel asli ke `instance/uploads/` dengan nama `<nama_event>_<username_client>_YYYY-MM-DD.xlsx` dan suffix `_2`, `_3`, dst jika nama pada hari yang sama sudah ada.
- Unit test guest service diperluas untuk validasi penamaan file upload berdasarkan event terbaru, username client, tanggal upload, dan suffix urut.
- Preview upload data tamu sekarang menyimpan dan menampilkan daftar baris yang dihapus saat cleaning file, lengkap dengan nilai asli dan alasan penghapusan.
- Popup `Konfirmasi Upload Data Tamu` dengan daftar data terhapus saat cleaning sekarang tersedia juga pada backend admin dan super admin.
- Verifikasi terbaru popup upload admin/super admin: route upload admin menampilkan popup konfirmasi, daftar data terhapus saat cleaning, pertanyaan update duplicate, dan konfirmasi `Ya` mengganti data sama tanpa duplikasi.
- Verifikasi terbaru: `.venv\Scripts\python.exe -m unittest discover` berhasil menjalankan 94 test.
- Duplicate upload tamu diperbarui agar `nama` tidak menjadi unique key. Preview upload dan replace row hanya mencocokkan data sama berdasarkan `no_hp` atau `email`.
- Arsip final event client ditambahkan dengan model `EventArchive`, service `services/event_archive_service.py`, script `scripts/backup_expired_events.py`, dan contoh cron `scripts/event_archive.cron`.
- Saat client nonaktif setelah `period_end`, halaman Data menyembunyikan tabel dan mutasi data, tetapi tetap menyediakan ekspor final dari CSV backup.
- Reaktivasi client mengarsipkan data event sebelumnya ke `backup/event/<user_id>/<nama_event>_YYYY.tar.gz` dan menghapus file CSV/upload lama setelah arsip berhasil dibuat.
- Pemindahan file upload Excel lama sekarang berjalan saat client melewati `period_end`; mode `--uploads-only` tersedia untuk menjalankan pemindahan file tanpa backup CSV.
- Verifikasi latest unique nama upload: `.venv\Scripts\python.exe -m py_compile app.py services\guest_service.py tests\test_guest_service.py`, `.venv\Scripts\python.exe -m unittest tests.test_guest_service` berhasil menjalankan 9 test, dan `.venv\Scripts\python.exe -m unittest discover` berhasil menjalankan 101 test.
- Cleanup deploy memindahkan data runtime lokal, log, backup, Excel, `.vscode`, dan cache ke `archieve/`; `context.md` dan `rules.txt` dikembalikan ke root karena merupakan dokumen aktif project.
- GitHub production dipulihkan lewat branch clean `deploy-clean` dan PR #1 agar history lama berisi database/log/upload/cache tidak ikut push ke `main`.
- Local `main` sudah disinkronkan ulang ke `origin/main` setelah PR clean merge, sehingga workflow normal kembali memakai `main`.
- Deploy VPS memakai domain `vlf.my.id`, IP `202.10.47.177`, path `/var/www/project_qr`, `.env` production, `systemd` service `project_qr`, Gunicorn bind `127.0.0.1:8000`, Nginx reverse proxy, dan SSL Certbot.
- Fix syntax Python production di `services/guest_service.py`: semua multiple exception sekarang memakai `except (A, B):`; commit deploy `6e4e7b2`.
- Fallback data demo dashboard client ditambahkan di `services/schema_service.py` agar mode Demo tetap tampil di VPS tanpa file Excel lokal; commit deploy `9d85101`.
- Audit dokumentasi 2026-07-02: `context.md` dan `rules.txt` direstore dari `archieve/project_notes/`, section Deploy VPS dan Job Otomatis ditambahkan, dan aturan dokumen aktif diperjelas.
- Audit dokumentasi 2026-07-05: `context.md` diperbarui untuk mencatat tombol `QR Client`, route `/kehadiran/<attendance_token>/qr.png`, alur verifikasi tamu berbasis pending konfirmasi staff tanpa popup tamu, pesan timeout/tolak terbaru, penghapusan `Request ID`/`Kode pemeriksaan` dari UI tamu, dan perubahan pesan halaman session staff.
- Update QR Client 2026-07-05: tombol `QR Client` sekarang mengunduh file PNG siap cetak berukuran sekitar 2400 px, dengan route lama `/kehadiran/<attendance_token>/qr.svg` dialihkan ke `/kehadiran/<attendance_token>/qr.png`.
- Verifikasi QR Client PNG: `.venv\Scripts\python.exe -m py_compile app.py constants.py services\attendance_service.py blueprints\attendance\routes.py blueprints\registry.py`, `.venv\Scripts\python.exe -m unittest tests.test_attendance_service`, `.venv\Scripts\python.exe -m unittest tests.test_attendance tests.test_admin_routes`, dan `.venv\Scripts\python.exe -m unittest discover` berhasil menjalankan 104 test.
- Update QR Client per Staff 2026-07-07: Link publik/QR Client dipindahkan dari client ke staff, kolom `URL Client` dipindahkan dari Manage Client admin/super admin ke halaman Staff client, dan request verifikasi dari QR staff hanya muncul pada staff pemilik QR.
- Verifikasi QR Client per Staff 2026-07-07: `.venv\Scripts\python.exe -m py_compile app.py models.py services\attendance_service.py services\schema_service.py blueprints\attendance\routes.py blueprints\client_staff\routes.py blueprints\dashboard\routes.py blueprints\admin\routes.py blueprints\registry.py`, targeted unittest attendance/client_staff/admin/staff/guest_qr, dan `.venv\Scripts\python.exe -m unittest discover` berhasil menjalankan 108 test.
- Audit dokumentasi 2026-07-07: `context.md` diperbarui untuk mencatat perubahan Tambah Client, Payment Client, popup gagal login, action popup `Show`/`Hide`, mobile sidebar auto-close, layout Verifikasi Kehadiran dashboard client, tombol `Batal` merah, dan searchable dropdown Provinsi/Kota.
- Aturan dokumentasi 2026-07-07: `rules.txt` diperketat agar setiap perubahan fitur, UI/UX, route, model database, validasi, job otomatis, deploy, atau spesifikasi wajib ditutup dengan update `context.md` sebelum jawaban final.
- Update Payment History 2026-07-07: histori pembayaran admin/super admin dipindahkan dari halaman `/admin/payment` ke halaman baru `/admin/payment-history`, dan submenu `Client` sekarang menampilkan `Payment History` tepat di bawah `Payment`.
- Verifikasi Payment History 2026-07-07: `.venv\Scripts\python.exe -m py_compile blueprints\admin\routes.py`, targeted unittest route admin payment, dan render template `admin_payment.html` serta `admin_payment_history.html` berhasil.
- Update Data Tamu client 2026-07-09: tabel client/staff menampilkan kolom `Ditambahkan` setelah `Status`; upload client/admin untuk client dan tambah manual client mengisi `username` client, sedangkan tambah manual staff mengisi nama staff. Mode edit client memastikan tombol `Simpan` dan `Batal` tetap visible sampai salah satunya diklik, termasuk saat klik area lain di halaman.
- Verifikasi Data Tamu client 2026-07-09: `.venv\Scripts\python.exe -m py_compile app.py blueprints\registry.py blueprints\staff\routes.py blueprints\user\routes.py constants.py models.py services\guest_service.py services\schema_service.py tests\test_guest_service.py tests\test_user_routes.py`, targeted unittest `tests.test_guest_service tests.test_user_routes tests.test_staff`, dan `.venv\Scripts\python.exe -m unittest discover` berhasil menjalankan 110 test.
- Fix action menu Data Tamu client 2026-07-09: `static/action_toggle.js` tidak menutup menu action pada row yang sedang `is-editing`; template Data Tamu mengirim event `guest-row-editing-change` supaya menu `Show/Hide` tetap terbuka selama edit.
- Tombol action Data Tamu client memakai `data-row-id` untuk tetap menemukan tombol `Simpan/Batal` setelah action menu memindahkan tombol ke popup `Show/Hide`.
- Update edit Data Tamu client 2026-07-09: tombol `Edit` pada backend client sekarang dapat mengedit `nama`, `no_hp`, `email`, dan `status`; validasi backend tetap membersihkan nama, normalisasi no HP ke `62...`, mengosongkan email invalid menjadi `N/A`, serta menolak no HP duplicate milik client yang sama. Tambah tamu manual client sekarang mencatat `Ditambahkan` memakai nama client, bukan username.
- Verifikasi edit Data Tamu client 2026-07-09: `.venv\Scripts\python.exe -m py_compile app.py blueprints\guests\routes.py blueprints\registry.py blueprints\user\routes.py services\guest_service.py services\listing_service.py tests\test_guest_routes.py tests\test_user_routes.py`, targeted unittest `tests.test_guest_routes tests.test_user_routes tests.test_guest_service` berhasil menjalankan 19 test, dan `.venv\Scripts\python.exe -m unittest discover` berhasil menjalankan 112 test.

Catatan browser:
- Jika tampilan browser belum berubah setelah edit, kemungkinan masih ada proses Flask lama yang berjalan di port yang sama atau cache browser belum refresh.
- Restart server Flask dari environment project dan lakukan hard refresh browser.

## Catatan Pengembangan

Ikuti `rules.txt`:
- Gunakan clean code.
- Pisahkan logic dan route.
- Gunakan function modular.
- Hindari hardcode jika ada constant/helper yang sudah tersedia.
- Sesuaikan tampilan UI dengan tema yang sudah ada.
- Beri komentar `#` di atas fungsi untuk menjelaskan kegunaan/peruntukan fungsi.
- Test hasil coding secara menyeluruh, termasuk sisi browser pengguna jika memungkinkan.
- Update `context.md` setiap kali mengedit fitur, format, atau spesifikasi project.
- Jangan pindahkan `context.md` dan `rules.txt` ke `archieve/`; keduanya adalah file dokumentasi aktif root project.
- Catat perubahan job otomatis, deploy VPS, cron, service, Nginx, SSL, dan environment production di `context.md`.

## Next Step Potensial

- Tambahkan test otomatis permanen untuk upload Excel dan duplicate replacement.
- Tambahkan indikator visual jika server/browser masih memakai proses lama.
- Pertimbangkan endpoint health/version sederhana untuk memastikan browser memuat versi aplikasi terbaru.
