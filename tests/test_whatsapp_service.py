import unittest
from datetime import date, timedelta

import app as app_module
from models import BillingPayment, GuestShortUrl, Guests, User
from services import whatsapp_service


class WhatsappServiceTest(unittest.TestCase):
    # Fungsi untuk membersihkan data test short URL QR.
    def tearDown(self):
        with app_module.app.app_context():
            GuestShortUrl.query.delete()
            Guests.query.filter(Guests.nama.in_(("Ajin Ajojing", "Ajin Ajojing!!!"))).delete()
            client = User.query.filter_by(username="shortqrclient").first()
            if client:
                BillingPayment.query.filter_by(user_id=client.id).delete()
            User.query.filter_by(username="shortqrclient").delete()
            app_module.db.session.commit()

    # Fungsi untuk memastikan nama tamu diubah menjadi slug URL pendek.
    def test_slugify_guest_name(self):
        self.assertEqual(whatsapp_service.slugify_guest_name("Ajin Ajojing"), "Ajin_Ajojing")
        self.assertEqual(whatsapp_service.slugify_guest_name(" Ajin   Ajojing!!! "), "Ajin_Ajojing")
        self.assertEqual(whatsapp_service.slugify_guest_name(""), "Tamu")

    # Fungsi untuk memastikan API token disensor dengan menyisakan 4 karakter terakhir.
    def test_mask_whatsapp_secret(self):
        self.assertEqual(whatsapp_service.mask_whatsapp_secret("abcd1234"), "****1234")
        self.assertEqual(whatsapp_service.mask_whatsapp_secret("abc"), "***")
        self.assertEqual(whatsapp_service.mask_whatsapp_secret(""), "Belum diatur")

    # Fungsi untuk memastikan short URL QR memakai user_id, nama tamu, dan suffix unik.
    def test_build_guest_short_qr_url_uses_unique_user_id_and_guest_name(self):
        with app_module.app.app_context():
            User.query.filter_by(username="shortqrclient").delete()
            User.query.filter_by(no_hp=6281299990000).delete()
            client = User()
            client.username = "shortqrclient"
            client.nama = "Short QR Client"
            client.email = "shortqrclient@example.com"
            client.no_hp = 6281299990000
            client.role = app_module.ROLE_USER
            client.paket = app_module.PACKAGE_PREMIUM
            app_module.db.session.add(client)
            app_module.db.session.commit()
            payment = BillingPayment()
            payment.user_id = client.id
            payment.payment_date = date.today()
            payment.amount = 100000
            payment.package_name = app_module.PACKAGE_PREMIUM
            payment.period_start = date.today() - timedelta(days=1)
            payment.period_end = date.today() + timedelta(days=1)
            payment.event_name = "Short QR Event"
            payment.status = "verified"
            app_module.db.session.add(payment)
            app_module.db.session.commit()

            first_guest = Guests()
            first_guest.nama = "Ajin Ajojing"
            first_guest.no_hp = "6281211111111"
            first_guest.user_id = client.id
            first_guest.owner = client

            second_guest = Guests()
            second_guest.nama = "Ajin Ajojing"
            second_guest.no_hp = "6281222222222"
            second_guest.user_id = client.id
            second_guest.owner = client

            app_module.db.session.add(first_guest)
            app_module.db.session.add(second_guest)
            app_module.db.session.commit()
            first_guest_id = first_guest.id
            second_guest_id = second_guest.id
            client_id = client.id

            with app_module.app.test_request_context("/"):
                first_url = app_module.build_guest_short_qr_url(first_guest)
                second_url = app_module.build_guest_short_qr_url(second_guest)

            self.assertIn(f"/q/{client_id}_Ajin_Ajojing", first_url)
            self.assertIn(f"/q/{client_id}_Ajin_Ajojing_2", second_url)

        response = app_module.app.test_client().get(f"/q/{client_id}_Ajin_Ajojing")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/qr/", response.location)

        with app_module.app.app_context():
            self.assertEqual(GuestShortUrl.query.filter_by(guest_id=first_guest_id).count(), 1)
            self.assertEqual(GuestShortUrl.query.filter_by(guest_id=second_guest_id).count(), 1)


if __name__ == "__main__":
    unittest.main()
