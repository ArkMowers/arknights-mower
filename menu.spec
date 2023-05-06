# -*- mode: python ; coding: utf-8 -*-


block_cipher = None


a = Analysis(
    ['menu.py'],
    pathex=[],
    binaries=[],
    datas=[('arknights_mower/fonts', 'arknights_mower/__init__/fonts'),
        ('arknights_mower/models', 'arknights_mower/__init__/models'),
        ('arknights_mower/templates', 'arknights_mower/__init__/templates'),
        ('arknights_mower/resources', 'arknights_mower/__init__/resources'),
        ('arknights_mower/data', 'arknights_mower/__init__/data'),
        ('arknights_mower/ocr', 'arknights_mower/__init__/ocr'),
        ('arknights_mower/vendor', 'arknights_mower/__init__/vendor'),
        ('arknights_mower/solvers', 'arknights_mower/__init__/solvers'),
        ('venv/Lib/site-packages/onnxruntime/capi/onnxruntime_providers_shared.dll', 'onnxruntime/capi/'),
        ('venv/Lib/site-packages/paddleocr', 'paddleocr'),
        ('venv/Lib/site-packages/paddle/libs/mkldnn.dll', '.'),
        ('venv/Lib/site-packages/paddle/libs/mklml.dll', '.'),
        ('venv/Lib/site-packages/shapely/DLLs/geos.dll', '.'),
        ('venv/Lib/site-packages/paddle/fluid/proto/framework_pb2.py', '.'),
        ('venv/Lib/site-packages/paddle/fluid/libpaddle.lib', '.'),
        ('venv/Lib/site-packages/paddle/fluid/libpaddle.pyd', '.'),
        ('venv/Lib/site-packages/shapely/DLLs/geos_c.dll', '.')],
    hiddenimports=['imghdr','imgaug','scipy.io','lmdb'],
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='mower',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False   ,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='logo.ico'
)
