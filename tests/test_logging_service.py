import tempfile
import unittest
from pathlib import Path

import app as app_module
from services import logging_service


class LoggingServiceTest(unittest.TestCase):
    # Fungsi untuk menyiapkan folder log sementara bagi service logging.
    def setUp(self):
        self.original_log_dir = logging_service.ACTIVITY_LOG_DIR
        self.original_file_prefix = logging_service.ACTIVITY_LOG_FILE_PREFIX
        self.temp_dir = tempfile.TemporaryDirectory()
        logging_service.configure_activity_log(Path(self.temp_dir.name), "activity")

    # Fungsi untuk mengembalikan konfigurasi log setelah test.
    def tearDown(self):
        logging_service.configure_activity_log(self.original_log_dir, self.original_file_prefix)
        self.temp_dir.cleanup()

    # Fungsi untuk memastikan unified log bisa ditulis dan dibaca kembali.
    def test_write_unified_log_creates_parseable_payload(self):
        with app_module.app.test_request_context("/logs", method="POST"):
            logging_service.write_unified_log(
                "INFO",
                "TEST",
                {"event_type": "UNIT_TEST"},
                request_id="REQ_ID-UNIT",
            )

        log_path = logging_service.get_daily_activity_log_path()
        log_line = log_path.read_text(encoding="utf-8").strip()
        payload = logging_service.parse_activity_log_line(log_line)

        self.assertIsNotNone(payload)
        self.assertEqual(payload["event_type"], "UNIT_TEST")
        self.assertEqual(payload["_log_category"], "TEST")
        self.assertTrue(payload["timestamp"].endswith("+07:00"))

    # Fungsi untuk memastikan tracking session id dibuat sekali dan dipakai ulang.
    def test_tracking_session_id_created_once(self):
        with app_module.app.test_request_context("/"):
            first_session_id = logging_service.get_tracking_session_id(create=True)
            second_session_id = logging_service.get_tracking_session_id(create=True)

        self.assertTrue(first_session_id.startswith("sess_"))
        self.assertEqual(first_session_id, second_session_id)


if __name__ == "__main__":
    unittest.main()
