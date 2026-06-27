import unittest
from types import SimpleNamespace

from services import listing_service


class ListingServiceTest(unittest.TestCase):
    # Fungsi untuk memastikan opsi sort dan paging memakai fallback yang benar.
    def test_normalize_sort_and_per_page(self):
        self.assertEqual(listing_service.normalize_guest_sort("name_asc"), "name_asc")
        self.assertEqual(listing_service.normalize_guest_sort("attendance_desc"), "attendance_desc")
        self.assertEqual(listing_service.normalize_guest_sort("unknown"), "latest")
        self.assertEqual(listing_service.normalize_user_sort("name_desc"), "name_desc")
        self.assertEqual(listing_service.normalize_user_sort("latest"), "name_asc")
        self.assertEqual(listing_service.normalize_per_page(50), 50)
        self.assertEqual(listing_service.normalize_per_page(25), 10)

    # Fungsi untuk memastikan akses staff ke tamu dibatasi owner_user_id.
    def test_get_accessible_staff_guest_owner_guard(self):
        staff = SimpleNamespace(owner_user_id=10)
        allowed_guest = SimpleNamespace(user_id=10)
        denied_guest = SimpleNamespace(user_id=11)

        self.assertIs(listing_service.get_accessible_staff_guest_from_object(staff, allowed_guest), allowed_guest)
        self.assertIsNone(listing_service.get_accessible_staff_guest_from_object(staff, denied_guest))
        self.assertIsNone(listing_service.get_accessible_staff_guest_from_object(None, allowed_guest))

    # Fungsi untuk memastikan halaman staff selalu memakai sort kehadiran terbaru.
    def test_build_staff_guest_context_forces_attendance_sort(self):
        original_get_staff_owner = listing_service.staff_service.get_staff_owner
        original_build_guest_pagination_context = listing_service.build_guest_pagination_context
        captured = {}

        def fake_get_staff_owner(staff):
            return SimpleNamespace(id=staff.owner_user_id)

        def fake_build_guest_pagination_context(search, page, per_page, owner_user_id=None, sort_by="latest"):
            captured["sort_by"] = sort_by
            return {
                "guests": [],
                "pagination": SimpleNamespace(page=page, pages=0, has_prev=False, has_next=False),
                "search": search,
                "per_page": per_page,
                "sort_by": sort_by,
                "total_guests": 0,
                "guest_status_options": ("Reguler", "VIP"),
                "default_guest_status": "Reguler",
            }

        listing_service.staff_service.get_staff_owner = fake_get_staff_owner
        listing_service.build_guest_pagination_context = fake_build_guest_pagination_context
        try:
            context = listing_service.build_staff_guest_context(
                SimpleNamespace(owner_user_id=10, nama="Staff Test"),
                search="",
                page=1,
                per_page=10,
                sort_by="name_asc",
            )
        finally:
            listing_service.staff_service.get_staff_owner = original_get_staff_owner
            listing_service.build_guest_pagination_context = original_build_guest_pagination_context

        self.assertEqual(captured["sort_by"], "attendance_desc")
        self.assertEqual(context["sort_by"], "attendance_desc")
        self.assertFalse(context["show_guest_qr_column"])

    # Fungsi untuk memastikan client inactive hanya mendapat akses export di halaman Data.
    def test_build_user_guest_context_disables_guest_table_for_inactive_client(self):
        original_calculate_status = listing_service.account_service.calculate_account_activation_status
        original_build_guest_pagination_context = listing_service.build_guest_pagination_context

        def fake_build_guest_pagination_context(search, page, per_page, owner_user_id=None, sort_by="latest"):
            return {
                "guests": [],
                "pagination": SimpleNamespace(page=page, pages=0, has_prev=False, has_next=False),
                "search": search,
                "per_page": per_page,
                "sort_by": sort_by,
                "total_guests": 0,
                "guest_status_options": ("Reguler", "VIP"),
                "default_guest_status": "Reguler",
            }

        listing_service.account_service.calculate_account_activation_status = lambda _user: False
        listing_service.build_guest_pagination_context = fake_build_guest_pagination_context
        try:
            context = listing_service.build_user_guest_context(
                SimpleNamespace(id=9, nama="Client Inactive", username="inactive"),
                search="",
                page=1,
                per_page=10,
                sort_by="latest",
            )
        finally:
            listing_service.account_service.calculate_account_activation_status = original_calculate_status
            listing_service.build_guest_pagination_context = original_build_guest_pagination_context

        self.assertFalse(context["allow_guest_upload"])
        self.assertFalse(context["allow_guest_mutations"])
        self.assertFalse(context["show_guest_table"])
        self.assertTrue(context["allow_guest_export"])


if __name__ == "__main__":
    unittest.main()
