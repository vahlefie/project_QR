import unittest

from constants import DEFAULT_SUPER_ADMIN_PASSWORD, ROLE_SUPER_ADMIN
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


if __name__ == "__main__":
    unittest.main()
