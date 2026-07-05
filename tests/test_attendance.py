import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import app as app_module
from models import AttendanceVerificationRequest, BillingPayment, Guests, Staff, User


class AttendanceRouteTest(unittest.TestCase):
    # Fungsi untuk menyiapkan test client dengan log diarahkan ke folder sementara.
    def setUp(self):
        self.original_log_dir = app_module.ACTIVITY_LOG_DIR
        self.temp_dir = tempfile.TemporaryDirectory()
        app_module.ACTIVITY_LOG_DIR = Path(self.temp_dir.name)
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()
        self.created_usernames = []

    # Fungsi untuk membersihkan konfigurasi test setelah setiap skenario.
    def tearDown(self):
        with app_module.app.app_context():
            for username in self.created_usernames:
                account = User.query.filter_by(username=username).first()
                if account:
                    AttendanceVerificationRequest.query.filter_by(owner_user_id=account.id).delete()
                    Staff.query.filter_by(owner_user_id=account.id).delete()
                    BillingPayment.query.filter_by(user_id=account.id).delete()
                    Guests.query.filter_by(user_id=account.id).delete()
                    app_module.db.session.delete(account)
            app_module.db.session.commit()
        app_module.ACTIVITY_LOG_DIR = self.original_log_dir
        self.temp_dir.cleanup()

    # Fungsi untuk membuat client aktif dan token halaman verifikasi tamu.
    def create_active_attendance_owner(self, username, no_hp):
        with app_module.app.app_context():
            existing = User.query.filter_by(username=username).first()
            if existing:
                AttendanceVerificationRequest.query.filter_by(owner_user_id=existing.id).delete()
                Staff.query.filter_by(owner_user_id=existing.id).delete()
                BillingPayment.query.filter_by(user_id=existing.id).delete()
                Guests.query.filter_by(user_id=existing.id).delete()
                app_module.db.session.delete(existing)
            User.query.filter_by(no_hp=no_hp).delete()
            app_module.db.session.commit()

            owner = User()
            owner.username = username
            owner.nama = username.replace("_", " ").title()
            owner.email = f"{username}@example.com"
            owner.no_hp = no_hp
            owner.role = app_module.ROLE_USER
            owner.attendance_token_nonce = f"nonce-{username}"
            app_module.db.session.add(owner)
            app_module.db.session.commit()

            payment = BillingPayment()
            payment.user_id = owner.id
            payment.payment_date = date.today()
            payment.amount = 100000
            payment.package_name = app_module.PACKAGE_PREMIUM
            payment.period_start = date.today() - timedelta(days=1)
            payment.period_end = date.today() + timedelta(days=1)
            payment.event_name = f"Event {username}"
            payment.status = "verified"
            app_module.db.session.add(payment)
            app_module.db.session.commit()

            guest = Guests()
            guest.no = 1
            guest.nama = "Budi Attendance"
            guest.no_hp = "6281234567890"
            guest.email = f"{username}_guest@example.com"
            guest.status = app_module.DEFAULT_GUEST_STATUS
            guest.user_id = owner.id
            app_module.db.session.add(guest)
            app_module.db.session.commit()

            token = app_module.build_guest_attendance_token(owner)
            self.created_usernames.append(username)
            return owner.id, guest.id, token

    # Fungsi untuk menguji landing page menolak token kehadiran yang tidak valid.
    def test_attendance_landing_rejects_invalid_token(self):
        response = self.client.get("/kehadiran/not-a-valid-token")

        self.assertEqual(response.status_code, 404)
        self.assertIn("Link verifikasi tidak valid.", response.get_data(as_text=True))

    # Fungsi untuk memastikan route attendance sudah terdaftar melalui Blueprint.
    def test_attendance_routes_use_blueprint_endpoints(self):
        endpoints = {rule.endpoint for rule in app_module.app.url_map.iter_rules()}

        self.assertIn("attendance.guest_attendance_landing", endpoints)
        self.assertIn("attendance.guest_attendance_qr_image", endpoints)
        self.assertIn("attendance.verify_guest_attendance_route", endpoints)
        self.assertIn("attendance.guest_attendance_request_status", endpoints)
        self.assertIn("attendance.guest_attendance_request_result", endpoints)
        self.assertIn("attendance.guest_qr_page", endpoints)
        self.assertIn("attendance.guest_qr_image", endpoints)
        self.assertIn("attendance.guest_qr_status", endpoints)

    # Fungsi untuk menguji API verifikasi menolak token kehadiran yang tidak valid.
    def test_attendance_verify_rejects_invalid_token(self):
        response = self.client.post(
            "/kehadiran/not-a-valid-token/verify",
            json={"no_hp": "08123456789"},
            headers={"X-Client-Request-ID": "test-client-request"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json["status"], "invalid_link")
        self.assertEqual(response.json["client_request_id"], "test-client-request")

    # Fungsi untuk memastikan QR Client berisi URL halaman verifikasi kehadiran.
    def test_attendance_client_qr_image_contains_attendance_landing_url(self):
        _, _, attendance_token = self.create_active_attendance_owner("attendance_qr_client", 628120040004)
        captured = {}
        original_build_guest_qr_svg = app_module.attendance_service.build_guest_qr_svg
        try:

            # Fungsi test helper untuk menangkap nilai yang dimasukkan ke QR.
            def fake_build_guest_qr_svg(qr_value):
                captured["value"] = qr_value
                return b"<svg></svg>"

            app_module.attendance_service.build_guest_qr_svg = fake_build_guest_qr_svg
            response = self.client.get(f"/kehadiran/{attendance_token}/qr.svg")
        finally:
            app_module.attendance_service.build_guest_qr_svg = original_build_guest_qr_svg

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/svg+xml")
        self.assertIn("<svg", response.get_data(as_text=True))
        self.assertIn(f"/kehadiran/{attendance_token}", captured["value"])
        self.assertNotIn("/qr.svg", captured["value"])

    # Fungsi untuk memastikan halaman tamu menunggu staff lalu memuat hasil sukses.
    def test_attendance_guest_waits_for_staff_confirmation_result_page(self):
        owner_id, _, attendance_token = self.create_active_attendance_owner("attendance_wait_client", 628120040001)

        response = self.client.post(
            f"/kehadiran/{attendance_token}/verify",
            json={"no_hp": "081234567890"},
            headers={"X-Client-Request-ID": "test-wait-request"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "pending_confirmation")
        self.assertIn("verification_request_id", response.json)
        self.assertIn("/status", response.json["status_url"])
        self.assertIn("/result", response.json["result_url"])

        pending_status = self.client.get(response.json["status_url"])
        self.assertEqual(pending_status.status_code, 200)
        self.assertEqual(pending_status.json["status"], "pending")
        self.assertEqual(pending_status.json["message"], "Harap Tunggu Sebentar, Data Sedang Diverifikasi")

        with app_module.app.app_context():
            staff = Staff()
            staff.owner_user_id = owner_id
            staff.nama = "Staff Attendance"
            staff.no_hp = "6281299991111"
            app_module.db.session.add(staff)
            app_module.db.session.commit()
            confirm_result = app_module.confirm_attendance_verification_request(
                staff,
                response.json["verification_request_id"],
            )

        self.assertEqual(confirm_result["status"], "confirmed")

        confirmed_status = self.client.get(response.json["status_url"])
        self.assertEqual(confirmed_status.status_code, 200)
        self.assertEqual(confirmed_status.json["status"], "confirmed")

        result_page = self.client.get(response.json["result_url"])
        result_html = result_page.get_data(as_text=True)
        self.assertEqual(result_page.status_code, 200)
        self.assertIn("Selamat Datang Bpk/Ibu Budi Attendance", result_html)
        self.assertNotIn("attendanceResultModal", result_html)
        self.assertNotIn("Request ID", result_html)
        self.assertNotIn("Kode pemeriksaan", result_html)

    # Fungsi untuk memastikan request yang expired tampil sebagai waktu habis pada halaman tamu.
    def test_attendance_guest_request_expired_result_page(self):
        _, _, attendance_token = self.create_active_attendance_owner("attendance_expired_client", 628120040002)

        response = self.client.post(
            f"/kehadiran/{attendance_token}/verify",
            json={"no_hp": "081234567890"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "pending_confirmation")

        with app_module.app.app_context():
            verification_request = app_module.db.session.get(
                AttendanceVerificationRequest,
                response.json["verification_request_id"],
            )
            verification_request.expires_at = app_module.attendance_service.get_current_naive_datetime() - timedelta(
                seconds=1
            )
            app_module.db.session.commit()

        expired_status = self.client.get(response.json["status_url"])
        self.assertEqual(expired_status.status_code, 200)
        self.assertEqual(expired_status.json["status"], "expired")
        self.assertEqual(expired_status.json["message"], "Waktu Habis, Nomor Tidak Berhasil Diverifikasi")

        result_page = self.client.get(response.json["result_url"])
        result_html = result_page.get_data(as_text=True)
        self.assertEqual(result_page.status_code, 200)
        self.assertIn("Waktu Habis, Nomor Tidak Berhasil Diverifikasi", result_html)
        self.assertNotIn("Request ID", result_html)
        self.assertNotIn("Kode pemeriksaan", result_html)

    # Fungsi untuk memastikan semua staff yang menutup request memakai pesan gagal verifikasi khusus.
    def test_attendance_guest_all_staff_closed_request_result_page(self):
        owner_id, _, attendance_token = self.create_active_attendance_owner("attendance_rejected_client", 628120040003)

        response = self.client.post(
            f"/kehadiran/{attendance_token}/verify",
            json={"no_hp": "081234567890"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "pending_confirmation")

        with app_module.app.app_context():
            staff = Staff()
            staff.owner_user_id = owner_id
            staff.nama = "Staff Reject"
            staff.no_hp = "6281299992222"
            app_module.db.session.add(staff)
            app_module.db.session.commit()

            original_get_active_staff_ids = app_module.attendance_service.get_active_staff_ids_for_owner
            app_module.attendance_service.get_active_staff_ids_for_owner = lambda _owner_id: [staff.id]
            try:
                reject_result = app_module.reject_attendance_verification_request(
                    staff,
                    response.json["verification_request_id"],
                )
            finally:
                app_module.attendance_service.get_active_staff_ids_for_owner = original_get_active_staff_ids

        self.assertEqual(reject_result["status"], "rejected")

        rejected_status = self.client.get(response.json["status_url"])
        self.assertEqual(rejected_status.status_code, 200)
        self.assertEqual(rejected_status.json["status"], "expired")
        self.assertEqual(
            rejected_status.json["message"],
            "Nomor Tidak Berhasil Diverifikasi, Harap Hubungi Staff",
        )

        result_page = self.client.get(response.json["result_url"])
        result_html = result_page.get_data(as_text=True)
        self.assertEqual(result_page.status_code, 200)
        self.assertIn("Nomor Tidak Berhasil Diverifikasi, Harap Hubungi Staff", result_html)
        self.assertNotIn("Waktu Habis, Nomor Tidak Berhasil Diverifikasi", result_html)


if __name__ == "__main__":
    unittest.main()
