import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import app as app_module
from constants import SESSION_ACTIVE_TOKEN_KEY, SESSION_LAST_ACTIVITY_KEY
from models import AttendanceVerificationRequest, BillingPayment, Guests, Staff, User


class GuestQrTest(unittest.TestCase):
    # Fungsi untuk menyiapkan test client dengan log diarahkan ke folder sementara.
    def setUp(self):
        self.original_log_dir = app_module.ACTIVITY_LOG_DIR
        self.temp_dir = tempfile.TemporaryDirectory()
        app_module.ACTIVITY_LOG_DIR = Path(self.temp_dir.name)
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()
        self.created_usernames = []

    # Fungsi untuk membersihkan data test dan konfigurasi log.
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

    # Fungsi untuk membuat client test.
    def create_client_account(self, username, paket, no_hp):
        with app_module.app.app_context():
            existing = User.query.filter_by(username=username).first()
            if existing:
                Guests.query.filter_by(user_id=existing.id).delete()
                app_module.db.session.delete(existing)
                app_module.db.session.commit()
            User.query.filter_by(no_hp=no_hp).delete()
            app_module.db.session.commit()

            account = User()
            account.username = username
            account.nama = username.replace("_", " ").title()
            account.email = f"{username}@example.com"
            account.no_hp = no_hp
            account.role = app_module.ROLE_USER
            account.paket = paket
            account.active_session_token = f"active-{username}"
            app_module.db.session.add(account)
            app_module.db.session.commit()
            payment = BillingPayment()
            payment.user_id = account.id
            payment.payment_date = date.today()
            payment.amount = 100000
            payment.package_name = paket
            payment.period_start = date.today() - timedelta(days=1)
            payment.period_end = date.today() + timedelta(days=1)
            payment.event_name = f"Event {username}"
            payment.status = "verified"
            app_module.db.session.add(payment)
            app_module.db.session.commit()
            self.created_usernames.append(username)
            return account.id, account.active_session_token

    # Fungsi untuk membuat tamu test.
    def create_guest(self, owner_user_id, nama="Budi QR"):
        with app_module.app.app_context():
            guest = Guests()
            guest.no = 1
            guest.nama = nama
            guest.no_hp = "6281234567890"
            guest.email = f"{owner_user_id}_qr_guest@example.com"
            guest.status = app_module.DEFAULT_GUEST_STATUS
            guest.user_id = owner_user_id
            app_module.db.session.add(guest)
            app_module.db.session.commit()
            return guest.id

    # Fungsi untuk membuat session login client aktif.
    def login_as_user(self, username, active_session_token):
        with self.client.session_transaction() as session:
            session["user"] = username
            session["role"] = app_module.ROLE_USER
            session[SESSION_ACTIVE_TOKEN_KEY] = active_session_token
            session[SESSION_LAST_ACTIVITY_KEY] = app_module.auth_service.get_current_timestamp()

    # Fungsi untuk memastikan route QR publik dan gambar SVG tersedia untuk tamu Premium.
    def test_premium_guest_qr_page_and_image_routes(self):
        owner_user_id, _ = self.create_client_account("qr_premium_page", "premium", 628120020001)
        guest_id = self.create_guest(owner_user_id)

        with app_module.app.app_context():
            guest = app_module.db.session.get(Guests, guest_id)
            guest_token = app_module.build_guest_qr_token(guest)
            expected_qr_value = app_module.attendance_service.build_guest_qr_scan_value(guest, guest_token)

        page_response = self.client.get(f"/qr/{guest_token}")
        status_response = self.client.get(f"/qr/{guest_token}/status")
        captured_qr_value = {}
        original_build_guest_qr_svg = app_module.attendance_service.build_guest_qr_svg
        try:

            # Fungsi test helper untuk membuat SVG QR palsu.
            def fake_build_guest_qr_svg(qr_value):
                captured_qr_value["value"] = qr_value
                return b"<svg></svg>"

            app_module.attendance_service.build_guest_qr_svg = fake_build_guest_qr_svg
            image_response = self.client.get(f"/qr/{guest_token}/image.svg")
        finally:
            app_module.attendance_service.build_guest_qr_svg = original_build_guest_qr_svg

        self.assertEqual(page_response.status_code, 200)
        page_html = page_response.get_data(as_text=True)
        self.assertIn("QR Code", page_html)
        self.assertIn(f"/qr/{guest_token}/image.svg", page_html)
        self.assertIn('id="guestQrTimer"', page_html)
        self.assertIn('data-duration="300"', page_html)
        self.assertIn("Halaman QR Code Sudah Expired.", page_html)
        self.assertEqual(image_response.status_code, 200)
        self.assertEqual(image_response.mimetype, "image/svg+xml")
        self.assertIn("<svg", image_response.get_data(as_text=True))
        self.assertEqual(captured_qr_value["value"], expected_qr_value)
        self.assertNotIn("+", captured_qr_value["value"])
        self.assertTrue(captured_qr_value["value"].startswith(f"{guest_id}{owner_user_id}"))
        self.assertIn(guest_token, captured_qr_value["value"])
        self.assertTrue(captured_qr_value["value"].endswith("6281234567890"))
        self.assertEqual(status_response.json["status"], "pending")

    # Fungsi untuk memastikan mode scanner fisik langsung auto-submit tanpa tombol verifikasi.
    def test_scan_page_auto_submits_physical_scanner_input(self):
        _, active_token = self.create_client_account("qr_premium_scanner", "premium", 628120020004)
        self.login_as_user("qr_premium_scanner", active_token)

        response = self.client.get("/user/scan")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('id="scannerTokenInput"', html)
        self.assertNotIn('<button type="submit">Verifikasi</button>', html)
        self.assertIn('scannerTokenInput.addEventListener("input"', html)

    # Fungsi untuk memastikan scan QR Premium membuat request dan staff confirm mengisi kehadiran.
    def test_premium_scan_waits_for_staff_confirmation(self):
        owner_user_id, active_token = self.create_client_account("qr_premium_scan", "premium", 628120020002)
        guest_id = self.create_guest(owner_user_id, nama="Siti QR")

        with app_module.app.app_context():
            guest = app_module.db.session.get(Guests, guest_id)
            guest_token = app_module.build_guest_qr_token(guest)
            qr_scan_value = app_module.attendance_service.build_guest_qr_scan_value(guest, guest_token)

        self.login_as_user("qr_premium_scan", active_token)

        invalid_response = self.client.post(
            "/user/scan/verify",
            json={"token": f"{guest_id}{owner_user_id}{guest_token}000000"},
        )

        self.assertEqual(invalid_response.status_code, 400)
        self.assertEqual(invalid_response.json["status"], "invalid_qr")

        response = self.client.post("/user/scan/verify", json={"token": qr_scan_value})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "pending_confirmation")
        self.assertIn("Menunggu konfirmasi staff", response.json["message"])

        with app_module.app.app_context():
            guest = app_module.db.session.get(Guests, guest_id)
            self.assertIsNone(guest.kehadiran)
            verification_request = AttendanceVerificationRequest.query.filter_by(
                owner_user_id=owner_user_id,
                guest_id=guest_id,
                status="pending",
            ).first()
            self.assertIsNotNone(verification_request)

            staff = Staff()
            staff.owner_user_id = owner_user_id
            staff.nama = "Staff QR"
            staff.no_hp = "6281299990000"
            app_module.db.session.add(staff)
            app_module.db.session.commit()

            confirm_result = app_module.attendance_service.confirm_attendance_verification_request(
                staff,
                verification_request.id,
            )
            guest = app_module.db.session.get(Guests, guest_id)
            first_attendance_time = guest.kehadiran
            verified_by_staff_name = guest.verified_by_staff_name

        self.assertEqual(confirm_result["status"], "confirmed")
        self.assertIsNotNone(first_attendance_time)
        self.assertEqual(verified_by_staff_name, "Staff QR")

        second_response = self.client.post("/user/scan/verify", json={"token": guest_token})
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(second_response.json["status"], "already_verified")
        self.assertIn("Kode QR Sudah Terverifikasi Sebelumnya.", second_response.json["message"])

        with app_module.app.app_context():
            guest = app_module.db.session.get(Guests, guest_id)
            self.assertEqual(guest.kehadiran, first_attendance_time)

        welcome_page = self.client.get(f"/qr/{guest_token}?verified=1")
        already_page = self.client.get(f"/qr/{guest_token}")

        self.assertIn("Selamat Datang Bpk/Ibu Siti QR.", welcome_page.get_data(as_text=True))
        self.assertIn("Silahkan untuk menutup browser ini", welcome_page.get_data(as_text=True))
        self.assertIn("Kode QR Sudah Terverifikasi Sebelumnya.", already_page.get_data(as_text=True))

    # Fungsi untuk memastikan fitur Scan dan QR tidak tersedia bagi client non-Premium.
    def test_non_premium_user_cannot_access_scan_or_guest_qr(self):
        owner_user_id, active_token = self.create_client_account("qr_standard_scan", "standard", 628120020003)
        guest_id = self.create_guest(owner_user_id)

        with app_module.app.app_context():
            guest = app_module.db.session.get(Guests, guest_id)
            self.assertEqual(app_module.build_guest_qr_url(guest), "")

        self.login_as_user("qr_standard_scan", active_token)
        response = self.client.get("/user/scan")

        self.assertEqual(response.status_code, 403)
        self.assertIn("Fitur Scan hanya tersedia untuk paket Premium.", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
