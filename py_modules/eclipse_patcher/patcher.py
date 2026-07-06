"""Apply / remove Eclipse mods with crash-safe backups and manifests.

Layout under the plugin runtime dir:
    manifests/<appid>.json   authoritative install record
    backups/<appid>/<rel>    originals of overwritten files
    mods/<appid>/mod.zip     managed copy of the applied zip

Ordering guarantees:
  * the manifest (state="applying", full file list) is written BEFORE any
    game file is touched, so an interrupted apply is always rollback-able;
  * every overwritten file is backed up before extraction starts.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from . import archive, scanner

MANIFEST_SCHEMA = 1
MARKER_FILENAME = "ECLIPSE_PATCH.json"
FREE_SPACE_FACTOR = 1.2


class PatchError(RuntimeError):
    pass


# ── paths & io helpers ────────────────────────────────────────────────────────

def manifest_path(runtime_dir: Path, appid: str) -> Path:
    return runtime_dir / "manifests" / f"{appid}.json"


def backups_dir(runtime_dir: Path, appid: str) -> Path:
    return runtime_dir / "backups" / appid


def managed_mod_dir(runtime_dir: Path, appid: str) -> Path:
    return runtime_dir / "mods" / appid


def managed_zip_path(runtime_dir: Path, appid: str) -> Path | None:
    """The stored copy of the applied archive (mod.zip / mod.rar / mod.7z)."""
    mod_dir = managed_mod_dir(runtime_dir, appid)
    if mod_dir.is_dir():
        for candidate in sorted(mod_dir.glob("mod.*")):
            if candidate.is_file():
                return candidate
    return None


def load_manifest(runtime_dir: Path, appid: str) -> dict | None:
    path = manifest_path(runtime_dir, appid)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_join(root: Path, relpath: str) -> Path:
    """Join and refuse to escape root (defense in depth after scanner)."""
    target = (root / PurePosixPath(relpath)).resolve()
    if not str(target).startswith(str(root.resolve()) + os.sep):
        raise PatchError(f"Refusing path outside game directory: {relpath}")
    return target


# ── apply ─────────────────────────────────────────────────────────────────────

def apply_mod(
    zip_path: Path,
    game_dir: Path,
    runtime_dir: Path,
    appid: str,
    game_name: str,
    scan_result: dict | None = None,
    original_launch_options: str = "",
    managed_launch_options: str = "",
) -> dict:
    appid = str(appid)
    if load_manifest(runtime_dir, appid) is not None:
        raise PatchError("A mod is already installed on this game. Remove it first.")
    if scan_result is None:
        scan_result = scanner.scan(zip_path, game_dir)

    free = shutil.disk_usage(game_dir).free
    needed = int(scan_result["total_uncompressed"] * FREE_SPACE_FACTOR)
    if free < needed:
        raise PatchError(f"Not enough free space: need ~{needed} bytes, have {free}.")

    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "state": "applying",
        "appid": appid,
        "game_name": game_name,
        "install_root": str(game_dir),
        "mod_zip_name": scan_result["zip_name"],
        "mod_zip_sha256": _sha256(zip_path),
        "zip_root_prefix": scan_result["zip_root_prefix"],
        "proxy_dll": scan_result["proxy_dll"],
        "proxy_dlls": scan_result["proxy_dlls"],
        "original_launch_options": original_launch_options,
        "managed_launch_options": managed_launch_options,
        "created_dirs": scan_result["created_dirs"],
        "files": [
            {
                "relpath": f["relpath"],
                "zip_path": f["zip_path"],
                "action": f["action"],
                "orig_sha256": None,
                "new_sha256": None,
            }
            for f in scan_result["files"]
        ],
        "applied_at": None,
    }
    # Crash marker: full plan on disk before we touch anything.
    _write_json_atomic(manifest_path(runtime_dir, appid), manifest)

    backup_root = backups_dir(runtime_dir, appid)

    # 1) Back up everything we are about to overwrite.
    for entry in manifest["files"]:
        if entry["action"] != "overwrite":
            continue
        source = _safe_join(game_dir, entry["relpath"])
        backup = backup_root / entry["relpath"]
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, backup)
        entry["orig_sha256"] = _sha256(backup)
    _write_json_atomic(manifest_path(runtime_dir, appid), manifest)

    # 2) Extract mod files (backups are safe now).
    with tempfile.TemporaryDirectory(prefix="eclipse-apply-") as tmp:
        try:
            archive.extract_archive(zip_path, Path(tmp))
        except archive.ArchiveError as exc:
            raise PatchError(str(exc)) from exc
        tree = Path(tmp)
        for entry in manifest["files"]:
            source = tree / PurePosixPath(entry["zip_path"])
            target = _safe_join(game_dir, entry["relpath"])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            entry["new_sha256"] = _sha256(target)

    # 3) Keep a managed copy of the archive for re-apply.
    mod_dir = managed_mod_dir(runtime_dir, appid)
    mod_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(zip_path, mod_dir / f"mod{zip_path.suffix.lower()}")

    # 4) Finalize.
    manifest["state"] = "applied"
    manifest["applied_at"] = datetime.now(timezone.utc).isoformat()
    _write_json_atomic(manifest_path(runtime_dir, appid), manifest)
    _write_json_atomic(
        game_dir / MARKER_FILENAME,
        {
            "plugin": "decky-eclipse-patcher",
            "appid": appid,
            "mod_zip_name": manifest["mod_zip_name"],
            "applied_at": manifest["applied_at"],
        },
    )
    return manifest


# ── remove / rollback ─────────────────────────────────────────────────────────

def remove_mod(runtime_dir: Path, appid: str, game_dir: Path, tolerant: bool = False) -> dict:
    """Revert a mod. `tolerant=True` also handles interrupted installs."""
    appid = str(appid)
    manifest = load_manifest(runtime_dir, appid)
    if manifest is None:
        raise PatchError("No mod is recorded for this game.")
    if manifest.get("state") == "applying" and not tolerant:
        raise PatchError("Previous install was interrupted; use rollback instead.")

    backup_root = backups_dir(runtime_dir, appid)
    report = {"restored": [], "deleted": [], "missing_backups": [], "notes": []}

    for entry in manifest.get("files", []):
        relpath = entry["relpath"]
        target = _safe_join(game_dir, relpath)
        if entry["action"] == "new":
            if target.is_file():
                target.unlink()
                report["deleted"].append(relpath)
        else:  # overwrite -> restore original
            backup = backup_root / relpath
            if backup.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup, target)
                report["restored"].append(relpath)
            elif entry.get("orig_sha256") is None and manifest.get("state") == "applying":
                # Interrupted before this file was backed up -> it was never
                # overwritten either (backups strictly precede extraction).
                report["notes"].append(f"{relpath}: untouched by interrupted install")
            else:
                report["missing_backups"].append(relpath)

    # Remove directories the mod introduced (deepest first, only if empty).
    for rel_dir in sorted(manifest.get("created_dirs", []), key=lambda d: d.count("/"), reverse=True):
        dir_path = _safe_join(game_dir, rel_dir)
        try:
            if dir_path.is_dir() and not any(dir_path.iterdir()):
                dir_path.rmdir()
        except OSError:
            report["notes"].append(f"could not remove directory {rel_dir}")

    marker = game_dir / MARKER_FILENAME
    if marker.is_file():
        marker.unlink()

    shutil.rmtree(backup_root, ignore_errors=True)
    shutil.rmtree(managed_mod_dir(runtime_dir, appid), ignore_errors=True)
    manifest_file = manifest_path(runtime_dir, appid)
    if manifest_file.is_file():
        manifest_file.unlink()

    report["original_launch_options"] = manifest.get("original_launch_options", "")
    return report


# ── status ────────────────────────────────────────────────────────────────────

def get_status(runtime_dir: Path, appid: str, game_dir: Path | None) -> dict:
    appid = str(appid)
    manifest = load_manifest(runtime_dir, appid)
    if manifest is None:
        return {"patched": False, "state": "none"}
    if manifest.get("state") == "applying":
        return {
            "patched": True,
            "state": "incomplete",
            "mod_zip_name": manifest.get("mod_zip_name"),
        }

    intact = modified = missing = 0
    if game_dir is not None and game_dir.is_dir():
        for entry in manifest.get("files", []):
            target = game_dir / PurePosixPath(entry["relpath"])
            if not target.is_file():
                missing += 1
            elif entry.get("new_sha256") and _sha256(target) == entry["new_sha256"]:
                intact += 1
            else:
                modified += 1
    state = "intact"
    if missing or modified:
        state = "modified"
    return {
        "patched": True,
        "state": state,
        "mod_zip_name": manifest.get("mod_zip_name"),
        "applied_at": manifest.get("applied_at"),
        "proxy_dll": manifest.get("proxy_dll"),
        "proxy_dlls": manifest.get("proxy_dlls", []),
        "managed_launch_options": manifest.get("managed_launch_options", ""),
        "original_launch_options": manifest.get("original_launch_options", ""),
        "files_intact": intact,
        "files_modified": modified,
        "files_missing": missing,
        "file_count": len(manifest.get("files", [])),
        "has_managed_zip": managed_zip_path(runtime_dir, appid) is not None,
    }


# ── per-game debug details ────────────────────────────────────────────────────

def get_patch_details(runtime_dir: Path, appid: str, game_dir: Path | None, max_files: int = 300) -> dict:
    """Full per-file breakdown of what a mod changed — for the details view."""
    appid = str(appid)
    manifest = load_manifest(runtime_dir, appid)
    if manifest is None:
        return {"patched": False}

    backup_root = backups_dir(runtime_dir, appid)
    files: list[dict] = []
    counts = {"intact": 0, "modified": 0, "missing": 0, "unknown": 0}
    for entry in manifest.get("files", []):
        relpath = entry["relpath"]
        state = "unknown"
        if game_dir is not None and game_dir.is_dir():
            target = game_dir / PurePosixPath(relpath)
            if not target.is_file():
                state = "missing"
            elif entry.get("new_sha256") and _sha256(target) == entry["new_sha256"]:
                state = "intact"
            else:
                state = "modified"
        counts[state] += 1
        if len(files) < max_files:
            files.append(
                {
                    "relpath": relpath,
                    "action": entry["action"],
                    "state": state,
                    "backup_present": entry["action"] == "overwrite"
                    and (backup_root / relpath).is_file(),
                }
            )

    managed = managed_zip_path(runtime_dir, appid)
    return {
        "patched": True,
        "state": manifest.get("state"),
        "mod_zip_name": manifest.get("mod_zip_name"),
        "mod_zip_sha256": manifest.get("mod_zip_sha256"),
        "applied_at": manifest.get("applied_at"),
        "install_root": manifest.get("install_root"),
        "zip_root_prefix": manifest.get("zip_root_prefix", ""),
        "proxy_dlls": manifest.get("proxy_dlls", []),
        "original_launch_options": manifest.get("original_launch_options", ""),
        "managed_launch_options": manifest.get("managed_launch_options", ""),
        "created_dirs": manifest.get("created_dirs", []),
        "managed_zip": str(managed) if managed else None,
        "counts": counts,
        "files": files,
        "files_truncated": max(0, len(manifest.get("files", [])) - len(files)),
    }
