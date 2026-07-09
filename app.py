from pathlib import Path
from types import SimpleNamespace

from blueprints.registry import register_app_blueprints
from config import Config
from constants import (
    ACTIVITY_LOG_DIR,
    ACTIVITY_LOG_FILE_PREFIX,
    DEFAULT_ADMIN_PASSWORD,
    DEFAULT_GUEST_STATUS,
    DEFAULT_USER_RESET_PASSWORD,
    GUEST_STATUS_OPTIONS,
    LOGIN_ATTEMPT_SESSION_KEY,
    GUEST_QR_PAGE_TTL_SECONDS,
    INDONESIA_BANK_OPTIONS,
    PACKAGE_OPTIONS,
    PACKAGE_PREMIUM,
    PASSWORD_RESET_PATH,
    ROLE_ADMIN,
    ROLE_SUPER_ADMIN,
    ROLE_USER,
    STAFF_PIN_MAX_ATTEMPTS,
)
from exceptions import UploadValidationError
from extensions import db
from flask import Flask, request, url_for
from models import BillingPayment, DemoGuest, EventArchive, Guests, Staff, User
from services import (
    account_service,
    attendance_service,
    auth_service,
    event_archive_service,
    guest_service,
    listing_service,
    logging_service,
    request_service,
    schema_service,
    staff_service,
    whatsapp_service,
)
from werkzeug.middleware.proxy_fix import ProxyFix


# Fungsi factory untuk membuat instance Flask aplikasi.
def create_app(config_object=Config):
    flask_app = Flask(__name__)
    Path(flask_app.instance_path).mkdir(parents=True, exist_ok=True)
    flask_app.config.from_object(config_object)

    if flask_app.config["ENABLE_PROXY_FIX"]:
        trusted_proxy_count = flask_app.config["TRUSTED_PROXY_COUNT"]
        flask_app.wsgi_app = ProxyFix(
            flask_app.wsgi_app,
            x_for=trusted_proxy_count,
            x_proto=trusted_proxy_count,
            x_host=trusted_proxy_count,
            x_prefix=trusted_proxy_count,
        )

    db.init_app(flask_app)
    flask_app.template_filter("attendance_time")(attendance_time_filter)
    flask_app.template_filter("rupiah")(rupiah_filter)
    flask_app.context_processor(inject_template_feature_flags)
    flask_app.before_request(prepare_activity_log_context)
    flask_app.before_request(enforce_login_session_timeout)
    flask_app.after_request(write_request_access_log)
    flask_app.errorhandler(Exception)(handle_unexpected_error)
    register_app_blueprints(flask_app, build_blueprint_dependencies())

    with flask_app.app_context():
        schema_service.initialize_database()

    return flask_app


# MySQL
# app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+pymysql://user:pass@localhost/dbname"

# PostgreSQL
# app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://user:pass@localhost/dbname"


# Fungsi untuk mengambil waktu aplikasi tanpa timezone.
def get_utc_naive_datetime():
    return auth_service.get_utc_naive_datetime()


# Fungsi untuk menyinkronkan konfigurasi logging app ke service.
def sync_logging_service_config():
    logging_service.configure_activity_log(ACTIVITY_LOG_DIR, ACTIVITY_LOG_FILE_PREFIX)


# Fungsi untuk membuat timestamp GMT+7 format ISO-8601 bagi payload JSON log
def get_utc_iso_timestamp():
    return logging_service.get_utc_iso_timestamp()


# Fungsi untuk mendapatkan path log harian tunggal
def get_daily_activity_log_path():
    sync_logging_service_config()
    return logging_service.get_daily_activity_log_path()


# Fungsi untuk menghasilkan request id.
def generate_request_id():
    return logging_service.generate_request_id()


# Fungsi untuk menghasilkan tracking session id.
def generate_tracking_session_id():
    return logging_service.generate_tracking_session_id()


# Fungsi untuk memastikan request saat ini punya request id
def get_request_id():
    return logging_service.get_request_id()


# Fungsi untuk mengambil atau membuat session id pelacakan pengguna
def get_tracking_session_id(create=False):
    return logging_service.get_tracking_session_id(create=create)


# Fungsi untuk mengambil IP client.
def get_client_ip():
    return logging_service.get_client_ip()


# Fungsi untuk mencari lokasi lokasi IP.
def lookup_ip_location(ip_address):
    return logging_service.lookup_ip_location(ip_address)


# Fungsi untuk mengambil lokasi akun.
def get_account_location(account):
    return logging_service.get_account_location(account)


# Fungsi inti penulisan log gabungan text + JSON
def write_unified_log(level, category, payload, request_id=None):
    sync_logging_service_config()
    logging_service.write_unified_log(level, category, payload, request_id=request_id)


# Fungsi untuk mencatat event akses.
def log_access_event(response):
    sync_logging_service_config()
    logging_service.log_access_event(response)


# Fungsi untuk mencatat event autentikasi.
def log_auth_event(
    event_type,
    message,
    account=None,
    identifier=None,
    level="INFO",
    login_attempts=None,
    is_brute_force_suspicion=False,
):
    sync_logging_service_config()
    logging_service.log_auth_event(
        event_type,
        message,
        account=account,
        identifier=identifier,
        level=level,
        login_attempts=login_attempts,
        is_brute_force_suspicion=is_brute_force_suspicion,
    )


# Fungsi untuk mencatat event aktivitas.
def log_activity_event(event_type, details=None, level="INFO", username=None, role=None, session_id=None):
    sync_logging_service_config()
    logging_service.log_activity_event(
        event_type,
        details=details,
        level=level,
        username=username,
        role=role,
        session_id=session_id,
    )


# Fungsi untuk mencatat error sistem.
def log_system_error(error):
    sync_logging_service_config()
    logging_service.log_system_error(error)


# Fungsi untuk membaca payload JSON dari satu baris log harian
def parse_activity_log_line(line):
    return logging_service.parse_activity_log_line(line)


# Fungsi untuk menormalkan identifier login.
def normalize_login_identifier(identifier):
    return auth_service.normalize_login_identifier(identifier)


# Fungsi untuk membuat key login throttle.
def build_login_throttle_key(identifier, ip_address):
    return auth_service.build_login_throttle_key(identifier, ip_address)


# Fungsi untuk mencari login throttle.
def find_login_throttle(identifier, ip_address=None):
    return auth_service.find_login_throttle(identifier, ip_address)


# Fungsi untuk memeriksa apakah login throttle sedang terkunci.
def is_login_throttle_locked(throttle):
    return auth_service.is_login_throttle_locked(throttle)


# Fungsi untuk mengambil sisa detik lockout login.
def get_login_lockout_remaining_seconds(throttle):
    return auth_service.get_login_lockout_remaining_seconds(throttle)


# Fungsi untuk mendaftarkan login gagal.
def register_failed_login(identifier, ip_address=None):
    return auth_service.register_failed_login(identifier, ip_address)


# Fungsi untuk membersihkan login throttle.
def clear_login_throttle(identifier, ip_address=None):
    auth_service.clear_login_throttle(identifier, ip_address)


# Fungsi untuk membersihkan sesi login aktif milik user saat ini.
def clear_active_login_session_for_current_user():
    return auth_service.clear_active_login_session_for_current_user()


# Fungsi untuk mengubah nilai menjadi integer dengan fallback default
def parse_int(value, default=None):
    return auth_service.parse_int(value, default)


# Fungsi untuk menormalkan opsi sorting data tamu
def normalize_guest_sort(sort_by):
    return listing_service.normalize_guest_sort(sort_by)


# Fungsi untuk menormalkan opsi sorting daftar user
def normalize_user_sort(sort_by):
    return listing_service.normalize_user_sort(sort_by)


# Fungsi untuk membatasi pilihan jumlah data jumlah per halaman
def normalize_per_page(per_page):
    return listing_service.normalize_per_page(per_page)


# Fungsi untuk mengubah teks tanggal format YYYY-MM-DD menjadi objek date
def parse_iso_date(value):
    return account_service.parse_iso_date(value)


# Fungsi untuk mendapatkan tanggal minimal periode akhir (hari esok)
def get_min_period_end_date():
    return account_service.get_min_period_end_date()


# Fungsi untuk menghitung status aktivasi berdasarkan periode akhir.
def calculate_activation_status(period_end_date):
    return account_service.calculate_activation_status(period_end_date)


# Fungsi untuk menghitung status aktivasi akun dari payment verified terbaru.
def calculate_account_activation_status(user):
    return account_service.calculate_account_activation_status(user)


# Fungsi untuk mengambil payment verified terbaru.
def get_latest_verified_payment(user):
    return account_service.get_latest_verified_billing_payment(user)


# Fungsi untuk menyinkronkan status aktivasi user berdasarkan tanggal expired
def sync_user_activation_status(user):
    account_service.sync_user_activation_status(user)


# Fungsi untuk menyinkronkan status aktivasi banyak user sekaligus
def sync_users_activation_status(users):
    account_service.sync_users_activation_status(users)


# Fungsi untuk memblokir akun login user/admin.
def block_account_login(account):
    account_service.block_account_login(account)


# Fungsi untuk membuka blokir akun login user/admin.
def unblock_account_login(account):
    account_service.unblock_account_login(account)


# Fungsi untuk mendapatkan teks dari form dengan strip
def get_form_text(field_name):
    return request_service.get_form_text(field_name)


# Fungsi untuk mendapatkan timestamp saat ini dalam satuan detik
def get_current_timestamp():
    return auth_service.get_current_timestamp()


# Fungsi untuk membuat session login baru untuk semua role
def start_login_session(user):
    auth_service.start_login_session(user)


# Fungsi untuk memperbarui waktu aktivitas terakhir session login
def refresh_login_session_activity():
    auth_service.refresh_login_session_activity()


# Fungsi untuk mengecek apakah session login sudah melewati batas tidak aktif
def is_login_session_expired():
    return auth_service.is_login_session_expired()


# Fungsi untuk mengakhiri session login dan membersihkan data session
def end_login_session():
    auth_service.end_login_session(cleanup_callback=clear_pending_guest_upload)


# Fungsi untuk membuat serializer token session staff
def get_staff_session_serializer():
    return staff_service.get_staff_session_serializer()


# Fungsi untuk membuat hash token akses staff
def hash_staff_access_token(raw_token):
    return staff_service.hash_staff_access_token(raw_token)


# Fungsi untuk membuat token URL random staff
def generate_staff_access_token():
    return staff_service.generate_staff_access_token()


# Fungsi untuk membuat PIN staff enam digit
def generate_staff_pin():
    return staff_service.generate_staff_pin()


# Fungsi untuk membuat URL login staff dari token mentah
def build_staff_access_url(raw_token):
    return staff_service.build_staff_access_url(raw_token)


# Fungsi untuk membuat token session staff yang ditandatangani
def build_staff_session_token(staff_access):
    return staff_service.build_staff_session_token(staff_access)


# Fungsi untuk memasang cookie session staff pada response
def set_staff_session_cookie(response, staff_access):
    return staff_service.set_staff_session_cookie(response, staff_access)


# Fungsi untuk menghapus cookie session staff pada response
def delete_staff_session_cookie(response):
    return staff_service.delete_staff_session_cookie(response)


# Fungsi untuk membaca payload session staff dari cookie
def load_staff_session_payload():
    return staff_service.load_staff_session_payload()


# Fungsi untuk mengambil waktu aktivitas terakhir akses staff
def get_staff_access_activity_time(staff_access):
    return staff_service.get_staff_access_activity_time(staff_access)


# Fungsi untuk mengecek akses staff sudah melewati batas idle
def is_staff_access_idle_expired(staff_access):
    return staff_service.is_staff_access_idle_expired(staff_access)


# Fungsi untuk mencabut akses staff aktif
def revoke_staff_access(staff_access, revoked_by="system", reason="revoked"):
    staff_service.revoke_staff_access(staff_access, revoked_by=revoked_by, reason=reason)


# Fungsi untuk memblokir staff dan mencabut semua akses aktifnya
def block_staff_account(staff, reason="blocked"):
    staff_service.block_staff_account(staff, reason=reason)


# Fungsi untuk membuka blokir staff
def unblock_staff_account(staff):
    staff_service.unblock_staff_account(staff)


# Fungsi untuk mengambil akses staff aktif terbaru
def get_active_staff_access(staff):
    return staff_service.get_active_staff_access(staff)


# Fungsi untuk membuat akses staff baru dan mencabut akses lama staff yang sama
def create_staff_access(staff):
    return staff_service.create_staff_access(staff)


# Fungsi untuk mengambil akses staff berdasarkan token URL
def get_staff_access_by_token(raw_token):
    return staff_service.get_staff_access_by_token(raw_token)


# Fungsi untuk mendapatkan staff aktif dari cookie session staff
def get_current_staff():
    return staff_service.get_current_staff()


# Fungsi untuk memperpanjang cookie session staff saat staff masih aktif
def refresh_staff_session_cookie(response):
    return staff_service.refresh_staff_session_cookie(response)


# Fungsi untuk menampilkan nama staff yang ramah dibaca
def get_staff_display_name(staff):
    return staff_service.get_staff_display_name(staff)


# Fungsi untuk membuat username log bagi aktivitas staff
def get_staff_log_username(staff):
    return staff_service.get_staff_log_username(staff)


# Fungsi untuk mendapatkan client pemilik staff yang masih valid
def get_staff_owner(staff):
    return staff_service.get_staff_owner(staff)


# Fungsi untuk mencatat aktivitas yang dilakukan staff
def log_staff_activity_event(event_type, staff, details=None, level="INFO"):
    sync_logging_service_config()
    staff_service.log_staff_activity_event(event_type, staff, details=details, level=level)


# Decorator untuk memastikan request dashboard staff memiliki session staff aktif
def staff_login_required(f):
    return staff_service.staff_login_required(f)


# Fungsi untuk menormalkan nomor HP agar diawali kode negara 62
def normalize_phone_number(no_hp_text):
    return account_service.normalize_phone_number(no_hp_text)


# Validasi format email sederhana
def is_valid_email_format(email):
    return account_service.is_valid_email_format(email)


# Fungsi untuk mengecek password memiliki huruf besar, huruf kecil, dan angka
def has_upper_lower_number(password):
    return auth_service.has_upper_lower_number(password)


# Validasi format password user: minimal 8 karakter, kombinasi huruf besar, huruf kecil, dan angka
def is_valid_user_password_format(password):
    return auth_service.is_valid_user_password_format(password)


# Validasi format password admin: minimal 8 karakter, kombinasi huruf besar, huruf kecil, angka, dan karakter spesial
def is_valid_admin_password_format(password):
    return auth_service.is_valid_admin_password_format(password)


# Fungsi untuk memilih validasi password sesuai role akun
def is_valid_password_for_role(password, role):
    return auth_service.is_valid_password_for_role(password, role)


# Fungsi untuk mengambil pattern HTML password sesuai role akun
def get_password_pattern_for_role(role):
    return auth_service.get_password_pattern_for_role(role)


# Fungsi untuk mengambil teks bantuan validasi password sesuai role akun
def get_password_title_for_role(role):
    return auth_service.get_password_title_for_role(role)


# Fungsi untuk membandingkan password input dengan password tersimpan
def password_matches(stored_password, password):
    return auth_service.password_matches(stored_password, password)


# Fungsi untuk menyimpan password akun dalam bentuk hash
def set_account_password(account, password):
    auth_service.set_account_password(account, password)


# Fungsi untuk menampilkan nama akun yang ramah dibaca di UI
def get_user_display_name(account):
    return account_service.get_user_display_name(account)


# Fungsi untuk membuat serializer token halaman kehadiran tamu
def get_attendance_token_serializer():
    return attendance_service.get_attendance_token_serializer()


# Fungsi untuk membuat token halaman kehadiran berdasarkan client pemilik data tamu
def build_guest_attendance_token(owner_user):
    return attendance_service.build_guest_attendance_token(owner_user)


# Fungsi untuk membaca client pemilik data tamu dari token halaman kehadiran
def get_attendance_owner_from_token(attendance_token):
    return attendance_service.get_attendance_owner_from_token(attendance_token)


# Fungsi untuk membaca staff pemilik QR dari token halaman kehadiran
def get_attendance_staff_from_token(attendance_token):
    return attendance_service.get_attendance_staff_from_token(attendance_token)


# Fungsi untuk memeriksa akses periode payment aktif client.
def is_owner_in_active_billing_period(owner_user):
    return attendance_service.is_owner_in_active_billing_period(owner_user)


# Fungsi untuk membuat pesan akses periode payment tidak aktif.
def build_inactive_billing_period_message():
    return attendance_service.build_inactive_billing_period_message()


# Fungsi untuk membuat URL publik halaman verifikasi kehadiran tamu
def build_guest_attendance_url(owner_user):
    return attendance_service.build_guest_attendance_url(owner_user)


# Fungsi untuk membuat URL gambar QR halaman verifikasi kehadiran client.
def build_guest_attendance_qr_url(owner_user):
    return attendance_service.build_guest_attendance_qr_url(owner_user)


# Fungsi untuk membuat URL publik halaman verifikasi kehadiran milik staff.
def build_staff_attendance_url(staff):
    return attendance_service.build_staff_attendance_url(staff)


# Fungsi untuk membuat URL download QR halaman verifikasi kehadiran milik staff.
def build_staff_attendance_qr_url(staff):
    return attendance_service.build_staff_attendance_qr_url(staff)


# Fungsi untuk membuat ulang URL publik verifikasi kehadiran tamu
def generate_guest_attendance_url(owner_user):
    return attendance_service.generate_guest_attendance_url(owner_user)


# Fungsi untuk membuat ulang URL publik verifikasi kehadiran milik staff.
def generate_staff_attendance_url(staff):
    return attendance_service.generate_staff_attendance_url(staff)


# Fungsi untuk memeriksa apakah user premium.
def is_premium_user(account):
    return attendance_service.is_premium_user(account)


# Fungsi untuk membuat token QR tamu.
def build_guest_qr_token(guest):
    return attendance_service.build_guest_qr_token(guest)


# Fungsi untuk mengambil tamu dari token QR.
def get_guest_from_qr_token(guest_token):
    return attendance_service.get_guest_from_qr_token(guest_token)


# Fungsi untuk membuat URL QR tamu.
def build_guest_qr_url(guest):
    return attendance_service.build_guest_qr_url(guest)


# Fungsi untuk membuat URL pendek QR tamu.
def build_guest_short_qr_url(guest):
    return whatsapp_service.build_guest_short_qr_url(guest)


# Fungsi untuk mengambil tamu dari short code QR.
def get_guest_from_short_qr_code(short_code):
    return whatsapp_service.get_guest_from_short_qr_code(short_code)


# Fungsi untuk membuat nilai scan QR tamu.
def build_guest_qr_scan_value(guest, guest_token=None):
    return attendance_service.build_guest_qr_scan_value(guest, guest_token)


# Fungsi untuk membuat SVG QR tamu.
def build_guest_qr_svg(qr_value):
    return attendance_service.build_guest_qr_svg(qr_value)


# Fungsi untuk membuat PNG QR halaman verifikasi kehadiran client.
def build_guest_attendance_qr_png(qr_value):
    return attendance_service.build_guest_attendance_qr_png(qr_value)


# Fungsi untuk membuat pesan QR yang sudah terverifikasi.
def build_qr_already_verified_message():
    return attendance_service.build_qr_already_verified_message()


# Fungsi untuk membuat pesan selamat datang QR.
def build_qr_welcome_message(guest):
    return attendance_service.build_qr_welcome_message(guest)


# Fungsi untuk memverifikasi kehadiran QR tamu.
def verify_guest_qr_attendance(owner_user, raw_qr_value):
    sync_logging_service_config()
    return attendance_service.verify_guest_qr_attendance(owner_user, raw_qr_value)


# Fungsi untuk mengambil status request verifikasi kehadiran tamu publik.
def get_guest_attendance_verification_status(owner_user, request_id, target_staff=None):
    return attendance_service.get_guest_attendance_verification_status(owner_user, request_id, target_staff)


# Fungsi untuk mengambil popup request verifikasi kehadiran staff.
def get_staff_attendance_notification(staff):
    return attendance_service.get_staff_attendance_notification(staff)


# Fungsi untuk mengonfirmasi request verifikasi kehadiran oleh staff.
def confirm_attendance_verification_request(staff, request_id):
    sync_logging_service_config()
    return attendance_service.confirm_attendance_verification_request(staff, request_id)


# Fungsi untuk menolak/menutup request verifikasi kehadiran oleh staff.
def reject_attendance_verification_request(staff, request_id):
    return attendance_service.reject_attendance_verification_request(staff, request_id)


# Fungsi untuk menampilkan waktu terakhir generate URL attendance client
def format_attendance_token_generated_at(value):
    return attendance_service.format_attendance_token_generated_at(value)


# Fungsi untuk menampilkan timestamp kehadiran dengan format dd-MMM HH:mm
def format_attendance_time(value):
    return attendance_service.format_attendance_time(value)


# Fungsi filter template untuk menampilkan timestamp kehadiran
def attendance_time_filter(value):
    return format_attendance_time(value) or "N/A"


# Fungsi filter template untuk menampilkan nominal Rupiah.
def rupiah_filter(value):
    try:
        amount = int(value or 0)
    except (TypeError, ValueError):
        amount = 0
    return f"Rp {amount:,}".replace(",", ".")


# Fungsi untuk membuat URL pagination dengan query saat ini tetap terbawa.
def build_pagination_url(page):
    query_args = request.args.to_dict(flat=True)
    query_args["page"] = page
    return url_for(request.endpoint, **(request.view_args or {}), **query_args)


# Fungsi untuk menyisipkan flag fitur template.
def inject_template_feature_flags():
    current_user = auth_service.get_current_user()
    is_client_active = bool(
        current_user and current_user.role == ROLE_USER and calculate_account_activation_status(current_user)
    )
    return {
        "build_guest_attendance_qr_url": build_guest_attendance_qr_url,
        "build_guest_qr_url": build_guest_qr_url,
        "build_guest_short_qr_url": build_guest_short_qr_url,
        "build_pagination_url": build_pagination_url,
        "can_access_client_staff": is_client_active,
        "can_access_guest_scan": bool(is_client_active and is_premium_user(current_user)),
        "is_client_active": is_client_active,
    }


# Fungsi untuk mencatat event verifikasi kehadiran tamu
def log_attendance_event(event_type, owner_user=None, guest=None, no_hp=None, level="INFO", details=None):
    sync_logging_service_config()
    attendance_service.log_attendance_event(
        event_type,
        owner_user=owner_user,
        guest=guest,
        no_hp=no_hp,
        level=level,
        details=details,
    )


# Fungsi untuk mencari tamu berdasarkan nomor HP bersih pada data milik client tertentu
def find_attendance_guests(owner_user, no_hp):
    return attendance_service.find_attendance_guests(owner_user, no_hp)


# Fungsi untuk memproses verifikasi nomor HP tamu dan mengisi waktu kehadiran
def verify_guest_attendance(owner_user, raw_no_hp, target_staff=None):
    sync_logging_service_config()
    clean_phone_func = clean_guest_phone if guest_service.is_allowed_phone_input(raw_no_hp) else lambda _value: ""
    return attendance_service.verify_guest_attendance(owner_user, raw_no_hp, clean_phone_func, target_staff)


# Fungsi untuk menyiapkan context halaman pembuatan password baru
def build_password_template_context(error=None):
    return account_service.build_password_template_context(error)


# Fungsi untuk generate username client baru: 4 huruf awal nama + 2 digit nomor HP
def generate_client_username(nama, no_hp_text):
    return account_service.generate_client_username(nama, no_hp_text)


# Fungsi untuk memvalidasi form tambah user baru
def validate_new_user_form(password, nama, no_hp_text, no_hp, email):
    return account_service.validate_new_user_form(password, nama, no_hp_text, no_hp, email)


# Fungsi untuk memvalidasi form tambah admin baru
def validate_admin_form(username, password, no_hp_text, no_hp, email):
    return account_service.validate_admin_form(username, password, no_hp_text, no_hp, email)


# Fungsi untuk mendapatkan user saat ini berdasarkan session
def get_current_user():
    return auth_service.get_current_user()


# Fungsi untuk mendapatkan nama tampilan user aktif dari session
def get_current_user_display_name():
    return account_service.get_current_user_display_name()


# Fungsi untuk mendapatkan daftar user admin yang dapat dikelola
def get_manageable_users():
    return account_service.get_manageable_users()


# Fungsi untuk mendapatkan daftar admin yang dapat dikelola super admin
def get_manageable_admins():
    return account_service.get_manageable_admins()


# Fungsi untuk mendapatkan daftar staff milik client
def get_client_staff_members(owner_user):
    return staff_service.get_client_staff_members(owner_user)


# Fungsi untuk membuat status ringkas staff untuk UI client
def build_staff_status_item(staff):
    return staff_service.build_staff_status_item(staff)


# Fungsi untuk membuat daftar status staff milik client
def build_staff_status_items(owner_user):
    return staff_service.build_staff_status_items(owner_user)


# Fungsi untuk membuat redirect kembali ke halaman staff client dengan pesan
def build_staff_redirect(message=None, error=None):
    return staff_service.build_staff_redirect(message, error)


# Fungsi untuk membangun konteks halaman staff milik client
def build_staff_page_context(current_user, error=None, form_data=None):
    return staff_service.build_staff_page_context(current_user, error=error, form_data=form_data)


# Fungsi untuk memvalidasi input staff baru milik client
def validate_staff_form(owner_user, nama, no_hp):
    return staff_service.validate_staff_form(owner_user, nama, no_hp)


# Fungsi untuk membuat keyword pencarian staff pada log utama
def build_staff_log_keyword(staff):
    return staff_service.build_staff_log_keyword(staff)


# Fungsi untuk mengecek payload log adalah milik staff terpilih
def is_staff_log_payload(payload, staff):
    return staff_service.is_staff_log_payload(payload, staff)


# Fungsi untuk membuat teks awam dari event log staff
def format_staff_log_message(payload):
    return staff_service.format_staff_log_message(payload)


# Fungsi untuk mengambil log aktivitas staff hari ini dari file log harian
def get_today_staff_log_entries(staff):
    sync_logging_service_config()
    return staff_service.get_today_staff_log_entries(staff)


# Fungsi untuk membuat redirect kembali ke halaman users dengan pesan
def build_users_redirect(message=None, error=None):
    return listing_service.build_users_redirect(message, error)


# Fungsi untuk membuat redirect kembali ke halaman manage admin dengan pesan
def build_admins_redirect(message=None, error=None):
    return listing_service.build_admins_redirect(message, error)


# Fungsi untuk membuat redirect tabel tamu.
def build_guest_table_redirect():
    return listing_service.build_guest_table_redirect()


# Fungsi untuk membuat redirect kembali ke tabel data tamu staff
def build_staff_guest_table_redirect():
    return listing_service.build_staff_guest_table_redirect()


# Fungsi untuk mengambil tamu yang bisa diakses.
def get_accessible_guest(guest_id):
    return listing_service.get_accessible_guest(guest_id)


# Fungsi untuk mengambil data tamu yang boleh dikelola staff aktif
def get_accessible_staff_guest(staff, guest_id):
    return listing_service.get_accessible_staff_guest(staff, guest_id)


# Fungsi untuk memastikan schema guests memiliki kolom user_id dan index
def ensure_guests_user_schema():
    schema_service.ensure_guests_user_schema()


# Fungsi untuk memastikan schema user memiliki kolom provinsi
def ensure_user_provinsi_schema():
    schema_service.ensure_user_provinsi_schema()


# Fungsi untuk memastikan schema user memiliki flag wajib reset password
def ensure_user_password_reset_schema():
    schema_service.ensure_user_password_reset_schema()


# Fungsi untuk memastikan schema staff memiliki kolom blokir terbaru
def ensure_staff_schema():
    schema_service.ensure_staff_schema()


# Fungsi untuk mendapatkan file yang diupload dan validasi keberadaannya
def get_uploaded_file(field_name="file"):
    return guest_service.get_uploaded_file(field_name)


# Fungsi untuk validasi ekstensi file Excel
def validate_excel_file(file):
    guest_service.validate_excel_file(file)


# Fungsi untuk memuat file Excel ke dalam DataFrame dengan validasi dan normalisasi
def load_excel_dataframe(file):
    return guest_service.load_excel_dataframe(file)


# Fungsi untuk validasi format kolom Excel tamu secara ketat
def validate_guest_excel_format(df):
    guest_service.validate_guest_excel_format(df)


# Fungsi untuk mendapatkan nilai integer opsional dari DataFrame dengan normalisasi
def get_optional_integer(row, column_name):
    return guest_service.get_optional_integer(row, column_name)


# Fungsi untuk mendapatkan user yang dipilih sebagai pemilik data tamu berdasarkan form input
def get_selected_owner_user(source, field_name="owner_user_id"):
    return guest_service.get_selected_owner_user(source, field_name)


# Fungsi untuk membersihkan nama tamu dari karakter tidak valid dan membatasi panjangnya
def clean_guest_name(value):
    return guest_service.clean_guest_name(value)


# Fungsi untuk membersihkan dan menormalkan nomor HP tamu
def clean_guest_phone(value):
    return guest_service.clean_guest_phone(value)


# Fungsi untuk membersihkan nama staff dengan aturan nama tamu
def clean_staff_name(value):
    return guest_service.clean_staff_name(value)


# Fungsi untuk membersihkan nomor HP staff dengan aturan nomor HP tamu
def clean_staff_phone(value):
    return guest_service.clean_staff_phone(value)


# Fungsi untuk membersihkan dan memvalidasi email tamu
def clean_guest_email(value):
    return guest_service.clean_guest_email(value)


# Fungsi untuk membersihkan dan menormalkan status tamu berdasarkan opsi yang diperbolehkan
def clean_guest_status(value):
    return guest_service.clean_guest_status(value)


# Fungsi untuk mengambil nilai pembanding duplicate dari field tamu
def get_guest_match_value(field_name, value):
    return guest_service.get_guest_match_value(field_name, value)


# Fungsi untuk membangun record tamu bersih dari satu baris Excel
def build_guest_record(row, fallback_no):
    return guest_service.build_guest_record(row, fallback_no)


# Fungsi untuk mendeteksi field tamu yang duplicate terhadap database atau file upload
def get_guest_duplicate_fields(record, existing_guests, seen_keys):
    return guest_service.get_guest_duplicate_fields(record, existing_guests, seen_keys)


# Fungsi untuk menyimpan key tamu yang sudah dibaca agar duplicate dalam file bisa terdeteksi
def remember_guest_keys(record, seen_keys):
    guest_service.remember_guest_keys(record, seen_keys)


# Fungsi untuk mengecek apakah data tamu dari file upload cocok dengan data tamu yang sudah ada di database
def guest_matches_row(guest, row):
    return guest_service.guest_matches_row(guest, row)


# Fungsi untuk memperbarui data tamu dengan data dari satu baris Excel jika cocok
def update_guest_from_row(guest, row, added_by=None):
    guest_service.update_guest_from_row(guest, row, added_by=added_by)


# Fungsi untuk mendapatkan nomor urut tamu berikutnya untuk pemilik tertentu
def get_next_guest_no(owner_user_id):
    return guest_service.get_next_guest_no(owner_user_id)


# Fungsi untuk mengambil label penambah tamu dari akun client pemilik data.
def build_owner_guest_added_by(owner_user):
    return guest_service.build_owner_guest_added_by(owner_user)


# Fungsi untuk mengambil label penambah tamu dari akun staff.
def build_staff_guest_added_by(staff):
    return guest_service.build_staff_guest_added_by(staff)


# Fungsi untuk membangun data tamu manual dari input form dengan validasi dan normalisasi
def build_manual_guest_data(source, owner_user, added_by=None):
    return guest_service.build_manual_guest_data(source, owner_user, added_by=added_by)


# Fungsi untuk membangun data edit tamu dari input form dengan validasi dan normalisasi.
def build_guest_edit_data(source):
    return guest_service.build_guest_edit_data(source)


# Fungsi untuk mengecek apakah nomor HP tamu sudah terdaftar di data milik user tertentu
def is_guest_phone_registered(owner_user, no_hp, exclude_guest_id=None):
    return guest_service.is_guest_phone_registered(owner_user, no_hp, exclude_guest_id=exclude_guest_id)


# Fungsi untuk membersihkan data tamu tersimpan milik user tertentu
def clean_saved_guests_for_owner(owner_user_id):
    return guest_service.clean_saved_guests_for_owner(owner_user_id)


# Fungsi untuk membuat preview upload tamu sebelum data benar-benar disimpan
def build_guest_upload_preview(file, owner_user):
    return guest_service.build_guest_upload_preview(file, owner_user)


# Fungsi untuk membuat nama file export data tamu aktif.
def build_active_guest_export_filename(owner_user):
    return event_archive_service.build_active_export_filename(owner_user)


# Fungsi untuk membuat nama file export data tamu final.
def build_final_guest_export_filename(owner_user, archive=None):
    return event_archive_service.build_final_export_filename(owner_user, archive=archive)


# Fungsi untuk memastikan data tamu expired sudah dibackup ke CSV final.
def ensure_final_guest_backup(owner_user):
    return event_archive_service.ensure_final_guest_backup(owner_user)


# Fungsi untuk mengambil arsip final terbaru milik client.
def get_latest_final_archive(owner_user):
    return event_archive_service.get_latest_final_archive(owner_user)


# Fungsi untuk membuat Excel dari CSV final event.
def build_final_archive_excel(owner_user, archive=None):
    return event_archive_service.build_final_archive_excel(owner_user, archive=archive)


# Fungsi untuk mengarsipkan event lama saat client aktivasi kembali.
def archive_previous_event_for_reactivation(owner_user, previous_payment=None):
    return event_archive_service.archive_previous_event_for_reactivation(owner_user, previous_payment=previous_payment)


# Fungsi untuk menyimpan file upload Excel tamu asli ke folder instance/uploads
def save_uploaded_guest_file(file, owner_user):
    return guest_service.save_uploaded_guest_file(file, owner_user)


# Fungsi untuk menyimpan baris tamu hasil preview ke database
def save_guest_rows(owner_user, rows, duplicate_indexes=None, include_duplicates=False, added_by=None):
    return guest_service.save_guest_rows(owner_user, rows, duplicate_indexes, include_duplicates, added_by=added_by)


# Fungsi untuk mengganti data tamu yang sudah ada dengan data dari file upload jika user memilih opsi replace
def replace_guest_rows(owner_user, rows, added_by=None):
    return guest_service.replace_guest_rows(owner_user, rows, added_by=added_by)


# Fungsi untuk membangun path file pending upload berdasarkan id session
def get_pending_upload_path(pending_id):
    return guest_service.get_pending_upload_path(pending_id)


# Fungsi untuk menyimpan preview upload tamu sementara sampai user memberi konfirmasi
def save_pending_guest_upload(owner_user, preview):
    return guest_service.save_pending_guest_upload(owner_user, preview)


# Fungsi untuk memuat preview upload tamu yang masih pending dari session
def load_pending_guest_upload():
    return guest_service.load_pending_guest_upload()


# Fungsi untuk menghapus data pending upload tamu dari session dan disk
def clear_pending_guest_upload():
    guest_service.clear_pending_guest_upload()


# Fungsi untuk memproses upload data tamu dengan validasi dan normalisasi, serta mengaitkannya dengan user pemilik
def process_guests_upload(file, owner_user):
    guest_service.process_guests_upload(file, owner_user)


# Fungsi untuk menangani proses upload dengan validasi dan penanganan error yang terstruktur
def handle_upload(processor):
    return guest_service.handle_upload(processor)


# Fungsi untuk membangun query tamu dengan filter pencarian, pemilik, dan opsi sort
def build_guest_query(search="", owner_user_id=None, sort_by="latest"):
    return listing_service.build_guest_query(search, owner_user_id, sort_by)


# Fungsi untuk membangun konteks pagination tamu berdasarkan filter pencarian, pemilik, dan opsi sort
def build_guest_pagination_context(search, page, per_page, owner_user_id=None, sort_by="latest"):
    return listing_service.build_guest_pagination_context(search, page, per_page, owner_user_id, sort_by)


# Fungsi untuk membangun konteks halaman data tamu untuk user biasa dengan filter pencarian, pagination, dan opsi sort
def build_user_guest_context(current_user, search, page, per_page, sort_by):
    return listing_service.build_user_guest_context(current_user, search, page, per_page, sort_by)


# Fungsi untuk membangun konteks halaman data tamu yang dikelola staff
def build_staff_guest_context(staff, search, page, per_page, sort_by):
    return listing_service.build_staff_guest_context(staff, search, page, per_page, sort_by)


# Fungsi untuk membangun konteks halaman data tamu admin dengan filter, pagination,
# sorting, dan daftar user pemilik data.
def build_admin_guest_context(search, page, per_page, selected_owner_user_id=None, sort_by="latest"):
    return listing_service.build_admin_guest_context(search, page, per_page, selected_owner_user_id, sort_by)


# Fungsi untuk membangun context halaman setting WhatsApp.
def build_whatsapp_settings_context(selected_template_id=None, message="", error=""):
    return whatsapp_service.build_whatsapp_settings_context(selected_template_id, message=message, error=error)


# Fungsi untuk menyimpan mode pengiriman WhatsApp.
def update_whatsapp_send_mode(send_mode):
    return whatsapp_service.update_whatsapp_send_mode(send_mode)


# Fungsi untuk menyimpan nomor WhatsApp.
def update_whatsapp_phone(raw_phone_number):
    return whatsapp_service.update_whatsapp_phone(raw_phone_number)


# Fungsi untuk menyimpan token API WhatsApp.
def update_whatsapp_api_token(api_token):
    return whatsapp_service.update_whatsapp_api_token(api_token)


# Fungsi untuk menyimpan Phone Number ID WhatsApp API.
def update_whatsapp_api_phone_number_id(phone_number_id):
    return whatsapp_service.update_whatsapp_api_phone_number_id(phone_number_id)


# Fungsi untuk menyimpan template pesan WhatsApp.
def save_whatsapp_template(template_id, name, body):
    return whatsapp_service.save_whatsapp_template(template_id, name, body)


# Fungsi untuk membuat payload kirim WhatsApp undangan QR tamu.
def build_guest_whatsapp_invite(guest):
    return whatsapp_service.build_guest_whatsapp_invite(guest)


# Fungsi untuk membangun query daftar user dengan filter pencarian dan sorting
def build_user_query(search="", sort_by="name_asc"):
    return listing_service.build_user_query(search, sort_by)


# Fungsi untuk membangun context halaman daftar user dengan pagination dan pesan UI
def build_user_list_context(search, page, per_page, sort_by):
    return listing_service.build_user_list_context(search, page, per_page, sort_by)


# Fungsi untuk memastikan akun super admin bawaan tersedia dan benar
def ensure_default_super_admin():
    return schema_service.ensure_default_super_admin()


# Fungsi untuk menyiapkan request id, session id, dan waktu mulai request
def prepare_activity_log_context():
    return request_service.prepare_activity_log_context()


# Fungsi untuk mengakhiri session login yang idle lebih dari batas waktu
def enforce_login_session_timeout():
    sync_logging_service_config()
    return request_service.enforce_login_session_timeout(cleanup_callback=clear_pending_guest_upload)


# Fungsi untuk mencatat access log semua request
def write_request_access_log(response):
    sync_logging_service_config()
    return request_service.write_request_access_log(response)


# Fungsi untuk mencatat error aplikasi yang tidak tertangani
def handle_unexpected_error(error):
    sync_logging_service_config()
    return request_service.handle_unexpected_error(error)


# Decorator untuk memastikan user sudah login
def login_required(f):
    sync_logging_service_config()
    return request_service.login_required(f)


# Decorator untuk memastikan user memiliki role tertentu
def role_required(*roles):
    sync_logging_service_config()
    return request_service.role_required(*roles)


# Fungsi untuk membuat dependency Blueprint dari wrapper aplikasi.
def build_blueprint_dependencies():
    return SimpleNamespace(
        DEFAULT_ADMIN_PASSWORD=DEFAULT_ADMIN_PASSWORD,
        DEFAULT_GUEST_STATUS=DEFAULT_GUEST_STATUS,
        DEFAULT_USER_RESET_PASSWORD=DEFAULT_USER_RESET_PASSWORD,
        BillingPayment=BillingPayment,
        DemoGuest=DemoGuest,
        EventArchive=EventArchive,
        Guests=Guests,
        GUEST_STATUS_OPTIONS=GUEST_STATUS_OPTIONS,
        GUEST_QR_PAGE_TTL_SECONDS=GUEST_QR_PAGE_TTL_SECONDS,
        INDONESIA_BANK_OPTIONS=INDONESIA_BANK_OPTIONS,
        LOGIN_ATTEMPT_SESSION_KEY=LOGIN_ATTEMPT_SESSION_KEY,
        PACKAGE_OPTIONS=PACKAGE_OPTIONS,
        PACKAGE_PREMIUM=PACKAGE_PREMIUM,
        PASSWORD_RESET_PATH=PASSWORD_RESET_PATH,
        ROLE_ADMIN=ROLE_ADMIN,
        ROLE_SUPER_ADMIN=ROLE_SUPER_ADMIN,
        ROLE_USER=ROLE_USER,
        STAFF_PIN_MAX_ATTEMPTS=STAFF_PIN_MAX_ATTEMPTS,
        Staff=Staff,
        UploadValidationError=UploadValidationError,
        User=User,
        block_account_login=block_account_login,
        block_staff_account=block_staff_account,
        build_admin_guest_context=build_admin_guest_context,
        build_admins_redirect=build_admins_redirect,
        build_active_guest_export_filename=build_active_guest_export_filename,
        build_final_archive_excel=build_final_archive_excel,
        build_final_guest_export_filename=build_final_guest_export_filename,
        build_guest_attendance_qr_url=build_guest_attendance_qr_url,
        build_guest_attendance_url=build_guest_attendance_url,
        build_guest_attendance_qr_png=build_guest_attendance_qr_png,
        build_guest_qr_svg=build_guest_qr_svg,
        build_guest_qr_token=build_guest_qr_token,
        build_guest_qr_scan_value=build_guest_qr_scan_value,
        build_guest_qr_url=build_guest_qr_url,
        build_guest_short_qr_url=build_guest_short_qr_url,
        build_inactive_billing_period_message=build_inactive_billing_period_message,
        build_staff_attendance_qr_url=build_staff_attendance_qr_url,
        build_staff_attendance_url=build_staff_attendance_url,
        build_guest_query=build_guest_query,
        build_guest_table_redirect=build_guest_table_redirect,
        build_guest_edit_data=build_guest_edit_data,
        build_guest_upload_preview=build_guest_upload_preview,
        build_guest_whatsapp_invite=build_guest_whatsapp_invite,
        build_owner_guest_added_by=build_owner_guest_added_by,
        build_qr_already_verified_message=build_qr_already_verified_message,
        build_qr_welcome_message=build_qr_welcome_message,
        build_manual_guest_data=build_manual_guest_data,
        build_password_template_context=build_password_template_context,
        build_staff_access_url=build_staff_access_url,
        build_staff_guest_added_by=build_staff_guest_added_by,
        build_staff_guest_context=build_staff_guest_context,
        build_staff_guest_table_redirect=build_staff_guest_table_redirect,
        build_staff_log_keyword=build_staff_log_keyword,
        build_staff_page_context=build_staff_page_context,
        build_staff_redirect=build_staff_redirect,
        build_staff_status_items=build_staff_status_items,
        build_user_guest_context=build_user_guest_context,
        build_user_list_context=build_user_list_context,
        build_users_redirect=build_users_redirect,
        build_whatsapp_settings_context=build_whatsapp_settings_context,
        clean_guest_status=clean_guest_status,
        clean_staff_name=clean_staff_name,
        clean_staff_phone=clean_staff_phone,
        clear_active_login_session_for_current_user=clear_active_login_session_for_current_user,
        clear_login_throttle=clear_login_throttle,
        clear_pending_guest_upload=clear_pending_guest_upload,
        calculate_account_activation_status=calculate_account_activation_status,
        archive_previous_event_for_reactivation=archive_previous_event_for_reactivation,
        confirm_attendance_verification_request=confirm_attendance_verification_request,
        create_staff_access=create_staff_access,
        db=db,
        delete_staff_session_cookie=delete_staff_session_cookie,
        end_login_session=end_login_session,
        find_login_throttle=find_login_throttle,
        format_attendance_time=format_attendance_time,
        format_attendance_token_generated_at=format_attendance_token_generated_at,
        generate_client_username=generate_client_username,
        generate_guest_attendance_url=generate_guest_attendance_url,
        generate_staff_attendance_url=generate_staff_attendance_url,
        ensure_final_guest_backup=ensure_final_guest_backup,
        get_accessible_guest=get_accessible_guest,
        get_accessible_staff_guest=get_accessible_staff_guest,
        get_active_staff_access=get_active_staff_access,
        get_attendance_owner_from_token=get_attendance_owner_from_token,
        get_attendance_staff_from_token=get_attendance_staff_from_token,
        get_guest_attendance_verification_status=get_guest_attendance_verification_status,
        get_guest_from_qr_token=get_guest_from_qr_token,
        get_guest_from_short_qr_code=get_guest_from_short_qr_code,
        get_client_ip=get_client_ip,
        get_current_staff=get_current_staff,
        get_current_user=get_current_user,
        get_current_user_display_name=get_current_user_display_name,
        get_form_text=get_form_text,
        get_login_lockout_remaining_seconds=get_login_lockout_remaining_seconds,
        get_manageable_admins=get_manageable_admins,
        get_min_period_end_date=get_min_period_end_date,
        get_password_title_for_role=get_password_title_for_role,
        get_request_id=get_request_id,
        get_selected_owner_user=get_selected_owner_user,
        get_latest_final_archive=get_latest_final_archive,
        get_latest_verified_payment=get_latest_verified_payment,
        get_staff_access_by_token=get_staff_access_by_token,
        get_staff_display_name=get_staff_display_name,
        get_staff_attendance_notification=get_staff_attendance_notification,
        get_staff_owner=get_staff_owner,
        get_today_staff_log_entries=get_today_staff_log_entries,
        get_tracking_session_id=get_tracking_session_id,
        get_uploaded_file=get_uploaded_file,
        get_user_display_name=get_user_display_name,
        get_utc_naive_datetime=get_utc_naive_datetime,
        handle_upload=handle_upload,
        is_guest_phone_registered=is_guest_phone_registered,
        is_owner_in_active_billing_period=is_owner_in_active_billing_period,
        is_premium_user=is_premium_user,
        is_login_throttle_locked=is_login_throttle_locked,
        is_staff_access_idle_expired=is_staff_access_idle_expired,
        is_valid_password_for_role=is_valid_password_for_role,
        load_pending_guest_upload=load_pending_guest_upload,
        log_activity_event=log_activity_event,
        log_attendance_event=log_attendance_event,
        log_auth_event=log_auth_event,
        log_staff_activity_event=log_staff_activity_event,
        log_system_error=log_system_error,
        login_required=login_required,
        normalize_phone_number=normalize_phone_number,
        parse_int=parse_int,
        parse_iso_date=parse_iso_date,
        password_matches=password_matches,
        process_guests_upload=process_guests_upload,
        register_failed_login=register_failed_login,
        reject_attendance_verification_request=reject_attendance_verification_request,
        replace_guest_rows=replace_guest_rows,
        revoke_staff_access=revoke_staff_access,
        role_required=role_required,
        save_whatsapp_template=save_whatsapp_template,
        save_guest_rows=save_guest_rows,
        save_uploaded_guest_file=save_uploaded_guest_file,
        save_pending_guest_upload=save_pending_guest_upload,
        set_account_password=set_account_password,
        set_staff_session_cookie=set_staff_session_cookie,
        staff_login_required=staff_login_required,
        start_login_session=start_login_session,
        sync_user_activation_status=sync_user_activation_status,
        sync_users_activation_status=sync_users_activation_status,
        unblock_account_login=unblock_account_login,
        unblock_staff_account=unblock_staff_account,
        update_whatsapp_api_phone_number_id=update_whatsapp_api_phone_number_id,
        update_whatsapp_api_token=update_whatsapp_api_token,
        update_whatsapp_phone=update_whatsapp_phone,
        update_whatsapp_send_mode=update_whatsapp_send_mode,
        validate_admin_form=validate_admin_form,
        validate_new_user_form=validate_new_user_form,
        validate_staff_form=validate_staff_form,
        verify_guest_attendance=verify_guest_attendance,
        verify_guest_qr_attendance=verify_guest_qr_attendance,
    )


app = create_app()
