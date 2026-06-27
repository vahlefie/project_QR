from datetime import datetime
from io import BytesIO
from pathlib import Path
import os
import re
import shutil
import tarfile

import pandas as pd
from constants import APP_TIMEZONE, DEFAULT_GUEST_STATUS, ROLE_USER
from extensions import db
from flask import current_app
from models import BillingPayment, EventArchive, Guests, User
from services import attendance_service

ARCHIVE_COLUMNS = ("no", "nama", "no_hp", "email", "status", "kehadiran", "verifikasi")


# Fungsi untuk mengambil tanggal hari ini sesuai timezone aplikasi.
def get_local_today():
    return datetime.now(APP_TIMEZONE).date()


# Fungsi untuk membersihkan teks agar aman dipakai sebagai nama file.
def clean_archive_filename_part(value, fallback="event"):
    text_value = str(value or "").strip()
    cleaned_value = re.sub(r"[^A-Za-z0-9]+", "_", text_value).strip("_")
    return cleaned_value or fallback


# Fungsi untuk mengambil payment verified terbaru milik client.
def get_latest_verified_payment(owner_user):
    if not owner_user or not getattr(owner_user, "id", None):
        return None
    return (
        BillingPayment.query.filter_by(user_id=owner_user.id, status="verified")
        .order_by(BillingPayment.payment_date.desc(), BillingPayment.id.desc())
        .first()
    )


# Fungsi untuk memilih nama event dari payment/client.
def get_event_name(owner_user, payment=None):
    payment = payment or get_latest_verified_payment(owner_user)
    event_name_options = (
        payment.event_name if payment else "",
        getattr(owner_user, "perusahaan", None),
        getattr(owner_user, "nama", None),
        "event",
    )
    for event_name in event_name_options:
        event_name = str(event_name or "").strip()
        if event_name and event_name.upper() != "N/A":
            return event_name
    return "event"


# Fungsi untuk membuat nama file export aktif.
def build_active_export_filename(owner_user, download_date=None):
    download_date = download_date or get_local_today()
    if not owner_user:
        return f"data_tamu_{download_date.isoformat()}.xlsx"
    event_name = clean_archive_filename_part(get_event_name(owner_user), "data_tamu")
    return f"{event_name}_{download_date.isoformat()}.xlsx"


# Fungsi untuk membuat nama file export final.
def build_final_export_filename(owner_user, payment=None, archive=None, download_date=None):
    download_date = download_date or get_local_today()
    event_name_source = archive.event_name if archive else get_event_name(owner_user, payment=payment)
    event_name = clean_archive_filename_part(event_name_source, "data_tamu")
    return f"{event_name}_Final_{download_date.isoformat()}.xlsx"


# Fungsi untuk mengambil folder backup event per client.
def get_event_backup_dir(owner_user):
    backup_dir = Path(current_app.root_path) / "backup" / "event" / str(owner_user.id)
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


# Fungsi untuk membuat path CSV final event.
def get_final_csv_path(owner_user, payment=None):
    payment = payment or get_latest_verified_payment(owner_user)
    archive_year = (payment.period_end or get_local_today()).year if payment else get_local_today().year
    event_name = clean_archive_filename_part(get_event_name(owner_user, payment=payment), "event")
    return get_event_backup_dir(owner_user) / f"{event_name}_Final_{archive_year}.csv"


# Fungsi untuk membuat path CSV final format lama tanpa tahun.
def get_legacy_final_csv_path(owner_user, payment=None):
    event_name = clean_archive_filename_part(get_event_name(owner_user, payment=payment), "event")
    return get_event_backup_dir(owner_user) / f"{event_name}_Final.csv"


# Fungsi untuk memindahkan CSV final lama ke format nama baru jika ditemukan.
def normalize_final_csv_path(owner_user, payment=None):
    csv_path = get_final_csv_path(owner_user, payment=payment)
    legacy_csv_path = get_legacy_final_csv_path(owner_user, payment=payment)
    if legacy_csv_path != csv_path and legacy_csv_path.exists() and not csv_path.exists():
        os.replace(legacy_csv_path, csv_path)
    return csv_path


# Fungsi untuk membuat path arsip tar.gz event lama.
def get_event_tar_path(owner_user, payment=None):
    payment = payment or get_latest_verified_payment(owner_user)
    today = get_local_today()
    archive_year = (payment.period_end or today).year if payment else today.year
    event_name = clean_archive_filename_part(get_event_name(owner_user, payment=payment), "event")
    return get_event_backup_dir(owner_user) / f"{event_name}_{archive_year}.tar.gz"


# Fungsi untuk mengecek apakah payment sudah melewati tanggal periode akhir.
def is_payment_expired(payment, today):
    return bool(payment and payment.period_end and payment.period_end < today)


# Fungsi untuk mengambil client dengan payment terverifikasi terbaru yang sudah expired.
def get_expired_client_event_candidates(today=None):
    today = today or get_local_today()
    clients = User.query.filter_by(role=ROLE_USER).order_by(User.id.asc()).all()
    candidates = []
    for client in clients:
        payment = get_latest_verified_payment(client)
        if is_payment_expired(payment, today):
            candidates.append((client, payment))
    return candidates


# Fungsi untuk mengubah query/list tamu menjadi baris arsip.
def build_guest_archive_rows(guests):
    rows = []
    for index, guest in enumerate(guests, start=1):
        rows.append(
            {
                "no": index,
                "nama": guest.nama,
                "no_hp": guest.no_hp or "N/A",
                "email": guest.email or "N/A",
                "status": guest.status or DEFAULT_GUEST_STATUS,
                "kehadiran": attendance_service.format_attendance_time(guest.kehadiran) or "N/A",
                "verifikasi": guest.verified_by_staff_name or "N/A",
            }
        )
    return rows


# Fungsi untuk menulis CSV final secara atomik dan memverifikasi hasilnya.
def write_final_csv(csv_path, rows):
    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = csv_path.with_name(f".{csv_path.name}.tmp")
    if temp_path.exists():
        temp_path.unlink()

    try:
        pd.DataFrame(rows, columns=ARCHIVE_COLUMNS).to_csv(temp_path, index=False, encoding="utf-8")
        loaded_rows = pd.read_csv(temp_path, dtype=str).fillna("").to_dict("records")
        if len(loaded_rows) != len(rows):
            raise RuntimeError("Verifikasi CSV final gagal: jumlah baris tidak sesuai.")
        os.replace(temp_path, csv_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


# Fungsi untuk mengambil atau membuat metadata arsip event.
def upsert_event_archive(owner_user, payment, csv_path, guest_count, status="csv_ready"):
    archive = EventArchive.query.filter_by(user_id=owner_user.id, csv_path=str(csv_path)).first()
    if not archive:
        archive = EventArchive()
        archive.user_id = owner_user.id
        archive.csv_path = str(csv_path)
        db.session.add(archive)

    archive.event_name = get_event_name(owner_user, payment=payment)
    archive.package_name = payment.package_name if payment else getattr(owner_user, "paket", None)
    archive.period_start = payment.period_start if payment else None
    archive.period_end = payment.period_end if payment else getattr(owner_user, "periode_akhir", None)
    archive.guest_count = guest_count
    archive.status = status
    if not archive.created_at:
        archive.created_at = datetime.now(APP_TIMEZONE).replace(tzinfo=None)
    return archive


# Fungsi untuk memastikan data tamu event expired sudah dibackup ke CSV final.
def ensure_final_guest_backup(owner_user, payment=None, today=None):
    today = today or get_local_today()
    payment = payment or get_latest_verified_payment(owner_user)
    if not owner_user or not payment or not payment.period_end or payment.period_end >= today:
        return None

    csv_path = normalize_final_csv_path(owner_user, payment=payment)
    legacy_csv_path = get_legacy_final_csv_path(owner_user, payment=payment)
    guests = Guests.query.filter_by(user_id=owner_user.id).order_by(Guests.id.asc()).all()
    existing_archive = EventArchive.query.filter_by(user_id=owner_user.id, csv_path=str(csv_path)).first()
    legacy_archive = EventArchive.query.filter_by(user_id=owner_user.id, csv_path=str(legacy_csv_path)).first()
    if legacy_archive and not existing_archive:
        legacy_archive.csv_path = str(csv_path)
        existing_archive = legacy_archive
    if not guests and csv_path.exists():
        archive = existing_archive or upsert_event_archive(owner_user, payment, csv_path, 0)
        move_previous_event_uploads(owner_user, payment=payment)
        db.session.commit()
        return archive
    if not guests:
        move_previous_event_uploads(owner_user, payment=payment)
        return existing_archive

    rows = build_guest_archive_rows(guests)
    write_final_csv(csv_path, rows)
    archive = upsert_event_archive(owner_user, payment, csv_path, len(rows), status="csv_ready")
    move_previous_event_uploads(owner_user, payment=payment)

    for guest in guests:
        db.session.delete(guest)
    db.session.commit()
    return archive


# Fungsi untuk backup semua client yang sudah melewati periode akhir.
def backup_expired_client_events(today=None):
    today = today or get_local_today()
    results = []
    for client, payment in get_expired_client_event_candidates(today=today):
        archive = ensure_final_guest_backup(client, payment=payment, today=today)
        if archive:
            results.append(archive)
    return results


# Fungsi untuk memindahkan file upload event milik semua client expired tanpa membuat arsip tar.gz.
def move_expired_client_uploads(today=None):
    today = today or get_local_today()
    results = []
    for client, payment in get_expired_client_event_candidates(today=today):
        moved_paths = move_previous_event_uploads(client, payment=payment)
        if moved_paths:
            results.append(
                {
                    "user_id": client.id,
                    "username": client.username,
                    "event_name": get_event_name(client, payment=payment),
                    "moved_paths": [str(path) for path in moved_paths],
                }
            )
    return results


# Fungsi untuk mencari CSV final terbaru milik client.
def get_latest_final_archive(owner_user):
    payment = get_latest_verified_payment(owner_user)
    csv_path = normalize_final_csv_path(owner_user, payment=payment) if payment else None
    archive = (
        EventArchive.query.filter(EventArchive.user_id == owner_user.id, EventArchive.csv_path.isnot(None))
        .order_by(EventArchive.period_end.desc(), EventArchive.id.desc())
        .first()
    )
    if archive and csv_path and Path(str(archive.csv_path)) == get_legacy_final_csv_path(owner_user, payment=payment):
        archive.csv_path = str(csv_path)
        db.session.commit()
    if archive and archive.csv_path and Path(archive.csv_path).exists():
        return archive

    if payment and csv_path and csv_path.exists():
        archive = upsert_event_archive(owner_user, payment, csv_path, 0)
        db.session.commit()
        return archive
    return None


# Fungsi untuk mengonversi CSV final menjadi workbook Excel in-memory.
def build_final_archive_excel(owner_user, archive=None):
    archive = archive or get_latest_final_archive(owner_user)
    if not archive or not archive.csv_path or not Path(archive.csv_path).exists():
        raise FileNotFoundError("File backup final belum tersedia.")

    dataframe = pd.read_csv(archive.csv_path, dtype=str).fillna("")
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        dataframe.to_excel(writer, index=False, sheet_name="Data Tamu")
    output.seek(0)
    return output


# Fungsi untuk memindahkan file upload event lama ke folder backup event.
def move_previous_event_uploads(owner_user, payment=None):
    upload_dir = Path(current_app.instance_path) / "uploads"
    if not upload_dir.exists():
        return []

    backup_dir = get_event_backup_dir(owner_user)
    event_prefix = clean_archive_filename_part(get_event_name(owner_user, payment=payment), "event")
    username_prefix = clean_archive_filename_part(getattr(owner_user, "username", ""), "client")
    filename_prefix = f"{event_prefix}_{username_prefix}_"
    moved_paths = []

    for upload_path in sorted(upload_dir.glob("*.xlsx")):
        if not upload_path.name.startswith(filename_prefix):
            continue

        destination = backup_dir / upload_path.name
        sequence = 2
        while destination.exists():
            destination = backup_dir / f"{upload_path.stem}_{sequence}{upload_path.suffix}"
            sequence += 1
        shutil.move(str(upload_path), destination)
        moved_paths.append(destination)

    return moved_paths


# Fungsi untuk membuat tar.gz dari seluruh file non-arsip di folder backup event.
def create_event_tar_archive(owner_user, payment=None):
    backup_dir = get_event_backup_dir(owner_user)
    tar_path = get_event_tar_path(owner_user, payment=payment)
    source_paths = sorted(
        path
        for path in backup_dir.iterdir()
        if path.is_file() and path != tar_path and not path.name.endswith(".tar.gz")
    )
    if not source_paths:
        return None

    temp_tar_path = tar_path.with_name(f".{tar_path.name}.tmp")
    if temp_tar_path.exists():
        temp_tar_path.unlink()

    expected_names = [path.name for path in source_paths]
    try:
        with tarfile.open(temp_tar_path, "w:gz") as archive:
            for source_path in source_paths:
                archive.add(source_path, arcname=source_path.name)

        with tarfile.open(temp_tar_path, "r:gz") as archive:
            archived_names = archive.getnames()
        if archived_names != expected_names:
            raise RuntimeError("Verifikasi arsip event gagal: daftar file tidak sesuai.")

        os.replace(temp_tar_path, tar_path)
        for source_path in source_paths:
            source_path.unlink()
    finally:
        if temp_tar_path.exists():
            temp_tar_path.unlink()

    return tar_path


# Fungsi untuk mengarsipkan event lama saat client aktivasi kembali.
def archive_previous_event_for_reactivation(owner_user, previous_payment=None, today=None):
    today = today or get_local_today()
    previous_payment = previous_payment or get_latest_verified_payment(owner_user)
    if not previous_payment or not previous_payment.period_end or previous_payment.period_end >= today:
        return None

    archive = ensure_final_guest_backup(owner_user, payment=previous_payment, today=today)
    move_previous_event_uploads(owner_user, payment=previous_payment)
    tar_path = create_event_tar_archive(owner_user, payment=previous_payment)
    if archive and tar_path:
        archive.tar_path = str(tar_path)
        archive.status = "tar_ready"
        archive.archived_at = datetime.now(APP_TIMEZONE).replace(tzinfo=None)
        db.session.commit()
    return tar_path
