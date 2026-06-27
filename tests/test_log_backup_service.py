from datetime import date
import tarfile
import tempfile
import unittest
from pathlib import Path

from services import log_backup_service


class LogBackupServiceTest(unittest.TestCase):
    # Fungsi untuk menyiapkan folder log sementara.
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_dir = Path(self.temp_dir.name)
        self.log_dir = self.root_dir / "logs"
        self.log_dir.mkdir()

    # Fungsi untuk membersihkan folder log sementara.
    def tearDown(self):
        self.temp_dir.cleanup()

    # Fungsi untuk membuat file log test.
    def write_log(self, filename, content="log"):
        log_path = self.log_dir / filename
        log_path.write_text(content, encoding="utf-8")
        return log_path

    # Fungsi untuk memastikan log bulan sebelumnya diarsipkan lalu dihapus dari logs.
    def test_backup_previous_month_archives_and_deletes_old_logs(self):
        self.write_log("activity_2026-05-22.log", "may-22")
        self.write_log("activity_2026-05-31.log", "may-31")
        self.write_log("activity_2026-06-01.log", "june-01")
        self.write_log("notes.txt", "ignored")

        result = log_backup_service.backup_monthly_logs(
            log_dir=self.log_dir,
            reference_date=date(2026, 6, 1),
        )

        archive_path = self.root_dir / "backup" / "log" / "2026" / "mei.tar.gz"
        self.assertEqual(result.status, "archived")
        self.assertEqual(result.archive_path, archive_path)
        self.assertTrue(archive_path.exists())
        self.assertFalse((self.log_dir / "activity_2026-05-22.log").exists())
        self.assertFalse((self.log_dir / "activity_2026-05-31.log").exists())
        self.assertTrue((self.log_dir / "activity_2026-06-01.log").exists())
        self.assertTrue((self.log_dir / "notes.txt").exists())

        with tarfile.open(archive_path, "r:gz") as archive:
            self.assertEqual(
                archive.getnames(),
                [
                    "mei/activity_2026-05-22.log",
                    "mei/activity_2026-05-31.log",
                ],
            )

    # Fungsi untuk memastikan retry aman saat log bulan sebelumnya sudah bersih.
    def test_backup_previous_month_is_noop_after_success(self):
        self.write_log("activity_2026-05-22.log")
        first_result = log_backup_service.backup_monthly_logs(
            log_dir=self.log_dir,
            reference_date=date(2026, 6, 1),
        )
        second_result = log_backup_service.backup_monthly_logs(
            log_dir=self.log_dir,
            reference_date=date(2026, 6, 1),
        )

        self.assertEqual(first_result.status, "archived")
        self.assertEqual(second_result.status, "no_logs")
        self.assertEqual(second_result.archive_path, self.root_dir / "backup" / "log" / "2026" / "mei.tar.gz")

    # Fungsi untuk memastikan backup Januari mengarah ke Desember tahun sebelumnya.
    def test_previous_month_handles_year_boundary(self):
        self.write_log("activity_2025-12-31.log")

        result = log_backup_service.backup_monthly_logs(
            log_dir=self.log_dir,
            reference_date=date(2026, 1, 1),
        )

        self.assertEqual(result.status, "archived")
        self.assertEqual(result.archive_path, self.root_dir / "backup" / "log" / "2025" / "desember.tar.gz")


if __name__ == "__main__":
    unittest.main()
