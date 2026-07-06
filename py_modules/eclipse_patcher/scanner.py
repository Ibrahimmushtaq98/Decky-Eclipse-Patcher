"""Scan an Eclipse mod archive against a game install directory (dry run).

The archive (.zip/.rar/.7z) is expected to mirror the game's folder
structure, either at the archive root or wrapped in a single top-level
folder. The archive is extracted to a temp dir and scanned as a tree;
nothing here writes to the game directory — `scan()` produces the
classification that `patcher.apply_mod()` executes later.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path, PurePosixPath

from . import archive

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

SCAN_SCHEMA_VERSION = 2


class ScanError(ValueError):
    """Raised when the archive is invalid or unsafe to apply."""


def list_tree_files(tree: Path) -> list[tuple[str, int]]:
    """[(relpath, size)] for every file under an extracted archive tree."""
    entries: list[tuple[str, int]] = []
    root = str(tree)
    for dirpath, _dirnames, filenames in os.walk(tree):
        rel_dir = os.path.relpath(dirpath, root)
        for filename in filenames:
            rel = filename if rel_dir == "." else f"{rel_dir}/{filename}"
            rel = rel.replace(os.sep, "/")
            entries.append((rel, (Path(dirpath) / filename).stat().st_size))
    return entries


def build_game_index(game_dir: Path) -> dict[str, str]:
    """Map lowercased relpath -> actual on-disk relpath for the game dir.

    Enables case-insensitive matching: mod archives are often authored on
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


def scan_tree(tree: Path, game_dir: Path, archive_name: str) -> dict:
    """Classify an extracted archive tree against the game dir."""
    entries = list_tree_files(tree)
    if not entries:
        raise ScanError("Archive contains no files.")
    index = build_game_index(game_dir)

    # Candidate roots: archive root itself, plus each top-level folder
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
            "No file in this archive matches an existing game file. "
            "Double-check that this mod is for the selected game."
        )
    if best_ignored:
        warnings.append(
            f"{len(best_ignored)} file(s) outside the mod's root folder will be skipped "
            f"(e.g. {best_ignored[0]!r})."
        )

    return {
        "schema_version": SCAN_SCHEMA_VERSION,
        "zip_name": archive_name,
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


def scan(archive_path: str | Path, game_dir: str | Path) -> dict:
    """Dry-run scan. Returns a JSON-safe dict describing what apply would do."""
    archive_path = Path(archive_path)
    game_dir = Path(game_dir)
    if not archive_path.is_file():
        raise ScanError(f"Mod archive not found: {archive_path}")
    if not game_dir.is_dir():
        raise ScanError(f"Game directory not found: {game_dir}")

    with tempfile.TemporaryDirectory(prefix="eclipse-scan-") as tmp:
        try:
            archive.extract_archive(archive_path, Path(tmp))
        except archive.ArchiveError as exc:
            raise ScanError(str(exc)) from exc
        return scan_tree(Path(tmp), game_dir, archive_path.name)
