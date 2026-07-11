import tempfile
import time
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import app as app_module
from constants import SESSION_ACTIVE_TOKEN_KEY, SESSION_LAST_ACTIVITY_KEY
from flask import render_template
from models import BillingPayment, User


class UserRouteTest(unittest.TestCase):
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
            account = User.query.filter_by(username="inactive_data_route_client").first()
            if account:
                BillingPayment.query.filter_by(user_id=account.id).delete()
                app_module.db.session.delete(account)
                app_module.db.session.commit()
        app_module.ACTIVITY_LOG_DIR = self.original_log_dir
        self.temp_dir.cleanup()

    # Fungsi untuk membuat session client yang valid untuk route user.
    def login_as_user(self, username, role, active_session_token):
        with self.client.session_transaction() as session:
            session["user"] = username
            session["role"] = role
            session[SESSION_ACTIVE_TOKEN_KEY] = active_session_token
            session[SESSION_LAST_ACTIVITY_KEY] = int(time.time())

    # Fungsi untuk memastikan route data/upload user wajib login.
    def test_user_routes_require_login(self):
        protected_requests = (
            ("get", "/user/data"),
            ("post", "/user/upload"),
            ("post", "/user/upload-confirm"),
            ("post", "/user/guests/new"),
            ("get", "/user/scan"),
            ("post", "/user/scan/verify"),
            ("post", "/user/delete-data"),
        )

        for method_name, path in protected_requests:
            with self.subTest(method=method_name, path=path):
                response = getattr(self.client, method_name)(path)

                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.location, "/login")

    # Fungsi untuk memastikan route user sudah terdaftar melalui Blueprint.
    def test_user_routes_use_blueprint_endpoints(self):
        endpoints = {rule.endpoint for rule in app_module.app.url_map.iter_rules()}

        self.assertIn("user.user_data", endpoints)
        self.assertIn("user.upload_excel", endpoints)
        self.assertIn("user.upload_confirm", endpoints)
        self.assertIn("user.add_user_guest", endpoints)
        self.assertIn("user.user_scan", endpoints)
        self.assertIn("user.verify_user_scan", endpoints)
        self.assertIn("user.delete_data", endpoints)

    # Fungsi untuk memastikan halaman Data client nonaktif tidak auto-download export.
    def test_inactive_client_data_page_renders_export_button_without_auto_download(self):
        with app_module.app.app_context():
            User.query.filter_by(username="inactive_data_route_client").delete()
            account = User()
            account.username = "inactive_data_route_client"
            account.nama = "Inactive Data Route Client"
            account.email = "inactive_data_route_client@example.com"
            account.no_hp = 6281200077001
            account.role = app_module.ROLE_USER
            account.aktivasi = True
            account.active_session_token = "inactive-data-route-token"
            app_module.db.session.add(account)
            app_module.db.session.commit()

            payment = BillingPayment()
            payment.user_id = account.id
            payment.payment_date = date(2026, 6, 1)
            payment.amount = 100000
            payment.package_name = "premium"
            payment.period_start = date(2026, 6, 1)
            payment.period_end = date(2026, 6, 20)
            payment.event_name = "Expired Route Event"
            payment.status = "verified"
            app_module.db.session.add(payment)
            app_module.db.session.commit()

        self.login_as_user(
            "inactive_data_route_client",
            app_module.ROLE_USER,
            "inactive-data-route-token",
        )
        response = self.client.get("/user/data")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("attachment", response.headers.get("Content-Disposition", ""))
        self.assertIn("Ekspor Data", html)
        self.assertIn("Masa aktif event sudah berakhir", html)

    # Fungsi untuk memastikan tabel Data client menampilkan sumber penambah dan action edit stabil.
    def test_user_data_template_shows_added_by_and_stable_edit_actions(self):
        guest = SimpleNamespace(
            id=987,
            nama="Tamu Added",
            no_hp="628123456789",
            email=None,
            status="VIP",
            added_by="client_added",
            kehadiran=None,
            jumlah_orang=2,
            verified_by_staff_name=None,
        )
        with app_module.app.test_request_context("/user/data"):
            html = render_template(
                "user_data.html",
                layout_template="user_layout.html",
                allow_guest_upload=False,
                allow_guest_export=False,
                allow_guest_mutations=True,
                allow_guest_full_edit=True,
                show_guest_qr_column=False,
                data_endpoint="user.user_data",
                add_guest_endpoint="user.add_user_guest",
                status_endpoint="guests.update_guest_status",
                delete_endpoint="guests.delete_guest_row",
                user="Client Test",
                message="",
                guests=[guest],
                total_guests=1,
                pagination=SimpleNamespace(page=1, pages=1, has_prev=False, has_next=False),
                search="",
                sort_by="latest",
                per_page=10,
                guest_status_options=("Reguler", "VIP"),
                default_guest_status="Reguler",
                staff=SimpleNamespace(id=1),
            )

        self.assertIn("<th>Ditambahkan</th>", html)
        self.assertIn("<th>Jumlah Orang</th>", html)
        self.assertIn("<td>client_added</td>", html)
        self.assertIn("<td>N/A</td>", html)
        self.assertIn('id="staffVerificationGuestCount"', html)
        self.assertIn("if (isNewNotification || !isPending)", html)
        self.assertNotIn('id="staffVerificationGuestName"', html)
        self.assertIn('name="nama"', html)
        self.assertIn('name="no_hp"', html)
        self.assertIn('name="email"', html)
        self.assertIn('form="guest-status-form-user-987"', html)
        self.assertIn('deleteButton.textContent = isEditing ? "Batal" : "Hapus";', html)
        self.assertIn("editButton.hidden = false;", html)
        self.assertIn("deleteButton.hidden = false;", html)
        self.assertIn('data-row-id="guest-row-987"', html)
        self.assertIn("const findGuestRowAction", html)
        self.assertIn('document.querySelector(`${selector}[data-row-id="${row.id}"]`)', html)
        self.assertIn('new CustomEvent("guest-row-editing-change"', html)
        self.assertIn("document.getElementById(button.dataset.rowId)", html)

        action_toggle_script = Path("static/action_toggle.js").read_text(encoding="utf-8")
        self.assertIn("function isActionMenuPinned(group)", action_toggle_script)
        self.assertIn('document.addEventListener("guest-row-editing-change"', action_toggle_script)
        self.assertIn("isActionMenuPinned(openGroup)", action_toggle_script)


if __name__ == "__main__":
    unittest.main()
