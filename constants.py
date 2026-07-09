from datetime import timedelta, timezone
import re
from pathlib import Path

APP_TIMEZONE = timezone(timedelta(hours=7), "GMT+7")
ALLOWED_EXCEL_EXTENSIONS = (".xlsx", ".xls")
GUEST_EXCEL_COLUMNS = ("no", "nama", "no_hp", "email", "status")
GUEST_NAME_MAX_LENGTH = 30
GUEST_EMAIL_MAX_LENGTH = 30
GUEST_ADDED_BY_MAX_LENGTH = 35
GUEST_PHONE_MIN_LENGTH = 8
GUEST_STATUS_OPTIONS = ("Reguler", "VIP")
DEFAULT_GUEST_STATUS = "Reguler"
GUEST_SORT_OPTIONS = {"latest", "name_asc", "name_desc", "attendance_desc"}
USER_SORT_OPTIONS = {"name_asc", "name_desc"}
PER_PAGE_OPTIONS = (10, 50, 100)
PACKAGE_OPTIONS = ("basic", "standard", "premium")
PACKAGE_PREMIUM = "premium"
INDONESIA_BANK_OPTIONS = (
    "Bank Syariah Indonesia",
    "BCA",
    "BCA Syariah",
    "BNI",
    "BRI",
    "BTN",
    "BTPN",
    "CIMB Niaga",
    "Danamon",
    "Jago",
    "Mandiri",
    "Maybank Indonesia",
    "Mega",
    "OCBC",
    "Panin",
    "Permata",
    "Seabank",
    "Sinarmas",
    "UOB Indonesia",
)
ROLE_SUPER_ADMIN = "super_admin"
ROLE_ADMIN = "admin"
ROLE_USER = "user"
ROLE_STAFF = "staff"
NAME_PATTERN = re.compile(r"^[A-Za-z ]+$")
GUEST_NAME_CLEANUP_PATTERN = re.compile(r"[^A-Za-z ]+")
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,15}$")
USER_PASSWORD_PATTERN = r"(?=.*[a-z])(?=.*[A-Z])(?=.*[0-9]).{8,}"
ADMIN_PASSWORD_PATTERN = r"(?=.*[a-z])(?=.*[A-Z])(?=.*[0-9])(?=.*[^A-Za-z0-9]).{8,}"
USER_PASSWORD_TITLE = "Password minimal 8 karakter dan harus kombinasi huruf besar, huruf kecil, dan angka"
ADMIN_PASSWORD_TITLE = (
    "Password minimal 8 karakter dan harus kombinasi huruf besar, huruf kecil, angka, dan karakter spesial"
)
DEFAULT_ADMIN_PASSWORD = "Admin1234!"
DEFAULT_SUPER_ADMIN_PASSWORD = "SuperAdmin1234!"
DEFAULT_USER_RESET_PASSWORD = "User1234"
PASSWORD_RESET_PATH = "/password/new"
PENDING_UPLOAD_SESSION_KEY = "pending_guest_upload_id"
SESSION_LAST_ACTIVITY_KEY = "last_activity_at"
SESSION_ACTIVE_TOKEN_KEY = "active_session_token"
SESSION_TIMEOUT_SECONDS = 60 * 60
SESSION_TRACKING_ID_KEY = "tracking_session_id"
LOGIN_ATTEMPT_SESSION_KEY = "login_attempts"
STAFF_SESSION_COOKIE_NAME = "staff_session"
STAFF_SESSION_SALT = "staff-session"
STAFF_SESSION_TIMEOUT_SECONDS = 2 * 60 * 60
STAFF_ACCESS_TOKEN_BYTES = 32
STAFF_PIN_LENGTH = 6
STAFF_PIN_MAX_ATTEMPTS = 3
ATTENDANCE_TOKEN_SALT = "guest-attendance"
GUEST_QR_TOKEN_SALT = "guest-qr-attendance"
GUEST_QR_PAGE_TTL_SECONDS = 5 * 60
GUEST_ATTENDANCE_QR_PRINT_SIZE_PX = 2400
ATTENDANCE_TOKEN_NONCE_BYTES = 32
ATTENDANCE_MONTH_ABBREVIATIONS = ("Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des")
BRUTE_FORCE_ATTEMPT_THRESHOLD = 5
LOGIN_FAILURE_WINDOW_SECONDS = 15 * 60
LOGIN_LOCKOUT_SECONDS = 15 * 60
ACTIVITY_LOG_DIR = Path(__file__).resolve().parent / "logs"
ACTIVITY_LOG_FILE_PREFIX = "activity"
DEMO_GUEST_EXCEL_FILENAME = "data_dummy_1000_baris.xlsx"
DEMO_GUEST_EXCEL_PATH = Path.home() / "Downloads" / DEMO_GUEST_EXCEL_FILENAME
