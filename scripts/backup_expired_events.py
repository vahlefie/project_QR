from argparse import ArgumentParser
from datetime import date
from pathlib import Path
import json
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import app  # noqa: E402
from services.event_archive_service import backup_expired_client_events, move_expired_client_uploads  # noqa: E402


# Fungsi untuk membaca tanggal ISO dari argumen CLI.
def parse_iso_date(value):
    if not value:
        return None
    return date.fromisoformat(value)


# Fungsi untuk membangun argumen CLI backup event expired.
def build_parser():
    parser = ArgumentParser(description="Backup final data tamu client yang sudah melewati periode akhir.")
    parser.add_argument("--date", default=None, help="Tanggal acuan format YYYY-MM-DD. Default: hari ini.")
    parser.add_argument(
        "--uploads-only",
        action="store_true",
        help="Hanya pindahkan file upload event client expired tanpa membuat CSV final.",
    )
    return parser


# Fungsi entry point CLI backup event expired.
def main(argv=None):
    args = build_parser().parse_args(argv)
    with app.app_context():
        today = parse_iso_date(args.date)
        if args.uploads_only:
            archives = []
            moved_uploads = move_expired_client_uploads(today=today)
        else:
            archives = backup_expired_client_events(today=today)
            moved_uploads = []
        payload = {
            "status": "ok",
            "archived_count": len(archives),
            "archives": [
                {
                    "user_id": archive.user_id,
                    "event_name": archive.event_name,
                    "csv_path": archive.csv_path,
                    "guest_count": archive.guest_count,
                }
                for archive in archives
            ],
        }
        if args.uploads_only:
            payload["moved_upload_count"] = sum(len(result["moved_paths"]) for result in moved_uploads)
            payload["moved_uploads"] = moved_uploads
        print(
            json.dumps(
                payload,
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
