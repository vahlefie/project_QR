import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import app as app_module
from flask import render_template
from constants import SESSION_ACTIVE_TOKEN_KEY, SESSION_LAST_ACTIVITY_KEY
from models import BillingPayment, User


class ClientStaffRouteTest(unittest.TestCase):
    # Fungsi untuk menyiapkan test client dengan log diarahkan ke folder sementara.
    def setUp(self):
        self.original_log_dir = app_module.ACTIVITY_LOG_DIR
        self.temp_dir = tempfile.TemporaryDirectory()
        app_module.ACTIVITY_LOG_DIR = Path(self.temp_dir.name)
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()

    # Fungsi untuk membersihkan konfigurasi test setelah setiap skenario.
    def tearDown(self):
        with app_module.app.app_context():
            account = User.query.filter_by(username="inactive_staff_client").first()
            if account:
                BillingPayment.query.filter_by(user_id=account.id).delete()
                app_module.db.session.delete(account)
                app_module.db.session.commit()
        app_module.ACTIVITY_LOG_DIR = self.original_log_dir
        self.temp_dir.cleanup()

    # Fungsi untuk memastikan route pengelolaan staff client wajib login.
    def test_client_staff_routes_require_login(self):
        protected_requests = (
            ("get", "/user/staff"),
            ("post", "/user/staff/1/login"),
            ("post", "/user/staff/1/logout"),
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
        self.assertIn("client_staff.login_staff", endpoints)
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


if __name__ == "__main__":
    unittest.main()
