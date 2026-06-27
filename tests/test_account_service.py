from datetime import date, timedelta
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import app as app_module
from services import account_service


class AccountServiceTest(unittest.TestCase):
    # Fungsi untuk memastikan nomor HP akun menerima input lokal dan canonical dari UI +62.
    def test_normalize_phone_number(self):
        self.assertEqual(account_service.normalize_phone_number("0812345678"), "62812345678")
        self.assertEqual(account_service.normalize_phone_number("812345678"), "62812345678")
        self.assertEqual(account_service.normalize_phone_number("62812345678"), "62812345678")
        self.assertEqual(account_service.normalize_phone_number("12345"), "")
        self.assertEqual(account_service.normalize_phone_number("abc"), "")

    # Fungsi untuk memastikan nama tampilan memakai nama lalu username.
    def test_get_user_display_name(self):
        named_account = SimpleNamespace(nama="Client A", username="clienta")
        unnamed_account = SimpleNamespace(nama="", username="clientb")

        self.assertEqual(account_service.get_user_display_name(named_account), "Client A")
        self.assertEqual(account_service.get_user_display_name(unnamed_account), "clientb")

    # Fungsi untuk memastikan parsing tanggal expired memakai format ISO.
    def test_parse_iso_date(self):
        self.assertEqual(account_service.parse_iso_date("2026-05-29"), date(2026, 5, 29))
        self.assertIsNone(account_service.parse_iso_date("29-05-2026"))
        self.assertIsNone(account_service.parse_iso_date(None))

    # Fungsi untuk memastikan status aktivasi dihitung dari tanggal expired.
    def test_calculate_activation_status(self):
        self.assertTrue(account_service.calculate_activation_status(date.today()))
        self.assertTrue(account_service.calculate_activation_status(date.today() + timedelta(days=1)))
        self.assertFalse(account_service.calculate_activation_status(date.today() - timedelta(days=1)))
        self.assertFalse(account_service.calculate_activation_status(None))

    # Fungsi untuk memastikan sinkronisasi banyak user hanya commit saat ada perubahan.
    def test_sync_users_activation_status_commits_when_changed(self):
        active_user = SimpleNamespace(tgl_expired=date.today() - timedelta(days=1), aktivasi=True)
        unchanged_user = SimpleNamespace(tgl_expired=date.today() + timedelta(days=1), aktivasi=True)

        with app_module.app.app_context():
            with patch.object(account_service.db.session, "commit") as commit:
                account_service.sync_users_activation_status([active_user, unchanged_user])

        self.assertFalse(active_user.aktivasi)
        self.assertTrue(unchanged_user.aktivasi)
        commit.assert_called_once()

    # Fungsi untuk memastikan fallback nama tampilan mengambil session user.
    def test_get_user_display_name_falls_back_to_session(self):
        with app_module.app.test_request_context("/"):
            from flask import session

            session["user"] = "session-user"
            self.assertEqual(account_service.get_user_display_name(None), "session-user")

    # Fungsi untuk memastikan validasi form user berhenti pada field wajib.
    def test_validate_new_user_form_required_fields(self):
        error = account_service.validate_new_user_form("", "", "", None, "")

        self.assertEqual(error, "Password, nama, no hp, dan email wajib diisi.")

    # Fungsi untuk memastikan validasi form admin berhenti pada username invalid.
    def test_validate_admin_form_username_pattern(self):
        error = account_service.validate_admin_form("ab", "Admin1234!", "0812345678", 62812345678, "admin@test.com")

        self.assertEqual(error, "Username 3-15 karakter, hanya huruf, angka, atau underscore.")


if __name__ == "__main__":
    unittest.main()
