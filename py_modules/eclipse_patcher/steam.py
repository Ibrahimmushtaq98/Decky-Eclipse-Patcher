"""Steam library discovery: installed games, install paths, running check."""
from __future__ import annotations

import re
from pathlib import Path

_VDF_PATH_RE = re.compile(r'"path"\s+"((?:[^"\\]|\\.)*)"')
_ACF_FIELD_RE = re.compile(r'"(appid|name|installdir)"\s+"((?:[^"\\]|\\.)*)"')


def _unescape_vdf(value: str) -> str:
    return value.replace("\\\\", "\\").replace('\\"', '"')


def steam_root_candidates(home: Path) -> list[Path]:
    """Possible Steam roots on SteamOS / desktop Linux (incl. flatpak)."""
    return [
        home / ".local" / "share" / "Steam",
        home / ".steam" / "steam",
        home / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam",
    ]


def steam_library_paths(home: Path) -> list[Path]:
    """All steamapps directories across every configured library folder."""
    libraries: list[Path] = []
    seen: set[str] = set()
    for root in steam_root_candidates(home):
        steamapps = root / "steamapps"
        if not steamapps.is_dir():
            continue
        candidates = [steamapps]
        vdf = steamapps / "libraryfolders.vdf"
        if vdf.is_file():
            try:
                content = vdf.read_text(encoding="utf-8", errors="replace")
                for match in _VDF_PATH_RE.finditer(content):
                    lib_steamapps = Path(_unescape_vdf(match.group(1))) / "steamapps"
                    if lib_steamapps.is_dir():
                        candidates.append(lib_steamapps)
            except OSError:
                pass
        for candidate in candidates:
            key = str(candidate.resolve())
            if key not in seen:
                seen.add(key)
                libraries.append(candidate)
    return libraries


def _parse_acf(acf_path: Path) -> dict | None:
    try:
        content = acf_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    fields = {m.group(1): _unescape_vdf(m.group(2)) for m in _ACF_FIELD_RE.finditer(content)}
    if not fields.get("appid") or not fields.get("installdir"):
        return None
    return fields


def find_installed_games(home: Path, appid: str | None = None) -> list[dict]:
    """List installed games as {appid, name, install_path} dicts."""
    games: list[dict] = []
    seen_appids: set[str] = set()
    for steamapps in steam_library_paths(home):
        pattern = f"appmanifest_{appid}.acf" if appid else "appmanifest_*.acf"
        for acf in steamapps.glob(pattern):
            fields = _parse_acf(acf)
            if not fields or fields["appid"] in seen_appids:
                continue
            install_path = steamapps / "common" / fields["installdir"]
            seen_appids.add(fields["appid"])
            games.append(
                {
                    "appid": fields["appid"],
                    "name": fields.get("name") or fields["installdir"],
                    "install_path": str(install_path),
                }
            )
    return games


def game_record(home: Path, appid: str) -> dict | None:
    games = find_installed_games(home, appid=str(appid))
    return games[0] if games else None


def is_game_running(install_root: Path, proc_dir: Path = Path("/proc")) -> bool:
    """True if any process command line references the game's install dir."""
    needle = str(install_root)
    try:
        entries = list(proc_dir.iterdir())
    except OSError:
        return False
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes().replace(b"\x00", b" ")
        except OSError:
            continue
        if needle.encode("utf-8", errors="replace") in cmdline:
            return True
    return False
