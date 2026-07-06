"""Rolling activity log so the UI can show what happened without SSH."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

LOG_FILENAME = "activity.log"
MAX_LINES = 400


def log_path(runtime_dir: Path) -> Path:
    return runtime_dir / LOG_FILENAME


def log_event(runtime_dir: Path, message: str) -> None:
    try:
        path = log_path(runtime_dir)
        stamp = datetime.now(timezone.utc).strftime("%m-%d %H:%M:%S")
        lines: list[str] = []
        if path.is_file():
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-(MAX_LINES - 1):]
        lines.append(f"[{stamp}] {message}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        pass  # logging must never break an operation


def read_log(runtime_dir: Path, limit: int = 80) -> list[str]:
    """Newest entries first."""
    path = log_path(runtime_dir)
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return list(reversed(lines[-limit:]))
