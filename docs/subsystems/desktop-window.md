# Desktop Window

The desktop entry in [`webview_ui.py`](../../webview_ui.py) owns window creation, startup mode and saved size. [`WindowShellBridge`](../../arknights_mower/utils/window_shell.py) connects the shared Vue title bar to WinForms, Cocoa, GTK or Qt. The ordinary browser page has no desktop title bar.

## Backend selection and capabilities

The entry selects the pywebview backend before choosing frameless behavior. WinForms keeps its existing Win32 input and DPI handling. Cocoa, GTK and Qt install native input handlers after the native window exists; bridge readiness waits for that installation. Unknown backends retain native window decorations.

The bridge reports whether the title bar is enabled, whether movement uses the JavaScript bridge or native input, and whether resizing uses HTML grips or native edges. The frontend uses those capabilities instead of inferring behavior from the operating-system name. Protocol-v1 bridges without capabilities retain their existing frontend behavior.

## Native input ownership

For Cocoa, GTK and Qt, Vue sends a bounded viewport snapshot containing the draggable title-bar rectangles and any HTML resize grips. Control buttons and page content remain outside those rectangles. Invalid snapshots clear earlier regions; a snapshot for a different viewport size cannot capture input while layout is changing. Corners and resize edges take precedence over dragging.

Native handlers use the original input event on the GUI thread. GTK preserves the input device, button, root coordinates and timestamp; Qt requests system movement and resizing; Cocoa hands dragging to NSWindow and retains its native resizable edges. A double click on the title bar toggles maximization. Native input does not also trigger the JavaScript drag or maximize handler.

GUI dispatch has a finite wait. Timed-out pending user operations are cancelled. Closing the window unregisters native handlers; cleanup already queued on an unavailable GUI thread remains eligible to run when that thread resumes. Native state callbacks signal one background publisher rather than evaluating JavaScript synchronously on the GUI thread.

## State and normal window size

Maximization and restoration use each backend's native operations. Cocoa maximization uses the current screen's visible frame and retains the earlier normal frame; ordinary maximization does not enter fullscreen. GTK explicitly unmaximizes, and Qt restores its normal state. A native fullscreen window is treated as maximized, and restoration exits fullscreen.

Native state is authoritative for button state and size persistence. Startup, closing, minimized and maximized resize samples do not replace normal dimensions. When a native query fails, the cached state remains available for display but cannot authorize size or mode persistence. The saved startup mode is applied only after the backend is ready. Non-WinForms backends check current confirmed state for each size sample, independently of coalesced state notifications. Screen proportions use an available work area rather than a whole-screen estimate; if that area cannot be read, the existing saved proportion is retained. WinForms alone performs the Windows DPI conversion.

## Failure behavior

When native input installation or a reported system operation fails, the adapter attempts to restore native decorations. The frontend hides its title bar only after restoration succeeds and the bridge reports the disabled capability. If restoring decorations also fails, the custom controls stay visible and the shared logger records the failure. Qt versions without system move and resize support use this same recovery path.

## Focused verification

From the repository root, run:

```bash
python -m pytest arknights_mower/tests/window_state_tests.py arknights_mower/tests/window_frameless_tests.py arknights_mower/tests/window_regions_tests.py arknights_mower/tests/window_backend_tests.py arknights_mower/tests/window_shell_platform_tests.py arknights_mower/tests/cocoa_window_tests.py arknights_mower/tests/linux_window_tests.py arknights_mower/tests/webview_ui_tests.py
```

From `ui/`, run:

```bash
npm test -- src/window-shell/adapter.test.js src/window-shell/hit-regions.test.js
```

Offline tests exercise bridge calls, native substitutes, state, saved proportions and cleanup. They do not establish real Cocoa, GTK or Qt event delivery. Native acceptance requires dragging, edge and corner resizing, double-click maximization, restoration, mixed display scaling, closing and tray reopening on macOS and Linux X11/Wayland. GTK window-manager cooperation and Qt platform-plugin support remain platform-dependent.
