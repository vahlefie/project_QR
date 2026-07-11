from datetime import datetime, timedelta
from io import BytesIO
import secrets
import struct
from urllib.parse import unquote, urlparse
import zlib

import qrcode
from qrcode.image.svg import SvgPathImage
from sqlalchemy import or_
from constants import (
    APP_TIMEZONE,
    ATTENDANCE_MONTH_ABBREVIATIONS,
    ATTENDANCE_TOKEN_NONCE_BYTES,
    ATTENDANCE_TOKEN_SALT,
    GUEST_ATTENDANCE_QR_PRINT_SIZE_PX,
    GUEST_QR_TOKEN_SALT,
    PACKAGE_PREMIUM,
    ROLE_USER,
    STAFF_SESSION_TIMEOUT_SECONDS,
)
from extensions import db
from flask import current_app, has_request_context, request, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from models import (
    AttendanceVerificationDismissal,
    AttendanceVerificationRequest,
    BillingPayment,
    Guests,
    Staff,
    StaffAccess,
    User,
)
from services import logging_service

ATTENDANCE_REQUEST_PENDING = "pending"
ATTENDANCE_REQUEST_CONFIRMED = "confirmed"
ATTENDANCE_REQUEST_EXPIRED = "expired"
ATTENDANCE_REQUEST_ALREADY_VERIFIED = "already_verified"
ATTENDANCE_REQUEST_NOT_REGISTERED = "not_registered"
ATTENDANCE_REQUEST_TTL_SECONDS = 60
STAFF_NOTIFICATION_AUTO_CLOSE_SECONDS = 10
GUEST_ATTENDANCE_WAITING_MESSAGE = "Harap Tunggu Sebentar, Data Sedang Diverifikasi"
GUEST_ATTENDANCE_EXPIRED_MESSAGE = "Waktu Habis, Nomor Tidak Berhasil Diverifikasi"
GUEST_ATTENDANCE_REJECTED_MESSAGE = "Nomor Tidak Berhasil Diverifikasi, Harap Hubungi Staff"


# Fungsi untuk mengubah nilai menjadi integer dengan default aman.
def parse_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# Fungsi untuk mengambil serializer token kehadiran.
def get_attendance_token_serializer():
    secret_key = current_app.secret_key
    if not secret_key:
        raise RuntimeError("SECRET_KEY aplikasi belum dikonfigurasi.")
    return URLSafeTimedSerializer(secret_key, salt=ATTENDANCE_TOKEN_SALT)


# Fungsi untuk mengambil serializer token QR tamu.
def get_guest_qr_token_serializer():
    secret_key = current_app.secret_key
    if not secret_key:
        raise RuntimeError("SECRET_KEY aplikasi belum dikonfigurasi.")
    return URLSafeTimedSerializer(secret_key, salt=GUEST_QR_TOKEN_SALT)


# Fungsi untuk membuat token kehadiran tamu.
def build_guest_attendance_token(owner_user):
    attendance_token_nonce = getattr(owner_user, "attendance_token_nonce", None)
    if not owner_user or not attendance_token_nonce:
        return ""
    payload = {
        "owner_user_id": owner_user.id,
        "nonce": attendance_token_nonce,
    }
    return get_attendance_token_serializer().dumps(payload)


# Fungsi untuk mengambil pemilik kehadiran dari token.
def get_attendance_owner_from_token(attendance_token):
    staff = get_attendance_staff_from_token(attendance_token)
    return staff.owner if staff else None


# Fungsi untuk membuat token kehadiran publik milik staff.
def build_staff_attendance_token(staff):
    attendance_token_nonce = getattr(staff, "attendance_token_nonce", None)
    if not staff or not attendance_token_nonce:
        return ""
    payload = {
        "scope": "staff_attendance",
        "owner_user_id": staff.owner_user_id,
        "staff_id": staff.id,
        "nonce": attendance_token_nonce,
    }
    return get_attendance_token_serializer().dumps(payload)


# Fungsi untuk mengambil staff pemilik QR dari token kehadiran.
def get_attendance_staff_from_token(attendance_token):
    try:
        payload = get_attendance_token_serializer().loads(attendance_token)
    except (BadSignature, SignatureExpired, TypeError):
        return None

    if not isinstance(payload, dict) or payload.get("scope") != "staff_attendance":
        return None

    owner_user_id = parse_int(payload.get("owner_user_id")) if isinstance(payload, dict) else None
    staff_id = parse_int(payload.get("staff_id")) if isinstance(payload, dict) else None
    token_nonce = payload.get("nonce") if isinstance(payload, dict) else None
    if owner_user_id is None or staff_id is None:
        return None
    staff = Staff.query.filter_by(id=staff_id, owner_user_id=owner_user_id).first()
    owner_user = staff.owner if staff else None
    if (
        not staff
        or staff.is_blocked
        or not owner_user
        or owner_user.role != ROLE_USER
        or not token_nonce
        or token_nonce != staff.attendance_token_nonce
    ):
        return None
    return staff


# Fungsi untuk membuat URL kehadiran tamu.
def build_guest_attendance_url(owner_user):
    if not is_owner_in_active_billing_period(owner_user):
        return ""
    attendance_token = build_guest_attendance_token(owner_user)
    if not attendance_token:
        return ""
    return url_for(
        "attendance.guest_attendance_landing",
        attendance_token=attendance_token,
        _external=True,
    )


# Fungsi untuk membuat URL gambar QR halaman verifikasi kehadiran client.
def build_guest_attendance_qr_url(owner_user):
    if not is_owner_in_active_billing_period(owner_user):
        return ""
    attendance_token = build_guest_attendance_token(owner_user)
    if not attendance_token:
        return ""
    return url_for(
        "attendance.guest_attendance_qr_download",
        attendance_token=attendance_token,
        _external=True,
    )


# Fungsi untuk membuat URL kehadiran publik milik staff.
def build_staff_attendance_url(staff):
    owner_user = getattr(staff, "owner", None)
    if not is_owner_in_active_billing_period(owner_user):
        return ""
    attendance_token = build_staff_attendance_token(staff)
    if not attendance_token:
        return ""
    return url_for(
        "attendance.guest_attendance_landing",
        attendance_token=attendance_token,
        _external=True,
    )


# Fungsi untuk membuat URL download QR kehadiran publik milik staff.
def build_staff_attendance_qr_url(staff):
    owner_user = getattr(staff, "owner", None)
    if not is_owner_in_active_billing_period(owner_user):
        return ""
    attendance_token = build_staff_attendance_token(staff)
    if not attendance_token:
        return ""
    return url_for(
        "attendance.guest_attendance_qr_download",
        attendance_token=attendance_token,
        _external=True,
    )


# Fungsi untuk memeriksa apakah user premium.
def is_premium_user(account):
    return bool(account and str(getattr(account, "paket", "") or "").lower() == PACKAGE_PREMIUM)


# Fungsi untuk mengambil tanggal aplikasi saat ini.
def get_current_app_date():
    return datetime.now(APP_TIMEZONE).date()


# Fungsi untuk mengambil payment verified terbaru milik client.
def get_latest_verified_billing_payment(owner_user):
    if not owner_user:
        return None
    return (
        BillingPayment.query.filter_by(user_id=owner_user.id, status="verified")
        .order_by(BillingPayment.payment_date.desc(), BillingPayment.id.desc())
        .first()
    )


# Fungsi untuk mengambil periode aktif berdasarkan BillingPayment terbaru.
def get_latest_billing_period(owner_user):
    latest_payment = get_latest_verified_billing_payment(owner_user)
    if not latest_payment or not latest_payment.period_start or not latest_payment.period_end:
        return None
    return latest_payment


# Fungsi untuk mengambil nama event publik verifikasi kehadiran.
def get_attendance_event_name(owner_user):
    latest_payment = get_latest_verified_billing_payment(owner_user)
    event_name = str(getattr(latest_payment, "event_name", "") or "").strip() if latest_payment else ""
    return event_name if event_name and event_name.upper() != "N/A" else "Event"


# Fungsi untuk mengecek akses client masih dalam periode payment.
def is_owner_in_active_billing_period(owner_user):
    latest_payment = get_latest_billing_period(owner_user)
    if not latest_payment:
        return False
    today = get_current_app_date()
    return latest_payment.period_start <= today <= latest_payment.period_end


# Fungsi untuk membuat pesan akses periode payment.
def build_inactive_billing_period_message():
    return "Link tidak aktif di luar periode client."


# Fungsi untuk memeriksa apakah QR tamu tersedia.
def is_guest_qr_available(guest):
    owner_user = getattr(guest, "owner", None)
    return bool(guest and guest.user_id and owner_user and owner_user.role == ROLE_USER and is_premium_user(owner_user))


# Fungsi untuk membuat token QR tamu.
def build_guest_qr_token(guest):
    if not is_guest_qr_available(guest):
        return ""
    payload = {
        "scope": "guest_qr",
        "guest_id": guest.id,
        "owner_user_id": guest.user_id,
    }
    return get_guest_qr_token_serializer().dumps(payload)


# Fungsi untuk mengambil tamu dari token QR.
def get_guest_from_qr_token(guest_token):
    try:
        payload = get_guest_qr_token_serializer().loads(guest_token)
    except (BadSignature, SignatureExpired, TypeError):
        return None

    if not isinstance(payload, dict) or payload.get("scope") != "guest_qr":
        return None

    guest_id = parse_int(payload.get("guest_id"))
    owner_user_id = parse_int(payload.get("owner_user_id"))
    if guest_id is None or owner_user_id is None:
        return None

    guest = db.session.get(Guests, guest_id)
    if not guest or guest.user_id != owner_user_id or not is_guest_qr_available(guest):
        return None
    return guest


# Fungsi untuk membuat URL QR tamu.
def build_guest_qr_url(guest):
    owner_user = getattr(guest, "owner", None)
    if not is_owner_in_active_billing_period(owner_user):
        return ""
    guest_token = build_guest_qr_token(guest)
    if not guest_token:
        return ""
    return url_for("attendance.guest_qr_page", guest_token=guest_token, _external=True)


# Fungsi untuk membuat nilai scan QR tamu.
def build_guest_qr_scan_value(guest, guest_token=None):
    guest_token = guest_token or build_guest_qr_token(guest)
    if not guest_token:
        return ""
    return f"{guest.id}{guest.user_id}{guest_token}{guest.no_hp or ''}"


# Fungsi untuk membuat SVG QR tamu.
def build_guest_qr_svg(qr_value):
    qr_image = qrcode.make(qr_value, image_factory=SvgPathImage, box_size=10, border=4)
    output = BytesIO()
    qr_image.save(output)
    return output.getvalue()


# Fungsi untuk membuat chunk PNG.
def build_png_chunk(chunk_type, chunk_data):
    return (
        struct.pack(">I", len(chunk_data))
        + chunk_type
        + chunk_data
        + struct.pack(">I", zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF)
    )


# Fungsi untuk merender matrix QR menjadi PNG RGB tanpa dependency image eksternal.
def build_qr_matrix_png(matrix, target_pixel_size):
    module_count = len(matrix)
    scale = max(1, target_pixel_size // module_count)
    image_size = module_count * scale
    black_pixel = b"\x00\x00\x00"
    white_pixel = b"\xff\xff\xff"
    raw_rows = bytearray()

    for matrix_row in matrix:
        row_pixels = b"".join((black_pixel if cell else white_pixel) * scale for cell in matrix_row)
        png_row = b"\x00" + row_pixels
        for _ in range(scale):
            raw_rows.extend(png_row)

    png_signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", image_size, image_size, 8, 2, 0, 0, 0)
    idat_data = zlib.compress(bytes(raw_rows), 9)
    return (
        png_signature
        + build_png_chunk(b"IHDR", ihdr_data)
        + build_png_chunk(b"IDAT", idat_data)
        + build_png_chunk(b"IEND", b"")
    )


# Fungsi untuk membuat PNG QR halaman verifikasi kehadiran client dengan resolusi siap cetak.
def build_guest_attendance_qr_png(qr_value):
    qr_code = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_Q,
        border=4,
    )
    qr_code.add_data(qr_value)
    qr_code.make(fit=True)
    return build_qr_matrix_png(qr_code.get_matrix(), GUEST_ATTENDANCE_QR_PRINT_SIZE_PX)


# Fungsi untuk mengurai nilai scan QR tamu.
def parse_guest_qr_scan_value(raw_value):
    text = str(raw_value or "").strip()
    if not text:
        return {"token": ""}

    parsed = urlparse(text)
    path = parsed.path if parsed.scheme or parsed.netloc else text
    marker = "/qr/"
    if marker in path:
        return {"token": unquote(path.split(marker, 1)[1].split("/", 1)[0])}

    parts = text.split("+", 3)
    if len(parts) == 4:
        return {
            "guest_id": parse_int(parts[0]),
            "owner_user_id": parse_int(parts[1]),
            "token": parts[2],
            "no_hp": parts[3],
        }

    prefix_end = next((index for index, character in enumerate(text) if not character.isdigit()), None)
    if prefix_end:
        prefix = text[:prefix_end]
        max_suffix_length = min(20, len(text) - prefix_end)
        for suffix_length in range(max_suffix_length + 1):
            token_end = len(text) - suffix_length if suffix_length else len(text)
            suffix = text[token_end:]
            if suffix and not suffix.isdigit():
                continue

            guest_token = text[prefix_end:token_end]
            guest = get_guest_from_qr_token(guest_token)
            if guest and prefix == f"{guest.id}{guest.user_id}" and suffix == str(guest.no_hp or ""):
                return {
                    "guest_id": guest.id,
                    "owner_user_id": guest.user_id,
                    "token": guest_token,
                    "no_hp": suffix,
                }

    return {"token": text}


# Fungsi untuk mengekstrak token QR tamu.
def extract_guest_qr_token(raw_value):
    return parse_guest_qr_scan_value(raw_value).get("token", "")


# Fungsi untuk memformat waktu pembuatan token kehadiran.
def format_attendance_token_generated_at(value):
    if not value:
        return "Belum pernah dibuat"
    return value.strftime("%Y-%m-%d %H:%M:%S")


# Fungsi untuk menghasilkan URL kehadiran tamu.
def generate_guest_attendance_url(owner_user):
    owner_user.attendance_token_nonce = secrets.token_urlsafe(ATTENDANCE_TOKEN_NONCE_BYTES)
    owner_user.attendance_token_generated_at = datetime.now(APP_TIMEZONE).replace(tzinfo=None, microsecond=0)
    db.session.commit()
    return build_guest_attendance_url(owner_user)


# Fungsi untuk menghasilkan URL kehadiran tamu yang melekat pada staff.
def generate_staff_attendance_url(staff):
    staff.attendance_token_nonce = secrets.token_urlsafe(ATTENDANCE_TOKEN_NONCE_BYTES)
    staff.attendance_token_generated_at = datetime.now(APP_TIMEZONE).replace(tzinfo=None, microsecond=0)
    db.session.commit()
    return build_staff_attendance_url(staff)


# Fungsi untuk memformat waktu kehadiran.
def format_attendance_time(value):
    if not value:
        return ""
    month_name = ATTENDANCE_MONTH_ABBREVIATIONS[value.month - 1]
    return f"{value.day:02d}-{month_name} {value.strftime('%H:%M')}"


# Fungsi untuk mencatat event kehadiran.
def log_attendance_event(event_type, owner_user=None, guest=None, no_hp=None, level="INFO", details=None):
    payload = {
        "event_type": event_type,
        "owner_user_id": owner_user.id if owner_user else None,
        "owner_username": owner_user.username if owner_user else None,
        "guest_id": guest.id if guest else None,
        "guest_name": guest.nama if guest else None,
        "no_hp": no_hp,
        "client_ip": logging_service.get_client_ip() if has_request_context() else None,
        "user_agent": request.headers.get("User-Agent", "") if has_request_context() else None,
        "client_request_id": request.headers.get("X-Client-Request-ID") if has_request_context() else None,
        "session_id": logging_service.get_tracking_session_id() if has_request_context() else None,
    }
    if details is not None:
        payload["details"] = details
    logging_service.write_unified_log(level, "ATTENDANCE", payload)


# Fungsi untuk mencari tamu berdasarkan nomor HP untuk kehadiran.
def find_attendance_guests(owner_user, no_hp):
    if not owner_user or not no_hp:
        return []
    return Guests.query.filter_by(user_id=owner_user.id, no_hp=no_hp).order_by(Guests.id.asc()).all()


# Fungsi untuk mengambil waktu saat ini tanpa timezone.
def get_current_naive_datetime():
    return datetime.now(APP_TIMEZONE).replace(tzinfo=None, microsecond=0)


# Fungsi untuk mengubah request verifikasi yang sudah lewat TTL menjadi expired.
def expire_stale_attendance_requests(owner_user_id=None):
    now = get_current_naive_datetime()
    query = AttendanceVerificationRequest.query.filter(
        AttendanceVerificationRequest.status.in_(
            (
                ATTENDANCE_REQUEST_PENDING,
                ATTENDANCE_REQUEST_ALREADY_VERIFIED,
                ATTENDANCE_REQUEST_NOT_REGISTERED,
            )
        ),
        AttendanceVerificationRequest.expires_at.isnot(None),
        AttendanceVerificationRequest.expires_at <= now,
    )
    if owner_user_id is not None:
        query = query.filter(AttendanceVerificationRequest.owner_user_id == owner_user_id)

    requests = query.all()
    for verification_request in requests:
        verification_request.status = ATTENDANCE_REQUEST_EXPIRED

    if requests:
        db.session.commit()
    return len(requests)


# Fungsi untuk mencari request verifikasi yang masih aktif.
def find_active_attendance_request(owner_user, no_hp=None, guest_id=None, target_staff=None):
    if not owner_user:
        return None
    expire_stale_attendance_requests(owner_user.id)
    query = AttendanceVerificationRequest.query.filter(
        AttendanceVerificationRequest.owner_user_id == owner_user.id,
        AttendanceVerificationRequest.status.in_(
            (
                ATTENDANCE_REQUEST_PENDING,
                ATTENDANCE_REQUEST_ALREADY_VERIFIED,
                ATTENDANCE_REQUEST_NOT_REGISTERED,
            )
        ),
        AttendanceVerificationRequest.expires_at > get_current_naive_datetime(),
    )
    if target_staff is not None:
        query = query.filter(AttendanceVerificationRequest.target_staff_id == target_staff.id)
    if guest_id is not None:
        query = query.filter(AttendanceVerificationRequest.guest_id == guest_id)
    elif no_hp:
        query = query.filter(AttendanceVerificationRequest.no_hp == no_hp)
    else:
        return None
    return query.order_by(AttendanceVerificationRequest.id.desc()).first()


# Fungsi untuk membuat pesan notifikasi staff.
def build_staff_notification_message(status, no_hp, guest=None):
    display_no_hp = no_hp or getattr(guest, "no_hp", "") or "-"
    if status == ATTENDANCE_REQUEST_ALREADY_VERIFIED:
        return f"Nomor {display_no_hp} Sudah Terverifikasi."
    if status == ATTENDANCE_REQUEST_NOT_REGISTERED:
        return f"Nomor {display_no_hp} Tidak Teridentifikasi."
    guest_name = getattr(guest, "nama", "") or "Tamu"
    return f"Verifikasi kehadiran Bpk/Ibu {guest_name}."


# Fungsi untuk membuat request verifikasi staff.
def create_attendance_verification_request(
    owner_user, guest=None, no_hp=None, status=ATTENDANCE_REQUEST_PENDING, source="phone", target_staff=None
):
    now = get_current_naive_datetime()
    ttl_seconds = (
        STAFF_NOTIFICATION_AUTO_CLOSE_SECONDS
        if status in {ATTENDANCE_REQUEST_ALREADY_VERIFIED, ATTENDANCE_REQUEST_NOT_REGISTERED}
        else ATTENDANCE_REQUEST_TTL_SECONDS
    )
    verification_request = AttendanceVerificationRequest()
    verification_request.owner_user_id = owner_user.id
    verification_request.target_staff_id = target_staff.id if target_staff else None
    verification_request.guest_id = guest.id if guest else None
    verification_request.no_hp = no_hp or getattr(guest, "no_hp", None)
    verification_request.status = status
    verification_request.source = source
    verification_request.message = build_staff_notification_message(status, verification_request.no_hp, guest)
    verification_request.created_at = now
    verification_request.expires_at = now + timedelta(seconds=ttl_seconds)
    db.session.add(verification_request)
    db.session.flush()
    AttendanceVerificationDismissal.query.filter_by(request_id=verification_request.id).delete()
    db.session.commit()
    return verification_request


# Fungsi untuk membuat respons ketika request aktif masih menunggu staff.
def build_pending_retry_response():
    return {
        "status": "pending_retry",
        "message": "Silahkan dicoba kembali setelah beberapa saat lagi",
    }


# Fungsi untuk menormalisasi jumlah orang dari popup staff.
def normalize_attendance_guest_count(value):
    guest_count = parse_int(value, default=1)
    if guest_count < 1 or guest_count > 9:
        return 1
    return guest_count


# Fungsi untuk membuat pesan selamat datang halaman verifikasi nomor HP tamu.
def build_phone_attendance_welcome_message(guest):
    guest_name = getattr(guest, "nama", "") or "Tamu"
    return f"Selamat Datang Bpk/Ibu {guest_name}"


# Fungsi untuk mengambil status request verifikasi tamu publik.
def get_guest_attendance_verification_status(owner_user, request_id, target_staff=None):
    if not owner_user:
        return {
            "status": "not_found",
            "message": "Request verifikasi tidak ditemukan.",
        }

    expire_stale_attendance_requests(owner_user.id)
    verification_request = db.session.get(AttendanceVerificationRequest, request_id)
    if not verification_request or verification_request.owner_user_id != owner_user.id:
        return {
            "status": "not_found",
            "message": "Request verifikasi tidak ditemukan.",
        }
    if target_staff is not None and verification_request.target_staff_id != target_staff.id:
        return {
            "status": "not_found",
            "message": "Request verifikasi tidak ditemukan.",
        }

    expires_in_seconds = 0
    if verification_request.expires_at:
        expires_in_seconds = max(
            int((verification_request.expires_at - get_current_naive_datetime()).total_seconds()),
            0,
        )

    if verification_request.status == ATTENDANCE_REQUEST_PENDING:
        return {
            "status": "pending",
            "request_id": verification_request.id,
            "message": GUEST_ATTENDANCE_WAITING_MESSAGE,
            "expires_in_seconds": expires_in_seconds,
        }

    if verification_request.status == ATTENDANCE_REQUEST_CONFIRMED:
        return {
            "status": "confirmed",
            "request_id": verification_request.id,
            "guest_name": verification_request.guest.nama if verification_request.guest else "",
            "attendance_time": format_attendance_time(verification_request.confirmed_at),
            "message": build_phone_attendance_welcome_message(verification_request.guest),
        }

    if verification_request.status == ATTENDANCE_REQUEST_EXPIRED:
        message = (
            GUEST_ATTENDANCE_REJECTED_MESSAGE
            if verification_request.message == GUEST_ATTENDANCE_REJECTED_MESSAGE
            else GUEST_ATTENDANCE_EXPIRED_MESSAGE
        )
        return {
            "status": "expired",
            "request_id": verification_request.id,
            "message": message,
        }

    return {
        "status": verification_request.status,
        "request_id": verification_request.id,
        "message": verification_request.message or "Data selesai diperiksa.",
        "expires_in_seconds": expires_in_seconds,
    }


# Fungsi untuk mengambil id staff aktif milik client.
def get_active_staff_ids_for_owner(owner_user_id):
    now = get_current_naive_datetime()
    active_staff_ids = []
    staff_accesses = (
        StaffAccess.query.join(Staff)
        .filter(
            Staff.owner_user_id == owner_user_id,
            Staff.is_blocked.is_(False),
            StaffAccess.is_active.is_(True),
            StaffAccess.revoked_at.is_(None),
        )
        .all()
    )

    for staff_access in staff_accesses:
        activity_time = staff_access.last_activity_at or staff_access.created_at
        if activity_time and (now - activity_time).total_seconds() <= STAFF_SESSION_TIMEOUT_SECONDS:
            active_staff_ids.append(staff_access.staff_id)

    return sorted(set(active_staff_ids))


# Fungsi untuk mengecek apakah semua staff aktif sudah menolak request.
def have_all_active_staff_rejected(verification_request):
    if verification_request.target_staff_id:
        return bool(
            AttendanceVerificationDismissal.query.filter_by(
                request_id=verification_request.id,
                staff_id=verification_request.target_staff_id,
            )
            .filter(AttendanceVerificationDismissal.dismissed_at >= verification_request.created_at)
            .first()
        )

    active_staff_ids = set(get_active_staff_ids_for_owner(verification_request.owner_user_id))
    if not active_staff_ids:
        return False
    dismissed_staff_ids = {
        dismissal.staff_id
        for dismissal in AttendanceVerificationDismissal.query.filter_by(request_id=verification_request.id)
        .filter(AttendanceVerificationDismissal.dismissed_at >= verification_request.created_at)
        .all()
    }
    return active_staff_ids.issubset(dismissed_staff_ids)


# Fungsi untuk membuat payload popup staff.
def build_staff_notification_payload(verification_request):
    if not verification_request:
        return None

    guest = verification_request.guest
    expires_in_seconds = 0
    if verification_request.expires_at:
        expires_in_seconds = max(
            int((verification_request.expires_at - get_current_naive_datetime()).total_seconds()),
            0,
        )

    return {
        "id": verification_request.id,
        "target_staff_id": verification_request.target_staff_id,
        "status": verification_request.status,
        "source": verification_request.source,
        "message": verification_request.message,
        "no_hp": verification_request.no_hp or "",
        "expires_in_seconds": expires_in_seconds,
        "auto_close_seconds": (
            STAFF_NOTIFICATION_AUTO_CLOSE_SECONDS
            if verification_request.status in {ATTENDANCE_REQUEST_ALREADY_VERIFIED, ATTENDANCE_REQUEST_NOT_REGISTERED}
            else None
        ),
        "guest": {
            "id": guest.id if guest else None,
            "nama": guest.nama if guest else "",
            "no_hp": guest.no_hp if guest else verification_request.no_hp or "",
            "email": guest.email if guest else "",
            "status": guest.status if guest else "",
            "jumlah_orang": (
                normalize_attendance_guest_count(getattr(guest, "jumlah_orang", 1))
                if guest
                else 1
            ),
        },
    }


# Fungsi untuk mengambil notifikasi aktif untuk satu staff.
def get_staff_attendance_notification(staff):
    if not staff:
        return None

    expire_stale_attendance_requests(staff.owner_user_id)
    dismissed_request_ids = [
        dismissal.request_id
        for dismissal in AttendanceVerificationDismissal.query.join(
            AttendanceVerificationRequest,
            AttendanceVerificationDismissal.request_id == AttendanceVerificationRequest.id,
        )
        .filter(
            AttendanceVerificationDismissal.staff_id == staff.id,
            AttendanceVerificationRequest.owner_user_id == staff.owner_user_id,
            AttendanceVerificationDismissal.dismissed_at >= AttendanceVerificationRequest.created_at,
        )
        .all()
    ]
    query = AttendanceVerificationRequest.query.filter(
        AttendanceVerificationRequest.owner_user_id == staff.owner_user_id,
        or_(
            AttendanceVerificationRequest.target_staff_id == staff.id,
            AttendanceVerificationRequest.target_staff_id.is_(None),
        ),
        AttendanceVerificationRequest.status.in_(
            (
                ATTENDANCE_REQUEST_PENDING,
                ATTENDANCE_REQUEST_ALREADY_VERIFIED,
                ATTENDANCE_REQUEST_NOT_REGISTERED,
            )
        ),
        AttendanceVerificationRequest.expires_at > get_current_naive_datetime(),
    )
    if dismissed_request_ids:
        query = query.filter(AttendanceVerificationRequest.id.notin_(dismissed_request_ids))

    return build_staff_notification_payload(query.order_by(AttendanceVerificationRequest.id.asc()).first())


# Fungsi untuk menolak/menutup request verifikasi untuk staff tertentu.
def reject_attendance_verification_request(staff, request_id):
    verification_request = db.session.get(AttendanceVerificationRequest, request_id)
    if not staff or not verification_request or verification_request.owner_user_id != staff.owner_user_id:
        return {"status": "not_found", "message": "Request verifikasi tidak ditemukan."}
    if verification_request.target_staff_id and verification_request.target_staff_id != staff.id:
        return {"status": "not_found", "message": "Request verifikasi tidak ditemukan."}

    expire_stale_attendance_requests(staff.owner_user_id)
    if verification_request.status == ATTENDANCE_REQUEST_EXPIRED:
        return {"status": "expired", "message": "Request verifikasi sudah expired."}

    dismissed_at = get_current_naive_datetime()
    existing_dismissal = AttendanceVerificationDismissal.query.filter_by(
        request_id=verification_request.id,
        staff_id=staff.id,
    ).first()
    if not existing_dismissal:
        dismissal = AttendanceVerificationDismissal()
        dismissal.request_id = verification_request.id
        dismissal.staff_id = staff.id
        dismissal.dismissed_at = dismissed_at
        db.session.add(dismissal)
        db.session.flush()
    elif existing_dismissal.dismissed_at < verification_request.created_at:
        existing_dismissal.dismissed_at = dismissed_at

    if have_all_active_staff_rejected(verification_request):
        verification_request.status = ATTENDANCE_REQUEST_EXPIRED
        verification_request.message = GUEST_ATTENDANCE_REJECTED_MESSAGE

    db.session.commit()
    return {"status": "rejected", "message": "Request verifikasi ditutup."}


# Fungsi untuk mengonfirmasi request verifikasi dan mengisi kehadiran.
def confirm_attendance_verification_request(staff, request_id, jumlah_orang=1):
    verification_request = db.session.get(AttendanceVerificationRequest, request_id)
    if not staff or not verification_request or verification_request.owner_user_id != staff.owner_user_id:
        return {"status": "not_found", "message": "Request verifikasi tidak ditemukan."}
    if verification_request.target_staff_id and verification_request.target_staff_id != staff.id:
        return {"status": "not_found", "message": "Request verifikasi tidak ditemukan."}

    expire_stale_attendance_requests(staff.owner_user_id)
    if verification_request.status == ATTENDANCE_REQUEST_EXPIRED:
        return {"status": "expired", "message": "Request verifikasi sudah expired."}
    if verification_request.status != ATTENDANCE_REQUEST_PENDING:
        return {"status": verification_request.status, "message": verification_request.message}

    guest = verification_request.guest
    if not guest:
        verification_request.status = ATTENDANCE_REQUEST_NOT_REGISTERED
        verification_request.message = build_staff_notification_message(
            ATTENDANCE_REQUEST_NOT_REGISTERED,
            verification_request.no_hp,
        )
        db.session.commit()
        return {"status": "not_registered", "message": verification_request.message}

    if guest.kehadiran:
        verification_request.status = ATTENDANCE_REQUEST_ALREADY_VERIFIED
        verification_request.message = build_staff_notification_message(
            ATTENDANCE_REQUEST_ALREADY_VERIFIED,
            guest.no_hp,
            guest,
        )
        db.session.commit()
        return {"status": "already_verified", "message": verification_request.message}

    staff_name = staff.nama or staff.no_hp
    guest_count = normalize_attendance_guest_count(jumlah_orang)
    guest.kehadiran = get_current_naive_datetime()
    guest.jumlah_orang = guest_count
    guest.verified_by_staff_id = staff.id
    guest.verified_by_staff_name = staff_name
    verification_request.status = ATTENDANCE_REQUEST_CONFIRMED
    verification_request.confirmed_at = guest.kehadiran
    verification_request.confirmed_by_staff_id = staff.id
    verification_request.confirmed_by_staff_name = staff_name
    db.session.commit()

    attendance_time = format_attendance_time(guest.kehadiran)
    log_attendance_event(
        "GUEST_ATTENDANCE_CONFIRMED_BY_STAFF",
        owner_user=verification_request.owner,
        guest=guest,
        no_hp=guest.no_hp,
        details={
            "kehadiran": attendance_time,
            "staff_id": staff.id,
            "staff_name": staff_name,
            "source": verification_request.source,
            "jumlah_orang": guest_count,
        },
    )
    return {
        "status": "confirmed",
        "guest_name": guest.nama,
        "attendance_time": attendance_time,
        "jumlah_orang": guest_count,
        "verified_by": staff_name,
        "message": f"Kehadiran {guest.nama} berhasil diverifikasi.",
    }


# Fungsi untuk membuat pesan QR yang sudah terverifikasi.
def build_qr_already_verified_message():
    return "Kode QR Sudah Terverifikasi Sebelumnya.\nHarap Hubungi Staff Reservasi Jika Terdapat Kendala."


# Fungsi untuk membuat pesan selamat datang QR.
def build_qr_welcome_message(guest):
    return f"Selamat Datang Bpk/Ibu {guest.nama}.\nTerima Kasih Atas Kehadiran dan Partisipasinya."


# Fungsi untuk memverifikasi kehadiran QR tamu.
def verify_guest_qr_attendance(owner_user, raw_qr_value):
    if not is_premium_user(owner_user):
        return {
            "status": "forbidden",
            "message": "Fitur Scan hanya tersedia untuk paket Premium.",
        }
    if not is_owner_in_active_billing_period(owner_user):
        return {
            "status": "inactive_period",
            "message": build_inactive_billing_period_message(),
        }

    scan_payload = parse_guest_qr_scan_value(raw_qr_value)
    guest_token = scan_payload.get("token", "")
    guest = get_guest_from_qr_token(guest_token)
    has_scan_metadata = any(key in scan_payload for key in ("guest_id", "owner_user_id", "no_hp"))
    metadata_matches = False
    if guest:
        metadata_matches = not has_scan_metadata or (
            scan_payload.get("guest_id") == guest.id
            and scan_payload.get("owner_user_id") == guest.user_id
            and str(scan_payload.get("no_hp", "")) == str(guest.no_hp or "")
        )

    if not guest or guest.user_id != owner_user.id or not metadata_matches:
        display_no_hp = str(scan_payload.get("no_hp") or "").strip()
        if display_no_hp:
            active_request = find_active_attendance_request(owner_user, no_hp=display_no_hp)
            if active_request:
                return build_pending_retry_response()
            verification_request = create_attendance_verification_request(
                owner_user,
                no_hp=display_no_hp,
                status=ATTENDANCE_REQUEST_NOT_REGISTERED,
                source="qr",
            )
        log_attendance_event(
            "GUEST_QR_ATTENDANCE_INVALID",
            owner_user=owner_user,
            no_hp=None,
            level="WARN",
            details={"token_prefix": guest_token[:12], "has_metadata": has_scan_metadata},
        )
        return {
            "status": "invalid_qr",
            "verification_request_id": verification_request.id if display_no_hp else None,
            "message": "Kode QR tidak valid.",
        }

    if guest.kehadiran:
        active_request = find_active_attendance_request(owner_user, guest_id=guest.id)
        if active_request:
            return build_pending_retry_response()
        verification_request = create_attendance_verification_request(
            owner_user,
            guest=guest,
            no_hp=guest.no_hp,
            status=ATTENDANCE_REQUEST_ALREADY_VERIFIED,
            source="qr",
        )
        log_attendance_event(
            "GUEST_QR_ATTENDANCE_ALREADY_VERIFIED",
            owner_user=owner_user,
            guest=guest,
            no_hp=guest.no_hp,
            level="WARN",
            details={"kehadiran": format_attendance_time(guest.kehadiran)},
        )
        return {
            "status": "already_verified",
            "verification_request_id": verification_request.id,
            "guest_name": guest.nama,
            "attendance_time": format_attendance_time(guest.kehadiran),
            "message": build_qr_already_verified_message(),
        }

    active_request = find_active_attendance_request(owner_user, guest_id=guest.id)
    if active_request:
        return build_pending_retry_response()

    verification_request = create_attendance_verification_request(
        owner_user,
        guest=guest,
        no_hp=guest.no_hp,
        status=ATTENDANCE_REQUEST_PENDING,
        source="qr",
    )
    log_attendance_event(
        "GUEST_QR_ATTENDANCE_PENDING_STAFF_CONFIRMATION",
        owner_user=owner_user,
        guest=guest,
        no_hp=guest.no_hp,
        details={"verification_request_id": verification_request.id},
    )
    return {
        "status": "pending_confirmation",
        "verification_request_id": verification_request.id,
        "guest_name": guest.nama,
        "message": "Menunggu konfirmasi staff.",
    }


# Fungsi untuk memverifikasi kehadiran tamu.
def verify_guest_attendance(owner_user, raw_no_hp, clean_phone_func, target_staff=None):
    if not is_owner_in_active_billing_period(owner_user):
        return {
            "status": "inactive_period",
            "message": build_inactive_billing_period_message(),
        }

    normalized_no_hp = clean_phone_func(raw_no_hp)
    display_no_hp = normalized_no_hp or str(raw_no_hp or "").strip()
    guests = find_attendance_guests(owner_user, normalized_no_hp)

    if not normalized_no_hp or not guests:
        active_request = find_active_attendance_request(owner_user, no_hp=display_no_hp, target_staff=target_staff)
        if active_request:
            return build_pending_retry_response()
        verification_request = create_attendance_verification_request(
            owner_user,
            no_hp=display_no_hp,
            status=ATTENDANCE_REQUEST_NOT_REGISTERED,
            source="phone",
            target_staff=target_staff,
        )
        log_attendance_event(
            "GUEST_ATTENDANCE_NOT_FOUND",
            owner_user=owner_user,
            no_hp=display_no_hp,
            level="WARN",
        )
        return {
            "status": "not_registered",
            "verification_request_id": verification_request.id,
            "no_hp": display_no_hp,
            "message": f"Nomor {display_no_hp} Tidak Terdaftar.\nHarap Hubungi Staff Reservasi",
        }

    guest_to_verify = next((guest for guest in guests if not guest.kehadiran), None)
    if not guest_to_verify:
        active_request = find_active_attendance_request(owner_user, no_hp=normalized_no_hp, target_staff=target_staff)
        if active_request:
            return build_pending_retry_response()
        verification_request = create_attendance_verification_request(
            owner_user,
            guest=guests[0],
            no_hp=normalized_no_hp,
            status=ATTENDANCE_REQUEST_ALREADY_VERIFIED,
            source="phone",
            target_staff=target_staff,
        )
        log_attendance_event(
            "GUEST_ATTENDANCE_ALREADY_VERIFIED",
            owner_user=owner_user,
            guest=guests[0],
            no_hp=normalized_no_hp,
            level="WARN",
            details={"kehadiran": format_attendance_time(guests[0].kehadiran)},
        )
        return {
            "status": "already_verified",
            "verification_request_id": verification_request.id,
            "no_hp": normalized_no_hp,
            "message": f"Nomor {normalized_no_hp} Sudah Terverifikasi.\nHarap Hubungi Staff Reservasi",
        }

    active_request = find_active_attendance_request(owner_user, guest_id=guest_to_verify.id, target_staff=target_staff)
    if active_request:
        return build_pending_retry_response()

    verification_request = create_attendance_verification_request(
        owner_user,
        guest=guest_to_verify,
        no_hp=normalized_no_hp,
        status=ATTENDANCE_REQUEST_PENDING,
        source="phone",
        target_staff=target_staff,
    )
    log_attendance_event(
        "GUEST_ATTENDANCE_PENDING_STAFF_CONFIRMATION",
        owner_user=owner_user,
        guest=guest_to_verify,
        no_hp=normalized_no_hp,
        details={
            "verification_request_id": verification_request.id,
            "target_staff_id": target_staff.id if target_staff else None,
        },
    )
    return {
        "status": "pending_confirmation",
        "verification_request_id": verification_request.id,
        "no_hp": normalized_no_hp,
        "guest_name": guest_to_verify.nama,
        "message": "Menunggu konfirmasi staff.",
    }
