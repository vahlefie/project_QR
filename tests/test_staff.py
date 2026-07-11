import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import app as app_module
from flask import render_template
from constants import STAFF_SESSION_COOKIE_NAME
from models import Guests, Staff, StaffAccess, User


class StaffRouteTest(unittest.TestCase):
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
            StaffAccess.query.filter_by(token_hash="staff-client-logout-token").delete()
            owner = User.query.filter_by(username="staff_client_logout_owner").first()
            if owner:
                for staff in Staff.query.filter_by(owner_user_id=owner.id).all():
                    StaffAccess.query.filter_by(staff_id=staff.id).delete()
                    app_module.db.session.delete(staff)
                app_module.db.session.delete(owner)
            app_module.db.session.commit()
        app_module.ACTIVITY_LOG_DIR = self.original_log_dir
        self.temp_dir.cleanup()

    # Fungsi untuk menguji halaman session staff expired.
    def test_staff_session_expired_page(self):
        expired_response = self.client.get("/staff/session-expired")
        logout_response = self.client.get("/staff/session-expired?reason=logout")

        self.assertEqual(expired_response.status_code, 401)
        self.assertEqual(logout_response.status_code, 200)
        self.assertIn("Silakan minta client membuka akses staff kembali.", expired_response.get_data(as_text=True))
        self.assertNotIn("Session staff berakhir karena idle 2 jam.", expired_response.get_data(as_text=True))

    # Fungsi untuk menguji link akses staff yang tidak valid ditolak.
    def test_staff_access_rejects_invalid_token(self):
        response = self.client.get("/staff/access/not-a-valid-token")

        self.assertEqual(response.status_code, 401)
        self.assertIn("Link akses staff tidak valid", response.get_data(as_text=True))

    # Fungsi untuk memastikan route data staff wajib session staff.
    def test_staff_routes_require_staff_session(self):
        protected_requests = (
            ("get", "/staff/data"),
            ("post", "/staff/guests/new"),
            ("post", "/staff/guests/1/status"),
            ("post", "/staff/guests/1/delete"),
            ("get", "/staff/attendance-notification"),
            ("post", "/staff/attendance-notification/1/confirm"),
            ("post", "/staff/attendance-notification/1/reject"),
        )

        for method_name, path in protected_requests:
            with self.subTest(method=method_name, path=path):
                response = getattr(self.client, method_name)(path)

                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.location, "/staff/session-expired")

    # Fungsi untuk menguji logout staff tanpa session tetap diarahkan ke halaman logout.
    def test_staff_logout_redirects_to_session_expired_logout(self):
        response = self.client.get("/staff/logout")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/staff/session-expired?reason=logout")

    # Fungsi untuk memastikan akses staff yang dilogout client tidak menampilkan pesan idle.
    def test_client_logged_out_staff_session_does_not_show_idle_message(self):
        with app_module.app.app_context():
            StaffAccess.query.filter_by(token_hash="staff-client-logout-token").delete()
            existing_owner = User.query.filter_by(username="staff_client_logout_owner").first()
            if existing_owner:
                for existing_staff in Staff.query.filter_by(owner_user_id=existing_owner.id).all():
                    StaffAccess.query.filter_by(staff_id=existing_staff.id).delete()
                    app_module.db.session.delete(existing_staff)
                app_module.db.session.delete(existing_owner)
            app_module.db.session.commit()

            owner = User()
            owner.username = "staff_client_logout_owner"
            owner.nama = "Staff Client Logout Owner"
            owner.email = "staff_client_logout_owner@example.com"
            owner.no_hp = 628120050001
            owner.role = app_module.ROLE_USER
            app_module.db.session.add(owner)
            app_module.db.session.commit()

            staff = Staff()
            staff.owner_user_id = owner.id
            staff.nama = "Staff Logout"
            staff.no_hp = "6281299993333"
            app_module.db.session.add(staff)
            app_module.db.session.commit()

            staff_access = StaffAccess()
            staff_access.staff_id = staff.id
            staff_access.token_hash = "staff-client-logout-token"
            staff_access.pin_hash = "pin"
            staff_access.is_active = False
            staff_access.revoked_at = app_module.staff_service.get_utc_naive_datetime()
            staff_access.revoked_by = "client"
            staff_access.revoked_reason = "client_logout"
            app_module.db.session.add(staff_access)
            app_module.db.session.commit()
            staff_access_id = staff_access.id

            session_cookie = app_module.staff_service.get_staff_session_serializer().dumps(
                {"staff_access_id": staff_access_id}
            )

        self.client.set_cookie(STAFF_SESSION_COOKIE_NAME, session_cookie)
        response = self.client.get("/staff/data", follow_redirects=True)
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Logout staff berhasil.", html)
        self.assertNotIn("Session staff berakhir karena idle 2 jam.", html)

    # Fungsi untuk memastikan route staff sudah terdaftar melalui Blueprint.
    def test_staff_routes_use_blueprint_endpoints(self):
        endpoints = {rule.endpoint for rule in app_module.app.url_map.iter_rules()}

        self.assertIn("staff.staff_session_expired", endpoints)
        self.assertIn("staff.staff_access_login", endpoints)
        self.assertIn("staff.staff_data", endpoints)
        self.assertIn("staff.add_staff_guest", endpoints)
        self.assertIn("staff.update_staff_guest_status", endpoints)
        self.assertIn("staff.delete_staff_guest_row", endpoints)
        self.assertIn("staff.staff_attendance_notification", endpoints)
        self.assertIn("staff.confirm_staff_attendance_notification", endpoints)
        self.assertIn("staff.reject_staff_attendance_notification", endpoints)
        self.assertIn("staff.staff_logout", endpoints)
        self.assertNotIn("staff.staff_dashboard", endpoints)

    # Fungsi untuk memastikan popup tambah tamu staff memakai UI nomor HP dengan prefix +62.
    def test_staff_data_add_guest_modal_uses_phone_prefix_format(self):
        with app_module.app.test_request_context("/staff/data"):
            html = render_template(
                "user_data.html",
                layout_template="staff_layout.html",
                allow_guest_upload=False,
                data_endpoint="staff.staff_data",
                add_guest_endpoint="staff.add_staff_guest",
                status_endpoint="staff.update_staff_guest_status",
                delete_endpoint="staff.delete_staff_guest_row",
                user="Staff Test",
                message="",
                guests=[],
                total_guests=0,
                pagination=SimpleNamespace(page=1, pages=0, has_prev=False, has_next=False),
                search="",
                sort_by="latest",
                per_page=10,
                guest_status_options=("Reguler", "VIP"),
                default_guest_status="Reguler",
            )

        self.assertIn('id="addGuestPhoneLocalInput"', html)
        self.assertIn('id="addGuestPhoneFullInput" type="hidden" name="no_hp"', html)
        self.assertIn("<span>+62</span>", html)
        self.assertIn('minlength="8"', html)
        self.assertIn('pattern="(08[0-9]{6,}|8[0-9]{7,})"', html)
        self.assertIn("addGuestPhoneFullInput.value = `62${localNumber}`;", html)

    # Fungsi untuk memastikan halaman Data staff tidak menampilkan tombol hapus baris.
    def test_staff_data_template_hides_delete_button(self):
        guest = SimpleNamespace(
            id=77,
            nama="Tamu Staff",
            no_hp="6281200770001",
            email=None,
            status="Reguler",
            added_by="Staff 1",
            kehadiran=None,
            verified_by_staff_name=None,
        )
        with app_module.app.test_request_context("/staff/data"):
            html = render_template(
                "user_data.html",
                layout_template="staff_layout.html",
                allow_guest_upload=False,
                allow_guest_delete=False,
                show_guest_qr_column=False,
                data_endpoint="staff.staff_data",
                add_guest_endpoint="staff.add_staff_guest",
                status_endpoint="staff.update_staff_guest_status",
                delete_endpoint="staff.delete_staff_guest_row",
                user="Staff Test",
                message="",
                guests=[guest],
                total_guests=1,
                pagination=SimpleNamespace(page=1, pages=1, has_prev=False, has_next=False),
                search="",
                sort_by="attendance_desc",
                per_page=10,
                guest_status_options=("Reguler", "VIP"),
                default_guest_status="Reguler",
            )

        self.assertIn("Edit", html)
        self.assertNotIn('class="danger-button table-action-button guest-delete-toggle"', html)

    # Fungsi untuk memastikan route hapus tamu staff menolak request langsung.
    def test_staff_delete_guest_route_is_forbidden(self):
        username = "staff_delete_forbidden_owner"
        with app_module.app.app_context():
            StaffAccess.query.filter_by(token_hash="staff-delete-forbidden-token").delete()
            existing_owner = User.query.filter_by(username=username).first()
            if existing_owner:
                Guests.query.filter_by(user_id=existing_owner.id).delete()
                for existing_staff in Staff.query.filter_by(owner_user_id=existing_owner.id).all():
                    StaffAccess.query.filter_by(staff_id=existing_staff.id).delete()
                    app_module.db.session.delete(existing_staff)
                app_module.db.session.delete(existing_owner)
                app_module.db.session.commit()

            owner = User()
            owner.username = username
            owner.nama = "Staff Delete Owner"
            owner.email = f"{username}@example.com"
            owner.no_hp = 628120050099
            owner.role = app_module.ROLE_USER
            app_module.db.session.add(owner)
            app_module.db.session.commit()

            staff = Staff()
            staff.owner_user_id = owner.id
            staff.nama = "Staff Delete"
            staff.no_hp = "628120050098"
            app_module.db.session.add(staff)
            app_module.db.session.commit()

            guest = Guests()
            guest.no = 1
            guest.nama = "Guest Delete"
            guest.no_hp = "628120050097"
            guest.status = app_module.DEFAULT_GUEST_STATUS
            guest.user_id = owner.id
            app_module.db.session.add(guest)

            staff_access = StaffAccess()
            staff_access.staff_id = staff.id
            staff_access.token_hash = "staff-delete-forbidden-token"
            staff_access.pin_hash = "pin"
            staff_access.last_activity_at = app_module.staff_service.get_utc_naive_datetime()
            app_module.db.session.add(staff_access)
            app_module.db.session.commit()

            guest_id = guest.id
            session_cookie = app_module.staff_service.get_staff_session_serializer().dumps(
                {"staff_access_id": staff_access.id}
            )

        try:
            self.client.set_cookie(STAFF_SESSION_COOKIE_NAME, session_cookie)
            response = self.client.post(f"/staff/guests/{guest_id}/delete")

            self.assertEqual(response.status_code, 403)
            self.assertIn("Staff tidak diizinkan menghapus data tamu.", response.get_data(as_text=True))
            with app_module.app.app_context():
                self.assertIsNotNone(app_module.db.session.get(Guests, guest_id))
        finally:
            with app_module.app.app_context():
                owner = User.query.filter_by(username=username).first()
                if owner:
                    Guests.query.filter_by(user_id=owner.id).delete()
                    for staff in Staff.query.filter_by(owner_user_id=owner.id).all():
                        StaffAccess.query.filter_by(staff_id=staff.id).delete()
                        app_module.db.session.delete(staff)
                    app_module.db.session.delete(owner)
                    app_module.db.session.commit()


if __name__ == "__main__":
    unittest.main()
