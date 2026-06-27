from datetime import datetime
import importlib
import ipaddress
import json
import time
import traceback
from uuid import uuid4

from constants import (
    ACTIVITY_LOG_DIR as DEFAULT_ACTIVITY_LOG_DIR,
    ACTIVITY_LOG_FILE_PREFIX as DEFAULT_ACTIVITY_LOG_FILE_PREFIX,
    APP_TIMEZONE,
    LOGIN_ATTEMPT_SESSION_KEY,
    ROLE_STAFF,
    SESSION_TRACKING_ID_KEY,
)
from flask import current_app, g, has_app_context, has_request_context, request, session

ACTIVITY_LOG_DIR = DEFAULT_ACTIVITY_LOG_DIR
ACTIVITY_LOG_FILE_PREFIX = DEFAULT_ACTIVITY_LOG_FILE_PREFIX


# Fungsi untuk mengatur target file log, terutama saat test memakai folder sementara.
def configure_activity_log(log_dir=None, file_prefix=None):
    global ACTIVITY_LOG_DIR, ACTIVITY_LOG_FILE_PREFIX

    if log_dir is not None:
        ACTIVITY_LOG_DIR = log_dir
    if file_prefix is not None:
        ACTIVITY_LOG_FILE_PREFIX = file_prefix


# Fungsi untuk membuat timestamp GMT+7 format ISO-8601 bagi payload JSON log
def get_utc_iso_timestamp():
    return datetime.now(APP_TIMEZONE).replace(microsecond=0).isoformat()


# Fungsi untuk mendapatkan path log harian tunggal
def get_daily_activity_log_path():
    ACTIVITY_LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_date = datetime.now(APP_TIMEZONE).date().isoformat()
    return ACTIVITY_LOG_DIR / f"{ACTIVITY_LOG_FILE_PREFIX}_{log_date}.log"


# Fungsi untuk menghasilkan request id.
def generate_request_id():
    return f"REQ_ID-{uuid4().hex[:12].upper()}"


# Fungsi untuk menghasilkan tracking session id.
def generate_tracking_session_id():
    return f"sess_{uuid4().hex}"


# Fungsi untuk memastikan request saat ini punya request id
def get_request_id():
    if has_request_context():
        request_id = getattr(g, "request_id", None)
        if not request_id:
            request_id = generate_request_id()
            g.request_id = request_id
        return request_id
    return generate_request_id()


# Fungsi untuk mengambil atau membuat session id pelacakan pengguna
def get_tracking_session_id(create=False):
    if not has_request_context():
        return None

    tracking_session_id = session.get(SESSION_TRACKING_ID_KEY) or getattr(g, "tracking_session_id", None)
    if not tracking_session_id and create:
        tracking_session_id = generate_tracking_session_id()
        session[SESSION_TRACKING_ID_KEY] = tracking_session_id

    if tracking_session_id:
        g.tracking_session_id = tracking_session_id

    return tracking_session_id


# Fungsi untuk mengambil IP client.
def get_client_ip():
    return request.remote_addr or "unknown"


# Fungsi untuk mencari lokasi lokasi IP.
def lookup_ip_location(ip_address):
    if not ip_address or ip_address == "unknown":
        return None

    try:
        parsed_ip = ipaddress.ip_address(ip_address)
    except ValueError:
        return None

    if parsed_ip.is_loopback:
        return "Localhost"
    if parsed_ip.is_private:
        return "Private Network"
    if not has_app_context():
        return None

    geoip_db_path = current_app.config.get("GEOIP_DB_PATH")
    if not geoip_db_path:
        return None

    try:
        geoip_database = importlib.import_module("geoip2.database")

        with geoip_database.Reader(geoip_db_path) as reader:
            response = reader.city(ip_address)
            city = response.city.name
            country = response.country.name
            parts = [part for part in (city, country) if part]
            if parts:
                return ", ".join(parts)
    except Exception:
        return None

    return None


# Fungsi untuk mengambil lokasi akun.
def get_account_location(account):
    if has_request_context():
        ip_location = lookup_ip_location(get_client_ip())
        if ip_location:
            return ip_location

    if not account:
        return "Tidak tersedia"

    parts = [part for part in (account.kota, account.provinsi) if part]
    if parts:
        return ", ".join(parts + ["Indonesia"])
    return "Tidak tersedia"


# Fungsi untuk membuat username log bagi aktivitas staff dari object staff aktif.
def get_staff_log_username(staff):
    if not staff:
        return None
    return f"staff:{staff.no_hp}"


# Fungsi inti penulisan log gabungan text + JSON
def write_unified_log(level, category, payload, request_id=None):
    try:
        payload = dict(payload)
        payload.setdefault("timestamp", get_utc_iso_timestamp())
        request_id = request_id or get_request_id()
        log_time = datetime.now(APP_TIMEZONE).strftime("%H:%M:%S")
        json_payload = json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":"))
        log_line = f"[{request_id}] | [{log_time}] | [{level}] | [{category}] | {json_payload}\n"

        with get_daily_activity_log_path().open("a", encoding="utf-8") as log_file:
            log_file.write(log_line)
    except Exception:
        pass


# Fungsi untuk mencatat event akses.
def log_access_event(response):
    started_at = getattr(g, "request_started_at", None)
    response_time_ms = None
    if started_at is not None:
        response_time_ms = int((time.perf_counter() - started_at) * 1000)

    current_staff = getattr(g, "current_staff", None)
    username = get_staff_log_username(current_staff) if current_staff else session.get("user")
    role = ROLE_STAFF if current_staff else session.get("role")

    payload = {
        "client_ip": get_client_ip(),
        "forwarded_for": request.headers.get("X-Forwarded-For"),
        "http_method": request.method,
        "url_path": request.path,
        "status_code": str(response.status_code),
        "response_time_ms": response_time_ms,
        "referrer": request.referrer,
        "user_agent": request.headers.get("User-Agent", ""),
        "client_request_id": request.headers.get("X-Client-Request-ID"),
        "session_id": get_tracking_session_id(),
        "username": username,
        "role": role,
    }
    write_unified_log("INFO", "ACCESS", payload)


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
    if login_attempts is None:
        try:
            login_attempts = int(session.get(LOGIN_ATTEMPT_SESSION_KEY, 0))
        except (TypeError, ValueError):
            login_attempts = 0

    username = account.username if account else identifier or session.get("user")
    email = account.email if account else identifier if identifier and "@" in identifier else None
    role = account.role if account else session.get("role")

    payload = {
        "event_type": event_type,
        "message": message,
        "session_id": get_tracking_session_id(),
        "user_details": {
            "username": username,
            "email": email,
            "ip_address": get_client_ip(),
            "location": get_account_location(account),
            "role": role,
        },
        "security": {
            "login_attempts": login_attempts,
            "is_brute_force_suspicion": bool(is_brute_force_suspicion),
        },
    }
    write_unified_log(level, "AUTH", payload)


# Fungsi untuk mencatat event aktivitas.
def log_activity_event(event_type, details=None, level="INFO", username=None, role=None, session_id=None):
    payload = {
        "event_type": event_type,
        "username": username or session.get("user"),
        "role": role or session.get("role"),
        "session_id": session_id or get_tracking_session_id(),
    }
    if details is not None:
        payload["details"] = details
    write_unified_log(level, "ACTIVITY", payload)


# Fungsi untuk mencatat error sistem.
def log_system_error(error):
    payload = {
        "error_type": error.__class__.__name__,
        "message": str(error),
        "session_id": get_tracking_session_id(),
        "username": session.get("user"),
        "role": session.get("role"),
        "request_context": {
            "url": request.path,
            "method": request.method,
        },
        "stack_trace": "".join(traceback.format_exception(type(error), error, error.__traceback__)),
    }
    write_unified_log("ERROR", "SYS_ERR", payload)


# Fungsi untuk membaca payload JSON dari satu baris log harian
def parse_activity_log_line(line):
    try:
        prefix, json_payload = line.rsplit(" | ", 1)
        payload = json.loads(json_payload)
    except (ValueError, json.JSONDecodeError):
        return None

    parts = [part.strip() for part in prefix.split("|")]
    if len(parts) < 4:
        return None

    payload["_log_time"] = parts[1].strip("[] ")
    payload["_log_category"] = parts[3].strip("[] ")
    return payload
