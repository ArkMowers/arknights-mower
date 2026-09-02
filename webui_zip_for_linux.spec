# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys

import rapidocr_onnxruntime
from PyInstaller.utils.hooks import collect_submodules

SPEC_DIR = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
if str(SPEC_DIR) not in sys.path:
    sys.path.insert(0, str(SPEC_DIR))

from build_assets import get_pyinstaller_common_datas

block_cipher = None

# pywebview 在 Linux 上默认先加载 GTK 后端（webview.platforms.gtk），该后端只依赖
# PyGObject（gi），Qt 后端（qtpy + PyQt/PySide）不是默认路径、体积也大，刻意不收集，
# 避免把不需要的 Qt 全家打进包。guilib.py 对 webview.platforms.gtk 的 import 位于
# 惰性加载路径，PyInstaller 并不稳定地沿它收集 gi；这里显式收集 gi 的 Python 包并
# 强制 webview.platforms.gtk，保证产物带上 PyGObject。运行期经 gi.repository 的
# DynamicImporter 从宿主加载 Gtk/WebKit2 等 typelib。宿主仍需安装 libgtk-3、
# libwebkit2gtk-4.1、gir1.2-webkit2 等原生库。
PYWEBVIEW_GTK_HIDDENIMPORTS = []
PYWEBVIEW_GTK_EXCLUDES = []
try:
    import gi  # noqa: F401  # 仅探测构建机是否安装 PyGObject

    PYWEBVIEW_GTK_HIDDENIMPORTS = [
        "webview.platforms.gtk",
        "gi",
        "gi.repository",
    ]
    try:
        PYWEBVIEW_GTK_HIDDENIMPORTS += collect_submodules("gi")
    except Exception:
        pass
    # GTK/WebKit2 的原生库与 typelib 一律来自宿主，不进产物，避免把 libgtk-3、
    # libwebkit2gtk-4.1 整棵依赖树打包并与宿主 WebKit2 版本不一致。
    PYWEBVIEW_GTK_EXCLUDES = [
        "gi.repository.GLib",
        "gi.repository.GObject",
        "gi.repository.Gio",
        "gi.repository.Gdk",
        "gi.repository.GdkPixbuf",
        "gi.repository.Gtk",
        "gi.repository.Pango",
        "gi.repository.PangoCairo",
        "gi.repository.cairo",
        "gi.repository.Soup",
        "gi.repository.WebKit2",
        "gi.repository.HarfBuzz",
    ]
except ImportError:
    # 构建机没有安装 PyGObject：产物不含 pywebview 的 GTK 后端，运行期会用中文提示
    # 宿主安装原生库，而不是抛出裸 ImportError。
    pass

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


site_packages = install_dir.parent


mower_a = Analysis(
    ["webview_ui.py"],
    pathex=[],
    binaries=[],
    datas=get_pyinstaller_common_datas()
    + [
        (
            f"{site_packages}/onnxruntime/capi/libonnxruntime_providers_shared.so",
            "onnxruntime/capi/",
        ),
    ]
    + add_data,
    hiddenimports=PYWEBVIEW_GTK_HIDDENIMPORTS,
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "torch",
        "transformers",
        "tokenizers",
        "safetensors",
        "huggingface_hub",
        "accelerate",
        "scipy",
        "skimage",
        "sklearn",
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
        *PYWEBVIEW_GTK_EXCLUDES,
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
    hiddenimports=PYWEBVIEW_GTK_HIDDENIMPORTS,
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
        *PYWEBVIEW_GTK_EXCLUDES,
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
    upx=True,
    upx_exclude=[],
    name="mower",
)
