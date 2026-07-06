"""Self-update from GitHub releases.

Checks the repo's latest release, compares versions, downloads the plugin
zip (verifying the published sha256), and installs it over the plugin
directory. A Decky/Steam restart is needed afterwards to load new code.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import urllib.request
from pathlib import Path

from . import archive

GITHUB_REPO = "Ibrahimmushtaq98/Decky-Eclipse-Patcher"
API_LATEST = "https://api.github.com/repos/{repo}/releases/latest"
USER_AGENT = "decky-eclipse-patcher"


class UpdateError(RuntimeError):
    pass


def parse_version(text: str) -> tuple[int, ...]:
    """'v0.2.1' / '0.2.1' -> (0, 2, 1). Unparseable -> (0,)."""
    numbers = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in numbers[:3]) or (0,)


def is_newer(candidate: str, installed: str) -> bool:
    return parse_version(candidate) > parse_version(installed)


def _get(url: str, timeout: int = 20) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except Exception as exc:
        raise UpdateError(f"Download failed for {url}: {exc}") from exc


def get_latest_release(repo: str = GITHUB_REPO) -> dict:
    data = json.loads(_get(API_LATEST.format(repo=repo)))
    tag = data.get("tag_name") or ""
    zip_asset = None
    sha_asset = None
    for asset in data.get("assets", []):
        name = asset.get("name", "")
        if name.endswith(".zip.sha256"):
            sha_asset = asset
        elif name.endswith(".zip"):
            zip_asset = asset
    if not tag or not zip_asset:
        raise UpdateError("Latest release has no plugin zip asset.")
    return {
        "tag": tag,
        "title": data.get("name") or tag,
        "published_at": data.get("published_at"),
        "zip_url": zip_asset["browser_download_url"],
        "zip_size": zip_asset.get("size"),
        "sha256_url": sha_asset["browser_download_url"] if sha_asset else None,
        "notes": (data.get("body") or "")[:2000],
    }


def _force_copy(source: Path, target: Path) -> None:
    """Copy, un-read-onlying the target if needed (Decky chmods plugin.json 444)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(source, target)
    except PermissionError:
        try:
            target.chmod(0o644)
            shutil.copy2(source, target)
        except PermissionError as exc:
            raise UpdateError(
                f"Cannot overwrite {target.name}. Fix ownership once with: "
                "sudo chown -R deck:deck ~/homebrew/plugins/decky-eclipse-patcher"
            ) from exc


def install_update(zip_url: str, plugin_dir: Path, sha256_url: str | None = None) -> None:
    plugin_dir = Path(plugin_dir)
    if not os.access(plugin_dir, os.W_OK):
        raise UpdateError(
            "Plugin directory is not writable. Fix ownership once with: "
            "sudo chown -R deck:deck ~/homebrew/plugins/decky-eclipse-patcher"
        )
    with tempfile.TemporaryDirectory(prefix="eclipse-update-") as tmp:
        tmp_path = Path(tmp)
        zip_file = tmp_path / "update.zip"
        zip_file.write_bytes(_get(zip_url, timeout=180))

        if sha256_url:
            expected = _get(sha256_url).decode("utf-8", errors="replace").split()[0].strip()
            actual = hashlib.sha256(zip_file.read_bytes()).hexdigest()
            if actual.lower() != expected.lower():
                raise UpdateError("Checksum mismatch on downloaded update — aborting.")

        extract_dir = tmp_path / "extracted"
        try:
            archive.extract_archive(zip_file, extract_dir)
        except archive.ArchiveError as exc:
            raise UpdateError(f"Bad update zip: {exc}") from exc

        # Release zips wrap everything in a single plugin folder.
        root = extract_dir / "decky-eclipse-patcher"
        if not root.is_dir():
            subdirs = [p for p in extract_dir.iterdir() if p.is_dir()]
            root = subdirs[0] if len(subdirs) == 1 else extract_dir
        if not (root / "main.py").is_file() or not (root / "plugin.json").is_file():
            raise UpdateError("Update zip does not look like this plugin — aborting.")

        for dirpath, _dirnames, filenames in os.walk(root):
            for filename in filenames:
                source = Path(dirpath) / filename
                target = plugin_dir / source.relative_to(root)
                _force_copy(source, target)
