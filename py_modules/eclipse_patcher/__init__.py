"""Eclipse Patcher backend logic.

Pure-Python modules with no Decky dependency so they can be unit-tested
off-device. `main.py` is the only file that imports `decky`.
"""

__all__ = ["scanner", "patcher", "steam"]
