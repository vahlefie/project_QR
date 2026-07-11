import tempfile
import unittest
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path

import app as app_module
import pandas as pd
from constants import SESSION_ACTIVE_TOKEN_KEY, SESSION_LAST_ACTIVITY_KEY
from flask import render_template
from models import BillingPayment, Guests, Staff, User, WhatsappSetting, WhatsappTemplate


class AdminRouteTest(unittest.TestCase):
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

    # Fungsi untuk membuat session admin aktif pada test client.
    def login_as_admin(self, username="admin_route_test"):
        active_session_token = "active-admin-route-test-token"
        with app_module.app.app_context():
            User.query.filter_by(username=username).delete()
            User.query.filter_by(no_hp=6281200011001).delete()
            admin = User()
            admin.username = username
            admin.nama = "Admin Route Test"
            admin.email = f"{username}@example.com"
            admin.no_hp = 6281200011001
            admin.role = app_module.ROLE_ADMIN
            admin.active_session_token = active_session_token
            app_module.db.session.add(admin)
            app_module.db.session.commit()

        with self.client.session_transaction() as session:
            session["user"] = username
            session["role"] = app_module.ROLE_ADMIN
            session[SESSION_ACTIVE_TOKEN_KEY] = active_session_token
            session[SESSION_LAST_ACTIVITY_KEY] = app_module.auth_service.get_current_timestamp()

    # Fungsi untuk membuat session super admin aktif pada test client.
    def login_as_super_admin(self, username="super_admin_route_test"):
        active_session_token = "active-super-admin-route-test-token"
        with app_module.app.app_context():
            User.query.filter_by(username=username).delete()
            User.query.filter_by(no_hp=6281200011002).delete()
            super_admin = User()
            super_admin.username = username
            super_admin.nama = "Super Admin Route Test"
            super_admin.email = f"{username}@example.com"
            super_admin.no_hp = 6281200011002
            super_admin.role = app_module.ROLE_SUPER_ADMIN
            super_admin.active_session_token = active_session_token
            app_module.db.session.add(super_admin)
            app_module.db.session.commit()

        with self.client.session_transaction() as session:
            session["user"] = username
            session["role"] = app_module.ROLE_SUPER_ADMIN
            session[SESSION_ACTIVE_TOKEN_KEY] = active_session_token
            session[SESSION_LAST_ACTIVITY_KEY] = app_module.auth_service.get_current_timestamp()

    # Fungsi untuk memastikan route admin/super-admin wajib login.
    def test_admin_routes_require_login(self):
        protected_requests = (
            ("get", "/users"),
            ("get", "/admin/users/new"),
            ("get", "/super-admin/admins"),
            ("get", "/super-admin/admins/new"),
            ("get", "/super-admin/settings/whatsapp"),
            ("post", "/super-admin/admins/1/reset"),
            ("post", "/super-admin/admins/1/delete"),
            ("post", "/super-admin/settings/whatsapp/mode"),
            ("post", "/super-admin/settings/whatsapp/phone"),
            ("post", "/super-admin/settings/whatsapp/api-token"),
            ("post", "/super-admin/settings/whatsapp/api-phone-number-id"),
            ("post", "/super-admin/settings/whatsapp/template"),
            ("post", "/admin/users/1/period"),
            ("post", "/admin/users/1/attendance-url/generate"),
            ("post", "/admin/users/1/reset"),
            ("post", "/admin/upload-guests"),
            ("post", "/admin/upload-guests-confirm"),
            ("get", "/admin/guests"),
            ("get", "/admin/guests/download"),
            ("post", "/admin/delete-guests"),
            ("get", "/admin/payment"),
            ("get", "/admin/payment-history"),
            ("post", "/admin/payment/input"),
        )

        for method_name, path in protected_requests:
            with self.subTest(method=method_name, path=path):
                response = getattr(self.client, method_name)(path)

                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.location, "/login")

    # Fungsi untuk memastikan route admin/super-admin sudah terdaftar melalui Blueprint.
    def test_admin_routes_use_blueprint_endpoints(self):
        endpoints = {rule.endpoint for rule in app_module.app.url_map.iter_rules()}

        self.assertIn("admin.users", endpoints)
        self.assertIn("admin.add_user", endpoints)
        self.assertIn("admin.manage_admins", endpoints)
        self.assertIn("admin.add_admin", endpoints)
        self.assertIn("admin.whatsapp_settings", endpoints)
        self.assertIn("admin.update_whatsapp_mode", endpoints)
        self.assertIn("admin.update_whatsapp_phone", endpoints)
        self.assertIn("admin.update_whatsapp_api_token", endpoints)
        self.assertIn("admin.update_whatsapp_api_phone_number_id", endpoints)
        self.assertIn("admin.save_whatsapp_message_template", endpoints)
        self.assertIn("admin.reset_admin_password", endpoints)
        self.assertIn("admin.delete_admin", endpoints)
        self.assertIn("admin.update_user_period", endpoints)
        self.assertIn("admin.generate_user_attendance_url", endpoints)
        self.assertIn("admin.reset_user_password", endpoints)
        self.assertIn("admin.upload_guests", endpoints)
        self.assertIn("admin.upload_guests_confirm", endpoints)
        self.assertIn("admin.view_guests", endpoints)
        self.assertIn("admin.download_guests", endpoints)
        self.assertIn("admin.delete_guests", endpoints)
        self.assertIn("admin.admin_payment", endpoints)
        self.assertIn("admin.admin_payment_history", endpoints)
        self.assertIn("admin.input_payment", endpoints)

    # Fungsi untuk memastikan upload tamu admin menampilkan popup konfirmasi dengan daftar baris terhapus.
    def test_admin_upload_guests_shows_confirmation_with_removed_rows(self):
        self.login_as_admin()
        original_instance_path = app_module.app.instance_path
        app_module.app.instance_path = self.temp_dir.name
        client = None
        client_id = None

        try:
            with app_module.app.app_context():
                User.query.filter_by(username="admin_upload_client").delete()
                User.query.filter_by(no_hp=6281200011555).delete()
                client = User()
                client.username = "admin_upload_client"
                client.nama = "Admin Upload Client"
                client.email = "admin_upload_client@example.com"
                client.no_hp = 6281200011555
                client.role = app_module.ROLE_USER
                app_module.db.session.add(client)
                app_module.db.session.commit()
                client_id = client.id

            excel_data = BytesIO()
            pd.DataFrame(
                [
                    {"no": 1, "nama": "valid admin", "no_hp": "0812345678", "email": "", "status": "Reguler"},
                    {"no": 2, "nama": "", "no_hp": "0812345678", "email": "hapus@example.com", "status": "VIP"},
                    {"no": 3, "nama": "hp salah", "no_hp": "-812345678", "email": "", "status": "Reguler"},
                ]
            ).to_excel(excel_data, index=False)
            excel_data.seek(0)

            response = self.client.post(
                "/admin/upload-guests",
                data={
                    "owner_user_id": str(client_id),
                    "file": (excel_data, "guests.xlsx"),
                },
                content_type="multipart/form-data",
            )
            html = response.get_data(as_text=True)

            self.assertEqual(response.status_code, 200)
            self.assertIn("Konfirmasi Upload Data Tamu", html)
            self.assertIn("Data tamu yang dihapus saat cleaning", html)
            self.assertIn("Nama kosong/tidak valid", html)
            self.assertIn("No HP kosong/tidak valid", html)
            self.assertNotIn("Apakah akan memperbarui data yang sama?", html)

            with app_module.app.app_context():
                self.assertEqual(Guests.query.filter_by(user_id=client_id).count(), 1)
        finally:
            app_module.app.instance_path = original_instance_path
            with app_module.app.app_context():
                if client is not None:
                    Guests.query.filter_by(user_id=client_id).delete()
                    stored_client = app_module.db.session.get(User, client_id)
                    if stored_client:
                        app_module.db.session.delete(stored_client)
                User.query.filter_by(username="admin_route_test").delete()
                app_module.db.session.commit()

    # Fungsi untuk memastikan konfirmasi duplicate admin dapat memperbarui data tanpa duplikasi.
    def test_admin_upload_guests_confirm_replaces_duplicate_rows(self):
        self.login_as_admin()
        original_instance_path = app_module.app.instance_path
        app_module.app.instance_path = self.temp_dir.name
        client = None
        client_id = None

        try:
            with app_module.app.app_context():
                User.query.filter_by(username="admin_duplicate_client").delete()
                User.query.filter_by(no_hp=6281200011666).delete()
                client = User()
                client.username = "admin_duplicate_client"
                client.nama = "Admin Duplicate Client"
                client.email = "admin_duplicate_client@example.com"
                client.no_hp = 6281200011666
                client.role = app_module.ROLE_USER
                app_module.db.session.add(client)
                app_module.db.session.commit()
                client_id = client.id

                existing_guest = Guests()
                existing_guest.no = 1
                existing_guest.nama = "Nama Lama"
                existing_guest.no_hp = "62812345678"
                existing_guest.email = "lama@example.com"
                existing_guest.status = "Reguler"
                existing_guest.user_id = client_id
                app_module.db.session.add(existing_guest)
                app_module.db.session.commit()

            excel_data = BytesIO()
            pd.DataFrame(
                [
                    {
                        "no": 1,
                        "nama": "nama baru",
                        "no_hp": "0812345678",
                        "email": "baru@example.com",
                        "status": "VIP",
                    }
                ]
            ).to_excel(excel_data, index=False)
            excel_data.seek(0)

            response = self.client.post(
                "/admin/upload-guests",
                data={
                    "owner_user_id": str(client_id),
                    "file": (excel_data, "guests.xlsx"),
                },
                content_type="multipart/form-data",
            )
            html = response.get_data(as_text=True)

            self.assertEqual(response.status_code, 200)
            self.assertIn("Apakah akan memperbarui data yang sama?", html)
            self.assertIn("/admin/upload-guests-confirm", html)
            with app_module.app.app_context():
                self.assertEqual(Guests.query.filter_by(user_id=client_id).count(), 1)
                self.assertEqual(Guests.query.filter_by(user_id=client_id).first().nama, "Nama Lama")

            response = self.client.post("/admin/upload-guests-confirm", data={"include_duplicates": "yes"})

            self.assertEqual(response.status_code, 302)
            self.assertIn(f"owner_user_id={client_id}", response.location)
            with app_module.app.app_context():
                guests = Guests.query.filter_by(user_id=client_id).all()
                self.assertEqual(len(guests), 1)
                self.assertEqual(guests[0].nama, "Nama Baru")
                self.assertEqual(guests[0].email, "baru@example.com")
                self.assertEqual(guests[0].status, "VIP")
                self.assertEqual(guests[0].edited_by, "admin_duplicate_client")
        finally:
            app_module.app.instance_path = original_instance_path
            with app_module.app.app_context():
                if client is not None:
                    Guests.query.filter_by(user_id=client_id).delete()
                    stored_client = app_module.db.session.get(User, client_id)
                    if stored_client:
                        app_module.db.session.delete(stored_client)
                User.query.filter_by(username="admin_route_test").delete()
                app_module.db.session.commit()

    # Fungsi untuk memastikan form tambah client dan admin memakai UI No HP prefix +62.
    def test_add_account_forms_use_phone_prefix_ui(self):
        template_cases = (
            ("add_user.html", "/admin/users/new"),
            ("add_admin.html", "/super-admin/admins/new"),
        )

        for template_name, path in template_cases:
            with self.subTest(template=template_name):
                with app_module.app.test_request_context(path):
                    html = render_template(template_name, user="Admin", error=None, form_data={})

                self.assertIn('class="phone-input"', html)
                self.assertIn("<span>+62</span>", html)
                self.assertIn('id="phoneLocalInput"', html)
                self.assertIn('id="phoneFullInput" type="hidden" name="no_hp"', html)
                self.assertIn("phoneFullInput.value = `62${localNumber}`;", html)

    # Fungsi untuk memastikan upload admin meminta konfirmasi dan tamu hadir tidak bisa diedit dari UI.
    def test_admin_guests_template_confirms_upload_and_locks_verified_guest_edit(self):
        verified_guest = type(
            "Guest",
            (),
            {
                "id": 889,
                "owner": None,
                "user_id": None,
                "nama": "Tamu Hadir Admin",
                "no_hp": "6281200889001",
                "email": "hadir-admin@example.com",
                "status": "VIP",
                "added_by": "client_owner",
                "edited_by": None,
                "kehadiran": datetime(2026, 7, 12, 10, 30, 0),
                "verified_by_staff_name": "Staff Admin",
            },
        )()
        with app_module.app.test_request_context("/admin/guests"):
            html = render_template(
                "admin_guests.html",
                user="Admin",
                users=[],
                selected_owner_user_id="",
                message="",
                upload_error="",
                upload_warning="",
                pending_upload=None,
                upload_result=None,
                guests=[verified_guest],
                total_guests=1,
                pagination=type("Pagination", (), {"page": 1, "pages": 1, "has_prev": False, "has_next": False})(),
                search="",
                sort_by="latest",
                per_page=10,
                guest_status_options=("Reguler", "VIP"),
                default_guest_status="Reguler",
            )

        self.assertIn("Apakah akan upload data?", html)
        self.assertIn('data-upload-confirm="true"', html)
        self.assertIn('id="confirmUploadSubmit">Ya</button>', html)
        self.assertIn('class="danger-button" id="cancelUploadSubmit">Batal</button>', html)
        self.assertNotIn('id="guest-status-form-admin-889"', html)
        self.assertNotIn('data-form-id="guest-status-form-admin-889"', html)
        self.assertNotIn('class="secondary-button table-action-button guest-edit-toggle"', html)
        self.assertIn("Staff Admin", html)
        self.assertIn("Hapus", html)

    # Fungsi untuk memastikan halaman setting WhatsApp memakai UI No HP prefix +62.
    def test_whatsapp_settings_form_uses_phone_prefix_ui(self):
        with app_module.app.test_request_context("/super-admin/settings/whatsapp"):
            html = render_template(
                "whatsapp_settings.html",
                user="Super Admin",
                setting=type(
                    "Setting",
                    (),
                    {
                        "send_mode": "development",
                        "phone_number": "",
                        "api_phone_number_id": "",
                    },
                )(),
                send_modes=(("development", "Development - wa.me"), ("production", "Production - WhatsApp API")),
                phone_display="Belum diatur",
                api_token_display="********1234",
                api_phone_number_id_display="Belum diatur",
                templates=[],
                selected_template=None,
                selected_template_id="",
                template_name="",
                template_body="",
                template_variables=("{nama_tamu}", "{short_qr_url}"),
                message="",
                error="",
            )

        self.assertIn('class="phone-input"', html)
        self.assertIn("<span>+62</span>", html)
        self.assertIn('id="whatsappPhoneLocalInput"', html)
        self.assertIn('id="whatsappPhoneFullInput" type="hidden" name="whatsapp_phone"', html)
        self.assertIn("whatsappPhoneFullInput.value = `62${localNumber}`;", html)
        self.assertIn('data-format="bold"', html)
        self.assertIn('data-format="monospace"', html)

    # Fungsi untuk memastikan super admin bisa menyimpan konfigurasi WhatsApp.
    def test_super_admin_can_update_whatsapp_settings(self):
        self.login_as_super_admin()
        with app_module.app.app_context():
            WhatsappTemplate.query.delete()
            WhatsappSetting.query.delete()
            app_module.db.session.commit()

        response = self.client.post(
            "/super-admin/settings/whatsapp/phone",
            data={"whatsapp_phone": "081234567890"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/super-admin/settings/whatsapp", response.location)

        response = self.client.post(
            "/super-admin/settings/whatsapp/template",
            data={
                "template_name": "Undangan QR",
                "template_body": "Halo {nama_tamu}, buka {short_qr_url}",
            },
        )

        self.assertEqual(response.status_code, 302)

        with app_module.app.app_context():
            setting = WhatsappSetting.query.order_by(WhatsappSetting.id.asc()).first()
            template = WhatsappTemplate.query.order_by(WhatsappTemplate.id.asc()).first()
            self.assertEqual(setting.phone_number, "6281234567890")
            self.assertEqual(setting.active_template_id, template.id)
            self.assertTrue(template.is_default)
            self.assertIn("{short_qr_url}", template.body)
            WhatsappTemplate.query.delete()
            WhatsappSetting.query.delete()
            User.query.filter_by(username="super_admin_route_test").delete()
            app_module.db.session.commit()

    # Fungsi untuk memastikan template daftar client tidak lagi memiliki kolom generate URL client.
    def test_users_template_hides_client_url_column(self):
        account = User()
        account.id = 99
        account.username = "clienturl"
        account.nama = "Client Url"
        account.email = "clienturl@example.com"
        account.no_hp = 628120009999
        account.aktivasi = True

        with app_module.app.test_request_context("/users"):
            html = render_template(
                "users.html",
                users=[account],
                pagination=type(
                    "Pagination",
                    (),
                    {"page": 1, "pages": 1, "has_prev": False, "has_next": False},
                )(),
                search="",
                sort_by="name_asc",
                per_page=10,
                total_users=1,
                user="Admin",
                package_options=app_module.PACKAGE_OPTIONS,
                min_expired_date="2026-06-06",
                message="",
                error="",
                default_user_reset_password=app_module.DEFAULT_USER_RESET_PASSWORD,
                attendance_url_states={99: {"generated_at_text": "Belum pernah dibuat"}},
                latest_payment_period_starts={99: None},
                latest_payment_period_ends={99: None},
                latest_payment_event_names={99: None},
                latest_payment_package_names={99: None},
            )

        self.assertNotIn("URL Client", html)
        self.assertNotIn("QR Client", html)
        self.assertNotIn("/admin/users/99/attendance-url/generate", html)

    # Fungsi untuk memastikan endpoint generate URL client lama sudah dipindahkan ke Staff.
    def test_generate_user_attendance_url_is_moved_to_staff(self):
        self.login_as_admin()
        with app_module.app.app_context():
            User.query.filter_by(username="attendance_generate_client").delete()
            User.query.filter_by(no_hp=6281200011777).delete()
            client = User()
            client.username = "attendance_generate_client"
            client.nama = "Attendance Generate Client"
            client.email = "attendance_generate_client@example.com"
            client.no_hp = 6281200011777
            client.role = app_module.ROLE_USER
            client.attendance_token_nonce = "old-nonce"
            app_module.db.session.add(client)
            app_module.db.session.commit()
            client_id = client.id

        response = self.client.post(f"/admin/users/{client_id}/attendance-url/generate")

        self.assertEqual(response.status_code, 410)
        payload = response.get_json()
        self.assertEqual(payload["status"], "moved")
        self.assertIn("menu Staff", payload["message"])

        with app_module.app.app_context():
            client = app_module.db.session.get(User, client_id)
            self.assertEqual(client.attendance_token_nonce, "old-nonce")
            self.assertIsNone(client.attendance_token_generated_at)
            app_module.db.session.delete(client)
            User.query.filter_by(username="admin_route_test").delete()
            app_module.db.session.commit()

    # Fungsi untuk memastikan reaktivasi event baru menghapus staff event sebelumnya.
    def test_input_payment_reactivation_deletes_previous_event_staff(self):
        self.login_as_admin("admin_reactivate_staff_test")
        username = "reactivation_staff_client"
        with app_module.app.app_context():
            existing_client = User.query.filter_by(username=username).first()
            if existing_client:
                Staff.query.filter_by(owner_user_id=existing_client.id).delete()
                BillingPayment.query.filter_by(user_id=existing_client.id).delete()
                app_module.db.session.delete(existing_client)
            User.query.filter_by(no_hp=6281200011888).delete()
            app_module.db.session.commit()

            client = User()
            client.username = username
            client.nama = "Reactivation Staff Client"
            client.email = f"{username}@example.com"
            client.no_hp = 6281200011888
            client.role = app_module.ROLE_USER
            app_module.db.session.add(client)
            app_module.db.session.commit()

            previous_payment = BillingPayment()
            previous_payment.user_id = client.id
            previous_payment.payment_date = date.today() - timedelta(days=14)
            previous_payment.amount = 100000
            previous_payment.payment_method = "Cash"
            previous_payment.payment_type = "Lunas"
            previous_payment.package_name = app_module.PACKAGE_PREMIUM
            previous_payment.period_start = date.today() - timedelta(days=14)
            previous_payment.period_end = date.today() - timedelta(days=1)
            previous_payment.event_name = "Old Staff Event"
            previous_payment.status = "verified"
            app_module.db.session.add(previous_payment)

            staff = Staff()
            staff.owner_user_id = client.id
            staff.nama = "Old Staff 1"
            staff.no_hp = "6281200011889"
            app_module.db.session.add(staff)
            app_module.db.session.commit()
            client_id = client.id

        try:
            response = self.client.post(
                "/admin/payment/input",
                data={
                    "owner_user_id": str(client_id),
                    "amount": "100000",
                    "payment_date": date.today().isoformat(),
                    "payment_time": "10:00",
                    "package_name": app_module.PACKAGE_PREMIUM,
                    "payment_type": "Lunas",
                    "period_start": date.today().isoformat(),
                    "period_end": (date.today() + timedelta(days=7)).isoformat(),
                    "event_name": "New Staff Event",
                    "payment_method": "Cash",
                },
            )

            self.assertEqual(response.status_code, 302)
            with app_module.app.app_context():
                self.assertEqual(Staff.query.filter_by(owner_user_id=client_id).count(), 0)
        finally:
            with app_module.app.app_context():
                client = User.query.filter_by(username=username).first()
                if client:
                    Staff.query.filter_by(owner_user_id=client.id).delete()
                    BillingPayment.query.filter_by(user_id=client.id).delete()
                    app_module.db.session.delete(client)
                User.query.filter_by(username="admin_reactivate_staff_test").delete()
                app_module.db.session.commit()


if __name__ == "__main__":
    unittest.main()
