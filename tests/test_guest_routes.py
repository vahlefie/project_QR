import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import app as app_module
from constants import SESSION_ACTIVE_TOKEN_KEY, SESSION_LAST_ACTIVITY_KEY
from models import BillingPayment, GuestShortUrl, Guests, User, WhatsappSetting


class GuestRouteTest(unittest.TestCase):
    # Fungsi untuk menyiapkan test client dengan log diarahkan ke folder sementara.
    def setUp(self):
        self.original_log_dir = app_module.ACTIVITY_LOG_DIR
        self.temp_dir = tempfile.TemporaryDirectory()
        app_module.ACTIVITY_LOG_DIR = Path(self.temp_dir.name)
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()

    # Fungsi untuk membersihkan konfigurasi test setelah setiap skenario.
    def tearDown(self):
        app_module.ACTIVITY_LOG_DIR = self.original_log_dir
        self.temp_dir.cleanup()

    # Fungsi untuk membuat session user aktif pada test client.
    def login_as_user(self, username="guest_route_user"):
        active_session_token = "active-guest-route-user-token"
        with app_module.app.app_context():
            User.query.filter_by(username=username).delete()
            User.query.filter_by(no_hp=6281200044001).delete()
            account = User()
            account.username = username
            account.nama = "Guest Route User"
            account.email = f"{username}@example.com"
            account.no_hp = 6281200044001
            account.role = app_module.ROLE_USER
            account.paket = app_module.PACKAGE_PREMIUM
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
            payment.event_name = "Guest Route Event"
            payment.status = "verified"
            app_module.db.session.add(payment)
            app_module.db.session.commit()
            account_id = account.id

        with self.client.session_transaction() as session:
            session["user"] = username
            session["role"] = app_module.ROLE_USER
            session[SESSION_ACTIVE_TOKEN_KEY] = active_session_token
            session[SESSION_LAST_ACTIVITY_KEY] = app_module.auth_service.get_current_timestamp()

        return account_id

    # Fungsi untuk membuat session admin aktif pada test client.
    def login_as_admin(self, username="guest_route_admin"):
        active_session_token = "active-guest-route-admin-token"
        with app_module.app.app_context():
            User.query.filter_by(username=username).delete()
            User.query.filter_by(no_hp=6281200044002).delete()
            admin = User()
            admin.username = username
            admin.nama = "Guest Route Admin"
            admin.email = f"{username}@example.com"
            admin.no_hp = 6281200044002
            admin.role = app_module.ROLE_ADMIN
            admin.active_session_token = active_session_token
            app_module.db.session.add(admin)
            app_module.db.session.commit()

        with self.client.session_transaction() as session:
            session["user"] = username
            session["role"] = app_module.ROLE_ADMIN
            session[SESSION_ACTIVE_TOKEN_KEY] = active_session_token
            session[SESSION_LAST_ACTIVITY_KEY] = app_module.auth_service.get_current_timestamp()

    # Fungsi untuk memastikan route update/hapus tamu wajib login.
    def test_guest_mutation_routes_require_login(self):
        protected_requests = (
            ("post", "/guests/1/status"),
            ("post", "/guests/1/delete"),
            ("get", "/guests/1/whatsapp-invite"),
        )

        for method_name, path in protected_requests:
            with self.subTest(method=method_name, path=path):
                response = getattr(self.client, method_name)(path)

                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.location, "/login")

    # Fungsi untuk memastikan route tamu bersama sudah terdaftar melalui Blueprint.
    def test_guest_routes_use_blueprint_endpoints(self):
        endpoints = {rule.endpoint for rule in app_module.app.url_map.iter_rules()}

        self.assertIn("guests.update_guest_status", endpoints)
        self.assertIn("guests.delete_guest_row", endpoints)
        self.assertIn("guests.send_guest_whatsapp_invite", endpoints)

    # Fungsi untuk memastikan undangan WhatsApp QR development redirect ke wa.me.
    def test_send_guest_whatsapp_invite_redirects_to_wa_me(self):
        owner_user_id = self.login_as_user()

        with app_module.app.app_context():
            GuestShortUrl.query.delete()
            Guests.query.filter_by(nama="WA Invite Guest").delete()
            setting = WhatsappSetting.query.order_by(WhatsappSetting.id.asc()).first()
            if not setting:
                setting = WhatsappSetting()
                app_module.db.session.add(setting)
            setting.send_mode = "development"
            setting.active_template_id = None

            guest = Guests()
            guest.nama = "WA Invite Guest"
            guest.no_hp = "6281200099999"
            guest.user_id = owner_user_id
            app_module.db.session.add(guest)
            app_module.db.session.commit()
            guest_id = guest.id

        response = self.client.get(f"/guests/{guest_id}/whatsapp-invite")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.startswith("https://wa.me/6281200099999?text="))
        self.assertIn("WA%20Invite%20Guest", response.location)
        self.assertIn(f"{owner_user_id}_WA_Invite_Guest", response.location)

        with app_module.app.app_context():
            Guests.query.filter_by(id=guest_id).delete()
            GuestShortUrl.query.delete()
            BillingPayment.query.filter_by(user_id=owner_user_id).delete()
            User.query.filter_by(username="guest_route_user").delete()
            app_module.db.session.commit()

    # Fungsi untuk memastikan client dapat mengedit nama, no HP, email, dan status tamu.
    def test_user_can_edit_full_guest_details(self):
        owner_user_id = self.login_as_user("guest_full_edit_user")

        with app_module.app.app_context():
            guest = Guests()
            guest.nama = "Nama Awal"
            guest.no_hp = "6281200011111"
            guest.email = "awal@example.com"
            guest.status = "Reguler"
            guest.user_id = owner_user_id
            app_module.db.session.add(guest)
            app_module.db.session.commit()
            guest_id = guest.id

        response = self.client.post(
            f"/guests/{guest_id}/status",
            data={
                "nama": "  nama baru@@  ",
                "no_hp": "081200022222",
                "email": "BARU@EXAMPLE.COM",
                "status": "VIP",
            },
        )

        self.assertEqual(response.status_code, 302)
        with app_module.app.app_context():
            guest = app_module.db.session.get(Guests, guest_id)
            self.assertEqual(guest.nama, "Nama Baru")
            self.assertEqual(guest.no_hp, "6281200022222")
            self.assertEqual(guest.email, "baru@example.com")
            self.assertEqual(guest.status, "VIP")
            self.assertEqual(guest.edited_by, "Guest Route User")

            guest.kehadiran = app_module.get_utc_naive_datetime()
            app_module.db.session.commit()

        response = self.client.post(
            f"/guests/{guest_id}/status",
            data={
                "nama": "nama ditolak",
                "no_hp": "081200044444",
                "email": "ditolak@example.com",
                "status": "Reguler",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("sudah terverifikasi kehadirannya", response.get_data(as_text=True))
        with app_module.app.app_context():
            guest = app_module.db.session.get(Guests, guest_id)
            self.assertEqual(guest.nama, "Nama Baru")
            self.assertEqual(guest.status, "VIP")

            Guests.query.filter_by(user_id=owner_user_id).delete()
            BillingPayment.query.filter_by(user_id=owner_user_id).delete()
            User.query.filter_by(username="guest_full_edit_user").delete()
            app_module.db.session.commit()

    # Fungsi untuk memastikan tambah manual client mencatat nama client sebagai sumber penambah.
    def test_user_manual_add_guest_records_client_name(self):
        owner_user_id = self.login_as_user("guest_manual_added_by_user")

        response = self.client.post(
            "/user/guests/new",
            data={
                "nama": "tamu manual",
                "no_hp": "081200033333",
                "email": "",
                "status": "Reguler",
            },
        )

        self.assertEqual(response.status_code, 302)
        with app_module.app.app_context():
            guest = Guests.query.filter_by(user_id=owner_user_id, no_hp="6281200033333").first()
            self.assertIsNotNone(guest)
            self.assertEqual(guest.nama, "Tamu Manual")
            self.assertEqual(guest.added_by, "Guest Route User")

            Guests.query.filter_by(user_id=owner_user_id).delete()
            BillingPayment.query.filter_by(user_id=owner_user_id).delete()
            User.query.filter_by(username="guest_manual_added_by_user").delete()
            app_module.db.session.commit()

    # Fungsi untuk memastikan admin mencatat username client sebagai pengedit tamu.
    def test_admin_guest_status_edit_records_owner_username_as_editor(self):
        self.login_as_admin("guest_status_admin")
        owner_username = "admin_edit_owner"

        with app_module.app.app_context():
            User.query.filter_by(username=owner_username).delete()
            User.query.filter_by(no_hp=6281200044003).delete()
            owner = User()
            owner.username = owner_username
            owner.nama = "Admin Edit Owner"
            owner.email = f"{owner_username}@example.com"
            owner.no_hp = 6281200044003
            owner.role = app_module.ROLE_USER
            app_module.db.session.add(owner)
            app_module.db.session.commit()

            guest = Guests()
            guest.nama = "Admin Status Guest"
            guest.no_hp = "6281200044004"
            guest.status = "Reguler"
            guest.user_id = owner.id
            app_module.db.session.add(guest)
            app_module.db.session.commit()
            guest_id = guest.id
            owner_id = owner.id

        try:
            response = self.client.post(f"/guests/{guest_id}/status", data={"status": "VIP"})

            self.assertEqual(response.status_code, 302)
            with app_module.app.app_context():
                guest = app_module.db.session.get(Guests, guest_id)
                self.assertEqual(guest.status, "VIP")
                self.assertEqual(guest.edited_by, owner_username)

                guest.kehadiran = app_module.get_utc_naive_datetime()
                app_module.db.session.commit()

            response = self.client.post(f"/guests/{guest_id}/status", data={"status": "Reguler"})

            self.assertEqual(response.status_code, 403)
            self.assertIn("sudah terverifikasi kehadirannya", response.get_data(as_text=True))
            with app_module.app.app_context():
                guest = app_module.db.session.get(Guests, guest_id)
                self.assertEqual(guest.status, "VIP")
        finally:
            with app_module.app.app_context():
                Guests.query.filter_by(user_id=owner_id).delete()
                User.query.filter_by(username=owner_username).delete()
                User.query.filter_by(username="guest_status_admin").delete()
                app_module.db.session.commit()


if __name__ == "__main__":
    unittest.main()
