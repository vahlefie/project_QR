import unittest
from types import SimpleNamespace

from blueprints import registry


class BlueprintRegistryTest(unittest.TestCase):
    # Fungsi untuk memastikan registry hanya meneruskan dependency yang diminta.
    def test_select_dependencies(self):
        deps = SimpleNamespace(alpha=1, beta=2, gamma=3)

        selected = registry.select_dependencies(deps, ("alpha", "gamma"))

        self.assertEqual(selected.alpha, 1)
        self.assertEqual(selected.gamma, 3)
        self.assertFalse(hasattr(selected, "beta"))

    # Fungsi untuk memastikan daftar dependency Blueprint tetap unik.
    def test_blueprint_dependency_names_are_unique(self):
        dependency_groups = (
            registry.AUTH_DEPS,
            registry.ATTENDANCE_DEPS,
            registry.DASHBOARD_DEPS,
            registry.CLIENT_STAFF_DEPS,
            registry.STAFF_DEPS,
            registry.GUESTS_DEPS,
            registry.USER_DEPS,
            registry.ADMIN_DEPS,
        )

        for names in dependency_groups:
            self.assertEqual(len(names), len(set(names)))


if __name__ == "__main__":
    unittest.main()
