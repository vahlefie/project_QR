import tempfile
import unittest
from pathlib import Path

import app as app_module


class DashboardRouteTest(unittest.TestCase):
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

    # Fungsi untuk memastikan dashboard dan profile wajib login.
    def test_dashboard_routes_require_login(self):
        protected_paths = (
            "/admin/dashboard",
            "/super-admin/dashboard",
            "/user/dashboard",
            "/profile",
        )

        for path in protected_paths:
            with self.subTest(path=path):
                response = self.client.get(path)

                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.location, "/login")

    # Fungsi untuk memastikan route dashboard/profile sudah terdaftar melalui Blueprint.
    def test_dashboard_routes_use_blueprint_endpoints(self):
        endpoints = {rule.endpoint for rule in app_module.app.url_map.iter_rules()}

        self.assertIn("dashboard.admin_dashboard", endpoints)
        self.assertIn("dashboard.super_admin_dashboard", endpoints)
        self.assertIn("dashboard.user_dashboard", endpoints)
        self.assertIn("dashboard.profile", endpoints)


if __name__ == "__main__":
    unittest.main()
