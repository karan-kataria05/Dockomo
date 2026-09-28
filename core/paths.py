"""
Central place for every filesystem path Dockomo touches, so path resolution
behaves the same whether we're running from source (`python main.py`) or from
a compiled Dockomo.exe.

Two different kinds of path, handled differently:

1. READ-ONLY bundled resources (icon.ico, the bundled vina.exe, any other
   file shipped inside the installer) -> resource_path().
   Once frozen, these live next to the .exe (onedir build) or in a temp
   extraction folder (onefile build) -- never at the __file__ location the
   source code happens to live at.

2. WRITABLE per-user data (dockomo_settings.ini) -> settings_ini_path().
   Never written next to the exe: if Dockomo is installed to
   C:\\Program Files\\Dockomo, that folder isn't writable without admin
   rights. We use the standard per-user AppData folder instead, like any
   normal Windows app.
"""

import os
import sys

from PyQt5.QtCore import QStandardPaths


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_root() -> str:
    """Folder containing Dockomo.exe (frozen) or the project's top-level
    folder, i.e. the one containing main.py (running from source)."""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    # this file lives in core/, so the project root is one level up
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(*parts: str) -> str:
    """Path to a bundled, read-only resource (assets, bundled vina, etc.)."""
    # Only set for a PyInstaller ONEFILE build's temp extraction dir.
    # For a onedir build (what we're using) this is just app_root().
    base = getattr(sys, "_MEIPASS", None) or app_root()
    return os.path.join(base, *parts)


def bundled_vina_exe() -> str:
    return resource_path("vina", "vina.exe")


def writable_data_dir() -> str:
    """Per-user, always-writable folder for anything Dockomo saves at
    runtime (currently just the settings .ini)."""
    path = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    os.makedirs(path, exist_ok=True)
    return path


def settings_ini_path() -> str:
    return os.path.join(writable_data_dir(), "dockomo_settings.ini")

def default_output_dir() -> str:
    """Default, always-writable location for run outputs (poses, receptor
    prep, ligand PDBQTs) -- inside the user's own Documents folder, never
    tied to wherever the app happens to be installed or launched from."""
    docs = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
    path = os.path.join(docs, "Dockomo", "vinadock_output")
    os.makedirs(path, exist_ok=True)
    return path


def is_writable_dir(path: str) -> bool:
    """True only if we can actually create files under this directory --
    used to distrust a remembered folder that might no longer be writable
    (e.g. an old value pointing inside Program Files)."""
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".dockomo_write_test")
        with open(probe, "w") as fh:
            fh.write("ok")
        os.remove(probe)
        return True
    except OSError:
        return False