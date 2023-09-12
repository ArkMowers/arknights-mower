# -*- mode: python ; coding: utf-8 -*-


block_cipher = None


mower_a = Analysis(
    ["webview_ui.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("arknights_mower/fonts", "arknights_mower/__init__/fonts"),
        ("arknights_mower/models", "arknights_mower/__init__/models"),
        ("arknights_mower/templates", "arknights_mower/__init__/templates"),
        ("arknights_mower/resources", "arknights_mower/__init__/resources"),
        ("arknights_mower/data", "arknights_mower/__init__/data"),
        ("arknights_mower/ocr", "arknights_mower/__init__/ocr"),
        ("arknights_mower/vendor", "arknights_mower/__init__/vendor"),
        ("arknights_mower/solvers", "arknights_mower/__init__/solvers"),
        (
            "venv/Lib/site-packages/onnxruntime/capi/onnxruntime_providers_shared.dll",
            "onnxruntime/capi/",
        ),
        ("venv/Lib/site-packages/paddleocr", "paddleocr"),
        ("venv/Lib/site-packages/paddle/libs/mklml.dll", "."),
        ("venv/Lib/site-packages/shapely/DLLs/geos.dll", "."),
        ("venv/Lib/site-packages/paddle/fluid/proto/framework_pb2.py", "."),
        ("venv/Lib/site-packages/paddle/fluid/libpaddle.lib", "."),
        ("venv/Lib/site-packages/paddle/fluid/libpaddle.pyd", "."),
        ("venv/Lib/site-packages/shapely/DLLs/geos_c.dll", "."),
        ("logo.png", "."),
        ("dist", "dist"),
    ],
    hiddenimports=["imghdr", "imgaug", "scipy.io", "lmdb"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

mower_pyz = PYZ(mower_a.pure, mower_a.zipped_data, cipher=block_cipher)

mower_exe = EXE(
    mower_pyz,
    mower_a.scripts,
    [],
    exclude_binaries=True,
    name="mower",
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
    icon="logo.ico",
)

mower0_a = Analysis(
    ["Mower0.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("arknights_mower/fonts", "arknights_mower/__init__/fonts"),
        ("arknights_mower/models", "arknights_mower/__init__/models"),
        ("arknights_mower/templates", "arknights_mower/__init__/templates"),
        ("arknights_mower/resources", "arknights_mower/__init__/resources"),
        ("arknights_mower/data", "arknights_mower/__init__/data"),
        ("arknights_mower/ocr", "arknights_mower/__init__/ocr"),
        ("arknights_mower/vendor", "arknights_mower/__init__/vendor"),
        ("arknights_mower/solvers", "arknights_mower/__init__/solvers"),
        (
            "venv/Lib/site-packages/onnxruntime/capi/onnxruntime_providers_shared.dll",
            "onnxruntime/capi/",
        ),
        ("venv/Lib/site-packages/paddleocr", "paddleocr"),
        ("venv/Lib/site-packages/paddle/libs/mklml.dll", "."),
        ("venv/Lib/site-packages/shapely/DLLs/geos.dll", "."),
        ("venv/Lib/site-packages/paddle/fluid/proto/framework_pb2.py", "."),
        ("venv/Lib/site-packages/paddle/fluid/libpaddle.lib", "."),
        ("venv/Lib/site-packages/paddle/fluid/libpaddle.pyd", "."),
        ("venv/Lib/site-packages/shapely/DLLs/geos_c.dll", "."),
        ("Mower0用户配置文件.yaml", "."),
        ("logo.png", "."),
    ],
    hiddenimports=["imghdr", "imgaug", "scipy.io", "lmdb"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

mower0_pyz = PYZ(mower0_a.pure, mower0_a.zipped_data, cipher=block_cipher)

mower0_exe = EXE(
    mower0_pyz,
    mower0_a.scripts,
    [],
    exclude_binaries=True,
    name="Mower0",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="logo.ico",
)

coll = COLLECT(
    mower_exe,
    mower_a.binaries,
    mower_a.zipfiles,
    mower_a.datas,
    mower0_exe,
    mower0_a.binaries,
    mower0_a.zipfiles,
    mower0_a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="mower",
)
