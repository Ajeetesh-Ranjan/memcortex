# Unified Memory Stack — Menubar Widget Build Spec
# Build single-file executable for all platforms
# Usage: pyinstaller memory_menubar.spec

block_cipher = None

a = Analysis(
    ['memory_menubar.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('../README.md', '.'),
    ],
    hiddenimports=[
        'pystray',
        'PIL',
        'PIL.Image',
        'PIL.ImageDraw',
        'requests',
        'json',
        'threading',
        'time',
        'platform',
        'subprocess',
        'webbrowser',
        'os',
        'sys',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
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
    name='memory-menubar',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # macOS specific
    icon='icon.icns' if sys.platform == 'darwin' else None,
    # Windows specific
    uac_admin=False,
    uac_uiaccess=False,
)