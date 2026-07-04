from pathlib import Path

import pytest

from conftest import make_zip
from eclipse_patcher import scanner
from eclipse_patcher.scanner import ScanError


def test_mirror_zip_classification(game_dir: Path, mirror_zip: Path):
    result = scanner.scan(mirror_zip, game_dir)
    assert result["zip_root_prefix"] == ""
    assert result["overwrite_count"] == 2
    assert result["new_count"] == 3  # moon.pak, shaders.fx, dxgi.dll
    actions = {f["relpath"]: f["action"] for f in result["files"]}
    assert actions["engine/renderer.dll"] == "overwrite"
    assert actions["data/config.ini"] == "overwrite"
    assert actions["data/textures/moon.pak"] == "new"
    assert "eclipse" in result["created_dirs"]
    assert result["proxy_dll"] == "dxgi.dll"
    assert result["warnings"] == []


def test_wrapped_zip_root_detection(game_dir: Path, wrapped_zip: Path):
    result = scanner.scan(wrapped_zip, game_dir)
    assert result["zip_root_prefix"] == "EclipseMod/"
    assert result["overwrite_count"] == 2
    # README.txt sits outside the wrapped root -> skipped with a warning
    assert result["ignored"] == ["README.txt"]
    assert any("skipped" in w for w in result["warnings"])
    # zip_path keeps the prefix so the patcher can extract the right entry
    renderer = next(f for f in result["files"] if f["relpath"] == "engine/renderer.dll")
    assert renderer["zip_path"] == "EclipseMod/engine/renderer.dll"


def test_case_insensitive_overwrite_remap(game_dir: Path, tmp_path: Path):
    zip_path = make_zip(
        tmp_path / "case.zip",
        {"Engine/Renderer.DLL": b"NEWBYTES", "Data/Config.INI": b"x=1"},
    )
    result = scanner.scan(zip_path, game_dir)
    actions = {f["relpath"]: f["action"] for f in result["files"]}
    # remapped to on-disk casing, counted as overwrites not duplicates
    assert actions["engine/renderer.dll"] == "overwrite"
    assert actions["data/config.ini"] == "overwrite"
    assert result["new_count"] == 0


def test_pure_addition_mod_warns(game_dir: Path, tmp_path: Path):
    zip_path = make_zip(tmp_path / "addonly.zip", {"newstuff/a.pak": b"A"})
    result = scanner.scan(zip_path, game_dir)
    assert result["overwrite_count"] == 0
    assert any("Double-check" in w for w in result["warnings"])


def test_zip_slip_rejected(game_dir: Path, tmp_path: Path):
    zip_path = make_zip(tmp_path / "evil.zip", {"../../etc/passwd": b"root"})
    with pytest.raises(ScanError, match="traversal"):
        scanner.scan(zip_path, game_dir)


def test_absolute_path_rejected(game_dir: Path, tmp_path: Path):
    zip_path = make_zip(tmp_path / "abs.zip", {"/etc/passwd": b"root"})
    with pytest.raises(ScanError, match="absolute"):
        scanner.scan(zip_path, game_dir)


def test_not_a_zip_rejected(game_dir: Path, tmp_path: Path):
    bogus = tmp_path / "bogus.zip"
    bogus.write_bytes(b"not a zip at all")
    with pytest.raises(ScanError, match="valid zip"):
        scanner.scan(bogus, game_dir)


def test_empty_zip_rejected(game_dir: Path, tmp_path: Path):
    zip_path = make_zip(tmp_path / "empty.zip", {})
    with pytest.raises(ScanError, match="no files"):
        scanner.scan(zip_path, game_dir)


def test_missing_game_dir(mirror_zip: Path, tmp_path: Path):
    with pytest.raises(ScanError, match="Game directory"):
        scanner.scan(mirror_zip, tmp_path / "nope")


def test_proxy_priority(game_dir: Path, tmp_path: Path):
    zip_path = make_zip(
        tmp_path / "multi.zip",
        {"version.dll": b"V", "dxgi.dll": b"D", "engine/renderer.dll": b"R"},
    )
    result = scanner.scan(zip_path, game_dir)
    assert result["proxy_dlls"] == ["dxgi.dll", "version.dll"]
    assert result["proxy_dll"] == "dxgi.dll"
