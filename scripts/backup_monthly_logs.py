from argparse import ArgumentParser
from datetime import date
from pathlib import Path
import json
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from constants import ACTIVITY_LOG_DIR, ACTIVITY_LOG_FILE_PREFIX  # noqa: E402
from services.log_backup_service import backup_monthly_logs  # noqa: E402


# Fungsi untuk membaca tanggal ISO dari argumen CLI.
def parse_iso_date(value):
    if not value:
        return None
    return date.fromisoformat(value)


# Fungsi untuk membangun argumen CLI backup log bulanan.
def build_parser():
    parser = ArgumentParser(description="Backup log bulan sebelumnya ke arsip tar.gz.")
    parser.add_argument("--log-dir", default=str(ACTIVITY_LOG_DIR), help="Folder sumber log harian.")
    parser.add_argument(
        "--backup-root",
        default=None,
        help="Folder root backup. Default: backup/log, menghasilkan backup/log/YYYY/bulan.tar.gz.",
    )
    parser.add_argument("--file-prefix", default=ACTIVITY_LOG_FILE_PREFIX, help="Prefix nama file log.")
    parser.add_argument("--date", default=None, help="Tanggal acuan format YYYY-MM-DD. Default: hari ini.")
    return parser


# Fungsi entry point CLI backup log bulanan.
def main(argv=None):
    args = build_parser().parse_args(argv)
    result = backup_monthly_logs(
        log_dir=Path(args.log_dir),
        backup_root=Path(args.backup_root) if args.backup_root else None,
        file_prefix=args.file_prefix,
        reference_date=parse_iso_date(args.date),
    )
    print(
        json.dumps(
            {
                "status": result.status,
                "archive_path": str(result.archive_path),
                "target_year": result.target_year,
                "target_month": result.target_month,
                "archived_files": list(result.archived_files),
                "deleted_files": list(result.deleted_files),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
