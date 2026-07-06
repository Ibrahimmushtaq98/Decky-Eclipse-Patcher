"""Decky Eclipse Patcher — plugin entry point.

Thin async wrappers around py_modules/eclipse_patcher. Every method returns
{"status": "success", ...} or {"status": "error", "message": ...} so the
frontend never has to parse exceptions.
"""
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).parent
sys.path.insert(0, str(PLUGIN_DIR / "py_modules"))

import decky  # noqa: E402
from eclipse_patcher import activity, launch_options, patcher, scanner, steam, updater  # noqa: E402


def _home() -> Path:
    return Path(decky.HOME)


def _runtime_dir() -> Path:
    runtime = Path(decky.DECKY_PLUGIN_RUNTIME_DIR)
    runtime.mkdir(parents=True, exist_ok=True)
    return runtime


def _err(message: str) -> dict:
    decky.logger.error(message)
    activity.log_event(_runtime_dir(), f"ERROR: {message}")
    return {"status": "error", "message": message}


def _log(message: str) -> None:
    decky.logger.info(message)
    activity.log_event(_runtime_dir(), message)


def _game(appid: str) -> tuple[dict | None, Path | None]:
    record = steam.game_record(_home(), str(appid))
    if not record:
        return None, None
    install_root = Path(record["install_path"])
    return record, (install_root if install_root.is_dir() else None)


class Plugin:
    async def _main(self):
        decky.logger.info("Eclipse Patcher loaded")

    async def _unload(self):
        decky.logger.info("Eclipse Patcher unloaded")

    # ── games ────────────────────────────────────────────────────────────────

    async def list_installed_games(self) -> dict:
        try:
            runtime = _runtime_dir()
            games = []
            for game in steam.find_installed_games(_home()):
                status = patcher.get_status(runtime, game["appid"], None)
                games.append(
                    {
                        "appid": game["appid"],
                        "name": game["name"],
                        "install_found": Path(game["install_path"]).is_dir(),
                        "patched": status["patched"],
                    }
                )
            games.sort(key=lambda g: g["name"].lower())
            return {"status": "success", "games": games}
        except Exception as exc:
            return _err(f"list_installed_games failed: {exc}")

    async def get_game_mod_status(self, appid: str) -> dict:
        try:
            record, install_root = _game(appid)
            if not record:
                return _err("Game not found in Steam library.")
            status = patcher.get_status(_runtime_dir(), appid, install_root)
            status.update({"status": "success", "appid": str(appid), "name": record["name"]})
            return status
        except Exception as exc:
            return _err(f"get_game_mod_status failed: {exc}")

    # ── scan / apply / remove ────────────────────────────────────────────────

    async def scan_mod_zip(self, appid: str, zip_path: str) -> dict:
        try:
            record, install_root = _game(appid)
            if not record or not install_root:
                return _err("Game install directory not found.")
            result = scanner.scan(Path(zip_path).expanduser(), install_root)
            _log(
                f"Scanned {result['zip_name']} vs {record['name']}: "
                f"{result['overwrite_count']} overwrite, {result['new_count']} new, "
                f"proxy={result['proxy_dll'] or 'none'}"
                + (f", warnings={len(result['warnings'])}" if result["warnings"] else "")
            )
            result["status"] = "success"
            result["managed_launch_options"] = launch_options.build_managed_launch_options(
                result["proxy_dlls"]
            )
            return result
        except scanner.ScanError as exc:
            return _err(str(exc))
        except Exception as exc:
            return _err(f"scan_mod_zip failed: {exc}")

    async def apply_mod(self, appid: str, zip_path: str, current_launch_options: str = "") -> dict:
        try:
            record, install_root = _game(appid)
            if not record or not install_root:
                return _err("Game install directory not found.")
            if steam.is_game_running(install_root):
                return _err("Close the game before applying a mod.")

            zip_file = Path(zip_path).expanduser()
            scan_result = scanner.scan(zip_file, install_root)
            managed = launch_options.build_managed_launch_options(scan_result["proxy_dlls"])
            original = current_launch_options or ""
            if launch_options.is_managed_launch_options(original):
                original = ""

            manifest = patcher.apply_mod(
                zip_file,
                install_root,
                _runtime_dir(),
                str(appid),
                record["name"],
                scan_result=scan_result,
                original_launch_options=original,
                managed_launch_options=managed,
            )
            _log(
                f"Applied {manifest['mod_zip_name']} to {record['name']} ({appid}): "
                f"{scan_result['overwrite_count']} backed up + overwritten, "
                f"{scan_result['new_count']} added, launch options: {managed or 'none'}"
            )
            return {
                "status": "success",
                "appid": str(appid),
                "name": record["name"],
                "mod_zip_name": manifest["mod_zip_name"],
                "overwrite_count": scan_result["overwrite_count"],
                "new_count": scan_result["new_count"],
                "proxy_dll": scan_result["proxy_dll"],
                "launch_options": managed,
                "message": f"Applied {manifest['mod_zip_name']} to {record['name']}.",
            }
        except (scanner.ScanError, patcher.PatchError) as exc:
            return _err(str(exc))
        except Exception as exc:
            return _err(f"apply_mod failed: {exc}")

    async def remove_mod(self, appid: str) -> dict:
        try:
            record, install_root = _game(appid)
            if not record or not install_root:
                return _err("Game install directory not found.")
            if steam.is_game_running(install_root):
                return _err("Close the game before removing a mod.")
            manifest = patcher.load_manifest(_runtime_dir(), str(appid))
            tolerant = bool(manifest and manifest.get("state") == "applying")
            report = patcher.remove_mod(_runtime_dir(), str(appid), install_root, tolerant=tolerant)
            _log(
                f"Removed mod from {record['name']} ({appid}): "
                f"{len(report['restored'])} restored, {len(report['deleted'])} deleted, "
                f"{len(report['missing_backups'])} backups missing"
            )
            message = f"Mod removed from {record['name']}."
            if report["missing_backups"]:
                message += (
                    f" Warning: {len(report['missing_backups'])} backup(s) were missing; "
                    "run Steam's 'Verify integrity of game files'."
                )
            return {
                "status": "success",
                "appid": str(appid),
                "name": record["name"],
                "restored": len(report["restored"]),
                "deleted": len(report["deleted"]),
                "missing_backups": report["missing_backups"],
                "launch_options": report["original_launch_options"],
                "message": message,
            }
        except patcher.PatchError as exc:
            return _err(str(exc))
        except Exception as exc:
            return _err(f"remove_mod failed: {exc}")

    async def reapply_mod(self, appid: str, current_launch_options: str = "") -> dict:
        """Re-apply the managed zip after a game update."""
        try:
            record, install_root = _game(appid)
            if not record or not install_root:
                return _err("Game install directory not found.")
            managed_zip = patcher.managed_zip_path(_runtime_dir(), str(appid))
            if managed_zip is None:
                return _err("No stored mod archive for this game. Apply the mod from a file instead.")
            # Stage a copy outside the mod dir, since remove_mod deletes it.
            staging = managed_zip.parent.parent / f"reapply-{appid}{managed_zip.suffix}"
            import shutil

            shutil.copy2(managed_zip, staging)
            try:
                removal = await self.remove_mod(appid)
                if removal["status"] != "success":
                    return removal
                return await self.apply_mod(appid, str(staging), current_launch_options)
            finally:
                staging.unlink(missing_ok=True)
        except Exception as exc:
            return _err(f"reapply_mod failed: {exc}")

    async def get_patch_details(self, appid: str) -> dict:
        """Per-file debug breakdown for the details view (and the logs)."""
        try:
            record, install_root = _game(appid)
            details = patcher.get_patch_details(_runtime_dir(), str(appid), install_root)
            details["status"] = "success"
            details["appid"] = str(appid)
            details["name"] = record["name"] if record else None
            if details.get("patched"):
                counts = details.get("counts", {})
                decky.logger.info(
                    f"[details] appid={appid} mod={details.get('mod_zip_name')} "
                    f"state={details.get('state')} intact={counts.get('intact')} "
                    f"modified={counts.get('modified')} missing={counts.get('missing')}"
                )
            return details
        except Exception as exc:
            return _err(f"get_patch_details failed: {exc}")

    # ── self-update ──────────────────────────────────────────────────────────

    def _installed_version(self) -> str:
        try:
            import json as _json

            package = _json.loads((Path(decky.DECKY_PLUGIN_DIR) / "package.json").read_text())
            return str(package.get("version", "0.0.0"))
        except Exception:
            return "0.0.0"

    async def check_for_update(self) -> dict:
        try:
            installed = self._installed_version()
            release = updater.get_latest_release()
            return {
                "status": "success",
                "installed_version": installed,
                "latest_tag": release["tag"],
                "latest_title": release["title"],
                "published_at": release["published_at"],
                "zip_size": release["zip_size"],
                "notes": release["notes"],
                "update_available": updater.is_newer(release["tag"], installed),
            }
        except updater.UpdateError as exc:
            return _err(str(exc))
        except Exception as exc:
            return _err(f"check_for_update failed: {exc}")

    async def self_update(self) -> dict:
        try:
            installed = self._installed_version()
            release = updater.get_latest_release()
            if not updater.is_newer(release["tag"], installed):
                return {"status": "success", "updated": False, "message": "Already up to date."}
            updater.install_update(
                release["zip_url"], Path(decky.DECKY_PLUGIN_DIR), release["sha256_url"]
            )
            _log(f"Self-updated {installed} -> {release['tag']}")
            return {
                "status": "success",
                "updated": True,
                "message": (
                    f"Updated to {release['tag']}. Restart Steam (or reload the plugin "
                    "from Decky settings) to finish."
                ),
            }
        except updater.UpdateError as exc:
            return _err(str(exc))
        except Exception as exc:
            return _err(f"self_update failed: {exc}")

    async def get_activity_log(self, limit: int = 80) -> dict:
        try:
            return {"status": "success", "lines": activity.read_log(_runtime_dir(), int(limit))}
        except Exception as exc:
            return {"status": "error", "message": str(exc), "lines": []}

    # ── misc ─────────────────────────────────────────────────────────────────

    async def get_path_defaults(self) -> dict:
        home = _home()
        return {
            "status": "success",
            "home": str(home),
            "downloads": str(home / "Downloads"),
        }

    async def log_error(self, error: str) -> None:
        decky.logger.error(f"FRONTEND: {error}")
