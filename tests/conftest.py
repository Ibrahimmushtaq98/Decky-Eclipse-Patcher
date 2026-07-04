import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "py_modules"))


@pytest.fixture
def game_dir(tmp_path: Path) -> Path:
    """A fake game install with a few files."""
    root = tmp_path / "game" / "EclipseQuest"
    (root / "engine").mkdir(parents=True)
    (root / "data" / "textures").mkdir(parents=True)
    (root / "EclipseQuest.exe").write_bytes(b"EXE" * 100)
    (root / "engine" / "renderer.dll").write_bytes(b"RENDER-V1")
    (root / "data" / "config.ini").write_text("quality=low\n")
    (root / "data" / "textures" / "rock.pak").write_bytes(b"ROCK" * 50)
    return root


def make_zip(path: Path, entries: dict[str, bytes]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return path


@pytest.fixture
def mirror_zip(tmp_path: Path) -> Path:
    """Exact-mirror mod: overwrites 2 files, adds 2 new ones + proxy dll."""
    return make_zip(
        tmp_path / "mods" / "eclipse_mirror.zip",
        {
            "engine/renderer.dll": b"RENDER-V2-MODDED",
            "data/config.ini": b"quality=eclipse\n",
            "data/textures/moon.pak": b"MOON" * 60,
            "eclipse/shaders.fx": b"shader{}",
            "dxgi.dll": b"PROXYDLL",
        },
    )


@pytest.fixture
def wrapped_zip(tmp_path: Path) -> Path:
    """Same mod wrapped in a single top-level folder."""
    return make_zip(
        tmp_path / "mods" / "eclipse_wrapped.zip",
        {
            "EclipseMod/engine/renderer.dll": b"RENDER-V2-MODDED",
            "EclipseMod/data/config.ini": b"quality=eclipse\n",
            "EclipseMod/data/textures/moon.pak": b"MOON" * 60,
            "EclipseMod/eclipse/shaders.fx": b"shader{}",
            "EclipseMod/dxgi.dll": b"PROXYDLL",
            "README.txt": b"install instructions",
        },
    )
