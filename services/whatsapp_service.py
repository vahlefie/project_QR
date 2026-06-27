import re
from urllib.parse import quote

from extensions import db
from flask import url_for
from models import GuestShortUrl, Guests, WhatsappSetting, WhatsappTemplate
from services import account_service, attendance_service

DEFAULT_WHATSAPP_MESSAGE_TEMPLATE = (
    "Halo Bpk/Ibu {nama_tamu},\n\n" "Berikut link QR Code kehadiran Anda:\n" "{short_qr_url}\n\n" "Terima kasih."
)

WHATSAPP_SEND_MODES = (
    ("development", "Development - wa.me"),
    ("production", "Production - WhatsApp API"),
)

WHATSAPP_TEMPLATE_VARIABLES = (
    "{nama_tamu}",
    "{no_hp}",
    "{qr_url}",
    "{short_qr_url}",
    "{nama_client}",
)


# Fungsi untuk membuat slug URL dari nama tamu.
def slugify_guest_name(name):
    slug = re.sub(r"[^0-9A-Za-z]+", "_", str(name or "").strip())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "Tamu"


# Fungsi untuk membangun short code dasar QR tamu.
def build_guest_short_code_base(guest):
    return f"{guest.user_id}_{slugify_guest_name(guest.nama)}"


# Fungsi untuk membuat short code unik dari user_id dan nama tamu.
def generate_unique_guest_short_code(guest):
    base_code = build_guest_short_code_base(guest)
    candidate = base_code
    suffix = 2

    while GuestShortUrl.query.filter_by(short_code=candidate).first():
        candidate = f"{base_code}_{suffix}"
        suffix += 1

    return candidate


# Fungsi untuk mengambil atau membuat mapping short URL QR tamu.
def get_or_create_guest_short_url(guest):
    if not attendance_service.is_guest_qr_available(guest):
        return None
    if not attendance_service.is_owner_in_active_billing_period(getattr(guest, "owner", None)):
        return None

    existing_short_url = GuestShortUrl.query.filter_by(guest_id=guest.id).first()
    if existing_short_url:
        return existing_short_url

    short_url = GuestShortUrl()
    short_url.guest_id = guest.id
    short_url.short_code = generate_unique_guest_short_code(guest)
    db.session.add(short_url)
    db.session.commit()
    return short_url


# Fungsi untuk membuat URL pendek QR tamu.
def build_guest_short_qr_url(guest):
    short_url = get_or_create_guest_short_url(guest)
    if not short_url:
        return ""
    return url_for("attendance.guest_qr_short_redirect", short_code=short_url.short_code, _external=True)


# Fungsi untuk mengambil tamu dari short code QR.
def get_guest_from_short_qr_code(short_code):
    short_url = GuestShortUrl.query.filter_by(short_code=str(short_code or "").strip()).first()
    if not short_url:
        return None

    guest = db.session.get(Guests, short_url.guest_id)
    if not attendance_service.is_guest_qr_available(guest):
        return None
    return guest


# Fungsi untuk mengambil atau membuat konfigurasi WhatsApp utama.
def get_or_create_whatsapp_setting():
    setting = WhatsappSetting.query.order_by(WhatsappSetting.id.asc()).first()
    if setting:
        return setting

    setting = WhatsappSetting()
    setting.send_mode = "development"
    db.session.add(setting)
    db.session.commit()
    return setting


# Fungsi untuk menampilkan nomor WhatsApp dengan format ramah baca.
def format_whatsapp_phone(phone_number):
    if not phone_number:
        return "Belum diatur"
    return f"+{phone_number}"


# Fungsi untuk menyensor token API WhatsApp.
def mask_whatsapp_secret(secret):
    text = str(secret or "").strip()
    if not text:
        return "Belum diatur"
    if len(text) <= 4:
        return "*" * len(text)
    return f"{'*' * (len(text) - 4)}{text[-4:]}"


# Fungsi untuk mengambil template yang dipilih atau template default.
def get_selected_whatsapp_template(setting, selected_template_id=None):
    selected_template = None
    if selected_template_id:
        selected_template = db.session.get(WhatsappTemplate, selected_template_id)

    if not selected_template and setting.active_template_id:
        selected_template = db.session.get(WhatsappTemplate, setting.active_template_id)

    if not selected_template:
        selected_template = WhatsappTemplate.query.order_by(
            WhatsappTemplate.is_default.desc(), WhatsappTemplate.id.asc()
        ).first()

    return selected_template


# Fungsi untuk membuat context halaman setting WhatsApp.
def build_whatsapp_settings_context(selected_template_id=None, message="", error=""):
    setting = get_or_create_whatsapp_setting()
    templates = WhatsappTemplate.query.order_by(WhatsappTemplate.is_default.desc(), WhatsappTemplate.name.asc()).all()
    selected_template = get_selected_whatsapp_template(setting, selected_template_id)

    return {
        "user": account_service.get_current_user_display_name(),
        "setting": setting,
        "send_modes": WHATSAPP_SEND_MODES,
        "phone_display": format_whatsapp_phone(setting.phone_number),
        "api_token_display": mask_whatsapp_secret(setting.api_token),
        "api_phone_number_id_display": setting.api_phone_number_id or "Belum diatur",
        "templates": templates,
        "selected_template": selected_template,
        "selected_template_id": selected_template.id if selected_template else "",
        "template_name": selected_template.name if selected_template else "",
        "template_body": selected_template.body if selected_template else "",
        "template_variables": WHATSAPP_TEMPLATE_VARIABLES,
        "message": message,
        "error": error,
    }


# Fungsi untuk menyimpan mode pengiriman WhatsApp.
def update_whatsapp_send_mode(send_mode):
    valid_modes = {mode for mode, _label in WHATSAPP_SEND_MODES}
    if send_mode not in valid_modes:
        raise ValueError("Mode pengiriman WhatsApp tidak valid.")

    setting = get_or_create_whatsapp_setting()
    setting.send_mode = send_mode
    db.session.commit()
    return setting


# Fungsi untuk menyimpan nomor WhatsApp pengirim.
def update_whatsapp_phone(raw_phone_number):
    normalized_phone = account_service.normalize_phone_number(raw_phone_number)
    if not normalized_phone:
        raise ValueError("Nomor WhatsApp minimal 8 digit dan hanya boleh diawali 62, 08, atau 8.")

    setting = get_or_create_whatsapp_setting()
    setting.phone_number = normalized_phone
    db.session.commit()
    return setting


# Fungsi untuk menyimpan token API WhatsApp.
def update_whatsapp_api_token(api_token):
    token = str(api_token or "").strip()
    if not token:
        raise ValueError("API WhatsApp wajib diisi.")

    setting = get_or_create_whatsapp_setting()
    setting.api_token = token
    db.session.commit()
    return setting


# Fungsi untuk menyimpan Phone Number ID API WhatsApp.
def update_whatsapp_api_phone_number_id(phone_number_id):
    clean_phone_number_id = str(phone_number_id or "").strip()
    if not clean_phone_number_id:
        raise ValueError("Phone Number ID wajib diisi untuk mode production.")

    setting = get_or_create_whatsapp_setting()
    setting.api_phone_number_id = clean_phone_number_id
    db.session.commit()
    return setting


# Fungsi untuk menyimpan atau memperbarui template pesan WhatsApp.
def save_whatsapp_template(template_id, name, body):
    template_name = str(name or "").strip()
    template_body = str(body or "").strip()
    if not template_name:
        raise ValueError("Nama template wajib diisi.")
    if len(template_name) > 50:
        raise ValueError("Nama template maksimal 50 karakter.")
    if not template_body:
        raise ValueError("Isi template pesan wajib diisi.")

    template = db.session.get(WhatsappTemplate, template_id) if template_id else None
    if not template:
        template = WhatsappTemplate()
        db.session.add(template)

    template.name = template_name
    template.body = template_body

    WhatsappTemplate.query.update({WhatsappTemplate.is_default: False})
    template.is_default = True

    setting = get_or_create_whatsapp_setting()
    db.session.flush()
    setting.active_template_id = template.id
    db.session.commit()
    return template


# Fungsi untuk mengambil isi template aktif dengan fallback development.
def get_active_whatsapp_template_body(setting):
    selected_template = get_selected_whatsapp_template(setting)
    if selected_template and selected_template.body:
        return selected_template.body
    return DEFAULT_WHATSAPP_MESSAGE_TEMPLATE


# Fungsi untuk mengganti variabel template WhatsApp dengan data tamu.
def render_guest_whatsapp_message(guest, template_body=None):
    owner_user = getattr(guest, "owner", None)
    qr_url = attendance_service.build_guest_qr_url(guest)
    short_qr_url = build_guest_short_qr_url(guest)
    message = template_body if template_body is not None else DEFAULT_WHATSAPP_MESSAGE_TEMPLATE
    replacements = {
        "{nama_tamu}": guest.nama or "",
        "{no_hp}": guest.no_hp or "",
        "{qr_url}": qr_url,
        "{short_qr_url}": short_qr_url,
        "{nama_client}": account_service.get_user_display_name(owner_user) if owner_user else "",
    }

    for placeholder, value in replacements.items():
        message = message.replace(placeholder, str(value))

    return message


# Fungsi untuk membuat payload pengiriman WhatsApp undangan QR tamu.
def build_guest_whatsapp_invite(guest):
    if not attendance_service.is_guest_qr_available(guest):
        raise ValueError("Fitur kirim QR WhatsApp hanya tersedia untuk tamu client Premium.")
    if not attendance_service.is_owner_in_active_billing_period(getattr(guest, "owner", None)):
        raise ValueError("Fitur kirim QR WhatsApp hanya tersedia untuk client aktif.")
    if not guest.no_hp:
        raise ValueError("Nomor HP tamu belum tersedia.")

    setting = get_or_create_whatsapp_setting()
    template_body = get_active_whatsapp_template_body(setting)
    message = render_guest_whatsapp_message(guest, template_body)
    short_qr_url = build_guest_short_qr_url(guest)

    if setting.send_mode == "production":
        if not setting.api_token or not setting.api_phone_number_id:
            raise ValueError("Konfigurasi WhatsApp API production belum lengkap.")
        raise ValueError("Pengiriman WhatsApp API production belum diaktifkan pada development lokal.")

    return {
        "mode": "development",
        "guest": guest,
        "message": message,
        "short_qr_url": short_qr_url,
        "send_url": f"https://wa.me/{guest.no_hp}?text={quote(message)}",
    }
