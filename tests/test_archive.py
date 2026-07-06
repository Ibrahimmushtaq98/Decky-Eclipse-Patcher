import shutil
from pathlib import Path

import pytest

from conftest import make_zip
from eclipse_patcher import archive
from eclipse_patcher.archive import ArchiveError


def test_zip_extraction(tmp_path: Path):
    zip_path = make_zip(tmp_path / "m.zip", {"a/b.txt": b"hello", "c.txt": b"x"})
    dest = tmp_path / "out"
    archive.extract_archive(zip_path, dest)
    assert (dest / "a" / "b.txt").read_bytes() == b"hello"
    assert (dest / "c.txt").is_file()


def test_unsupported_extension(tmp_path: Path):
    bogus = tmp_path / "mod.tar.gz"
    bogus.write_bytes(b"whatever")
    with pytest.raises(ArchiveError, match="Unsupported archive type"):
        archive.extract_archive(bogus, tmp_path / "out")


def test_missing_archive(tmp_path: Path):
    with pytest.raises(ArchiveError, match="not found"):
        archive.extract_archive(tmp_path / "nope.zip", tmp_path / "out")


def test_rar_without_tool_gives_clear_error(tmp_path: Path, monkeypatch):
    fake_rar = tmp_path / "mod.rar"
    fake_rar.write_bytes(b"Rar!\x1a\x07\x00fake")
    monkeypatch.setattr(shutil, "which", lambda _tool: None)
    with pytest.raises(ArchiveError, match="No extraction tool"):
        archive.extract_archive(fake_rar, tmp_path / "out")


def test_rar_uses_available_tool(tmp_path: Path, monkeypatch):
    """Tool selection: when 7z exists, the command must target it."""
    monkeypatch.setattr(shutil, "which", lambda tool: "/usr/bin/7z" if tool == "7z" else None)
    cmd = archive._external_tool_command(Path("mod.rar"), Path("/tmp/out"))
    assert cmd[0] == "7z" and cmd[1] == "x"

    monkeypatch.setattr(shutil, "which", lambda tool: "/usr/bin/bsdtar" if tool == "bsdtar" else None)
    cmd = archive._external_tool_command(Path("mod.rar"), Path("/tmp/out"))
    assert cmd[0] == "bsdtar"


def test_symlink_sanitized(tmp_path: Path):
    """Symlinks that appear in an extracted tree are dropped."""
    dest = tmp_path / "out"
    dest.mkdir()
    (dest / "real.txt").write_bytes(b"ok")
    (dest / "evil").symlink_to("/etc/passwd")
    archive._sanitize_tree(dest)
    assert not (dest / "evil").exists()
    assert (dest / "real.txt").is_file()


def test_normalize_entry():
    assert archive.normalize_entry("a/b.txt") == "a/b.txt"
    assert archive.normalize_entry("a\\b.txt") == "a/b.txt"
    assert archive.normalize_entry("./a//b.txt") == "a/b.txt"
    assert archive.normalize_entry("dir/") is None
    with pytest.raises(ArchiveError, match="traversal"):
        archive.normalize_entry("../etc/passwd")
    with pytest.raises(ArchiveError, match="absolute"):
        archive.normalize_entry("/etc/passwd")
    with pytest.raises(ArchiveError, match="absolute"):
        archive.normalize_entry("C:\\Windows\\evil.dll")
