import unittest
from types import SimpleNamespace

import app as app_module
from constants import ROLE_USER, SESSION_LAST_ACTIVITY_KEY, SESSION_TIMEOUT_SECONDS
from flask import session
from services import auth_service
from werkzeug.security import generate_password_hash


class AuthServiceTest(unittest.TestCase):
    # Fungsi untuk menguji normalisasi identifier login pada service auth.
    def test_normalize_login_identifier(self):
        self.assertEqual(auth_service.normalize_login_identifier(" USER@Email.COM "), "user@email.com")
        self.assertEqual(auth_service.normalize_login_identifier("   "), "anonymous")

    # Fungsi untuk memastikan password helper menerima hash dan fallback password lama.
    def test_password_matches_hash_and_plaintext_fallback(self):
        password_hash = generate_password_hash("User1234")

        self.assertTrue(auth_service.password_matches(password_hash, "User1234"))
        self.assertTrue(auth_service.password_matches("legacy-password", "legacy-password"))
        self.assertFalse(auth_service.password_matches(password_hash, "wrong-password"))

    # Fungsi untuk memastikan session login dibuat dan timeout dihitung konsisten.
    def test_start_login_session_and_timeout(self):
        user = SimpleNamespace(username="client", role=ROLE_USER)

        with app_module.app.test_request_context("/"):
            auth_service.start_login_session(user)

            self.assertEqual(session["user"], "client")
            self.assertEqual(session["role"], ROLE_USER)
            self.assertFalse(auth_service.is_login_session_expired())

            session[SESSION_LAST_ACTIVITY_KEY] = auth_service.get_current_timestamp() - SESSION_TIMEOUT_SECONDS - 1
            self.assertTrue(auth_service.is_login_session_expired())


if __name__ == "__main__":
    unittest.main()
