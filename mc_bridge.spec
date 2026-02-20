# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for MC Bridge."""

block_cipher = None

a = Analysis(
    ['mc_bridge/app.py'],
    pathex=[],
    binaries=[],
    datas=[('resources/icon.png', 'resources')],
    hiddenimports=[
        'mc_bridge.server',
        'mc_bridge.config',
        'mc_bridge.models',
        'mc_bridge.security',
        'mc_bridge.connectors',
        'mc_bridge.connectors.snowflake',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'snowflake.connector',
        'snowflake.connector.snow_logging',
        'snowflake.connector.cursor',
        'snowflake.connector.connection',
        'snowflake.connector.network',
        'snowflake.connector.auth',
        'snowflake.connector.result_batch',
        'keyring',
        'keyring.backends',
        'keyring.backends.macOS',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='mc-bridge',
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
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='mc-bridge',
)

app = BUNDLE(
    coll,
    name='MC Bridge.app',
    icon='resources/AppIcon.icns',
    bundle_identifier='com.montecarlodata.bridge',
    info_plist={
        'CFBundleName': 'MC Bridge',
        'CFBundleDisplayName': 'MC Bridge',
        'CFBundleVersion': '0.1.0',
        'CFBundleShortVersionString': '0.1.0',
        'LSUIElement': True,  # Menu bar app - no dock icon
        'LSMinimumSystemVersion': '10.15',
        'NSHighResolutionCapable': True,
    },
)

