import unittest
import tempfile
from datetime import date
from io import BytesIO
from types import SimpleNamespace

import app as app_module
import pandas as pd
from exceptions import UploadValidationError
from models import BillingPayment, Guests, User
from services import guest_service
from werkzeug.datastructures import FileStorage


class GuestServiceTest(unittest.TestCase):
    # Fungsi untuk menyiapkan instance path sementara bagi test upload.
    def setUp(self):
        self.original_instance_path = app_module.app.instance_path
        self.temp_dir = tempfile.TemporaryDirectory()
        app_module.app.instance_path = self.temp_dir.name

    # Fungsi untuk mengembalikan instance path setelah test.
    def tearDown(self):
        app_module.app.instance_path = self.original_instance_path
        self.temp_dir.cleanup()

    # Fungsi untuk memastikan nama tamu dibersihkan dan dibuat title case.
    def test_clean_guest_name(self):
        self.assertEqual(guest_service.clean_guest_name("  budi@@ santoso  "), "Budi Santoso")
        self.assertEqual(guest_service.clean_guest_name(""), "")

    # Fungsi untuk memastikan nomor HP tamu dinormalisasi ke awalan 62.
    def test_clean_guest_phone(self):
        self.assertEqual(guest_service.clean_guest_phone("0812345678"), "62812345678")
        self.assertEqual(guest_service.clean_guest_phone("812345678"), "62812345678")
        self.assertEqual(guest_service.clean_guest_phone(812345678.0), "62812345678")
        self.assertEqual(guest_service.clean_guest_phone("-812345678"), "")

    # Fungsi untuk memastikan email dan status tamu memakai aturan default.
    def test_clean_guest_email_and_status(self):
        self.assertEqual(guest_service.clean_guest_email(" USER@Email.COM "), "user@email.com")
        self.assertEqual(guest_service.clean_guest_email("invalid-email"), "")
        self.assertEqual(guest_service.clean_guest_status("vip"), "VIP")
        self.assertEqual(guest_service.clean_guest_status("unknown"), "Reguler")

    # Fungsi untuk memastikan satu baris Excel dibangun menjadi record bersih.
    def test_build_guest_record(self):
        row = {
            "no": "2",
            "nama": "andi###",
            "no_hp": "0812345678",
            "email": "BAD",
            "status": "",
        }

        record = guest_service.build_guest_record(row, fallback_no=1)

        self.assertEqual(
            record,
            {
                "no": 2,
                "nama": "Andi",
                "no_hp": "62812345678",
                "email": None,
                "status": "Reguler",
            },
        )

    # Fungsi untuk memastikan sumber penambah dan pengedit tamu tersimpan pada jalur berbeda.
    def test_guest_added_by_is_saved_from_actor_label(self):
        with app_module.app.app_context():
            existing_client = User.query.filter_by(username="added_by_client").first()
            if existing_client:
                Guests.query.filter_by(user_id=existing_client.id).delete()
                app_module.db.session.delete(existing_client)
            User.query.filter_by(no_hp=6281200044103).delete()
            app_module.db.session.commit()

            client = User()
            client.username = "added_by_client"
            client.nama = "Added By Client"
            client.email = "added_by_client@example.com"
            client.no_hp = 6281200044103
            client.role = app_module.ROLE_USER
            app_module.db.session.add(client)
            app_module.db.session.commit()

            manual_data = guest_service.build_manual_guest_data(
                {
                    "nama": "tamu manual",
                    "no_hp": "0812345678",
                    "email": "",
                    "status": "Reguler",
                },
                client,
            )
            self.assertEqual(manual_data["added_by"], "added_by_client")

            rows = [
                {
                    "no": 1,
                    "nama": "Tamu Upload",
                    "no_hp": "62812345678",
                    "email": None,
                    "status": "Reguler",
                }
            ]
            guest_service.save_guest_rows(client, rows, include_duplicates=True)
            guest = Guests.query.filter_by(user_id=client.id, no_hp="62812345678").first()

            self.assertIsNotNone(guest)
            self.assertEqual(guest.added_by, "added_by_client")
            self.assertIsNone(guest.edited_by)
            self.assertEqual(
                guest_service.build_owner_guest_edited_by(
                    SimpleNamespace(nama="Client Display", username="client_username")
                ),
                "Client Display",
            )
            self.assertEqual(
                guest_service.build_staff_guest_added_by(SimpleNamespace(nama="Staff Input", no_hp="62812999")),
                "Staff Input",
            )

            guest_service.replace_guest_rows(
                client,
                [
                    {
                        "no": 1,
                        "nama": "Tamu Upload Baru",
                        "no_hp": "62812345678",
                        "email": None,
                        "status": "VIP",
                    }
                ],
                edited_by="Staff Input",
            )
            app_module.db.session.refresh(guest)

            self.assertEqual(guest.nama, "Tamu Upload Baru")
            self.assertEqual(guest.status, "VIP")
            self.assertEqual(guest.added_by, "added_by_client")
            self.assertEqual(guest.edited_by, "Staff Input")

            Guests.query.filter_by(user_id=client.id).delete()
            app_module.db.session.delete(client)
            app_module.db.session.commit()

    # Fungsi untuk memastikan nama sama tidak dianggap duplicate saat preview upload.
    def test_build_guest_upload_preview_ignores_matching_guest_name(self):
        with app_module.app.app_context():
            User.query.filter_by(username="same_name_upload_client").delete()
            User.query.filter_by(no_hp=6281200044102).delete()
            app_module.db.session.commit()

            client = User()
            client.username = "same_name_upload_client"
            client.nama = "Same Name Upload Client"
            client.email = "same_name_upload_client@example.com"
            client.no_hp = 6281200044102
            client.role = app_module.ROLE_USER
            app_module.db.session.add(client)
            app_module.db.session.commit()

            existing_guest = Guests()
            existing_guest.no = 1
            existing_guest.nama = "Nama Sama"
            existing_guest.no_hp = "628111111111"
            existing_guest.email = "lama@example.com"
            existing_guest.status = "Reguler"
            existing_guest.user_id = client.id
            app_module.db.session.add(existing_guest)
            app_module.db.session.commit()

            excel_data = BytesIO()
            pd.DataFrame(
                [
                    {
                        "no": 1,
                        "nama": "nama sama",
                        "no_hp": "081222222222",
                        "email": "baru@example.com",
                        "status": "VIP",
                    }
                ]
            ).to_excel(excel_data, index=False)
            excel_data.seek(0)
            file = FileStorage(stream=excel_data, filename="guests.xlsx")

            preview = guest_service.build_guest_upload_preview(file, client)

            self.assertEqual(preview["stats"]["cleaned_count"], 1)
            self.assertEqual(preview["stats"]["duplicate_count"], 0)
            self.assertEqual(preview["duplicates"], [])
            self.assertEqual(preview["duplicate_indexes"], [])

            Guests.query.filter_by(user_id=client.id).delete()
            app_module.db.session.delete(client)
            app_module.db.session.commit()

    # Fungsi untuk memastikan replace upload tidak mencocokkan tamu hanya dari nama.
    def test_guest_matches_row_ignores_name(self):
        guest = SimpleNamespace(
            nama="Nama Sama",
            no_hp="628111111111",
            email="lama@example.com",
        )

        self.assertFalse(
            guest_service.guest_matches_row(
                guest,
                {
                    "nama": "Nama Sama",
                    "no_hp": "628222222222",
                    "email": "baru@example.com",
                },
            )
        )
        self.assertTrue(
            guest_service.guest_matches_row(
                guest,
                {
                    "nama": "Nama Baru",
                    "no_hp": "08111111111",
                    "email": "baru@example.com",
                },
            )
        )

    # Fungsi untuk memastikan preview upload menyimpan daftar data yang dihapus saat cleaning.
    def test_build_guest_upload_preview_tracks_removed_rows(self):
        with app_module.app.app_context():
            User.query.filter_by(username="removed_rows_client").delete()
            User.query.filter_by(no_hp=6281200044101).delete()
            client = User()
            client.username = "removed_rows_client"
            client.nama = "Removed Rows Client"
            client.email = "removed_rows_client@example.com"
            client.no_hp = 6281200044101
            client.role = app_module.ROLE_USER
            app_module.db.session.add(client)
            app_module.db.session.commit()

            excel_data = BytesIO()
            pd.DataFrame(
                [
                    {"no": 1, "nama": "valid tamu", "no_hp": "0812345678", "email": "", "status": "Reguler"},
                    {"no": 2, "nama": "", "no_hp": "0812345678", "email": "hapus@example.com", "status": "VIP"},
                    {"no": 3, "nama": "hp salah", "no_hp": "-812345678", "email": "", "status": "Reguler"},
                ]
            ).to_excel(excel_data, index=False)
            excel_data.seek(0)
            file = FileStorage(stream=excel_data, filename="guests.xlsx")

            preview = guest_service.build_guest_upload_preview(file, client)

            self.assertEqual(preview["stats"]["cleaned_count"], 1)
            self.assertEqual(preview["stats"]["removed_count"], 2)
            self.assertEqual(len(preview["removed_rows"]), 2)
            self.assertEqual(preview["removed_rows"][0]["row_number"], 3)
            self.assertEqual(preview["removed_rows"][0]["nama"], "N/A")
            self.assertEqual(preview["removed_rows"][0]["reason"], "Nama kosong/tidak valid")
            self.assertEqual(preview["removed_rows"][1]["row_number"], 4)
            self.assertEqual(preview["removed_rows"][1]["reason"], "No HP kosong/tidak valid")

            Guests.query.filter_by(user_id=client.id).delete()
            app_module.db.session.delete(client)
            app_module.db.session.commit()

    # Fungsi untuk memastikan format kolom Excel tamu divalidasi ketat.
    def test_validate_guest_excel_format(self):
        valid_df = pd.DataFrame(columns=["no", "nama", "no_hp", "email", "status"])
        invalid_df = pd.DataFrame(columns=["nama", "no_hp"])

        guest_service.validate_guest_excel_format(valid_df)
        with self.assertRaises(UploadValidationError):
            guest_service.validate_guest_excel_format(invalid_df)

    # Fungsi untuk memastikan file upload disimpan dengan nama event, username, tanggal, dan suffix urut.
    def test_save_uploaded_guest_file_uses_event_username_date_and_sequence(self):
        with app_module.app.app_context():
            User.query.filter_by(username="upload_client_test").delete()
            User.query.filter_by(no_hp=6281200044001).delete()
            client = User()
            client.username = "upload_client_test"
            client.nama = "Upload Client"
            client.email = "upload_client_test@example.com"
            client.no_hp = 6281200044001
            client.role = app_module.ROLE_USER
            app_module.db.session.add(client)
            app_module.db.session.commit()

            payment = BillingPayment()
            payment.user_id = client.id
            payment.payment_date = date(2026, 6, 16)
            payment.amount = 100000
            payment.event_name = "Akad Mei 2026"
            payment.status = "verified"
            app_module.db.session.add(payment)
            app_module.db.session.commit()

            first_file = FileStorage(stream=BytesIO(b"first"), filename="guests.xlsx")
            second_file = FileStorage(stream=BytesIO(b"second"), filename="guests.xlsx")
            first_path = guest_service.save_uploaded_guest_file(first_file, client, upload_date=date(2026, 6, 16))
            second_path = guest_service.save_uploaded_guest_file(second_file, client, upload_date=date(2026, 6, 16))

            self.assertEqual(first_path.name, "Akad_Mei_2026_upload_client_test_2026-06-16.xlsx")
            self.assertEqual(second_path.name, "Akad_Mei_2026_upload_client_test_2026-06-16_2.xlsx")
            self.assertEqual(first_path.read_bytes(), b"first")
            self.assertEqual(second_path.read_bytes(), b"second")

            BillingPayment.query.filter_by(user_id=client.id).delete()
            app_module.db.session.delete(client)
            app_module.db.session.commit()


if __name__ == "__main__":
    unittest.main()
