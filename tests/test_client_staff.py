import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import app as app_module
from flask import render_template
from constants import SESSION_ACTIVE_TOKEN_KEY, SESSION_LAST_ACTIVITY_KEY
from models import BillingPayment, Staff, User


class ClientStaffRouteTest(unittest.TestCase):
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
            account = User.query.filter_by(username="inactive_staff_client").first()
            if account:
                BillingPayment.query.filter_by(user_id=account.id).delete()
                app_module.db.session.delete(account)
                app_module.db.session.commit()
            for username in self.created_usernames:
                account = User.query.filter_by(username=username).first()
                if account:
                    Staff.query.filter_by(owner_user_id=account.id).delete()
                    BillingPayment.query.filter_by(user_id=account.id).delete()
                    app_module.db.session.delete(account)
            app_module.db.session.commit()
        app_module.ACTIVITY_LOG_DIR = self.original_log_dir
        self.temp_dir.cleanup()

    # Fungsi untuk memastikan route pengelolaan staff client wajib login.
    def test_client_staff_routes_require_login(self):
        protected_requests = (
            ("get", "/user/staff"),
            ("post", "/user/staff/1/update"),
            ("post", "/user/staff/1/login"),
            ("post", "/user/staff/1/logout"),
            ("post", "/user/staff/1/attendance-url/generate"),
            ("post", "/user/staff/1/block"),
            ("post", "/user/staff/1/unblock"),
            ("get", "/user/staff/status"),
            ("get", "/user/staff/1/logs"),
        )

        for method_name, path in protected_requests:
            with self.subTest(method=method_name, path=path):
                response = getattr(self.client, method_name)(path)

                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.location, "/login")

    # Fungsi untuk memastikan route client staff sudah terdaftar melalui Blueprint.
    def test_client_staff_routes_use_blueprint_endpoints(self):
        endpoints = {rule.endpoint for rule in app_module.app.url_map.iter_rules()}

        self.assertIn("client_staff.user_staff", endpoints)
        self.assertIn("client_staff.update_staff", endpoints)
        self.assertIn("client_staff.login_staff", endpoints)
        self.assertIn("client_staff.generate_staff_attendance_url", endpoints)
        self.assertIn("client_staff.logout_staff_from_client", endpoints)
        self.assertIn("client_staff.block_staff", endpoints)
        self.assertIn("client_staff.unblock_staff", endpoints)
        self.assertIn("client_staff.user_staff_status", endpoints)
        self.assertIn("client_staff.user_staff_logs", endpoints)

    # Fungsi untuk memastikan client tidak aktif tidak bisa mengakses fitur Staff.
    def test_inactive_client_cannot_access_staff_feature(self):
        active_session_token = "active-inactive-staff-client-token"
        with app_module.app.app_context():
            existing = User.query.filter_by(username="inactive_staff_client").first()
            if existing:
                BillingPayment.query.filter_by(user_id=existing.id).delete()
                app_module.db.session.delete(existing)
            User.query.filter_by(no_hp=628120030001).delete()
            app_module.db.session.commit()

            account = User()
            account.username = "inactive_staff_client"
            account.nama = "Inactive Staff Client"
            account.email = "inactive_staff_client@example.com"
            account.no_hp = 628120030001
            account.role = app_module.ROLE_USER
            account.active_session_token = active_session_token
            app_module.db.session.add(account)
            app_module.db.session.commit()

            payment = BillingPayment()
            payment.user_id = account.id
            payment.payment_date = date.today() - timedelta(days=10)
            payment.amount = 100000
            payment.package_name = app_module.PACKAGE_PREMIUM
            payment.period_start = date.today() - timedelta(days=10)
            payment.period_end = date.today() - timedelta(days=1)
            payment.event_name = "Inactive Staff Event"
            payment.status = "verified"
            app_module.db.session.add(payment)
            app_module.db.session.commit()

        with self.client.session_transaction() as session:
            session["user"] = "inactive_staff_client"
            session["role"] = app_module.ROLE_USER
            session[SESSION_ACTIVE_TOKEN_KEY] = active_session_token
            session[SESSION_LAST_ACTIVITY_KEY] = app_module.auth_service.get_current_timestamp()

        response = self.client.get("/user/staff")

        self.assertEqual(response.status_code, 403)
        self.assertIn("Akun client tidak aktif.", response.get_data(as_text=True))

    # Fungsi untuk memastikan menu fitur client tidak aktif tetap terlihat sebagai item nonaktif.
    def test_inactive_client_dashboard_shows_disabled_feature_menu(self):
        with app_module.app.test_request_context("/user/dashboard"):
            html = render_template(
                "user_dashboard.html",
                user="Inactive Staff Client",
                can_access_guest_scan=False,
                can_access_client_staff=False,
                is_client_active=False,
                attendance_url="",
            )

        self.assertIn('aria-disabled="true">Scan</span>', html)
        self.assertIn('aria-disabled="true">Staff</span>', html)
        self.assertIn('class="secondary-button" disabled>Buka Staff</button>', html)
        self.assertNotIn('href="/user/scan"', html)
        self.assertNotIn('href="/user/staff"', html)

    # Fungsi untuk membuat client aktif dengan satu staff untuk test halaman Staff.
    def create_active_client_with_staff(self, username="active_staff_url_client"):
        active_session_token = f"active-{username}-token"
        with app_module.app.app_context():
            existing = User.query.filter_by(username=username).first()
            if existing:
                Staff.query.filter_by(owner_user_id=existing.id).delete()
                BillingPayment.query.filter_by(user_id=existing.id).delete()
                app_module.db.session.delete(existing)
            User.query.filter_by(no_hp=628120030101).delete()
            app_module.db.session.commit()

            account = User()
            account.username = username
            account.nama = "Active Staff Url Client"
            account.email = f"{username}@example.com"
            account.no_hp = 628120030101
            account.role = app_module.ROLE_USER
            account.active_session_token = active_session_token
            app_module.db.session.add(account)
            app_module.db.session.commit()

            payment = BillingPayment()
            payment.user_id = account.id
            payment.payment_date = date.today()
            payment.amount = 100000
            payment.package_name = app_module.PACKAGE_PREMIUM
            payment.period_start = date.today() - timedelta(days=1)
            payment.period_end = date.today() + timedelta(days=1)
            payment.event_name = "Active Staff URL Event"
            payment.status = "verified"
            app_module.db.session.add(payment)

            staff = Staff()
            staff.owner_user_id = account.id
            staff.nama = "Staff URL"
            staff.no_hp = "628120030102"
            app_module.db.session.add(staff)
            app_module.db.session.commit()
            staff_id = staff.id

        self.created_usernames.append(username)
        with self.client.session_transaction() as session:
            session["user"] = username
            session["role"] = app_module.ROLE_USER
            session[SESSION_ACTIVE_TOKEN_KEY] = active_session_token
            session[SESSION_LAST_ACTIVITY_KEY] = app_module.auth_service.get_current_timestamp()
        return staff_id

    # Fungsi untuk memastikan halaman Staff menampilkan kolom URL Client per staff.
    def test_client_staff_page_shows_staff_attendance_url_column(self):
        staff_id = self.create_active_client_with_staff("active_staff_url_page")

        response = self.client.get("/user/staff")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("URL Client", html)
        self.assertIn("Generate", html)
        self.assertIn("Buka", html)
        self.assertIn("QR Client", html)
        self.assertIn("Edit", html)
        self.assertIn("staff-edit-cancel", html)
        self.assertIn("Batal", html)
        self.assertIn("setStaffRowEditing", html)
        self.assertIn("hiddenForStaffEdit", html)
        self.assertIn(f"/user/staff/{staff_id}/update", html)
        self.assertIn(f"/user/staff/{staff_id}/attendance-url/generate", html)
        self.assertIn('aria-disabled="true"', html)

    # Fungsi untuk memastikan edit staff mengubah nama alfanumerik dan nomor HP.
    def test_update_staff_allows_alphanumeric_name_and_updates_phone(self):
        staff_id = self.create_active_client_with_staff("active_staff_update")

        response = self.client.post(
            f"/user/staff/{staff_id}/update",
            data={"nama": "Staff 2", "no_hp": "08120030199"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/user/staff", response.location)

        with app_module.app.app_context():
            staff = app_module.db.session.get(Staff, staff_id)
            self.assertEqual(staff.nama, "Staff 2")
            self.assertEqual(staff.no_hp, "628120030199")

    # Fungsi untuk memastikan nama staff dengan karakter selain huruf/angka ditolak.
    def test_update_staff_rejects_non_alphanumeric_name(self):
        staff_id = self.create_active_client_with_staff("active_staff_bad_name")

        response = self.client.post(
            f"/user/staff/{staff_id}/update",
            data={"nama": "Staff #2", "no_hp": "08120030102"},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Nama staff hanya boleh berisi huruf dan angka.", response.get_data(as_text=True))

    # Fungsi untuk memastikan generate URL Staff membuat token dan QR per staff.
    def test_generate_staff_attendance_url_creates_staff_public_link(self):
        staff_id = self.create_active_client_with_staff("active_staff_url_generate")

        response = self.client.post(f"/user/staff/{staff_id}/attendance-url/generate")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "success")
        self.assertIn("/kehadiran/", payload["attendance_url"])
        self.assertIn("/qr.png", payload["attendance_qr_url"])

        with app_module.app.app_context():
            staff = app_module.db.session.get(Staff, staff_id)
            self.assertIsNotNone(staff.attendance_token_nonce)
            self.assertIsNotNone(staff.attendance_token_generated_at)
            token = app_module.attendance_service.build_staff_attendance_token(staff)
            resolved_staff = app_module.get_attendance_staff_from_token(token)
            self.assertEqual(resolved_staff.id, staff.id)


if __name__ == "__main__":
    unittest.main()
