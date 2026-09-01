# -*- mode: python ; coding: utf-8 -*-
# macOS 专用 spec（build-macos 任务的 x64 与 arm64 共用，架构由 runner 决定）
#
# 与 Windows/Linux spec 的差异：
#   - 不引用任何 Windows DLL 或 Linux .so；onnxruntime providers 共享 dylib
#     仅在 wheel 提供时按存在性收集（onnxruntime 1.18.1 的 macOS wheel 不含）。
#   - libzbar 由宿主机提供（brew install zbar），与 Linux 依赖 libzbar0 一致，
#     不打进 .app；缺 zbar 只影响二维码功能，不影响启动。
#   - pywebview 的 Cocoa 后端经 pyobjc 访问系统框架，PyInstaller 6.22 无对应
#     hook，必须显式声明 hiddenimports（objc 运行时 + Cocoa/WebKit/Security/
#     Quartz 框架 + PyObjCTools），pystray 的 macOS 后端需要 Quartz。
#   - upx 关闭：避免压缩破坏 Mach-O 的 ad-hoc 签名。
#   - 生成标准 .app bundle：BUNDLE 会把所有 EXECUTABLE（mower 与 manager）
#     放进 Contents/MacOS，其余数据放进 Resources，并默认 ad-hoc 签名
#     （codesign_identity=None 即 --sign -，非 Developer ID）。
import sys
from pathlib import Path

import rapidocr_onnxruntime

SPEC_DIR = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
if str(SPEC_DIR) not in sys.path:
    sys.path.insert(0, str(SPEC_DIR))

from build_assets import get_pyinstaller_common_datas

block_cipher = None

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

site_packages = install_dir.parent

MACOS_HIDDEN_IMPORTS = [
    "objc",
    "PyObjCTools",
    "Cocoa",
    "WebKit",
    "Security",
    "Quartz",
    "webview.platforms.cocoa",
]


def existing_native_datas():
    """收集 macOS wheel 实际提供的原生 dylib，不引用 Windows DLL/Linux .so。"""
    datas = []
    providers = (
        site_packages / "onnxruntime" / "capi" / "libonnxruntime_providers_shared.dylib"
    )
    if providers.is_file():
        datas.append((str(providers), "onnxruntime/capi/"))
    return datas


mower_a = Analysis(
    ["webview_ui.py"],
    pathex=[],
    binaries=[],
    datas=get_pyinstaller_common_datas() + existing_native_datas() + add_data,
    hiddenimports=MACOS_HIDDEN_IMPORTS,
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "torch",
        "transformers",
        "tokenizers",
        "safetensors",
        "huggingface_hub",
        "accelerate",
        "opencv_videoio_ffmpeg",
        "sympy",
        "mpmath",
        "setuptools",
        "pkg_resources",
        "pygments",
        "rich",
        "fsspec",
        "xlsxwriter",
        "openpyxl",
        "_pytest",
        "pytest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

mower_pure = [i for i in mower_a.pure if not i[0].startswith("arknights_mower")]

mower_pyz = PYZ(
    mower_pure,
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
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="logo.icns",
)


manager_a = Analysis(
    ["manager.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=MACOS_HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "setuptools",
        "pkg_resources",
        "sympy",
        "mpmath",
        "pygments",
        "rich",
        "fsspec",
        "xlsxwriter",
        "openpyxl",
        "_pytest",
        "pytest",
    ],
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
    name="manager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="logo.icns",
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
    strip=False,
    upx=False,
    upx_exclude=[],
    name="mower",
)

app = BUNDLE(
    coll,
    name="mower.app",
    icon="logo.icns",
    bundle_identifier="com.arkmowers.arknights-mower",
    info_plist={
        "NSHighResolutionCapable": True,
        "CFBundleDisplayName": "arknights-mower",
    },
)
