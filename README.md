# Decky Eclipse Patcher

A [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin that installs and cleanly removes
[Eclipse mods](https://www.nexusmods.com/profile/SteamDeckEclipseMods/mods) (or any file-overlay mod zip)
on Steam Deck games — with automatic backups and byte-exact unpatching.

## How it works

1. Download an Eclipse mod zip for your game (e.g. from Nexus Mods) to your Deck.
2. Open the plugin from the Quick Access menu, pick the game, pick the zip.
3. The plugin scans the zip against the game's install folder and shows a preview:
   which files will be **overwritten** (backed up first) and which are **new**.
4. Apply. If the mod ships proxy DLLs (`dxgi.dll`, etc.), launch options
   (`WINEDLLOVERRIDES=...`) are set automatically.
5. Remove Mod restores every backed-up file, deletes everything the mod added,
   and restores your original launch options.

State (manifests, backups, a managed copy of the mod zip) lives in the plugin's
runtime directory, so you can re-apply a mod after a game update without
re-downloading anything.

## Safety model

- Dry-run scan + preview before anything is written.
- Originals are backed up before any file is overwritten; the install manifest is
  written *before* the game directory is touched, so an interrupted install can
  always be rolled back.
- Patching is refused while the game is running.
- All writes are confined to the game's install directory.

> **Note:** uninstalling this plugin does **not** automatically unpatch games.
> Remove mods first, or use Steam's "Verify integrity of game files" +
> manually delete added files.

## Development

```
pnpm install
pnpm build          # frontend -> dist/index.js
python -m pytest    # backend unit tests (no Deck required)
```

See `justfile` for build/deploy-to-Deck recipes (SSH required on the Deck).

## License

BSD-3-Clause
