"""Native directory selection for desktop windows."""

import ctypes
import sys
from contextlib import ExitStack
from pathlib import Path
from uuid import UUID


class _GUID(ctypes.Structure):
    _fields_ = [
        ("data1", ctypes.c_uint32),
        ("data2", ctypes.c_uint16),
        ("data3", ctypes.c_uint16),
        ("data4", ctypes.c_ubyte * 8),
    ]


_FILE_OPEN_DIALOG = _GUID.from_buffer_copy(
    UUID("dc1c5a9c-e88a-4dde-a5a1-60f82a20aef7").bytes_le
)
_I_FILE_DIALOG = _GUID.from_buffer_copy(
    UUID("42f85136-db7e-439c-85f1-e4075d135fc8").bytes_le
)
_I_SHELL_ITEM = _GUID.from_buffer_copy(
    UUID("43826d1e-e718-42ee-bc55-a1e261c37bfe").bytes_le
)
_CANCELLED = -2147023673
_FOS_PICKFOLDERS = 0x20
_FOS_FORCEFILESYSTEM = 0x40
_FOS_ALLOWMULTISELECT = 0x200
_FOS_PATHMUSTEXIST = 0x800
_SIGDN_FILESYSPATH = 0x80058000


def _check(result):
    if result < 0:
        raise OSError(
            f"Windows directory picker failed (HRESULT 0x{result & 0xFFFFFFFF:08X})"
        )


def _invoke(pointer, slot, argtypes=(), *args):
    # IFileDialog and IShellItem use the SDK's COM vtable order and stdcall ABI.
    table = ctypes.cast(
        pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
    ).contents
    method = ctypes.WINFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, *argtypes)(table[slot])
    return method(pointer, *args)


def _windows_libraries():
    ole32 = ctypes.WinDLL("ole32")
    shell32 = ctypes.WinDLL("shell32")
    pointer = ctypes.c_void_p
    signatures = (
        (ole32.CoInitializeEx, ctypes.c_int32, [pointer, ctypes.c_uint32]),
        (ole32.CoUninitialize, None, []),
        (ole32.CoTaskMemFree, None, [pointer]),
        (
            ole32.CoCreateInstance,
            ctypes.c_int32,
            [
                ctypes.POINTER(_GUID),
                pointer,
                ctypes.c_uint32,
                ctypes.POINTER(_GUID),
                ctypes.POINTER(pointer),
            ],
        ),
        (
            shell32.SHCreateItemFromParsingName,
            ctypes.c_int32,
            [ctypes.c_wchar_p, pointer, ctypes.POINTER(_GUID), ctypes.POINTER(pointer)],
        ),
    )
    for function, restype, argtypes in signatures:
        function.restype, function.argtypes = restype, argtypes
    return ole32, shell32


def _show_windows_folder(owner, directory, title):
    ole32, shell32 = _windows_libraries()
    _check(ole32.CoInitializeEx(None, 2))  # COINIT_APARTMENTTHREADED
    with ExitStack() as cleanup:
        cleanup.callback(ole32.CoUninitialize)
        dialog = ctypes.c_void_p()
        _check(
            ole32.CoCreateInstance(
                ctypes.byref(_FILE_OPEN_DIALOG),
                None,
                1,
                ctypes.byref(_I_FILE_DIALOG),
                ctypes.byref(dialog),
            )
        )
        cleanup.callback(_invoke, dialog, 2)  # IUnknown::Release
        options = ctypes.c_uint32()
        _check(
            _invoke(
                dialog, 10, (ctypes.POINTER(ctypes.c_uint32),), ctypes.byref(options)
            )
        )
        flags = (
            options.value | _FOS_PICKFOLDERS | _FOS_FORCEFILESYSTEM | _FOS_PATHMUSTEXIST
        ) & ~_FOS_ALLOWMULTISELECT
        _check(_invoke(dialog, 9, (ctypes.c_uint32,), flags))
        _check(_invoke(dialog, 17, (ctypes.c_wchar_p,), title))
        if directory and Path(directory).is_dir():
            initial = ctypes.c_void_p()
            _check(
                shell32.SHCreateItemFromParsingName(
                    str(Path(directory).resolve()),
                    None,
                    ctypes.byref(_I_SHELL_ITEM),
                    ctypes.byref(initial),
                )
            )
            cleanup.callback(_invoke, initial, 2)
            _check(_invoke(dialog, 12, (ctypes.c_void_p,), initial))
        result = _invoke(dialog, 3, (ctypes.c_void_p,), owner)
        if result == _CANCELLED:
            return None
        _check(result)
        selected = ctypes.c_void_p()
        _check(
            _invoke(
                dialog, 20, (ctypes.POINTER(ctypes.c_void_p),), ctypes.byref(selected)
            )
        )
        cleanup.callback(_invoke, selected, 2)
        name = ctypes.c_void_p()
        _check(
            _invoke(
                selected,
                5,
                (ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)),
                _SIGDN_FILESYSPATH,
                ctypes.byref(name),
            )
        )
        cleanup.callback(ole32.CoTaskMemFree, name)
        return ctypes.wstring_at(name)


def choose_directory(window, directory="", title="选择文件夹"):
    if sys.platform != "win32":
        import webview

        return window.create_file_dialog(
            dialog_type=webview.FOLDER_DIALOG, directory=directory
        )
    from arknights_mower.utils.windows_frameless import _winforms_hwnd, _winforms_window

    form = _winforms_window(window)

    def show():
        return _show_windows_folder(_winforms_hwnd(window), directory, title)

    if form.InvokeRequired:
        from System import Func, String

        return form.Invoke(Func[String](show))
    return show()
