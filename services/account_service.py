from datetime import date, datetime, timedelta

from constants import ADMIN_PASSWORD_TITLE, NAME_PATTERN, ROLE_ADMIN, ROLE_USER, USERNAME_PATTERN, USER_PASSWORD_TITLE
from extensions import db
from flask import session
from models import BillingPayment, User
from services import auth_service


# Fungsi untuk menormalkan nomor HP.
def normalize_phone_number(no_hp_text):
    digits = no_hp_text.strip()
    if not digits or not digits.isdigit():
        return ""
    if len(digits) < 8:
        return ""
    if digits.startswith("62"):
        return digits
    if digits.startswith("08"):
        return f"62{digits[1:]}"
    if digits.startswith("8"):
        return f"62{digits}"
    return ""


# Fungsi untuk memeriksa apakah format email valid.
def is_valid_email_format(email):
    return "@" in email and "." in email


# Fungsi untuk mengurai iso date.
def parse_iso_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


# Fungsi untuk mengambil tanggal minimal periode akhir.
def get_min_period_end_date():
    return date.today() + timedelta(days=1)


# Fungsi untuk menghitung status aktivasi.
def calculate_activation_status(period_end_date):
    if not period_end_date:
        return False
    return period_end_date >= date.today()


# Fungsi untuk mengambil periode akhir dari objek user lama atau model sekarang.
def get_account_period_end(user):
    return getattr(user, "periode_akhir", None) or getattr(user, "tgl_expired", None)


# Fungsi untuk mengambil payment verified terbaru dari akun tersimpan.
def get_latest_verified_billing_payment(user):
    user_id = getattr(user, "id", None)
    if not user_id:
        return None
    return (
        BillingPayment.query.filter_by(user_id=user_id, status="verified")
        .order_by(BillingPayment.payment_date.desc(), BillingPayment.id.desc())
        .first()
    )


# Fungsi untuk menghitung aktivasi akun tersimpan dari payment verified terbaru.
def calculate_account_activation_status(user):
    latest_payment = get_latest_verified_billing_payment(user)
    if latest_payment:
        today = date.today()
        return bool(
            latest_payment.period_start
            and latest_payment.period_end
            and latest_payment.period_start <= today <= latest_payment.period_end
        )
    if getattr(user, "id", None):
        return False
    return calculate_activation_status(get_account_period_end(user))


# Fungsi untuk menyinkronkan user status aktivasi.
def sync_user_activation_status(user):
    user.aktivasi = calculate_account_activation_status(user)


# Fungsi untuk menyinkronkan user status aktivasi.
def sync_users_activation_status(users):
    changed = False
    for user in users:
        expected_status = calculate_account_activation_status(user)
        if user.aktivasi != expected_status:
            user.aktivasi = expected_status
            changed = True

    if changed:
        db.session.commit()


# Fungsi untuk memblokir akun login user/admin.
def block_account_login(account):
    account.is_blocked = True
    account.blocked_at = auth_service.get_utc_naive_datetime()
    account.active_session_token = None


# Fungsi untuk membuka blokir akun login user/admin.
def unblock_account_login(account):
    account.is_blocked = False
    account.blocked_at = None


# Fungsi untuk mengambil nama tampilan user.
def get_user_display_name(account):
    if not account:
        return session.get("user")
    return account.nama or account.username


# Fungsi untuk membuat context template password.
def build_password_template_context(error=None):
    current_user = auth_service.get_current_user()
    role = current_user.role if current_user else session.get("role")
    return {
        "user": get_user_display_name(current_user),
        "error": error,
        "password_pattern": auth_service.get_password_pattern_for_role(role),
        "password_title": auth_service.get_password_title_for_role(role),
    }


# Fungsi untuk menghasilkan username client.
def generate_client_username(nama, no_hp_text):
    name_letters = "".join(character for character in nama.lower() if character.isalpha())
    prefix = name_letters[:4].ljust(4, "x")
    base_number = int(no_hp_text[-2:]) if len(no_hp_text) >= 2 else 0

    for offset in range(100):
        suffix = f"{(base_number + offset) % 100:02d}"
        candidate = f"{prefix}{suffix}"
        if not User.query.filter_by(username=candidate).first():
            return candidate

    raise ValueError("Username client untuk kombinasi nama dan no hp ini sudah penuh.")


# Fungsi untuk memvalidasi form user baru.
def validate_new_user_form(password, nama, no_hp_text, no_hp, email):
    if not password or not nama or no_hp is None or not email:
        return "Password, nama, no hp, dan email wajib diisi."

    if not NAME_PATTERN.fullmatch(nama):
        return "Nama hanya boleh berisi huruf."

    if not auth_service.is_valid_user_password_format(password):
        return USER_PASSWORD_TITLE + "."

    if not normalize_phone_number(no_hp_text):
        return "No HP minimal 8 digit dan hanya boleh diawali 08 atau 8."

    if not is_valid_email_format(email):
        return "format email tidak sesuai"

    if User.query.filter_by(no_hp=no_hp).first():
        return "No HP sudah terdaftar."

    if User.query.filter_by(email=email).first():
        return "Email sudah terdaftar."

    return None


# Fungsi untuk memvalidasi form admin.
def validate_admin_form(username, password, no_hp_text, no_hp, email):
    if not username or not password or no_hp is None or not email:
        return "Username, password, no hp, dan email wajib diisi."

    if not USERNAME_PATTERN.fullmatch(username):
        return "Username 3-15 karakter, hanya huruf, angka, atau underscore."

    if not auth_service.is_valid_admin_password_format(password):
        return ADMIN_PASSWORD_TITLE + "."

    if not normalize_phone_number(no_hp_text):
        return "No HP minimal 8 digit dan hanya boleh diawali 08 atau 8."

    if not is_valid_email_format(email):
        return "Format email tidak sesuai."

    if User.query.filter_by(username=username).first():
        return "Username sudah terdaftar."

    if User.query.filter_by(no_hp=no_hp).first():
        return "No HP sudah terdaftar."

    if User.query.filter_by(email=email).first():
        return "Email sudah terdaftar."

    return None


# Fungsi untuk mengambil nama tampilan user saat ini.
def get_current_user_display_name():
    return get_user_display_name(auth_service.get_current_user())


# Fungsi untuk mengambil user yang dapat dikelola.
def get_manageable_users():
    return User.query.filter_by(role=ROLE_USER).order_by(User.username.asc()).all()


# Fungsi untuk mengambil admin yang dapat dikelola.
def get_manageable_admins():
    return User.query.filter_by(role=ROLE_ADMIN).order_by(User.username.asc()).all()
