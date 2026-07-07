import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import app as app_module
from models import Staff, User
from services import attendance_service, logging_service


class AttendanceServiceTest(unittest.TestCase):
    # Fungsi untuk menyiapkan folder log sementara bagi event attendance.
    def setUp(self):
        self.original_log_dir = logging_service.ACTIVITY_LOG_DIR
        self.original_file_prefix = logging_service.ACTIVITY_LOG_FILE_PREFIX
        self.temp_dir = tempfile.TemporaryDirectory()
        logging_service.configure_activity_log(Path(self.temp_dir.name), "activity")

    # Fungsi untuk mengembalikan konfigurasi log setelah test.
    def tearDown(self):
        logging_service.configure_activity_log(self.original_log_dir, self.original_file_prefix)
        self.temp_dir.cleanup()

    # Fungsi untuk memastikan format waktu kehadiran memakai singkatan bulan lokal.
    def test_format_attendance_time(self):
        value = datetime(2026, 5, 28, 18, 25, 12)
        june_value = datetime(2026, 6, 5, 18, 0, 0)

        self.assertEqual(attendance_service.format_attendance_time(value), "28-Mei 18:25")
        self.assertEqual(attendance_service.format_attendance_time(june_value), "05-Jun 18:00")
        self.assertEqual(attendance_service.format_attendance_time(None), "")

    # Fungsi untuk memastikan token attendance membawa owner id.
    def test_build_guest_attendance_token_contains_owner_id(self):
        owner = SimpleNamespace(id=42, attendance_token_nonce="nonce-123")

        with app_module.app.app_context():
            token = attendance_service.build_guest_attendance_token(owner)
            payload = attendance_service.get_attendance_token_serializer().loads(token)

        self.assertEqual(payload["owner_user_id"], 42)
        self.assertEqual(payload["nonce"], "nonce-123")

    # Fungsi untuk memastikan token attendance belum dibuat jika client belum punya nonce.
    def test_build_guest_attendance_token_requires_nonce(self):
        owner = SimpleNamespace(id=42, attendance_token_nonce=None)

        with app_module.app.app_context():
            token = attendance_service.build_guest_attendance_token(owner)

        self.assertEqual(token, "")

    # Fungsi untuk memastikan token attendance staff resolve ke staff dan owner client.
    def test_build_staff_attendance_token_resolves_staff_and_owner(self):
        with app_module.app.app_context():
            User.query.filter_by(username="staff_attendance_token_owner").delete()
            app_module.db.session.commit()

            owner = User()
            owner.username = "staff_attendance_token_owner"
            owner.nama = "Staff Attendance Token Owner"
            owner.email = "staff_attendance_token_owner@example.com"
            owner.no_hp = 628120050001
            owner.role = app_module.ROLE_USER
            app_module.db.session.add(owner)
            app_module.db.session.commit()

            staff = Staff()
            staff.owner_user_id = owner.id
            staff.nama = "Staff Token"
            staff.no_hp = "628120050002"
            staff.attendance_token_nonce = "staff-token-nonce"
            app_module.db.session.add(staff)
            app_module.db.session.commit()

            token = attendance_service.build_staff_attendance_token(staff)
            resolved_staff = attendance_service.get_attendance_staff_from_token(token)
            resolved_owner = attendance_service.get_attendance_owner_from_token(token)

            self.assertEqual(resolved_staff.id, staff.id)
            self.assertEqual(resolved_owner.id, owner.id)

            app_module.db.session.delete(staff)
            app_module.db.session.delete(owner)
            app_module.db.session.commit()

    # Fungsi untuk memastikan QR Client PNG memakai format gambar besar yang siap cetak.
    def test_build_guest_attendance_qr_png_creates_large_png(self):
        png_data = attendance_service.build_guest_attendance_qr_png("https://example.com/kehadiran/token-test")

        self.assertEqual(png_data[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(png_data[12:16], b"IHDR")
        width = int.from_bytes(png_data[16:20], "big")
        height = int.from_bytes(png_data[20:24], "big")
        self.assertEqual(width, height)
        self.assertGreaterEqual(width, 2200)

    # Fungsi untuk memastikan token lama invalid setelah nonce client diperbarui.
    def test_get_attendance_owner_from_token_rejects_old_nonce(self):
        with app_module.app.app_context():
            User.query.filter_by(username="attendance_nonce_test").delete()
            app_module.db.session.commit()

            owner = User()
            owner.username = "attendance_nonce_test"
            owner.nama = "Attendance Nonce Test"
            owner.email = "attendance_nonce_test@example.com"
            owner.no_hp = 6281200001999
            owner.role = app_module.ROLE_USER
            owner.attendance_token_nonce = "old-nonce"
            app_module.db.session.add(owner)
            app_module.db.session.commit()
            token = attendance_service.build_guest_attendance_token(owner)

            owner.attendance_token_nonce = "new-nonce"
            app_module.db.session.commit()

            resolved_owner = attendance_service.get_attendance_owner_from_token(token)

            app_module.db.session.delete(owner)
            app_module.db.session.commit()

        self.assertIsNone(resolved_owner)

    # Fungsi untuk memastikan verifikasi nomor kosong menghasilkan status tidak terdaftar.
    def test_verify_guest_attendance_rejects_empty_clean_phone(self):
        owner = SimpleNamespace(id=42, username="client")

        original_is_active = attendance_service.is_owner_in_active_billing_period
        original_find_active_request = attendance_service.find_active_attendance_request
        original_create_request = attendance_service.create_attendance_verification_request
        attendance_service.is_owner_in_active_billing_period = lambda _owner: True
        attendance_service.find_active_attendance_request = lambda *_args, **_kwargs: None
        attendance_service.create_attendance_verification_request = lambda *_args, **_kwargs: SimpleNamespace(id=1)
        try:
            result = attendance_service.verify_guest_attendance(owner, "abc", lambda value: "")
        finally:
            attendance_service.is_owner_in_active_billing_period = original_is_active
            attendance_service.find_active_attendance_request = original_find_active_request
            attendance_service.create_attendance_verification_request = original_create_request

        self.assertEqual(result["status"], "not_registered")
        self.assertEqual(result["no_hp"], "abc")
        self.assertIn("Tidak Terdaftar", result["message"])


if __name__ == "__main__":
    unittest.main()
