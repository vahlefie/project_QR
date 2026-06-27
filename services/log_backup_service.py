from dataclasses import dataclass
from datetime import date
from pathlib import Path
import os
import re
import tarfile

from constants import ACTIVITY_LOG_DIR, ACTIVITY_LOG_FILE_PREFIX

INDONESIAN_MONTH_SLUGS = {
    1: "januari",
    2: "februari",
    3: "maret",
    4: "april",
    5: "mei",
    6: "juni",
    7: "juli",
    8: "agustus",
    9: "september",
    10: "oktober",
    11: "november",
    12: "desember",
}

LOG_FILE_PATTERN = re.compile(r"^(?P<prefix>[A-Za-z0-9_-]+)_(?P<date>\d{4}-\d{2}-\d{2})\.log$")


@dataclass(frozen=True)
class LogBackupResult:
    archive_path: Path
    target_year: int
    target_month: int
    archived_files: tuple[str, ...]
    deleted_files: tuple[str, ...]
    status: str


# Fungsi untuk mengambil tahun dan bulan sebelumnya dari tanggal acuan.
def get_previous_month(reference_date=None):
    reference_date = reference_date or date.today()
    if reference_date.month == 1:
        return reference_date.year - 1, 12
    return reference_date.year, reference_date.month - 1


# Fungsi untuk membuat slug bulan bahasa Indonesia.
def get_month_slug(month_number):
    return INDONESIAN_MONTH_SLUGS[month_number]


# Fungsi untuk membaca tanggal dari nama file log harian.
def parse_log_file_date(log_path, file_prefix=ACTIVITY_LOG_FILE_PREFIX):
    match = LOG_FILE_PATTERN.fullmatch(log_path.name)
    if not match or match.group("prefix") != file_prefix:
        return None

    try:
        return date.fromisoformat(match.group("date"))
    except ValueError:
        return None


# Fungsi untuk mencari file log pada bulan target.
def find_monthly_log_files(log_dir, target_year, target_month, file_prefix=ACTIVITY_LOG_FILE_PREFIX):
    log_dir = Path(log_dir)
    if not log_dir.exists():
        return []

    monthly_logs = []
    for log_path in log_dir.iterdir():
        if not log_path.is_file():
            continue

        log_date = parse_log_file_date(log_path, file_prefix=file_prefix)
        if log_date and log_date.year == target_year and log_date.month == target_month:
            monthly_logs.append(log_path)

    return sorted(monthly_logs, key=lambda item: item.name)


# Fungsi untuk memastikan file target tetap berada di folder log.
def ensure_paths_inside_log_dir(log_dir, log_paths):
    resolved_log_dir = Path(log_dir).resolve()
    for log_path in log_paths:
        resolved_path = log_path.resolve()
        if resolved_path.parent != resolved_log_dir:
            raise ValueError(f"Path log di luar folder logs: {log_path}")


# Fungsi untuk membuat arsip tar.gz dan memverifikasi isinya.
def create_log_archive(archive_path, month_slug, log_paths):
    archive_path = Path(archive_path)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    temp_archive_path = archive_path.with_name(f".{archive_path.name}.tmp")
    if temp_archive_path.exists():
        temp_archive_path.unlink()

    expected_names = [f"{month_slug}/{log_path.name}" for log_path in log_paths]
    try:
        with tarfile.open(temp_archive_path, "w:gz") as archive:
            for log_path, archive_name in zip(log_paths, expected_names):
                archive.add(log_path, arcname=archive_name)

        with tarfile.open(temp_archive_path, "r:gz") as archive:
            archived_names = archive.getnames()
        if archived_names != expected_names:
            raise RuntimeError("Verifikasi arsip gagal: daftar file tidak sesuai.")

        os.replace(temp_archive_path, archive_path)
    finally:
        if temp_archive_path.exists():
            temp_archive_path.unlink()


# Fungsi untuk backup log bulan tertentu ke arsip tahunan.
def backup_monthly_logs(
    log_dir=ACTIVITY_LOG_DIR,
    backup_root=None,
    target_year=None,
    target_month=None,
    file_prefix=ACTIVITY_LOG_FILE_PREFIX,
    reference_date=None,
):
    log_dir = Path(log_dir)
    backup_root = Path(backup_root) if backup_root else log_dir.parent / "backup" / "log"

    if target_year is None or target_month is None:
        target_year, target_month = get_previous_month(reference_date)

    month_slug = get_month_slug(target_month)
    archive_path = backup_root / str(target_year) / f"{month_slug}.tar.gz"
    log_paths = find_monthly_log_files(log_dir, target_year, target_month, file_prefix=file_prefix)

    if not log_paths:
        return LogBackupResult(
            archive_path=archive_path,
            target_year=target_year,
            target_month=target_month,
            archived_files=(),
            deleted_files=(),
            status="no_logs",
        )

    ensure_paths_inside_log_dir(log_dir, log_paths)
    create_log_archive(archive_path, month_slug, log_paths)

    deleted_files = []
    for log_path in log_paths:
        log_path.unlink()
        deleted_files.append(log_path.name)

    return LogBackupResult(
        archive_path=archive_path,
        target_year=target_year,
        target_month=target_month,
        archived_files=tuple(log_path.name for log_path in log_paths),
        deleted_files=tuple(deleted_files),
        status="archived",
    )
