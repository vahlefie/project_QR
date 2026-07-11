from datetime import datetime
from pathlib import Path
import json
import re
from uuid import uuid4

import pandas as pd
from constants import (
    ALLOWED_EXCEL_EXTENSIONS,
    APP_TIMEZONE,
    DEFAULT_GUEST_STATUS,
    GUEST_ADDED_BY_MAX_LENGTH,
    GUEST_EMAIL_MAX_LENGTH,
    GUEST_EXCEL_COLUMNS,
    GUEST_NAME_CLEANUP_PATTERN,
    GUEST_NAME_MAX_LENGTH,
    GUEST_PHONE_MIN_LENGTH,
    PENDING_UPLOAD_SESSION_KEY,
    ROLE_USER,
    STAFF_NAME_CLEANUP_PATTERN,
    STAFF_NAME_PATTERN,
)
from exceptions import UploadValidationError
from extensions import db
from flask import current_app, request, session
from models import BillingPayment, Guests, User
from sqlalchemy import func


# Fungsi untuk mengubah nilai menjadi integer dengan default aman.
def parse_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# Fungsi untuk memeriksa apakah format email valid.
def is_valid_email_format(email):
    return "@" in email and "." in email


# Fungsi untuk mengambil file upload.
def get_uploaded_file(field_name="file"):
    file = request.files.get(field_name)
    if not file or not getattr(file, "filename", ""):
        raise UploadValidationError("File belum dipilih")
    return file


# Fungsi untuk memvalidasi file Excel.
def validate_excel_file(file):
    filename = getattr(file, "filename", "") or Path(getattr(file, "name", "")).name
    if not filename.lower().endswith(ALLOWED_EXCEL_EXTENSIONS):
        allowed_formats = ", ".join(ALLOWED_EXCEL_EXTENSIONS)
        raise UploadValidationError(f"Format harus {allowed_formats} ❌")


# Fungsi untuk memuat DataFrame Excel.
def load_excel_dataframe(file):
    validate_excel_file(file)

    try:
        df = pd.read_excel(file)
    except Exception as exc:
        raise UploadValidationError(f"Error membaca file Excel: {str(exc)} ❌") from exc

    df.columns = df.columns.str.strip().str.lower()
    return df


# Fungsi untuk memvalidasi format Excel tamu.
def validate_guest_excel_format(df):
    if tuple(df.columns) != GUEST_EXCEL_COLUMNS:
        raise UploadValidationError("Format data excel tidak sesuai")


# Fungsi untuk membersihkan bagian nama file upload.
def clean_upload_filename_part(value, fallback):
    text_value = str(value or "").strip()
    cleaned_value = re.sub(r"[^A-Za-z0-9]+", "_", text_value).strip("_")
    return cleaned_value or fallback


# Fungsi untuk mengambil nama event terbaru milik client.
def get_latest_client_event_name(owner_user):
    if not owner_user:
        return ""

    latest_payment = (
        BillingPayment.query.filter_by(user_id=owner_user.id)
        .order_by(BillingPayment.payment_date.desc(), BillingPayment.id.desc())
        .first()
    )
    if latest_payment and latest_payment.event_name:
        return latest_payment.event_name
    return owner_user.perusahaan or owner_user.nama or "event"


# Fungsi untuk membangun nama dasar file upload tamu.
def build_guest_upload_base_filename(owner_user, upload_date=None):
    upload_date = upload_date or datetime.now(APP_TIMEZONE).date()
    event_name = clean_upload_filename_part(get_latest_client_event_name(owner_user), "event")
    username = clean_upload_filename_part(getattr(owner_user, "username", ""), "client")
    return f"{event_name}_{username}_{upload_date.isoformat()}"


# Fungsi untuk menentukan path file upload tamu berikutnya.
def get_next_guest_upload_path(owner_user, upload_date=None):
    upload_dir = Path(current_app.instance_path) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    base_filename = build_guest_upload_base_filename(owner_user, upload_date=upload_date)
    upload_path = upload_dir / f"{base_filename}.xlsx"
    sequence = 2
    while upload_path.exists():
        upload_path = upload_dir / f"{base_filename}_{sequence}.xlsx"
        sequence += 1
    return upload_path


# Fungsi untuk menyimpan file upload Excel asli ke folder instance/uploads.
def save_uploaded_guest_file(file, owner_user, upload_date=None):
    upload_path = get_next_guest_upload_path(owner_user, upload_date=upload_date)
    file.seek(0)
    file.save(upload_path)
    file.seek(0)
    return upload_path


# Fungsi untuk mengambil integer opsional.
def get_optional_integer(row, column_name):
    value = row.get(column_name)
    if pd.isna(value) or value == "":
        return None

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


# Fungsi untuk mengambil user pemilik yang dipilih.
def get_selected_owner_user(source, field_name="owner_user_id"):
    owner_user_id = parse_int(source.get(field_name))
    if owner_user_id is None:
        return None
    return User.query.filter_by(id=owner_user_id, role=ROLE_USER).first()


# Fungsi untuk membersihkan nama tamu.
def clean_guest_name(value):
    if pd.isna(value):
        return ""

    text_value = str(value).strip()
    text_value = GUEST_NAME_CLEANUP_PATTERN.sub(" ", text_value)
    text_value = " ".join(text_value.split())
    if not text_value:
        return ""
    return text_value.title()[:GUEST_NAME_MAX_LENGTH]


# Fungsi untuk membersihkan nomor HP tamu.
def clean_guest_phone(value):
    if pd.isna(value):
        return ""

    if isinstance(value, float) and value.is_integer():
        text_value = str(int(value))
    else:
        text_value = str(value).strip()

    if re.fullmatch(r"\d+\.0", text_value):
        text_value = text_value[:-2]

    if not text_value or text_value.startswith("-") or "." in text_value or "," in text_value:
        return ""
    if not text_value.isdigit():
        return ""

    if text_value.startswith("62"):
        if len(text_value) < GUEST_PHONE_MIN_LENGTH:
            return ""
        return text_value
    if len(text_value) < GUEST_PHONE_MIN_LENGTH:
        return ""
    if text_value.startswith("08"):
        text_value = f"62{text_value[1:]}"
    elif text_value.startswith("8"):
        text_value = f"62{text_value}"
    else:
        return ""
    return text_value


# Fungsi untuk memeriksa apakah input nomor HP yang diizinkan.
def is_allowed_phone_input(value):
    if pd.isna(value):
        return False
    text_value = str(value).strip()
    return (
        text_value.isdigit()
        and len(text_value) >= GUEST_PHONE_MIN_LENGTH
        and (text_value.startswith("62") or text_value.startswith("08") or text_value.startswith("8"))
    )


# Fungsi untuk membersihkan nama staff.
def clean_staff_name(value):
    if pd.isna(value):
        return ""

    text_value = str(value).strip()
    if not text_value or not STAFF_NAME_PATTERN.fullmatch(text_value):
        return ""

    text_value = STAFF_NAME_CLEANUP_PATTERN.sub(" ", text_value)
    text_value = " ".join(text_value.split())
    if not text_value:
        return ""
    return text_value.title()[:GUEST_ADDED_BY_MAX_LENGTH]


# Fungsi untuk memeriksa input nama staff hanya memakai huruf, angka, dan spasi.
def is_valid_staff_name(value):
    if pd.isna(value):
        return False
    text_value = str(value).strip()
    return bool(text_value and STAFF_NAME_PATTERN.fullmatch(text_value))


# Fungsi untuk membersihkan nomor HP staff.
def clean_staff_phone(value):
    if not is_allowed_phone_input(value):
        return ""
    return clean_guest_phone(value)


# Fungsi untuk membersihkan email tamu.
def clean_guest_email(value):
    if pd.isna(value):
        return ""

    email = str(value).strip().lower()
    if not email or len(email) > GUEST_EMAIL_MAX_LENGTH:
        return ""
    if not is_valid_email_format(email):
        return ""
    return email


# Fungsi untuk membersihkan status tamu.
def clean_guest_status(value):
    if pd.isna(value):
        return DEFAULT_GUEST_STATUS

    status = str(value).strip().lower()
    if status == "vip":
        return "VIP"
    if status == "reguler" or not status:
        return DEFAULT_GUEST_STATUS
    return DEFAULT_GUEST_STATUS


GUEST_DUPLICATE_MATCH_FIELDS = ("no_hp", "email")


# Fungsi untuk membersihkan label penambah data tamu.
def clean_guest_added_by(value):
    text_value = str(value or "").strip()
    return text_value[:GUEST_ADDED_BY_MAX_LENGTH] or None


# Fungsi untuk mengambil label penambah tamu dari akun client pemilik data.
def build_owner_guest_added_by(owner_user):
    if not owner_user:
        return None
    return clean_guest_added_by(getattr(owner_user, "username", "") or getattr(owner_user, "nama", ""))


# Fungsi untuk mengambil label penambah tamu dari akun staff.
def build_staff_guest_added_by(staff):
    if not staff:
        return None
    return clean_guest_added_by(getattr(staff, "nama", "") or getattr(staff, "no_hp", ""))


# Fungsi untuk mengambil nilai pembanding tamu.
def get_guest_match_value(field_name, value):
    if field_name == "no_hp":
        return clean_guest_phone(value)
    if field_name == "email":
        return clean_guest_email(value).lower()
    return ""


# Fungsi untuk membuat record tamu.
def build_guest_record(row, fallback_no):
    nama = clean_guest_name(row.get("nama"))
    raw_no_hp = row.get("no_hp")
    no_hp = clean_guest_phone(raw_no_hp) if is_allowed_phone_input(raw_no_hp) else ""
    if not nama or not no_hp:
        return None

    no = get_optional_integer(row, "no") or fallback_no
    email = clean_guest_email(row.get("email"))
    status = clean_guest_status(row.get("status"))

    return {
        "no": no,
        "nama": nama,
        "no_hp": no_hp,
        "email": email or None,
        "status": status,
    }


# Fungsi untuk menampilkan nilai asli Excel pada daftar baris yang dihapus.
def format_removed_guest_value(value):
    if pd.isna(value) or value == "":
        return "N/A"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text_value = str(value).strip()
    return text_value or "N/A"


# Fungsi untuk membuat item daftar data tamu yang dihapus saat cleaning.
def build_removed_guest_row(row, row_number):
    raw_no_hp = row.get("no_hp")
    cleaned_no_hp = clean_guest_phone(raw_no_hp) if is_allowed_phone_input(raw_no_hp) else ""
    reasons = []
    if not clean_guest_name(row.get("nama")):
        reasons.append("Nama kosong/tidak valid")
    if not cleaned_no_hp:
        reasons.append("No HP kosong/tidak valid")

    return {
        "row_number": row_number,
        "no": format_removed_guest_value(row.get("no")),
        "nama": format_removed_guest_value(row.get("nama")),
        "no_hp": format_removed_guest_value(row.get("no_hp")),
        "email": format_removed_guest_value(row.get("email")),
        "status": format_removed_guest_value(row.get("status")),
        "reason": ", ".join(reasons) or "Data tidak valid",
    }


# Fungsi untuk mengambil field duplikat tamu.
def get_guest_duplicate_fields(record, existing_guests, seen_keys):
    fields = set()
    record_values = {
        field_name: get_guest_match_value(field_name, record.get(field_name))
        for field_name in GUEST_DUPLICATE_MATCH_FIELDS
    }

    for guest in existing_guests:
        for field_name in GUEST_DUPLICATE_MATCH_FIELDS:
            guest_value = get_guest_match_value(field_name, getattr(guest, field_name))
            if record_values[field_name] and record_values[field_name] == guest_value:
                fields.add(field_name)

    for field_name in GUEST_DUPLICATE_MATCH_FIELDS:
        if record_values[field_name] and record_values[field_name] in seen_keys[field_name]:
            fields.add(field_name)

    return [field_name for field_name in GUEST_DUPLICATE_MATCH_FIELDS if field_name in fields]


# Fungsi untuk menyimpan penanda key tamu.
def remember_guest_keys(record, seen_keys):
    for field_name in GUEST_DUPLICATE_MATCH_FIELDS:
        value = get_guest_match_value(field_name, record.get(field_name))
        if value:
            seen_keys[field_name].add(value)


# Fungsi untuk menjalankan proses pencocokan baris tamu.
def guest_matches_row(guest, row):
    for field_name in GUEST_DUPLICATE_MATCH_FIELDS:
        row_value = get_guest_match_value(field_name, row.get(field_name))
        guest_value = get_guest_match_value(field_name, getattr(guest, field_name))
        if row_value and row_value == guest_value:
            return True
    return False


# Fungsi untuk memperbarui tamu dari baris.
def update_guest_from_row(guest, row, added_by=None):
    guest.no = row.get("no") or 0
    guest.nama = row.get("nama")
    guest.no_hp = row.get("no_hp")
    guest.email = row.get("email")
    guest.status = clean_guest_status(row.get("status"))
    source_label = clean_guest_added_by(added_by or row.get("added_by"))
    if source_label:
        guest.added_by = source_label


# Fungsi untuk mengambil nomor urut tamu berikutnya.
def get_next_guest_no(owner_user_id):
    max_no = db.session.query(func.max(Guests.no)).filter_by(user_id=owner_user_id).scalar()
    return (max_no or 0) + 1


# Fungsi untuk membuat data tamu manual.
def build_manual_guest_data(source, owner_user, added_by=None):
    raw_no_hp = source.get("no_hp")
    no_hp = clean_guest_phone(raw_no_hp) if is_allowed_phone_input(raw_no_hp) else ""
    guest_data = {
        "no": get_next_guest_no(owner_user.id),
        "nama": clean_guest_name(source.get("nama")),
        "no_hp": no_hp,
        "email": clean_guest_email(source.get("email")) or None,
        "status": clean_guest_status(source.get("status")),
        "added_by": clean_guest_added_by(added_by) or build_owner_guest_added_by(owner_user),
    }

    if not guest_data["nama"] or not guest_data["no_hp"]:
        return None
    return guest_data


# Fungsi untuk membangun data edit tamu dari input form.
def build_guest_edit_data(source):
    raw_no_hp = source.get("no_hp")
    no_hp = clean_guest_phone(raw_no_hp) if is_allowed_phone_input(raw_no_hp) else ""
    guest_data = {
        "nama": clean_guest_name(source.get("nama")),
        "no_hp": no_hp,
        "email": clean_guest_email(source.get("email")) or None,
        "status": clean_guest_status(source.get("status")),
    }

    if not guest_data["nama"] or not guest_data["no_hp"]:
        return None
    return guest_data


# Fungsi untuk memeriksa apakah nomor HP tamu sudah terdaftar.
def is_guest_phone_registered(owner_user, no_hp, exclude_guest_id=None):
    if not owner_user or not no_hp:
        return False

    query = Guests.query.filter_by(user_id=owner_user.id, no_hp=str(no_hp))
    if exclude_guest_id is not None:
        query = query.filter(Guests.id != exclude_guest_id)
    return query.first() is not None


# Fungsi untuk membersihkan data tamu tersimpan milik pemilik.
def clean_saved_guests_for_owner(owner_user_id):
    updated_count = 0
    deleted_count = 0
    query = Guests.query
    if owner_user_id is not None:
        query = query.filter_by(user_id=owner_user_id)
    guests = query.all()

    for guest in guests:
        cleaned_name = clean_guest_name(guest.nama)
        cleaned_phone = clean_guest_phone(guest.no_hp)
        cleaned_email = clean_guest_email(guest.email)
        cleaned_status = clean_guest_status(guest.status)

        if not cleaned_name or not cleaned_phone:
            db.session.delete(guest)
            deleted_count += 1
            continue

        if guest.nama != cleaned_name:
            guest.nama = cleaned_name
            updated_count += 1
        if guest.no_hp != cleaned_phone:
            guest.no_hp = cleaned_phone
            updated_count += 1

        normalized_email = cleaned_email or None
        if guest.email != normalized_email:
            guest.email = normalized_email
            updated_count += 1
        if guest.status != cleaned_status:
            guest.status = cleaned_status
            updated_count += 1

    if updated_count or deleted_count:
        db.session.commit()

    return {"updated": updated_count, "deleted": deleted_count}


# Fungsi untuk membuat preview upload tamu.
def build_guest_upload_preview(file, owner_user):
    if not owner_user or owner_user.role != ROLE_USER:
        raise UploadValidationError("Pemilik data tamu tidak valid")

    clean_saved_guests_for_owner(owner_user.id)

    df = load_excel_dataframe(file)
    validate_guest_excel_format(df)

    rows = []
    duplicates = []
    duplicate_indexes = set()
    removed_rows = []
    removed_count = 0
    existing_guests = Guests.query.filter_by(user_id=owner_user.id).all()
    seen_keys = {field_name: set() for field_name in GUEST_DUPLICATE_MATCH_FIELDS}

    for excel_row_number, (_, row) in enumerate(df.iterrows(), start=2):
        record = build_guest_record(row, fallback_no=len(rows) + 1)
        if not record:
            removed_count += 1
            removed_rows.append(build_removed_guest_row(row, excel_row_number))
            continue

        row_index = len(rows)
        duplicate_fields = get_guest_duplicate_fields(record, existing_guests, seen_keys)
        if duplicate_fields:
            duplicate_indexes.add(row_index)
            duplicates.append(
                {
                    "row_index": row_index,
                    "nama": record["nama"],
                    "no_hp": record["no_hp"] or "N/A",
                    "email": record["email"] or "N/A",
                    "matched_fields": ", ".join(duplicate_fields),
                }
            )

        rows.append(record)
        remember_guest_keys(record, seen_keys)

    if not rows:
        raise UploadValidationError("Tidak ada data tamu valid untuk disimpan")

    duplicates.sort(key=lambda item: item["nama"].lower())

    return {
        "rows": rows,
        "duplicates": duplicates,
        "duplicate_indexes": sorted(duplicate_indexes),
        "removed_rows": removed_rows,
        "stats": {
            "cleaned_count": len(rows),
            "duplicate_count": len(duplicate_indexes),
            "removed_count": removed_count,
        },
    }


# Fungsi untuk menyimpan baris tamu.
def save_guest_rows(owner_user, rows, duplicate_indexes=None, include_duplicates=False, added_by=None):
    duplicate_indexes = set(duplicate_indexes or [])
    saved_count = 0
    source_label = clean_guest_added_by(added_by) or build_owner_guest_added_by(owner_user)

    for row_index, row in enumerate(rows):
        if row_index in duplicate_indexes and not include_duplicates:
            continue

        guest = Guests()
        guest.no = row.get("no") or 0
        guest.nama = row.get("nama")
        guest.no_hp = row.get("no_hp")
        guest.email = row.get("email")
        guest.status = clean_guest_status(row.get("status"))
        guest.added_by = clean_guest_added_by(row.get("added_by")) or source_label
        guest.user_id = owner_user.id
        db.session.add(guest)
        saved_count += 1

    db.session.commit()
    return saved_count


# Fungsi untuk mengganti baris tamu.
def replace_guest_rows(owner_user, rows, added_by=None):
    affected_count = 0
    source_label = clean_guest_added_by(added_by) or build_owner_guest_added_by(owner_user)

    for row in rows:
        existing_guests = Guests.query.filter_by(user_id=owner_user.id).order_by(Guests.id.asc()).all()
        matching_guests = [guest for guest in existing_guests if guest_matches_row(guest, row)]

        if matching_guests:
            target_guest = matching_guests[0]
            update_guest_from_row(target_guest, row, added_by=source_label)
            for duplicate_guest in matching_guests[1:]:
                db.session.delete(duplicate_guest)
        else:
            guest = Guests()
            guest.user_id = owner_user.id
            update_guest_from_row(guest, row, added_by=source_label)
            db.session.add(guest)

        affected_count += 1

    db.session.commit()
    return affected_count


# Fungsi untuk mengambil path upload tertunda.
def get_pending_upload_path(pending_id):
    if not pending_id or not re.fullmatch(r"[a-f0-9]{32}", pending_id):
        return None

    pending_dir = Path(current_app.instance_path) / "pending_uploads"
    pending_dir.mkdir(parents=True, exist_ok=True)
    return pending_dir / f"{pending_id}.json"


# Fungsi untuk menyimpan upload tamu tertunda.
def save_pending_guest_upload(owner_user, preview):
    pending_id = uuid4().hex
    pending_path = get_pending_upload_path(pending_id)
    if pending_path is None:
        raise RuntimeError("Gagal membuat path pending upload.")

    payload = {
        "owner_user_id": owner_user.id,
        "rows": preview["rows"],
        "duplicates": preview["duplicates"],
        "duplicate_indexes": preview["duplicate_indexes"],
        "removed_rows": preview.get("removed_rows", []),
        "stats": preview["stats"],
    }

    with pending_path.open("w", encoding="utf-8") as pending_file:
        json.dump(payload, pending_file)

    session[PENDING_UPLOAD_SESSION_KEY] = pending_id
    return payload


# Fungsi untuk memuat upload tamu tertunda.
def load_pending_guest_upload():
    pending_path = get_pending_upload_path(session.get(PENDING_UPLOAD_SESSION_KEY))
    if not pending_path or not pending_path.exists():
        return None

    try:
        with pending_path.open("r", encoding="utf-8") as pending_file:
            return json.load(pending_file)
    except (OSError, json.JSONDecodeError):
        return None


# Fungsi untuk membersihkan upload tamu tertunda.
def clear_pending_guest_upload():
    pending_id = session.pop(PENDING_UPLOAD_SESSION_KEY, None)
    pending_path = get_pending_upload_path(pending_id)
    if pending_path and pending_path.exists():
        pending_path.unlink()


# Fungsi untuk memproses upload tamu.
def process_guests_upload(file, owner_user):
    preview = build_guest_upload_preview(file, owner_user)
    save_uploaded_guest_file(file, owner_user)
    save_guest_rows(
        owner_user=owner_user,
        rows=preview["rows"],
        duplicate_indexes=preview["duplicate_indexes"],
        include_duplicates=False,
    )


# Fungsi untuk menangani upload.
def handle_upload(processor):
    try:
        file = get_uploaded_file()
        processor(file)
    except UploadValidationError as exc:
        return str(exc)
    return None
