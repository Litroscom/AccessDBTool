# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\CO\\Desktop\\Progetti Antigravity\\AccessDBTool\\AccessDBTool_v5.0\\access_db_tool.pyw'],
    pathex=['C:\\Users\\CO\\Desktop\\Progetti Antigravity\\AccessDBTool\\AccessDBTool_v5.0\\_vendor'],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=['C:\\Users\\CO\\Desktop\\Progetti Antigravity\\AccessDBTool\\AccessDBTool_v5.0\\pyinstaller_hooks'],
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
    name='AccessDBToolPortable',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AccessDBToolPortable',
)
