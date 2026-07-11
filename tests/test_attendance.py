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

            staff = Staff()
            staff.owner_user_id = owner.id
            staff.nama = f"Staff {username}"
            staff.no_hp = str(no_hp + 100000)
            staff.attendance_token_nonce = f"staff-nonce-{username}"
            app_module.db.session.add(staff)
            app_module.db.session.commit()

            token = app_module.attendance_service.build_staff_attendance_token(staff)
            self.created_usernames.append(username)
            return owner.id, guest.id, token, staff.id

    # Fungsi untuk menguji landing page menolak token kehadiran yang tidak valid.
    def test_attendance_landing_rejects_invalid_token(self):
        response = self.client.get("/kehadiran/not-a-valid-token")

        self.assertEqual(response.status_code, 404)
        self.assertIn("Link verifikasi tidak valid.", response.get_data(as_text=True))

    # Fungsi untuk memastikan landing verifikasi menampilkan nama event, bukan nama client.
    def test_attendance_landing_shows_event_name_not_client_name(self):
        owner_id, _, attendance_token, _ = self.create_active_attendance_owner("attendance_event_client", 628120040006)

        with app_module.app.app_context():
            owner = app_module.db.session.get(User, owner_id)
            owner_name = owner.nama

        response = self.client.get(f"/kehadiran/{attendance_token}")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Event attendance_event_client", html)
        self.assertNotIn(owner_name, html)

    # Fungsi untuk memastikan route attendance sudah terdaftar melalui Blueprint.
    def test_attendance_routes_use_blueprint_endpoints(self):
        endpoints = {rule.endpoint for rule in app_module.app.url_map.iter_rules()}

        self.assertIn("attendance.guest_attendance_landing", endpoints)
        self.assertIn("attendance.guest_attendance_qr_image", endpoints)
        self.assertIn("attendance.guest_attendance_qr_download", endpoints)
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

    # Fungsi untuk memastikan download QR Client PNG berisi URL halaman verifikasi kehadiran.
    def test_attendance_client_qr_download_contains_attendance_landing_url(self):
        _, _, attendance_token, staff_id = self.create_active_attendance_owner("attendance_qr_client", 628120040004)
        captured = {}
        original_build_guest_attendance_qr_png = app_module.attendance_service.build_guest_attendance_qr_png
        try:

            # Fungsi test helper untuk menangkap nilai yang dimasukkan ke QR.
            def fake_build_guest_attendance_qr_png(qr_value):
                captured["value"] = qr_value
                return b"\x89PNG\r\n\x1a\nfake-png"

            app_module.attendance_service.build_guest_attendance_qr_png = fake_build_guest_attendance_qr_png
            response = self.client.get(f"/kehadiran/{attendance_token}/qr.png")
        finally:
            app_module.attendance_service.build_guest_attendance_qr_png = original_build_guest_attendance_qr_png

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/png")
        self.assertEqual(response.get_data()[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(response.headers["Content-Disposition"], f'attachment; filename="qr-staff-{staff_id}.png"')
        self.assertIn(f"/kehadiran/{attendance_token}", captured["value"])
        self.assertNotIn("/qr.png", captured["value"])

        legacy_response = self.client.get(f"/kehadiran/{attendance_token}/qr.svg")
        self.assertEqual(legacy_response.status_code, 302)
        self.assertIn(f"/kehadiran/{attendance_token}/qr.png", legacy_response.headers["Location"])

    # Fungsi untuk memastikan halaman tamu menunggu staff lalu memuat hasil sukses.
    def test_attendance_guest_waits_for_staff_confirmation_result_page(self):
        _, guest_id, attendance_token, staff_id = self.create_active_attendance_owner(
            "attendance_wait_client",
            628120040001,
        )

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
            staff = app_module.db.session.get(Staff, staff_id)
            confirm_result = app_module.confirm_attendance_verification_request(
                staff,
                response.json["verification_request_id"],
                4,
            )
            guest = app_module.db.session.get(Guests, guest_id)
            guest_count = guest.jumlah_orang

        self.assertEqual(confirm_result["status"], "confirmed")
        self.assertEqual(confirm_result["jumlah_orang"], 4)
        self.assertEqual(guest_count, 4)

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

    # Fungsi untuk memastikan request dari QR staff hanya muncul pada staff pemilik QR.
    def test_attendance_staff_qr_notification_is_targeted_to_owner_staff(self):
        owner_id, _, attendance_token, staff_id = self.create_active_attendance_owner(
            "attendance_target_staff_client",
            628120040005,
        )

        response = self.client.post(
            f"/kehadiran/{attendance_token}/verify",
            json={"no_hp": "081234567890"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "pending_confirmation")

        with app_module.app.app_context():
            target_staff = app_module.db.session.get(Staff, staff_id)
            other_staff = Staff()
            other_staff.owner_user_id = owner_id
            other_staff.nama = "Staff Other"
            other_staff.no_hp = "6281299993333"
            app_module.db.session.add(other_staff)
            app_module.db.session.commit()

            target_notification = app_module.get_staff_attendance_notification(target_staff)
            other_notification = app_module.get_staff_attendance_notification(other_staff)

        self.assertIsNotNone(target_notification)
        self.assertEqual(target_notification["id"], response.json["verification_request_id"])
        self.assertEqual(target_notification["target_staff_id"], staff_id)
        self.assertEqual(target_notification["guest"]["jumlah_orang"], 1)
        self.assertIsNone(other_notification)

    # Fungsi untuk memastikan request yang expired tampil sebagai waktu habis pada halaman tamu.
    def test_attendance_guest_request_expired_result_page(self):
        _, _, attendance_token, _ = self.create_active_attendance_owner("attendance_expired_client", 628120040002)

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
        _, _, attendance_token, staff_id = self.create_active_attendance_owner("attendance_rejected_client", 628120040003)

        response = self.client.post(
            f"/kehadiran/{attendance_token}/verify",
            json={"no_hp": "081234567890"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "pending_confirmation")

        with app_module.app.app_context():
            staff = app_module.db.session.get(Staff, staff_id)
            reject_result = app_module.reject_attendance_verification_request(
                staff,
                response.json["verification_request_id"],
            )

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
