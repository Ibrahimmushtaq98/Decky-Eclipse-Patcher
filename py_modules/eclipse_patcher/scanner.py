"""Scan an Eclipse mod zip against a game install directory (dry run).

The zip is expected to mirror the game's folder structure, either at the
zip root or wrapped in a single top-level folder. Nothing here writes to
disk — `scan()` produces the classification that `patcher.apply_mod()`
executes later.
"""
from __future__ import annotations

import os
import zipfile
from pathlib import Path, PurePosixPath

# Proxy DLLs that require WINEDLLOVERRIDES to load under Proton, in the
# order we prefer them if a mod ships more than one.
PROXY_DLL_PRIORITY = [
    "dxgi.dll",
    "d3d11.dll",
    "d3d12.dll",
    "d3d9.dll",
    "version.dll",
    "winmm.dll",
    "dbghelp.dll",
    "winhttp.dll",
    "wininet.dll",
    "dinput8.dll",
]

SCAN_SCHEMA_VERSION = 1


class ScanError(ValueError):
    """Raised when the zip is invalid or unsafe to apply."""


def normalize_entry(name: str) -> str | None:
    """Validate a zip entry name; return a clean posix relpath.

    Returns None for directory entries. Raises ScanError for absolute
    paths, drive letters, or traversal (zip-slip) attempts.
    """
    raw = name.replace("\\", "/")
    if raw.endswith("/"):
        return None
    if raw.startswith("/") or (len(raw) >= 2 and raw[1] == ":"):
        raise ScanError(f"Unsafe absolute path in zip: {name!r}")
    parts = []
    for part in raw.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise ScanError(f"Path traversal attempt in zip: {name!r}")
        parts.append(part)
    if not parts:
        return None
    return "/".join(parts)


def list_zip_files(zip_path: Path) -> list[tuple[str, int]]:
    """[(relpath, uncompressed_size)] for every file entry in the zip."""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            bad = zf.testzip()
            if bad is not None:
                raise ScanError(f"Corrupt zip entry: {bad}")
            entries: list[tuple[str, int]] = []
            for info in zf.infolist():
                if info.flag_bits & 0x1:
                    raise ScanError("Encrypted zip files are not supported.")
                relpath = normalize_entry(info.filename)
                if relpath is None:
                    continue
                entries.append((relpath, info.file_size))
    except zipfile.BadZipFile as exc:
        raise ScanError(f"Not a valid zip file: {exc}") from exc
    if not entries:
        raise ScanError("Zip contains no files.")
    return entries


def build_game_index(game_dir: Path) -> dict[str, str]:
    """Map lowercased relpath -> actual on-disk relpath for the game dir.

    Enables case-insensitive matching: mod zips are often authored on
    Windows and may not match the exact casing of files on the Deck's
    case-sensitive filesystem.
    """
    index: dict[str, str] = {}
    root = str(game_dir)
    for dirpath, _dirnames, filenames in os.walk(game_dir):
        rel_dir = os.path.relpath(dirpath, root)
        for filename in filenames:
            rel = filename if rel_dir == "." else f"{rel_dir}/{filename}"
            rel = rel.replace(os.sep, "/")
            index[rel.lower()] = rel
    return index


def _top_level_dirs(paths: list[str]) -> list[str]:
    tops: list[str] = []
    seen: set[str] = set()
    for path in paths:
        head = path.split("/", 1)[0]
        if "/" in path and head not in seen:
            seen.add(head)
            tops.append(head)
    return tops


def _align(paths: list[tuple[str, int]], prefix: str) -> tuple[list[tuple[str, int]], list[str]]:
    """Strip `prefix` (e.g. "ModFolder/") from paths; return (aligned, ignored)."""
    if not prefix:
        return list(paths), []
    aligned: list[tuple[str, int]] = []
    ignored: list[str] = []
    for path, size in paths:
        if path.startswith(prefix):
            aligned.append((path[len(prefix):], size))
        else:
            ignored.append(path)
    return aligned, ignored


def _overlap_score(aligned: list[tuple[str, int]], index: dict[str, str]) -> int:
    return sum(1 for path, _size in aligned if path.lower() in index)


def detect_proxy_dlls(root_files: list[str]) -> list[str]:
    present = {f.lower() for f in root_files}
    return [dll for dll in PROXY_DLL_PRIORITY if dll in present]


def scan(zip_path: str | Path, game_dir: str | Path) -> dict:
    """Dry-run scan. Returns a JSON-safe dict describing what apply would do."""
    zip_path = Path(zip_path)
    game_dir = Path(game_dir)
    if not zip_path.is_file():
        raise ScanError(f"Mod zip not found: {zip_path}")
    if not game_dir.is_dir():
        raise ScanError(f"Game directory not found: {game_dir}")

    entries = list_zip_files(zip_path)
    index = build_game_index(game_dir)

    # Candidate roots: zip root itself, plus each top-level folder
    # (mods are sometimes wrapped in a single directory).
    candidates: list[str] = [""] + [f"{d}/" for d in _top_level_dirs([p for p, _ in entries])]
    best_prefix = ""
    best_aligned, best_ignored = _align(entries, "")
    best_score = _overlap_score(best_aligned, index)
    for prefix in candidates[1:]:
        aligned, ignored = _align(entries, prefix)
        score = _overlap_score(aligned, index)
        # Prefer a wrapped root only if it matches strictly better.
        if score > best_score:
            best_prefix, best_aligned, best_ignored, best_score = prefix, aligned, ignored, score

    files: list[dict] = []
    overwrite: list[str] = []
    new: list[str] = []
    created_dirs: set[str] = set()
    total_size = 0
    for path, size in sorted(best_aligned):
        total_size += size
        disk_match = index.get(path.lower())
        if disk_match is not None:
            # Remap to on-disk casing so we overwrite instead of duplicating.
            files.append({"relpath": disk_match, "zip_path": best_prefix + path, "action": "overwrite", "size": size})
            overwrite.append(disk_match)
        else:
            files.append({"relpath": path, "zip_path": best_prefix + path, "action": "new", "size": size})
            new.append(path)
            parent = PurePosixPath(path).parent
            while str(parent) != ".":
                if not (game_dir / parent).is_dir():
                    created_dirs.add(str(parent))
                parent = parent.parent

    root_files = [f["relpath"] for f in files if "/" not in f["relpath"]]
    proxy_dlls = detect_proxy_dlls(root_files)

    warnings: list[str] = []
    if not overwrite:
        warnings.append(
            "No file in this zip matches an existing game file. "
            "Double-check that this mod is for the selected game."
        )
    if best_ignored:
        warnings.append(
            f"{len(best_ignored)} file(s) outside the mod's root folder will be skipped "
            f"(e.g. {best_ignored[0]!r})."
        )

    return {
        "schema_version": SCAN_SCHEMA_VERSION,
        "zip_name": zip_path.name,
        "zip_root_prefix": best_prefix,
        "files": files,
        "overwrite_count": len(overwrite),
        "new_count": len(new),
        "created_dirs": sorted(created_dirs),
        "ignored": sorted(best_ignored),
        "proxy_dlls": proxy_dlls,
        "proxy_dll": proxy_dlls[0] if proxy_dlls else None,
        "total_uncompressed": total_size,
        "warnings": warnings,
    }
