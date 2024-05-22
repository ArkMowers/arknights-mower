# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

import rapidocr_onnxruntime

block_cipher = None

# 参考 https://github.com/RapidAI/RapidOCR/blob/main/ocrweb/rapidocr_web/ocrweb.spec
package_name = "rapidocr_onnxruntime"
install_dir = Path(rapidocr_onnxruntime.__file__).resolve().parent

onnx_paths = list(install_dir.rglob("*.onnx"))
yaml_paths = list(install_dir.rglob("*.yaml"))

onnx_add_data = [(str(v.parent), f"{package_name}/{v.parent.name}") for v in onnx_paths]

yaml_add_data = []
for v in yaml_paths:
    if package_name == v.parent.name:
        yaml_add_data.append((str(v.parent / "*.yaml"), package_name))
    else:
        yaml_add_data.append(
            (str(v.parent / "*.yaml"), f"{package_name}/{v.parent.name}")
        )

add_data = list(set(yaml_add_data + onnx_add_data))

excludes = ["matplotib"]


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
        ("arknights_mower/vendor", "arknights_mower/__init__/vendor"),
        (
            "venv/Lib/site-packages/onnxruntime/capi/onnxruntime_providers_shared.dll",
            "onnxruntime/capi/",
        ),
        ("logo.png", "."),
        ("venv/Lib/site-packages/pyzbar/libzbar-64.dll", "."),
        ("venv/Lib/site-packages/pyzbar/libiconv.dll", "."),
    ]
    + add_data,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

mower_pyz = PYZ(
    mower_a.pure,
    mower_a.zipped_data,
    cipher=block_cipher,
)

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


manager_a = Analysis(
    ["manager.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

manager_pyz = PYZ(
    manager_a.pure,
    manager_a.zipped_data,
    cipher=block_cipher,
)

manager_exe = EXE(
    manager_pyz,
    manager_a.scripts,
    [],
    exclude_binaries=True,
    name="多开管理器",
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


toolbox_a = Analysis(
    ["toolbox.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

toolbox_pyz = PYZ(
    toolbox_a.pure,
    toolbox_a.zipped_data,
    cipher=block_cipher,
)

toolbox_exe = EXE(
    toolbox_pyz,
    toolbox_a.scripts,
    [],
    exclude_binaries=True,
    name="工具箱",
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


coll = COLLECT(
    mower_exe,
    mower_a.binaries,
    mower_a.zipfiles,
    mower_a.datas,
    manager_exe,
    manager_a.binaries,
    manager_a.zipfiles,
    manager_a.datas,
    toolbox_exe,
    toolbox_a.binaries,
    toolbox_a.zipfiles,
    toolbox_a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="mower",
)
