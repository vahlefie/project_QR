from datetime import date
import tarfile
import tempfile
import unittest
from pathlib import Path

import pandas as pd

import app as app_module
from models import BillingPayment, EventArchive, Guests, User
from services import event_archive_service


class EventArchiveServiceTest(unittest.TestCase):
    # Fungsi untuk menyiapkan root path dan instance path sementara.
    def setUp(self):
        self.original_root_path = app_module.app.root_path
        self.original_instance_path = app_module.app.instance_path
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_dir = Path(self.temp_dir.name)
        app_module.app.root_path = str(self.root_dir)
        app_module.app.instance_path = str(self.root_dir / "instance")

    # Fungsi untuk membersihkan data test dan path sementara.
    def tearDown(self):
        with app_module.app.app_context():
            client = User.query.filter_by(username="event_archive_client").first()
            if client:
                EventArchive.query.filter_by(user_id=client.id).delete()
                BillingPayment.query.filter_by(user_id=client.id).delete()
                Guests.query.filter_by(user_id=client.id).delete()
                app_module.db.session.delete(client)
                app_module.db.session.commit()
        app_module.app.root_path = self.original_root_path
        app_module.app.instance_path = self.original_instance_path
        self.temp_dir.cleanup()

    # Fungsi untuk membuat client expired dan payment event.
    def create_expired_client(self, event_name="Event Lama"):
        User.query.filter_by(username="event_archive_client").delete()
        User.query.filter_by(no_hp=6281200066001).delete()
        client = User()
        client.username = "event_archive_client"
        client.nama = "Event Archive Client"
        client.email = "event_archive_client@example.com"
        client.no_hp = 6281200066001
        client.role = app_module.ROLE_USER
        app_module.db.session.add(client)
        app_module.db.session.commit()

        payment = BillingPayment()
        payment.user_id = client.id
        payment.payment_date = date(2026, 6, 1)
        payment.amount = 100000
        payment.package_name = "premium"
        payment.period_start = date(2026, 6, 1)
        payment.period_end = date(2026, 6, 15)
        payment.event_name = event_name
        payment.status = "verified"
        app_module.db.session.add(payment)
        app_module.db.session.commit()
        return client, payment

    # Fungsi untuk memastikan backup final membuat CSV lalu menghapus data tamu.
    def test_ensure_final_guest_backup_writes_csv_and_deletes_guests(self):
        with app_module.app.app_context():
            client, payment = self.create_expired_client()
            guest = Guests()
            guest.user_id = client.id
            guest.no = 1
            guest.nama = "Tamu Lama"
            guest.no_hp = "62812345678"
            guest.email = "tamu@example.com"
            guest.status = "VIP"
            guest.jumlah_orang = 3
            app_module.db.session.add(guest)
            app_module.db.session.commit()
            upload_dir = Path(app_module.app.instance_path) / "uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)
            upload_path = upload_dir / "Event_Lama_event_archive_client_2026-06-01.xlsx"
            upload_path.write_bytes(b"upload lama")

            archive = event_archive_service.ensure_final_guest_backup(
                client,
                payment=payment,
                today=date(2026, 6, 17),
            )

            csv_path = self.root_dir / "backup" / "event" / str(client.id) / "Event_Lama_Final_2026.csv"
            self.assertEqual(archive.csv_path, str(csv_path))
            self.assertTrue(csv_path.exists())
            self.assertEqual(Guests.query.filter_by(user_id=client.id).count(), 0)
            dataframe = pd.read_csv(csv_path, dtype=str, keep_default_na=False).fillna("")
            self.assertEqual(dataframe.iloc[0]["nama"], "Tamu Lama")
            self.assertEqual(dataframe.iloc[0]["status"], "VIP")
            self.assertEqual(dataframe.iloc[0]["jumlah_orang"], "N/A")
            self.assertFalse(upload_path.exists())
            self.assertTrue((csv_path.parent / upload_path.name).exists())

    # Fungsi untuk memastikan pemindahan upload expired tidak membuat tar.gz.
    def test_move_expired_client_uploads_moves_upload_without_tar_archive(self):
        with app_module.app.app_context():
            client, _payment = self.create_expired_client(event_name="Event Upload")
            upload_dir = Path(app_module.app.instance_path) / "uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)
            upload_path = upload_dir / "Event_Upload_event_archive_client_2026-06-01.xlsx"
            upload_path.write_bytes(b"upload lama")

            results = event_archive_service.move_expired_client_uploads(today=date(2026, 6, 17))

            backup_path = self.root_dir / "backup" / "event" / str(client.id) / upload_path.name
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["user_id"], client.id)
            self.assertFalse(upload_path.exists())
            self.assertTrue(backup_path.exists())
            self.assertEqual(list(backup_path.parent.glob("*.tar.gz")), [])

    # Fungsi untuk memastikan reaktivasi mengarsipkan CSV dan upload lama ke tar.gz lalu menghapus sumber.
    def test_archive_previous_event_for_reactivation_creates_tar_and_removes_sources(self):
        with app_module.app.app_context():
            client, payment = self.create_expired_client(event_name="Event Reaktivasi")
            guest = Guests()
            guest.user_id = client.id
            guest.nama = "Tamu Reaktivasi"
            guest.no_hp = "62812345678"
            app_module.db.session.add(guest)
            app_module.db.session.commit()

            upload_dir = Path(app_module.app.instance_path) / "uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)
            upload_path = upload_dir / "Event_Reaktivasi_event_archive_client_2026-06-01.xlsx"
            upload_path.write_bytes(b"upload lama")

            tar_path = event_archive_service.archive_previous_event_for_reactivation(
                client,
                previous_payment=payment,
                today=date(2026, 6, 17),
            )

            self.assertTrue(tar_path.exists())
            with tarfile.open(tar_path, "r:gz") as archive:
                self.assertEqual(
                    sorted(archive.getnames()),
                    [
                        "Event_Reaktivasi_Final_2026.csv",
                        "Event_Reaktivasi_event_archive_client_2026-06-01.xlsx",
                    ],
                )
            self.assertFalse((tar_path.parent / "Event_Reaktivasi_Final_2026.csv").exists())
            self.assertFalse((tar_path.parent / upload_path.name).exists())
            self.assertFalse(upload_path.exists())


if __name__ == "__main__":
    unittest.main()
