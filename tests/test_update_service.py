import unittest
from services.update_service import parse_semver, is_version_newer, UpdateService


class TestUpdateService(unittest.TestCase):
    def test_parse_semver(self):
        self.assertEqual(parse_semver("1.0.0"), (1, 0, 0))
        self.assertEqual(parse_semver("v1.1.0"), (1, 1, 0))
        self.assertEqual(parse_semver("V2.10.5"), (2, 10, 5))
        self.assertEqual(parse_semver("1.2"), (1, 2, 0))
        self.assertEqual(parse_semver("3"), (3, 0, 0))

    def test_is_version_newer(self):
        self.assertTrue(is_version_newer("1.1.0", "1.0.0"))
        self.assertTrue(is_version_newer("v2.0.0", "1.9.9"))
        self.assertTrue(is_version_newer("1.0.1", "1.0.0"))
        self.assertFalse(is_version_newer("1.0.0", "1.0.0"))
        self.assertFalse(is_version_newer("1.0.0", "1.1.0"))
        self.assertFalse(is_version_newer("0.9.9", "1.0.0"))

    def test_update_service_defaults(self):
        svc = UpdateService(current_version="1.1.0")
        self.assertEqual(svc.current_version, "1.1.0")
        self.assertIn("github.com", svc.latest_release_url)


if __name__ == "__main__":
    unittest.main()

