# -*- mode: python ; coding: utf-8 -*-
# Build with build.bat  (onedir: fewer Windows Defender / Smart App Control warnings than onefile)
from PyInstaller.utils.hooks import collect_submodules

hidden = []
for pkg in ("winrt", "pycaw", "comtypes", "pystray", "speech_recognition", "plyer"):
    try:
        hidden += collect_submodules(pkg)
    except Exception:
        pass
hidden += ["PIL._tkinter_finder", "sounddevice"]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CommandCenter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                 # UPX-packed files are flagged by antivirus far more often
    console=False,
    disable_windowed_traceback=False,
    uac_admin=False,           # no admin prompt on every launch; Start with Windows needs this
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="CommandCenter")
