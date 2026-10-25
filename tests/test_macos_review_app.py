import plistlib
import shutil
import sys
import time

import pytest

from squint.platforms.macos.review_app import app_bundle, launch

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or shutil.which("swiftc") is None,
    reason="needs macOS and swiftc",
)


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    return app_bundle(tmp_path_factory.mktemp("cache"))


def test_app_bundle_has_executable_and_background_plist(bundle):
    assert (bundle / "Contents" / "MacOS" / "Squint").is_file()
    info = plistlib.loads((bundle / "Contents" / "Info.plist").read_bytes())
    assert info["CFBundleExecutable"] == "Squint"
    assert info["LSUIElement"] is True


def test_app_rejects_non_loopback_url(bundle):
    process = launch("http://evil.example:80/?t=x", bundle)
    assert process.wait(timeout=10) == 2


def test_app_starts_with_valid_url_and_stops(bundle):
    process = launch("http://127.0.0.1:9/?t=FAKEtoken", bundle)
    time.sleep(1.0)
    assert process.poll() is None
    process.terminate()
    process.wait(timeout=5)
