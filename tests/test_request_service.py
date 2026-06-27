import unittest
from unittest.mock import patch

import app as app_module
from constants import SESSION_TRACKING_ID_KEY
from flask import g, session
from services import request_service


class RequestServiceTest(unittest.TestCase):
    # Fungsi untuk memastikan helper form tetap menghapus spasi input.
    def test_get_form_text_strips_value(self):
        with app_module.app.test_request_context("/form", method="POST", data={"nama": "  Budi  "}):
            self.assertEqual(request_service.get_form_text("nama"), "Budi")

    # Fungsi untuk memastikan konteks log request menyiapkan request id dan session id.
    def test_prepare_activity_log_context(self):
        with app_module.app.test_request_context("/dashboard"):
            request_service.prepare_activity_log_context()

            self.assertTrue(g.request_id.startswith("REQ_ID-"))
            self.assertFalse(g.current_staff_loaded)
            self.assertIn(SESSION_TRACKING_ID_KEY, session)

    # Fungsi untuk memastikan akses tanpa login tetap diarahkan ke halaman login.
    def test_login_required_redirects_missing_session(self):
        with app_module.app.test_request_context("/protected"):
            with patch.object(request_service.logging_service, "log_auth_event") as log_auth_event:
                response = request_service.login_required(lambda: "OK")()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/login")
        log_auth_event.assert_called_once()

    # Fungsi untuk memastikan role yang tidak sesuai tetap ditolak.
    def test_role_required_blocks_wrong_role(self):
        with app_module.app.test_request_context("/admin"):
            session["role"] = "user"
            with patch.object(request_service.logging_service, "log_auth_event") as log_auth_event:
                result = request_service.role_required("admin")(lambda: "OK")()

        self.assertIn("Akses ditolak", result)
        log_auth_event.assert_called_once()


if __name__ == "__main__":
    unittest.main()
