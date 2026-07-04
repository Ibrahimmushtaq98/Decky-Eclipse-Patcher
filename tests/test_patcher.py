import filecmp
import shutil
import zipfile
from pathlib import Path

import pytest

from eclipse_patcher import patcher, scanner
from eclipse_patcher.patcher import PatchError


@pytest.fixture
def runtime_dir(tmp_path: Path) -> Path:
    rt = tmp_path / "runtime"
    rt.mkdir()
    return rt


def snapshot(game_dir: Path, tmp_path: Path) -> Path:
    dest = tmp_path / "snapshot"
    shutil.copytree(game_dir, dest)
    return dest


def trees_identical(a: Path, b: Path) -> bool:
    cmp = filecmp.dircmp(a, b)
    def walk(c: filecmp.dircmp) -> bool:
        if c.left_only or c.right_only or c.diff_files or c.funny_files:
            return False
        return all(walk(sub) for sub in c.subdirs.values())
    return walk(cmp)


APPID = "480"


def test_apply_then_remove_is_byte_identical(game_dir, mirror_zip, runtime_dir, tmp_path):
    pristine = snapshot(game_dir, tmp_path)

    manifest = patcher.apply_mod(
        mirror_zip, game_dir, runtime_dir, APPID, "Eclipse Quest",
        original_launch_options="PROTON_LOG=1 %command%",
        managed_launch_options="WINEDLLOVERRIDES=dxgi=n,b %command%",
    )
    assert manifest["state"] == "applied"
    # mod is really deployed
    assert (game_dir / "engine" / "renderer.dll").read_bytes() == b"RENDER-V2-MODDED"
    assert (game_dir / "eclipse" / "shaders.fx").is_file()
    assert (game_dir / patcher.MARKER_FILENAME).is_file()
    assert patcher.managed_zip_path(runtime_dir, APPID).is_file()

    report = patcher.remove_mod(runtime_dir, APPID, game_dir)
    assert report["original_launch_options"] == "PROTON_LOG=1 %command%"
    assert not report["missing_backups"]
    assert trees_identical(pristine, game_dir), "game dir must be byte-identical after remove"
    # runtime state fully cleaned
    assert patcher.load_manifest(runtime_dir, APPID) is None
    assert not patcher.backups_dir(runtime_dir, APPID).exists()


def test_wrapped_zip_apply(game_dir, wrapped_zip, runtime_dir, tmp_path):
    pristine = snapshot(game_dir, tmp_path)
    patcher.apply_mod(wrapped_zip, game_dir, runtime_dir, APPID, "Eclipse Quest")
    # loose README.txt outside the wrapped root must NOT be deployed
    assert not (game_dir / "README.txt").exists()
    assert (game_dir / "data" / "config.ini").read_bytes() == b"quality=eclipse\n"
    patcher.remove_mod(runtime_dir, APPID, game_dir)
    assert trees_identical(pristine, game_dir)


def test_double_apply_refused(game_dir, mirror_zip, runtime_dir):
    patcher.apply_mod(mirror_zip, game_dir, runtime_dir, APPID, "Eclipse Quest")
    with pytest.raises(PatchError, match="already installed"):
        patcher.apply_mod(mirror_zip, game_dir, runtime_dir, APPID, "Eclipse Quest")


def test_crash_mid_extract_rolls_back(game_dir, mirror_zip, runtime_dir, tmp_path, monkeypatch):
    pristine = snapshot(game_dir, tmp_path)
    # scan up-front so the only ZipFile.open calls happen during extraction
    scan_result = scanner.scan(mirror_zip, game_dir)

    real_open = zipfile.ZipFile.open
    calls = {"n": 0}

    def exploding_open(self, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 3:  # die partway through extraction
            raise OSError("simulated crash")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "open", exploding_open)
    with pytest.raises(OSError, match="simulated crash"):
        patcher.apply_mod(
            mirror_zip, game_dir, runtime_dir, APPID, "Eclipse Quest", scan_result=scan_result
        )
    monkeypatch.undo()

    # manifest recorded the interrupted state before anything was touched
    manifest = patcher.load_manifest(runtime_dir, APPID)
    assert manifest is not None and manifest["state"] == "applying"
    with pytest.raises(PatchError, match="interrupted"):
        patcher.remove_mod(runtime_dir, APPID, game_dir)

    patcher.remove_mod(runtime_dir, APPID, game_dir, tolerant=True)
    assert trees_identical(pristine, game_dir), "rollback must restore pristine state"


def test_remove_with_missing_backup_reports(game_dir, mirror_zip, runtime_dir):
    patcher.apply_mod(mirror_zip, game_dir, runtime_dir, APPID, "Eclipse Quest")
    # sabotage one backup
    (patcher.backups_dir(runtime_dir, APPID) / "data" / "config.ini").unlink()
    report = patcher.remove_mod(runtime_dir, APPID, game_dir)
    assert report["missing_backups"] == ["data/config.ini"]
    assert "engine/renderer.dll" in report["restored"]


def test_status_lifecycle(game_dir, mirror_zip, runtime_dir):
    assert patcher.get_status(runtime_dir, APPID, game_dir) == {"patched": False, "state": "none"}

    patcher.apply_mod(mirror_zip, game_dir, runtime_dir, APPID, "Eclipse Quest")
    status = patcher.get_status(runtime_dir, APPID, game_dir)
    assert status["state"] == "intact"
    assert status["files_intact"] == status["file_count"] == 5
    assert status["proxy_dll"] == "dxgi.dll"
    assert status["has_managed_zip"]

    # simulate a game update clobbering a modded file
    (game_dir / "engine" / "renderer.dll").write_bytes(b"GAME-UPDATE-V3")
    status = patcher.get_status(runtime_dir, APPID, game_dir)
    assert status["state"] == "modified"
    assert status["files_modified"] == 1

    patcher.remove_mod(runtime_dir, APPID, game_dir)
    assert patcher.get_status(runtime_dir, APPID, game_dir)["patched"] is False


def test_reapply_from_managed_zip(game_dir, mirror_zip, runtime_dir, tmp_path):
    patcher.apply_mod(mirror_zip, game_dir, runtime_dir, APPID, "Eclipse Quest")
    managed = patcher.managed_zip_path(runtime_dir, APPID)
    staging = tmp_path / "staged_mod.zip"
    shutil.copy2(managed, staging)

    # game update clobbers a file, then user re-applies
    (game_dir / "engine" / "renderer.dll").write_bytes(b"GAME-UPDATE-V3")
    patcher.remove_mod(runtime_dir, APPID, game_dir)
    result = scanner.scan(staging, game_dir)
    patcher.apply_mod(staging, game_dir, runtime_dir, APPID, "Eclipse Quest", scan_result=result)
    assert (game_dir / "engine" / "renderer.dll").read_bytes() == b"RENDER-V2-MODDED"
