import ctypes
import sys
from concurrent.futures import Future
from threading import Thread
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.utils import folder_dialog as dialogs


@pytest.fixture
def native(monkeypatch):
    ole32, shell32 = Mock(), Mock()
    ole32.CoInitializeEx.return_value = 0
    name = ctypes.create_unicode_buffer("C:\\Mower data\\选择目录")
    calls = []

    def create(*args):
        args[-1]._obj.value = 11
        return 0

    def initial(*args):
        args[-1]._obj.value = 22
        return 0

    def invoke(pointer, slot, argtypes=(), *args):
        calls.append((pointer.value, slot, args))
        if slot == 10:
            args[0]._obj.value = 0x200 | 0x100000
        elif slot == 20:
            args[0]._obj.value = 33
        elif slot == 5:
            args[-1]._obj.value = ctypes.addressof(name)
        return 0

    ole32.CoCreateInstance.side_effect = create
    shell32.SHCreateItemFromParsingName.side_effect = initial
    monkeypatch.setattr(dialogs, "_windows_libraries", lambda: (ole32, shell32))
    call = Mock(side_effect=invoke)
    monkeypatch.setattr(dialogs, "_invoke", call)
    return SimpleNamespace(
        ole=ole32, shell=shell32, calls=calls, invoke=call, dispatch=invoke
    )


def test_folder_selection_preserves_flags_owner_unicode_and_releases_resources(
    native, tmp_path
):
    assert (
        dialogs._show_windows_folder(12345, str(tmp_path), "选择目录")
        == "C:\\Mower data\\选择目录"
    )
    options = next(args[0] for _, slot, args in native.calls if slot == 9)
    assert options & 0x20
    assert options & 0x40
    assert options & 0x800
    assert options & 0x100000
    assert not options & 0x200
    assert next(args for _, slot, args in native.calls if slot == 3) == (12345,)
    assert next(args for _, slot, args in native.calls if slot == 17) == ("选择目录",)
    native.shell.SHCreateItemFromParsingName.assert_called_once()
    assert [(pointer, slot) for pointer, slot, _ in native.calls if slot == 2] == [
        (33, 2),
        (22, 2),
        (11, 2),
    ]
    native.ole.CoTaskMemFree.assert_called_once()
    native.ole.CoUninitialize.assert_called_once_with()


@pytest.mark.parametrize("cancelled", [True, False])
def test_cancel_and_errors_release_dialog_without_reading_selection(native, cancelled):
    def invoke(pointer, slot, argtypes=(), *args):
        if slot == 3:
            return dialogs._CANCELLED if cancelled else -2147467259
        return native.dispatch(pointer, slot, argtypes, *args)

    native.invoke.side_effect = invoke
    if cancelled:
        assert dialogs._show_windows_folder(123, "", "fixture") is None
    else:
        with pytest.raises(OSError, match="80004005"):
            dialogs._show_windows_folder(123, "", "fixture")
    assert not any(slot == 20 for _, slot, _ in native.calls)
    assert (11, 2) in [(pointer, slot) for pointer, slot, _ in native.calls]
    native.ole.CoTaskMemFree.assert_not_called()
    native.ole.CoUninitialize.assert_called_once()


@pytest.mark.parametrize("slot", [9, 12, 20, 5])
def test_native_failures_release_all_previously_acquired_resources(
    native, tmp_path, slot
):
    def invoke(pointer, current, argtypes=(), *args):
        if current == slot:
            return -2147467259
        return native.dispatch(pointer, current, argtypes, *args)

    native.invoke.side_effect = invoke
    with pytest.raises(OSError, match="80004005"):
        dialogs._show_windows_folder(123, str(tmp_path), "fixture")
    released = [pointer for pointer, current, _ in native.calls if current == 2]
    assert 11 in released
    if slot != 9:
        assert 22 in released
    if slot == 5:
        assert 33 in released
    native.ole.CoUninitialize.assert_called_once()


def test_failed_com_initialization_is_not_uninitialized(native):
    native.ole.CoInitializeEx.return_value = -2147417850
    with pytest.raises(OSError):
        dialogs._show_windows_folder(123, "", "fixture")
    native.ole.CoCreateInstance.assert_not_called()
    native.ole.CoUninitialize.assert_not_called()


def test_missing_initial_directory_uses_shell_default(native, tmp_path):
    dialogs._show_windows_folder(123, str(tmp_path / "missing"), "fixture")
    native.shell.SHCreateItemFromParsingName.assert_not_called()


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_other_platforms_keep_pywebview_selection(monkeypatch, platform):
    import webview

    monkeypatch.setattr(dialogs.sys, "platform", platform)
    window = Mock()
    assert (
        dialogs.choose_directory(window, "/data")
        is window.create_file_dialog.return_value
    )
    window.create_file_dialog.assert_called_once_with(
        dialog_type=webview.FileDialog.FOLDER, directory="/data"
    )


@pytest.mark.parametrize("invoke_required", [False, True])
@pytest.mark.parametrize("selection", [None, "C:\\选择目录"])
def test_windows_dialog_runs_on_owning_ui_thread(
    monkeypatch, invoke_required, selection
):
    monkeypatch.setattr(dialogs.sys, "platform", "win32")
    # Verify dispatch without loading Windows DLLs, including on Linux CI.
    monkeypatch.delattr(ctypes, "WinDLL", raising=False)
    form = Mock(InvokeRequired=invoke_required)
    form.Invoke.side_effect = lambda callback: callback()
    monkeypatch.setitem(
        sys.modules,
        "arknights_mower.utils.windows_frameless",
        SimpleNamespace(
            _winforms_window=lambda window: form,
            _winforms_hwnd=lambda window: 987,
        ),
    )
    show = Mock(return_value=selection)
    monkeypatch.setattr(dialogs, "_show_windows_folder", show)
    delegate = Mock()
    delegate.__getitem__ = Mock(return_value=lambda callback: callback)
    monkeypatch.setitem(
        sys.modules, "System", SimpleNamespace(Func=delegate, String=str)
    )
    assert dialogs.choose_directory(Mock(), "C:\\data", "fixture") == selection
    show.assert_called_once_with(987, "C:\\data", "fixture")
    assert form.Invoke.call_count == int(invoke_required)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows shell COM smoke test")
@pytest.mark.parametrize("cancelled", [False, True])
def test_windows_native_com_marshalling_without_displaying_a_window(
    monkeypatch, tmp_path, cancelled
):
    tmp_path = tmp_path / "folder 目录"
    tmp_path.mkdir()
    invoke = dialogs._invoke
    libraries = dialogs._windows_libraries()

    def without_ui(pointer, slot, argtypes=(), *args):
        if slot == 3:
            return dialogs._CANCELLED if cancelled else 0
        if slot == 20:
            return libraries[1].SHCreateItemFromParsingName(
                str(tmp_path), None, ctypes.byref(dialogs._I_SHELL_ITEM), args[0]
            )
        return invoke(pointer, slot, argtypes, *args)

    monkeypatch.setattr(dialogs, "_invoke", without_ui)
    monkeypatch.setattr(dialogs, "_windows_libraries", lambda: libraries)
    result = Future()

    def run():
        try:
            result.set_result(dialogs._show_windows_folder(0, str(tmp_path), "fixture"))
        except Exception as error:
            result.set_exception(error)

    thread = Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout=10)
    assert not thread.is_alive()
    selected = result.result(timeout=1)
    assert selected is None if cancelled else str(tmp_path) == selected
