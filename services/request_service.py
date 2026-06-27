from functools import wraps
import time

from constants import PASSWORD_RESET_PATH, ROLE_USER
from extensions import db
from flask import g, redirect, request, session
from services import account_service, auth_service, logging_service, staff_service
from werkzeug.exceptions import HTTPException


# Fungsi untuk mengambil form teks.
def get_form_text(field_name):
    return request.form.get(field_name, "").strip()


# Fungsi untuk menyiapkan context log aktivitas.
def prepare_activity_log_context():
    g.request_started_at = time.perf_counter()
    g.request_id = logging_service.generate_request_id()
    g.current_staff = None
    g.current_staff_access = None
    g.current_staff_loaded = False
    g.staff_session_skip_refresh = False
    if request.endpoint != "static":
        logging_service.get_tracking_session_id(create=True)
    return None


# Fungsi untuk menegakkan timeout sesi login.
def enforce_login_session_timeout(cleanup_callback=None):
    if request.endpoint == "static" or request.path.startswith("/staff") or "user" not in session:
        return None

    if not auth_service.is_current_login_session_active():
        expired_username = session.get("user")
        expired_role = session.get("role")
        expired_session_id = logging_service.get_tracking_session_id()
        logging_service.log_auth_event(
            "AUTH_SESSION_REPLACED",
            "Session login berakhir karena akun login di perangkat/browser lain",
            level="WARN",
            identifier=expired_username,
        )
        logging_service.log_activity_event(
            "SESSION_REPLACED",
            details={"reason": "new_login_elsewhere"},
            level="WARN",
            username=expired_username,
            role=expired_role,
            session_id=expired_session_id,
        )
        auth_service.end_login_session(cleanup_callback=cleanup_callback)
        if request.endpoint in {"login", "auth.login"}:
            return None
        return redirect("/login")

    current_user = auth_service.get_current_user()
    if current_user and getattr(current_user, "is_blocked", False):
        blocked_username = session.get("user")
        blocked_role = session.get("role")
        blocked_session_id = logging_service.get_tracking_session_id()
        logging_service.log_auth_event(
            "AUTH_SESSION_BLOCKED",
            "Session login berakhir karena akun diblokir",
            level="WARN",
            identifier=blocked_username,
        )
        logging_service.log_activity_event(
            "SESSION_BLOCKED",
            details={"reason": "account_blocked"},
            level="WARN",
            username=blocked_username,
            role=blocked_role,
            session_id=blocked_session_id,
        )
        auth_service.end_login_session(cleanup_callback=cleanup_callback)
        if request.endpoint in {"login", "auth.login"}:
            return None
        return redirect("/login")

    if auth_service.is_login_session_expired():
        expired_username = session.get("user")
        expired_role = session.get("role")
        expired_session_id = logging_service.get_tracking_session_id()
        logging_service.log_auth_event(
            "AUTH_SESSION_EXPIRED",
            "Session login berakhir karena idle",
            level="WARN",
            identifier=expired_username,
        )
        logging_service.log_activity_event(
            "SESSION_EXPIRED",
            details={"reason": "idle_timeout"},
            level="WARN",
            username=expired_username,
            role=expired_role,
            session_id=expired_session_id,
        )
        auth_service.end_login_session(cleanup_callback=cleanup_callback)
        if request.endpoint in {"login", "auth.login"}:
            return None
        return redirect("/login")

    auth_service.refresh_login_session_activity()
    if current_user and current_user.role == ROLE_USER:
        previous_activation = current_user.aktivasi
        account_service.sync_user_activation_status(current_user)
        if current_user.aktivasi != previous_activation:
            db.session.commit()
    return None


# Fungsi untuk menulis log akses request.
def write_request_access_log(response):
    response.headers["X-Request-ID"] = logging_service.get_request_id()
    staff_service.refresh_staff_session_cookie(response)
    logging_service.log_access_event(response)
    return response


# Fungsi untuk menangani error tidak terduga.
def handle_unexpected_error(error):
    if isinstance(error, HTTPException):
        if error.code and error.code >= 500:
            logging_service.log_system_error(error)
        return error

    logging_service.log_system_error(error)
    return "Terjadi kesalahan pada server.", 500


# Fungsi untuk menjalankan proses kewajiban login.
def login_required(f):
    @wraps(f)
    # Fungsi pembungkus untuk menjalankan handler setelah validasi akses.
    def wrapper(*args, **kwargs):
        if "user" not in session:
            logging_service.log_auth_event(
                "AUTH_REQUIRED",
                "Akses ditolak: pengguna belum login",
                level="WARN",
            )
            return redirect("/login")

        current_user = auth_service.get_current_user()
        if (
            current_user
            and current_user.must_reset_password
            and request.endpoint not in {"reset_password", "auth.reset_password", "static"}
        ):
            return redirect(PASSWORD_RESET_PATH)

        return f(*args, **kwargs)

    return wrapper


# Fungsi untuk membatasi kewajiban role.
def role_required(*roles):
    # Fungsi decorator untuk membungkus validasi akses route.
    def decorator(f):
        @wraps(f)
        # Fungsi pembungkus untuk menjalankan handler setelah validasi akses.
        def wrapper(*args, **kwargs):
            if session.get("role") not in roles:
                logging_service.log_auth_event(
                    "AUTH_FORBIDDEN",
                    "Akses ditolak: role tidak sesuai",
                    level="WARN",
                )
                return "Akses ditolak ❌"
            return f(*args, **kwargs)

        return wrapper

    return decorator
