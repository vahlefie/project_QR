import unittest
from types import SimpleNamespace

from services import staff_service


class StaffServiceTest(unittest.TestCase):
    # Fungsi untuk memastikan hash token staff stabil dan aman disimpan.
    def test_hash_staff_access_token_is_stable_sha256(self):
        first_hash = staff_service.hash_staff_access_token("token")
        second_hash = staff_service.hash_staff_access_token("token")

        self.assertEqual(first_hash, second_hash)
        self.assertEqual(len(first_hash), 64)

    # Fungsi untuk memastikan PIN staff selalu enam digit.
    def test_generate_staff_pin_has_six_digits(self):
        pin = staff_service.generate_staff_pin()

        self.assertEqual(len(pin), 6)
        self.assertTrue(pin.isdigit())

    # Fungsi untuk memastikan nama tampilan staff memakai nama lalu fallback nomor HP.
    def test_get_staff_display_name(self):
        staff_with_name = SimpleNamespace(nama="Staff A", no_hp="628123")
        staff_without_name = SimpleNamespace(nama="", no_hp="628456")

        self.assertEqual(staff_service.get_staff_display_name(staff_with_name), "Staff A")
        self.assertEqual(staff_service.get_staff_display_name(staff_without_name), "628456")
        self.assertEqual(staff_service.get_staff_display_name(None), "")

    # Fungsi untuk memastikan revoke staff access mengisi metadata pencabutan.
    def test_revoke_staff_access_marks_access_inactive(self):
        staff_access = SimpleNamespace(
            is_active=True,
            revoked_at=None,
            revoked_by=None,
            revoked_reason=None,
        )

        staff_service.revoke_staff_access(staff_access, revoked_by="client", reason="logout")

        self.assertFalse(staff_access.is_active)
        self.assertIsNotNone(staff_access.revoked_at)
        self.assertEqual(staff_access.revoked_by, "client")
        self.assertEqual(staff_access.revoked_reason, "logout")

    # Fungsi untuk memastikan payload log staff cocok berdasarkan id, nomor HP, atau username.
    def test_is_staff_log_payload(self):
        staff = SimpleNamespace(id=7, no_hp="628123")

        self.assertTrue(
            staff_service.is_staff_log_payload(
                {"_log_category": "ACTIVITY", "details": {"staff_id": 7}},
                staff,
            )
        )
        self.assertTrue(
            staff_service.is_staff_log_payload(
                {"_log_category": "ACTIVITY", "username": "staff:628123"},
                staff,
            )
        )
        self.assertFalse(
            staff_service.is_staff_log_payload(
                {"_log_category": "AUTH", "details": {"staff_id": 7}},
                staff,
            )
        )

    # Fungsi untuk memastikan pesan log staff dibuat ramah dibaca.
    def test_format_staff_log_message(self):
        payload = {
            "event_type": "UPDATE_GUEST_STATUS",
            "details": {"old_status": "Reguler", "new_status": "VIP"},
        }

        self.assertEqual(
            staff_service.format_staff_log_message(payload),
            "Staff mengubah status tamu dari Reguler ke VIP.",
        )
        self.assertEqual(
            staff_service.format_staff_log_message({"event_type": "UNKNOWN"}),
            "Staff melakukan aktivitas pada sistem.",
        )


if __name__ == "__main__":
    unittest.main()
