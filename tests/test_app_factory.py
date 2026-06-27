import unittest

import app as app_module


class AppFactoryTest(unittest.TestCase):
    # Fungsi untuk memastikan app global dibuat lewat factory tanpa memutus konfigurasi lama.
    def test_global_app_factory_setup(self):
        self.assertTrue(callable(app_module.create_app))
        self.assertIs(app_module.app.extensions["sqlalchemy"], app_module.db)
        self.assertIn("attendance_time", app_module.app.jinja_env.filters)

    # Fungsi untuk memastikan hook lifecycle request terpasang pada app hasil factory.
    def test_request_lifecycle_hooks_registered(self):
        before_request_names = {callback.__name__ for callback in app_module.app.before_request_funcs.get(None, [])}
        after_request_names = {callback.__name__ for callback in app_module.app.after_request_funcs.get(None, [])}

        self.assertIn("prepare_activity_log_context", before_request_names)
        self.assertIn("enforce_login_session_timeout", before_request_names)
        self.assertIn("write_request_access_log", after_request_names)


if __name__ == "__main__":
    unittest.main()
