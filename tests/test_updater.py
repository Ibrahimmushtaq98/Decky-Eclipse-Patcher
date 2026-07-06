import hashlib
import json
from pathlib import Path

import pytest

from conftest import make_zip
from eclipse_patcher import updater
from eclipse_patcher.updater import UpdateError


def test_parse_version():
    assert updater.parse_version("v0.2.1") == (0, 2, 1)
    assert updater.parse_version("0.10.0") == (0, 10, 0)
    assert updater.parse_version("garbage") == (0,)


def test_is_newer():
    assert updater.is_newer("v0.2.0", "0.1.0")
    assert updater.is_newer("v0.10.0", "0.9.9")  # numeric, not lexicographic
    assert not updater.is_newer("v0.1.0", "0.1.0")
    assert not updater.is_newer("v0.0.9", "0.1.0")


def _release_zip(tmp_path: Path) -> Path:
    return make_zip(
        tmp_path / "release.zip",
        {
            "decky-eclipse-patcher/main.py": b"# new main",
            "decky-eclipse-patcher/plugin.json": b'{"name": "Eclipse Patcher"}',
            "decky-eclipse-patcher/dist/index.js": b"// new bundle",
            "decky-eclipse-patcher/py_modules/eclipse_patcher/__init__.py": b"# pkg",
        },
    )


def test_install_update_from_file_url(tmp_path: Path):
    zip_path = _release_zip(tmp_path)
    sha = tmp_path / "release.zip.sha256"
    sha.write_text(hashlib.sha256(zip_path.read_bytes()).hexdigest() + "  release.zip\n")

    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    (plugin_dir / "main.py").write_bytes(b"# old main")
    stale = plugin_dir / "plugin.json"
    stale.write_bytes(b"{}")
    stale.chmod(0o444)  # simulate Decky's read-only plugin.json

    updater.install_update(zip_path.as_uri(), plugin_dir, sha.as_uri())
    assert (plugin_dir / "main.py").read_bytes() == b"# new main"
    assert (plugin_dir / "plugin.json").read_bytes() == b'{"name": "Eclipse Patcher"}'
    assert (plugin_dir / "dist" / "index.js").read_bytes() == b"// new bundle"


def test_install_update_checksum_mismatch(tmp_path: Path):
    zip_path = _release_zip(tmp_path)
    sha = tmp_path / "bad.sha256"
    sha.write_text("0" * 64 + "  release.zip\n")
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    with pytest.raises(UpdateError, match="Checksum mismatch"):
        updater.install_update(zip_path.as_uri(), plugin_dir, sha.as_uri())


def test_install_update_rejects_non_plugin_zip(tmp_path: Path):
    zip_path = make_zip(tmp_path / "junk.zip", {"random/stuff.txt": b"hi"})
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    with pytest.raises(UpdateError, match="does not look like this plugin"):
        updater.install_update(zip_path.as_uri(), plugin_dir)


def test_get_latest_release_parses_assets(monkeypatch, tmp_path: Path):
    payload = {
        "tag_name": "v0.2.0",
        "name": "Eclipse Patcher v0.2.0",
        "published_at": "2026-07-05T00:00:00Z",
        "body": "notes",
        "assets": [
            {"name": "decky-eclipse-patcher-v0.2.0.zip", "browser_download_url": "https://x/z.zip", "size": 123},
            {"name": "decky-eclipse-patcher-v0.2.0.zip.sha256", "browser_download_url": "https://x/z.zip.sha256"},
        ],
    }
    monkeypatch.setattr(updater, "_get", lambda url, timeout=20: json.dumps(payload).encode())
    release = updater.get_latest_release()
    assert release["tag"] == "v0.2.0"
    assert release["zip_url"] == "https://x/z.zip"
    assert release["sha256_url"] == "https://x/z.zip.sha256"
