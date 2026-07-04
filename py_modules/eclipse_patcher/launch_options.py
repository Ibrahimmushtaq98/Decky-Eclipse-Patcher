"""Build and recognize managed WINEDLLOVERRIDES launch options."""
from __future__ import annotations

MANAGED_SUFFIX = "%command%"


def build_managed_launch_options(proxy_dlls: list[str]) -> str:
    """e.g. ['dxgi.dll','version.dll'] -> 'WINEDLLOVERRIDES=dxgi,version=n,b %command%'"""
    if not proxy_dlls:
        return ""
    bases = ",".join(dll[:-4] if dll.lower().endswith(".dll") else dll for dll in proxy_dlls)
    return f"WINEDLLOVERRIDES={bases}=n,b {MANAGED_SUFFIX}"


def is_managed_launch_options(options: str) -> bool:
    """True if the string looks like something this plugin set."""
    if not options or not options.strip():
        return False
    normalized = " ".join(options.split())
    return "WINEDLLOVERRIDES=" in normalized and "=n,b" in normalized
