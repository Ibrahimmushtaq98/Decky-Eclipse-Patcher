"""Archive extraction for mod files: .zip (stdlib), .rar / .7z (system tools).

Non-zip formats are extracted with the first available external tool
(7z / 7zz / 7za / bsdtar — SteamOS ships bsdtar, and usually 7z too).
Everything is extracted to a temp directory first; scanning and patching
then operate on the extracted tree, so all formats share one code path.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import zipfile
from pathlib import Path

SUPPORTED_EXTENSIONS = [".zip", ".rar", ".7z"]


class ArchiveError(ValueError):
    pass


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def normalize_entry(name: str) -> str | None:
    """Validate an archive entry name; return a clean posix relpath.

    Returns None for directory entries. Raises ArchiveError for absolute
    paths, drive letters, or traversal (zip-slip) attempts.
    """
    raw = name.replace("\\", "/")
    if raw.endswith("/"):
        return None
    if raw.startswith("/") or (len(raw) >= 2 and raw[1] == ":"):
        raise ArchiveError(f"Unsafe absolute path in archive: {name!r}")
    parts = []
    for part in raw.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise ArchiveError(f"Path traversal attempt in archive: {name!r}")
        parts.append(part)
    if not parts:
        return None
    return "/".join(parts)


def _extract_zip(archive_path: Path, dest: Path) -> None:
    try:
        with zipfile.ZipFile(archive_path) as zf:
            for info in zf.infolist():
                if info.flag_bits & 0x1:
                    raise ArchiveError("Encrypted archives are not supported.")
                relpath = normalize_entry(info.filename)
                if relpath is None:
                    continue
                target = dest / relpath
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
    except zipfile.BadZipFile as exc:
        raise ArchiveError(f"Not a valid zip file: {exc}") from exc


def _external_tool_command(archive_path: Path, dest: Path) -> list[str]:
    for tool in ("7z", "7zz", "7za"):
        if shutil.which(tool):
            return [tool, "x", "-y", f"-o{dest}", str(archive_path)]
    if shutil.which("bsdtar"):
        return ["bsdtar", "-xf", str(archive_path), "-C", str(dest)]
    raise ArchiveError(
        f"No extraction tool found for {archive_path.suffix} files "
        "(need 7z or bsdtar on the system)."
    )


def _extract_external(archive_path: Path, dest: Path) -> None:
    cmd = _external_tool_command(archive_path, dest)
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = ""
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, env=env)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "unknown error").strip()
        raise ArchiveError(f"Failed to extract {archive_path.name}: {detail[:400]}")


def _sanitize_tree(dest: Path) -> None:
    """Post-extraction defense: drop symlinks, refuse anything escaping dest."""
    dest_resolved = dest.resolve()
    for dirpath, dirnames, filenames in os.walk(dest):
        for name in list(dirnames) + filenames:
            path = Path(dirpath) / name
            if path.is_symlink():
                path.unlink()
                if name in dirnames:
                    dirnames.remove(name)
                continue
            if not str(path.resolve()).startswith(str(dest_resolved) + os.sep):
                raise ArchiveError(f"Archive entry escapes extraction dir: {name!r}")


def extract_archive(archive_path: Path, dest: Path) -> None:
    """Extract any supported archive into dest (created if needed)."""
    archive_path = Path(archive_path)
    if not archive_path.is_file():
        raise ArchiveError(f"Archive not found: {archive_path}")
    if not is_supported(archive_path):
        raise ArchiveError(
            f"Unsupported archive type {archive_path.suffix!r} "
            f"(supported: {', '.join(SUPPORTED_EXTENSIONS)})."
        )
    dest.mkdir(parents=True, exist_ok=True)
    if archive_path.suffix.lower() == ".zip":
        _extract_zip(archive_path, dest)
    else:
        _extract_external(archive_path, dest)
    _sanitize_tree(dest)
    if not any(p.is_file() for p in dest.rglob("*")):
        raise ArchiveError("Archive contains no files.")
