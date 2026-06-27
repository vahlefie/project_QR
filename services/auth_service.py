from datetime import datetime, timedelta
import hashlib
import secrets
import time

from constants import (
    ADMIN_PASSWORD_PATTERN,
    ADMIN_PASSWORD_TITLE,
    APP_TIMEZONE,
    BRUTE_FORCE_ATTEMPT_THRESHOLD,
    LOGIN_FAILURE_WINDOW_SECONDS,
    LOGIN_LOCKOUT_SECONDS,
    ROLE_USER,
    SESSION_ACTIVE_TOKEN_KEY,
    SESSION_LAST_ACTIVITY_KEY,
    SESSION_TIMEOUT_SECONDS,
    SESSION_TRACKING_ID_KEY,
    USER_PASSWORD_PATTERN,
    USER_PASSWORD_TITLE,
)
from extensions import db
from flask import session
from models import LoginThrottle, User
from services import logging_service
from werkzeug.security import check_password_hash, generate_password_hash


# Fungsi untuk mengambil waktu aplikasi tanpa timezone.
def get_utc_naive_datetime():
    return datetime.now(APP_TIMEZONE).replace(tzinfo=None)


# Fungsi untuk mengambil timestamp sesi saat ini.
def get_current_timestamp():
    return int(time.time())


# Fungsi untuk mengubah nilai menjadi integer dengan default aman.
def parse_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# Fungsi untuk menormalkan identifier login.
def normalize_login_identifier(identifier):
    normalized_identifier = (identifier or "").strip().lower()
    return normalized_identifier or "anonymous"


# Fungsi untuk membuat key login throttle.
def build_login_throttle_key(identifier, ip_address):
    raw_key = f"{ip_address}|{normalize_login_identifier(identifier)}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


# Fungsi untuk mencari login throttle.
def find_login_throttle(identifier, ip_address=None):
    ip_address = ip_address or logging_service.get_client_ip()
    scope_key = build_login_throttle_key(identifier, ip_address)
    return LoginThrottle.query.filter_by(scope_key=scope_key).first()


# Fungsi untuk memeriksa apakah login throttle sedang terkunci.
def is_login_throttle_locked(throttle):
    return bool(throttle and throttle.locked_until and throttle.locked_until > get_utc_naive_datetime())


# Fungsi untuk mengambil sisa detik lockout login.
def get_login_lockout_remaining_seconds(throttle):
    if not is_login_throttle_locked(throttle):
        return 0
    return max(int((throttle.locked_until - get_utc_naive_datetime()).total_seconds()), 0)


# Fungsi untuk mendaftarkan login gagal.
def register_failed_login(identifier, ip_address=None):
    ip_address = ip_address or logging_service.get_client_ip()
    scope_key = build_login_throttle_key(identifier, ip_address)
    throttle = LoginThrottle.query.filter_by(scope_key=scope_key).first()
    now = get_utc_naive_datetime()

    if not throttle:
        throttle = LoginThrottle()
        throttle.scope_key = scope_key
        throttle.identifier = normalize_login_identifier(identifier)[:255]
        throttle.ip_address = ip_address[:45]
        throttle.failed_attempts = 0
        db.session.add(throttle)

    window_expired = (
        throttle.first_failed_at is None
        or (now - throttle.first_failed_at).total_seconds() > LOGIN_FAILURE_WINDOW_SECONDS
    )
    if window_expired and not is_login_throttle_locked(throttle):
        throttle.failed_attempts = 0
        throttle.first_failed_at = now
        throttle.locked_until = None

    throttle.identifier = normalize_login_identifier(identifier)[:255]
    throttle.ip_address = ip_address[:45]
    throttle.failed_attempts += 1
    throttle.last_failed_at = now

    if not throttle.first_failed_at:
        throttle.first_failed_at = now

    if throttle.failed_attempts >= BRUTE_FORCE_ATTEMPT_THRESHOLD:
        throttle.locked_until = now + timedelta(seconds=LOGIN_LOCKOUT_SECONDS)

    db.session.commit()
    return throttle


# Fungsi untuk membersihkan login throttle.
def clear_login_throttle(identifier, ip_address=None):
    throttle = find_login_throttle(identifier, ip_address)
    if throttle:
        db.session.delete(throttle)
        db.session.commit()


# Fungsi untuk memulai login sesi.
def start_login_session(user):
    tracking_session_id = logging_service.get_tracking_session_id(create=True)
    active_session_token = secrets.token_urlsafe(32)
    user.active_session_token = active_session_token
    db.session.commit()

    session.clear()
    session.permanent = False
    session[SESSION_TRACKING_ID_KEY] = tracking_session_id or logging_service.generate_tracking_session_id()
    session[SESSION_ACTIVE_TOKEN_KEY] = active_session_token
    session["user"] = user.username
    session["role"] = user.role
    session[SESSION_LAST_ACTIVITY_KEY] = get_current_timestamp()


# Fungsi untuk menyegarkan login sesi aktivitas.
def refresh_login_session_activity():
    session[SESSION_LAST_ACTIVITY_KEY] = get_current_timestamp()


# Fungsi untuk memeriksa apakah login sesi kedaluwarsa.
def is_login_session_expired():
    last_activity = parse_int(session.get(SESSION_LAST_ACTIVITY_KEY))
    if last_activity is None:
        return True
    return get_current_timestamp() - last_activity > SESSION_TIMEOUT_SECONDS


# Fungsi untuk mengakhiri login sesi.
def end_login_session(cleanup_callback=None):
    if cleanup_callback:
        cleanup_callback()
    session.clear()


# Fungsi untuk memeriksa apakah saat ini login sesi aktif.
def is_current_login_session_active():
    username = session.get("user")
    session_token = session.get(SESSION_ACTIVE_TOKEN_KEY)
    if not username or not session_token:
        return False

    user = User.query.filter_by(username=username).first()
    if not user:
        return False

    return user.active_session_token == session_token


# Fungsi untuk membersihkan sesi login aktif milik user saat ini.
def clear_active_login_session_for_current_user():
    username = session.get("user")
    session_token = session.get(SESSION_ACTIVE_TOKEN_KEY)
    if not username or not session_token:
        return

    user = User.query.filter_by(username=username).first()
    if user and user.active_session_token == session_token:
        user.active_session_token = None
        db.session.commit()


# Fungsi untuk memeriksa kepemilikan huruf besar, huruf kecil, dan angka.
def has_upper_lower_number(password):
    has_upper = any(character.isupper() for character in password)
    has_lower = any(character.islower() for character in password)
    has_number = any(character.isdigit() for character in password)
    return len(password) >= 8 and has_upper and has_lower and has_number


# Fungsi untuk memeriksa apakah format password user valid.
def is_valid_user_password_format(password):
    return has_upper_lower_number(password)


# Fungsi untuk memeriksa apakah format password admin valid.
def is_valid_admin_password_format(password):
    has_special = any(not character.isalnum() for character in password)
    return has_upper_lower_number(password) and has_special


# Fungsi untuk memeriksa apakah password valid sesuai role.
def is_valid_password_for_role(password, role):
    if role == ROLE_USER:
        return is_valid_user_password_format(password)
    return is_valid_admin_password_format(password)


# Fungsi untuk mengambil pola password sesuai role.
def get_password_pattern_for_role(role):
    if role == ROLE_USER:
        return USER_PASSWORD_PATTERN
    return ADMIN_PASSWORD_PATTERN


# Fungsi untuk mengambil teks bantuan password sesuai role.
def get_password_title_for_role(role):
    if role == ROLE_USER:
        return USER_PASSWORD_TITLE
    return ADMIN_PASSWORD_TITLE


# Fungsi untuk memeriksa password pencocokan.
def password_matches(stored_password, password):
    if not stored_password:
        return False
    if stored_password == password:
        return True

    try:
        return check_password_hash(stored_password, password)
    except ValueError:
        return stored_password == password


# Fungsi untuk mengatur password akun.
def set_account_password(account, password):
    account.password = generate_password_hash(password)


# Fungsi untuk mengambil user saat ini.
def get_current_user():
    username = session.get("user")
    if not username:
        return None
    return User.query.filter_by(username=username).first()
