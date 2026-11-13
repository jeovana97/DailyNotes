import io
import json
import os
import ssl
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from services.update_service import (
    parse_semver,
    is_version_newer,
    UpdateService,
    _build_ssl_context,
    _is_ssl_cert_error,
)


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

    def test_ssl_context_and_error_detection(self):
        ctx_verified = _build_ssl_context(verify=True)
        self.assertEqual(ctx_verified.verify_mode, ssl.CERT_REQUIRED)

        ctx_unverified = _build_ssl_context(verify=False)
        self.assertEqual(ctx_unverified.verify_mode, ssl.CERT_NONE)

        ssl_err = ssl.SSLCertVerificationError(1, "unable to get local issuer certificate")
        self.assertTrue(_is_ssl_cert_error(ssl_err))
        self.assertTrue(_is_ssl_cert_error(urllib.error.URLError(ssl_err)))
        self.assertTrue(
            _is_ssl_cert_error(
                urllib.error.URLError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
            )
        )
        self.assertFalse(_is_ssl_cert_error(urllib.error.URLError("Name or service not known")))

    def test_check_for_updates_ssl_fallback(self):
        svc = UpdateService(current_version="1.2.0")
        payload = json.dumps({
            "tag_name": "v1.3.0",
            "name": "DailyNotes v1.3.0",
            "body": "Novidades",
            "html_url": "https://github.com/jeovana97/DailyNotes/releases/tag/v1.3.0",
            "assets": [
                {
                    "name": "Instalador_DiarioAnotacoes_Setup.exe",
                    "browser_download_url": "https://github.com/jeovana97/DailyNotes/releases/download/v1.3.0/Instalador_DiarioAnotacoes_Setup.exe",
                    "size": 1024,
                }
            ],
        }).encode("utf-8")

        class FakeResp(io.BytesIO):
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.close()

        calls = []

        def fake_urlopen(req, timeout=5, context=None):
            calls.append(context.verify_mode if context else None)
            if len(calls) == 1:
                raise urllib.error.URLError(
                    ssl.SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
                )
            return FakeResp(payload)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            res = svc.check_for_updates()

        self.assertEqual(calls, [ssl.CERT_REQUIRED, ssl.CERT_NONE])
        self.assertIsNone(res["error"])
        self.assertTrue(res["has_update"])
        self.assertEqual(res["latest_version"], "1.3.0")

    def test_download_installer_ssl_fallback(self):
        svc = UpdateService(current_version="1.2.0")
        binary_data = b"MZ_FAKE_INSTALLER_DATA"

        class FakeDownloadResp(io.BytesIO):
            headers = {"content-length": str(len(binary_data))}
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.close()

        calls = []

        def fake_urlopen(req, timeout=30, context=None):
            calls.append(context.verify_mode if context else None)
            if len(calls) == 1:
                raise urllib.error.URLError(
                    ssl.SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate")
                )
            return FakeDownloadResp(binary_data)

        with tempfile.TemporaryDirectory() as tmpdir:
            dest_file = os.path.join(tmpdir, "setup.exe")
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                ok = svc.download_installer("https://example.com/setup.exe", dest_file)

            self.assertTrue(ok)
            self.assertEqual(calls, [ssl.CERT_REQUIRED, ssl.CERT_NONE])
            with open(dest_file, "rb") as f:
                self.assertEqual(f.read(), binary_data)


if __name__ == "__main__":
    unittest.main()

