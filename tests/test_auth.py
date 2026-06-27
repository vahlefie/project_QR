import tempfile
import unittest
from pathlib import Path

import app as app_module


class AuthHelperTest(unittest.TestCase):
    # Fungsi untuk menguji normalisasi identifier login.
    def test_normalize_login_identifier(self):
        self.assertEqual(app_module.normalize_login_identifier(" USER@Email.COM "), "user@email.com")
        self.assertEqual(app_module.normalize_login_identifier("   "), "anonymous")
        self.assertEqual(app_module.normalize_login_identifier(None), "anonymous")

    # Fungsi untuk menguji format password berdasarkan role.
    def test_password_validation_by_role(self):
        self.assertTrue(app_module.is_valid_password_for_role("User1234", app_module.ROLE_USER))
        self.assertFalse(app_module.is_valid_password_for_role("user1234", app_module.ROLE_USER))
        self.assertFalse(app_module.is_valid_password_for_role("Admin1234", app_module.ROLE_ADMIN))
        self.assertTrue(app_module.is_valid_password_for_role("Admin1234!", app_module.ROLE_ADMIN))

    # Fungsi untuk memastikan key throttle login berupa hash stabil.
    def test_build_login_throttle_key_is_stable_hash(self):
        first_key = app_module.build_login_throttle_key("User", "127.0.0.1")
        second_key = app_module.build_login_throttle_key(" user ", "127.0.0.1")

        self.assertEqual(first_key, second_key)
        self.assertEqual(len(first_key), 64)


class AuthRouteTest(unittest.TestCase):
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

    # Fungsi untuk menguji route root mengarah ke halaman login.
    def test_index_redirects_to_login(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/login")

    # Fungsi untuk memastikan route auth sudah terdaftar melalui Blueprint.
    def test_auth_routes_use_blueprint_endpoints(self):
        endpoints = {rule.endpoint for rule in app_module.app.url_map.iter_rules()}

        self.assertIn("auth.index", endpoints)
        self.assertIn("auth.login", endpoints)
        self.assertIn("auth.reset_password", endpoints)
        self.assertIn("auth.logout", endpoints)

    # Fungsi untuk menguji halaman login dapat dirender.
    def test_login_page_renders(self):
        response = self.client.get("/login")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"<form", response.data)

    # Fungsi untuk menguji halaman reset password dilindungi login.
    def test_reset_password_requires_login(self):
        for path in ("/reset-password", app_module.PASSWORD_RESET_PATH):
            with self.subTest(path=path):
                response = self.client.get(path)

                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.location, "/login")

    # Fungsi untuk menguji route logout membersihkan session dan kembali ke login.
    def test_logout_redirects_to_login(self):
        response = self.client.get("/logout")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/login")


if __name__ == "__main__":
    unittest.main()
