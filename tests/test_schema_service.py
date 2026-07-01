import unittest

from constants import DEFAULT_GUEST_STATUS, DEFAULT_SUPER_ADMIN_PASSWORD, ROLE_SUPER_ADMIN
from services import schema_service


class SchemaServiceTest(unittest.TestCase):
    # Fungsi untuk memastikan default super admin tetap sama setelah dipindah ke service.
    def test_get_default_super_admin_data(self):
        data = schema_service.get_default_super_admin_data()

        self.assertEqual(data["username"], "admin")
        self.assertEqual(data["nama"], "Super Admin")
        self.assertEqual(data["password"], DEFAULT_SUPER_ADMIN_PASSWORD)
        self.assertEqual(data["role"], ROLE_SUPER_ADMIN)
        self.assertIs(data["must_reset_password"], False)

    # Fungsi untuk memastikan data demo fallback tersedia saat file Excel dummy tidak ada di server.
    def test_build_fallback_demo_guest_rows(self):
        demo_guests = schema_service.build_fallback_demo_guest_rows(total_rows=8)

        self.assertEqual(len(demo_guests), 8)
        self.assertEqual(demo_guests[0].no, 1)
        self.assertEqual(demo_guests[0].status, DEFAULT_GUEST_STATUS)
        self.assertEqual(demo_guests[0].kehadiran, "08:00")
        self.assertTrue(demo_guests[0].verifikasi)
        self.assertEqual(demo_guests[0].source_file, schema_service.FALLBACK_DEMO_SOURCE)
        self.assertEqual(demo_guests[3].kehadiran, "")
        self.assertEqual(demo_guests[3].verifikasi, "")


if __name__ == "__main__":
    unittest.main()
