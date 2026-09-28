# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for Dockomo.
#
# WHY ONEDIR, NOT ONEFILE:
# Onefile re-extracts every bundled file into a temp folder on every single
# launch, which is slow with RDKit/Qt/WebEngine on board, and is exactly the
# kind of setup that produced the __file__ / _MEIPASS confusion we hit
# before. Onedir keeps everything in one stable folder next to Dockomo.exe.
# Inno Setup installs that whole folder, so the end user still just sees one
# shortcut -- this choice is invisible to them.
#
# WHY collect_data_files FOR rdkit/meeko:
# Both ship real data files (parameter tables, atom-typing data) alongside
# their .py code. Static import analysis only grabs code, not data -- this
# is almost certainly why past Nuitka builds installed but didn't work.
#
# Build with:  pyinstaller Dockomo.spec

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
PROJECT_ROOT = os.path.abspath(os.path.dirname(os.path.abspath(SPEC)))

rdkit_datas = collect_data_files("rdkit")
meeko_datas = collect_data_files("meeko")
meeko_hidden = collect_submodules("meeko")

datas = rdkit_datas + meeko_datas + [
    (os.path.join(PROJECT_ROOT, "assets", "icon.ico"), "assets"),
    # AutoDock Vina binary (Apache-2.0 licensed, redistribution is fine).
    # Put vina.exe (and any DLLs it needs) in a "vina" folder next to
    # main.py before building -- see PACKAGING_README.md.
    (os.path.join(PROJECT_ROOT, "vina", "vina.exe"), "vina"),
]

hiddenimports = meeko_hidden + [
    # Imported dynamically inside core/prep.py -- static analysis can miss it.
    "meeko.cli.mk_prepare_receptor",
]

a = Analysis(
    ["main.py"],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # onedir mode -- binaries go in COLLECT below
    name="Dockomo",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,               # UPX + Qt/WebEngine binaries is a common source
                              # of "works on my machine" AV false-positives
                              # and silent crashes -- leave off.
    console=False,
    icon=os.path.join(PROJECT_ROOT, "assets", "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Dockomo",
)
