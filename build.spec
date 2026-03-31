# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for EQ-Creds
# Build: pyinstaller build.spec

from pathlib import Path
from typing import Optional

try:
    from PIL import Image
except Exception:
    Image = None


def _resolve_icon() -> Optional[str]:
    """
    Return an ICO path for PyInstaller.

    Priority:
    1) assets/icon.ico if already present
    2) convert assets/icon.png or assets/EQ-Creds.png -> assets/icon.ico
    3) return None (no icon)
    """
    assets_dir = Path("assets")
    ico_path = assets_dir / "icon.ico"
    if ico_path.exists():
        return str(ico_path)

    png_candidates = [
        assets_dir / "icon.png",
        assets_dir / "EQ-Creds.png",
    ]
    png_path = next((p for p in png_candidates if p.exists()), None)
    if png_path is None:
        print("[build.spec] No PNG icon candidate found in assets/.")
        return None

    if Image is None:
        print("[build.spec] Pillow not available; cannot convert PNG to ICO.")
        return None

    try:
        with Image.open(png_path) as img:
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            img.save(
                ico_path,
                format="ICO",
                sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
            )
        print(f"[build.spec] Converted {png_path} -> {ico_path}")
        return str(ico_path)
    except Exception as exc:
        print(f"[build.spec] Failed to convert icon: {exc}")
        return None


ICON_PATH = _resolve_icon()

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets', 'assets'),
    ],
    hiddenimports=[
        'argon2',
        'argon2.low_level',
        'cryptography',
        'cryptography.hazmat.primitives.ciphers.aead',
        'pydantic',
        'pydantic.v1',
        'PySide6.QtWidgets',
        'PySide6.QtCore',
        'PySide6.QtGui',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'scipy',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngineCore',
        'PySide6.QtMultimedia',
        'PySide6.QtNetwork',
        'PySide6.Qt3DCore',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='EQCreds',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # no console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_PATH,
)
