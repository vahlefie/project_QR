from datetime import datetime
from functools import wraps
import hashlib
import secrets

from constants import (
    ROLE_STAFF,
    ROLE_USER,
    APP_TIMEZONE,
    STAFF_ACCESS_TOKEN_BYTES,
    STAFF_PIN_LENGTH,
    STAFF_PIN_MAX_ATTEMPTS,
    STAFF_SESSION_COOKIE_NAME,
    STAFF_SESSION_SALT,
    STAFF_SESSION_TIMEOUT_SECONDS,
)
from extensions import db
from flask import current_app, g, redirect, request, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from models import Staff, StaffAccess
from services import account_service, logging_service
from werkzeug.security import generate_password_hash


# Fungsi untuk mengambil waktu aplikasi tanpa timezone.
def get_utc_naive_datetime():
    return datetime.now(APP_TIMEZONE).replace(tzinfo=None)


# Fungsi untuk mengubah nilai menjadi integer dengan default aman.
def parse_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# Fungsi untuk mengambil serializer sesi staff.
def get_staff_session_serializer():
    secret_key = current_app.secret_key
    if not secret_key:
        raise RuntimeError("SECRET_KEY aplikasi belum dikonfigurasi.")
    return URLSafeTimedSerializer(secret_key, salt=STAFF_SESSION_SALT)


# Fungsi untuk membuat hash token akses staff.
def hash_staff_access_token(raw_token):
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


# Fungsi untuk menghasilkan token akses staff.
def generate_staff_access_token():
    return secrets.token_urlsafe(STAFF_ACCESS_TOKEN_BYTES)


# Fungsi untuk menghasilkan PIN staff.
def generate_staff_pin():
    return f"{secrets.randbelow(10 ** STAFF_PIN_LENGTH):0{STAFF_PIN_LENGTH}d}"


# Fungsi untuk membuat URL akses staff.
def build_staff_access_url(raw_token):
    return url_for("staff.staff_access_login", access_token=raw_token, _external=True)


# Fungsi untuk membuat token sesi staff.
def build_staff_session_token(staff_access):
    return get_staff_session_serializer().dumps({"staff_access_id": staff_access.id})


# Fungsi untuk mengatur cookie sesi staff.
def set_staff_session_cookie(response, staff_access):
    response.set_cookie(
        STAFF_SESSION_COOKIE_NAME,
        build_staff_session_token(staff_access),
        max_age=STAFF_SESSION_TIMEOUT_SECONDS,
        httponly=True,
        samesite="Lax",
        path="/",
    )
    return response


# Fungsi untuk menghapus cookie sesi staff.
def delete_staff_session_cookie(response):
    g.staff_session_skip_refresh = True
    response.delete_cookie(STAFF_SESSION_COOKIE_NAME, path="/")
    return response


# Fungsi untuk memuat payload sesi staff.
def load_staff_session_payload():
    token = request.cookies.get(STAFF_SESSION_COOKIE_NAME)
    if not token:
        return None

    try:
        return get_staff_session_serializer().loads(token, max_age=STAFF_SESSION_TIMEOUT_SECONDS)
    except SignatureExpired:
        g.staff_session_expired = True
        return None
    except BadSignature:
        g.staff_session_invalid = True
        return None


# Fungsi untuk mengambil waktu aktivitas akses staff.
def get_staff_access_activity_time(staff_access):
    return staff_access.last_activity_at or staff_access.created_at


# Fungsi untuk memeriksa apakah akses staff idle kedaluwarsa.
def is_staff_access_idle_expired(staff_access):
    activity_time = get_staff_access_activity_time(staff_access)
    if not activity_time:
        return True
    return (get_utc_naive_datetime() - activity_time).total_seconds() > STAFF_SESSION_TIMEOUT_SECONDS


# Fungsi untuk mencabut akses staff.
def revoke_staff_access(staff_access, revoked_by="system", reason="revoked"):
    if not staff_access:
        return
    if staff_access.is_active or not staff_access.revoked_at:
        staff_access.is_active = False
        staff_access.revoked_at = get_utc_naive_datetime()
        staff_access.revoked_by = revoked_by
        staff_access.revoked_reason = reason


# Fungsi untuk memblokir akun staff.
def block_staff_account(staff, reason="blocked"):
    if not staff:
        return
    staff.is_blocked = True
    staff.blocked_at = get_utc_naive_datetime()
    staff.block_reason = reason
    active_accesses = StaffAccess.query.filter_by(staff_id=staff.id, is_active=True).all()
    for staff_access in active_accesses:
        revoke_staff_access(staff_access, revoked_by="system", reason=reason)


# Fungsi untuk membuka blokir akun staff.
def unblock_staff_account(staff):
    if not staff:
        return
    staff.is_blocked = False
    staff.blocked_at = None
    staff.block_reason = None


# Fungsi untuk mengambil akses staff aktif.
def get_active_staff_access(staff):
    if not staff or staff.is_blocked:
        return None

    staff_access = (
        StaffAccess.query.filter_by(
            staff_id=staff.id,
            is_active=True,
        )
        .order_by(StaffAccess.id.desc())
        .first()
    )
    if not staff_access:
        return None

    if is_staff_access_idle_expired(staff_access):
        revoke_staff_access(staff_access, revoked_by="system", reason="idle_timeout")
        db.session.commit()
        return None
    return staff_access


# Fungsi untuk membuat akses staff.
def create_staff_access(staff):
    for existing_access in StaffAccess.query.filter_by(staff_id=staff.id, is_active=True).all():
        revoke_staff_access(existing_access, revoked_by="client", reason="replaced_by_new_login")

    raw_token = generate_staff_access_token()
    pin = generate_staff_pin()
    staff_access = StaffAccess()
    staff_access.staff_id = staff.id
    staff_access.token_hash = hash_staff_access_token(raw_token)
    staff_access.pin_hash = generate_password_hash(pin)
    staff_access.last_activity_at = get_utc_naive_datetime()
    db.session.add(staff_access)
    db.session.commit()
    return staff_access, raw_token, pin


# Fungsi untuk mengambil akses staff berdasarkan token.
def get_staff_access_by_token(raw_token):
    if not raw_token:
        return None
    return StaffAccess.query.filter_by(token_hash=hash_staff_access_token(raw_token)).first()


# Fungsi untuk mengambil pemilik staff.
def get_staff_owner(staff):
    if not staff:
        return None
    owner = staff.owner
    if not owner or owner.role != ROLE_USER:
        return None
    return owner


# Fungsi untuk mengambil staff saat ini.
def get_current_staff():
    if getattr(g, "current_staff_loaded", False):
        return getattr(g, "current_staff", None)

    g.current_staff_loaded = True
    payload = load_staff_session_payload()
    staff_access_id = parse_int(payload.get("staff_access_id")) if payload else None
    staff_access = db.session.get(StaffAccess, staff_access_id) if staff_access_id else None
    staff = staff_access.staff if staff_access else None

    if (
        not staff_access
        or not staff_access.is_active
        or staff_access.revoked_at
        or is_staff_access_idle_expired(staff_access)
        or not staff
        or staff.is_blocked
        or not get_staff_owner(staff)
    ):
        if staff_access:
            g.staff_session_revoked_reason = staff_access.revoked_reason
        if staff_access and staff_access.is_active and not staff_access.revoked_at:
            revoke_staff_access(staff_access, revoked_by="system", reason="idle_timeout_or_invalid")
            g.staff_session_revoked_reason = staff_access.revoked_reason
            db.session.commit()
        g.current_staff = None
        g.current_staff_access = None
        if request.cookies.get(STAFF_SESSION_COOKIE_NAME):
            g.staff_session_invalid = True
        return None

    g.current_staff = staff
    g.current_staff_access = staff_access
    return staff


# Fungsi untuk menyegarkan cookie sesi staff.
def refresh_staff_session_cookie(response):
    staff = getattr(g, "current_staff", None)
    staff_access = getattr(g, "current_staff_access", None)
    if staff and staff_access and not getattr(g, "staff_session_skip_refresh", False):
        staff_access.last_activity_at = get_utc_naive_datetime()
        db.session.commit()
        set_staff_session_cookie(response, staff_access)
    return response


# Fungsi untuk mengambil nama tampilan staff.
def get_staff_display_name(staff):
    if not staff:
        return ""
    return staff.nama or staff.no_hp


# Fungsi untuk mengambil username log staff.
def get_staff_log_username(staff):
    if not staff:
        return None
    return f"staff:{staff.no_hp}"


# Fungsi untuk mencatat event aktivitas staff.
def log_staff_activity_event(event_type, staff, details=None, level="INFO"):
    event_details = dict(details or {})
    event_details.setdefault("staff_id", staff.id)
    event_details.setdefault("staff_name", staff.nama)
    event_details.setdefault("staff_no_hp", staff.no_hp)
    event_details.setdefault("owner_user_id", staff.owner_user_id)
    logging_service.log_activity_event(
        event_type,
        details=event_details,
        level=level,
        username=get_staff_log_username(staff),
        role=ROLE_STAFF,
        session_id=f"staff_{staff.id}",
    )


# Fungsi untuk menangani akses staff wajib login.
def staff_login_required(f):
    @wraps(f)
    # Fungsi pembungkus untuk menolak akses staff tanpa session staff valid
    def wrapper(*args, **kwargs):
        staff = get_current_staff()
        if not staff:
            reason = "logout" if getattr(g, "staff_session_revoked_reason", None) == "client_logout" else None
            expired_url = (
                url_for("staff.staff_session_expired", reason=reason)
                if reason
                else url_for("staff.staff_session_expired")
            )
            response = redirect(expired_url)
            return delete_staff_session_cookie(response)
        return f(*args, **kwargs)

    return wrapper


# Fungsi untuk mengambil anggota staff client.
def get_client_staff_members(owner_user):
    return Staff.query.filter_by(owner_user_id=owner_user.id).order_by(Staff.id.asc()).all()


# Fungsi untuk membuat item status staff.
def build_staff_status_item(staff):
    active_access = get_active_staff_access(staff)
    return {
        "id": staff.id,
        "is_blocked": bool(staff.is_blocked),
        "is_active": bool(active_access),
    }


# Fungsi untuk membuat item status staffs.
def build_staff_status_items(owner_user):
    return [build_staff_status_item(staff) for staff in get_client_staff_members(owner_user)]


# Fungsi untuk membuat redirect staff.
def build_staff_redirect(message=None, error=None):
    query_args = {}
    if message:
        query_args["message"] = message
    if error:
        query_args["error"] = error
    return redirect(url_for("client_staff.user_staff", **query_args))


# Fungsi untuk membuat context halaman staff.
def build_staff_page_context(current_user, error=None, form_data=None):
    staff_members = get_client_staff_members(current_user)
    staff_states = {staff.id: build_staff_status_item(staff) for staff in staff_members}
    return {
        "user": account_service.get_user_display_name(current_user),
        "staff_members": staff_members,
        "staff_states": staff_states,
        "message": request.args.get("message", ""),
        "error": error or request.args.get("error", ""),
        "form_data": form_data or {},
    }


# Fungsi untuk memvalidasi form staff.
def validate_staff_form(owner_user, nama, no_hp):
    if not nama or not no_hp:
        return "Nomor HP dan nama staff wajib diisi dengan format valid."
    if Staff.query.filter_by(owner_user_id=owner_user.id, no_hp=no_hp).first():
        return "Nomor HP staff sudah terdaftar untuk client ini."
    return None


# Fungsi untuk membuat keyword log staff.
def build_staff_log_keyword(staff):
    return f"staff:{staff.no_hp}"


# Fungsi untuk memeriksa apakah payload log staff.
def is_staff_log_payload(payload, staff):
    if payload.get("_log_category") != "ACTIVITY":
        return False
    details = payload.get("details") or {}
    return (
        details.get("staff_id") == staff.id
        or details.get("staff_no_hp") == staff.no_hp
        or payload.get("username") == build_staff_log_keyword(staff)
    )


# Fungsi untuk memformat pesan log staff.
def format_staff_log_message(payload):
    event_type = payload.get("event_type", "")
    details = payload.get("details") or {}

    if event_type == "CREATE_STAFF_ACCESS":
        return "Client membuat URL login dan PIN baru untuk staff."
    if event_type == "LOGIN_STAFF_WITH_PIN":
        return "Staff login menggunakan PIN dan berhasil masuk menu Data."
    if event_type == "LOGOUT_STAFF":
        return "Staff logout dari menu Data."
    if event_type == "LOGOUT_STAFF_FROM_CLIENT":
        return "Client mencabut akses login staff."
    if event_type == "BLOCK_STAFF":
        return "Client memblokir staff."
    if event_type == "UNBLOCK_STAFF":
        return "Client membuka blokir staff."
    if event_type == "BLOCK_STAFF_PIN_FAILED":
        failed_attempts = details.get("failed_pin_attempts", STAFF_PIN_MAX_ATTEMPTS)
        return f"PIN salah {failed_attempts} kali. Staff diblokir dan akses dicabut."
    if event_type == "CREATE_GUEST_ROW":
        guest_name = details.get("guest_name") or "tanpa nama"
        return f"Staff menambahkan data tamu baru: {guest_name}."
    if event_type == "UPDATE_GUEST_STATUS":
        old_status = details.get("old_status") or "-"
        new_status = details.get("new_status") or "-"
        return f"Staff mengubah status tamu dari {old_status} ke {new_status}."
    if event_type == "DELETE_GUEST_ROW":
        guest_name = details.get("guest_name") or "tanpa nama"
        return f"Staff menghapus data tamu: {guest_name}."
    return "Staff melakukan aktivitas pada sistem."


# Fungsi untuk mengambil entri log staff hari ini.
def get_today_staff_log_entries(staff):
    log_path = logging_service.get_daily_activity_log_path()
    entries = []
    if not log_path.exists():
        return entries

    try:
        with log_path.open("r", encoding="utf-8") as log_file:
            for line in log_file:
                payload = logging_service.parse_activity_log_line(line.strip())
                if not payload or not is_staff_log_payload(payload, staff):
                    continue
                entries.append(
                    {
                        "time": payload.get("_log_time", ""),
                        "message": format_staff_log_message(payload),
                    }
                )
    except OSError:
        return []

    return entries


# Fungsi untuk membuat redirect tabel tamu staff.
def build_staff_guest_table_redirect():
    query_args = {
        "search": request.form.get("search", ""),
        "page": request.form.get("page", 1),
        "per_page": request.form.get("per_page", 10),
        "sort_by": request.form.get("sort_by", "latest"),
    }
    return redirect(url_for("staff.staff_data", **query_args))
