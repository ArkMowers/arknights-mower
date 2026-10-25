# Desktop Window

The desktop entry in [`webview_ui.py`](../../webview_ui.py) owns window creation, startup mode and saved size. [`WindowShellBridge`](../../arknights_mower/utils/window_shell.py) connects the shared Vue title bar to WinForms, Cocoa, GTK or Qt. The ordinary browser page has no desktop title bar.

## Backend selection and capabilities

The entry selects the pywebview backend before choosing frameless behavior. WinForms keeps its existing Win32 input and DPI handling. Cocoa, GTK and Qt install native input handlers after the native window exists; bridge readiness waits for that installation. Unknown backends retain native window decorations.

The bridge reports whether the title bar is enabled, whether movement uses the JavaScript bridge or native input, and whether resizing uses HTML grips or native edges. The frontend uses those capabilities instead of inferring behavior from the operating-system name. Protocol-v1 bridges without capabilities retain their existing frontend behavior.

Cocoa keeps the system red, yellow and green window buttons, including native hover and zoom/fullscreen behavior. Their native size and spacing are preserved, with the native titlebar container inset from the left and aligned with the content in the shared 36-point title bar; resize and move notifications reapply that placement after AppKit finishes its layout pass. The Vue title bar reserves space on the left and omits duplicate HTML controls when the bridge reports native controls. In that mode, the title bar compensates for page zoom so its height and native-button reservation retain their logical size. GTK and Qt keep neutral minimize, maximize and close glyphs in their custom title bar; Linux desktop themes do not share one traffic-light convention. These HTML controls do not inherit the window manager's theme or configured button order.

Managed instance windows close directly and leave the instance running under the multi-instance manager. They do not offer a separate tray or apply the standalone close preference. The manager remains responsible for reopening the window or stopping the instance.

For standalone windows, Cocoa's native close request opens the same frontend close choice as an HTML close button. Cancelling or deferring that choice keeps the window and normal-size tracking active. A confirmed close or supervisor exit proceeds directly. Native requests received before the page is ready wait until the frontend installs its close listener and confirms readiness. The listener acknowledges each delivered close event synchronously; a missing listener after page reload or a failed dispatch retains the request for the next readiness confirmation or native close request, without polling. Closing the window prevents further delivery.

## Native input ownership

For Cocoa, GTK and Qt, Vue sends a bounded viewport snapshot containing the draggable title-bar rectangles and any HTML resize grips. Control buttons and page content remain outside those rectangles. Invalid snapshots clear earlier regions; a snapshot for a different viewport size cannot capture input while layout is changing. Corners and resize edges take precedence over dragging.

Native handlers use the original input event on the GUI thread. GTK preserves the input device, button, root coordinates and timestamp; Qt requests system movement and resizing; Cocoa hands dragging to NSWindow and retains its native resizable edges. A double click on the title bar toggles maximization. Native input does not also trigger the JavaScript drag or maximize handler.

GUI dispatch has a finite wait. Timed-out pending user operations are cancelled. Closing the window unregisters native handlers; cleanup already queued on an unavailable GUI thread remains eligible to run when that thread resumes. Native state callbacks signal one background publisher rather than evaluating JavaScript synchronously on the GUI thread.

Cocoa releases its input monitor and observers on the native GUI thread before the window closes. After a macOS GUI helper completes normally, its target finalizers and command and logging channels finish cleanup before the helper process exits. A pywebview response still waiting for a destroyed page cannot retain that completed helper process.

## State and normal window size

Maximization and restoration use each backend's native operations. Cocoa maximization uses the current screen's visible frame and retains the earlier normal frame; ordinary maximization does not enter fullscreen. GTK explicitly unmaximizes, and Qt restores its normal state. A native fullscreen window is treated as maximized, and restoration exits fullscreen.

Native state is authoritative for button state and size persistence. Startup, closing, minimized and maximized resize samples do not replace normal dimensions. When a native query fails, the cached state remains available for display but cannot authorize size or mode persistence. A maximized startup first appears maximized: GTK and Qt receive the mode at creation; WinForms and Cocoa stay hidden until normal-frame calibration and native initialization allow maximization before display. An early manager show request waits for that display, and a confirmed close during initialization keeps the window closed. If maximization fails, the initialized window still appears with usable controls. Non-WinForms backends read current normal state and geometry together on the GUI thread instead of pairing a new state with old resize-event dimensions. Size sampling and assignment are serialized across event threads, and a sample that completes during closing is discarded. Screen proportions use an available work area rather than a whole-screen estimate; if that area cannot be read, the existing saved proportion is retained. WinForms alone performs the Windows DPI conversion.

## Instance GUI preference storage

The current instance's `config/gui.yml` stores native window mode, screen proportions,
launch mode and close preference together with `mood_board` and `log_layout`.
`mood_board.hiddenLines` and `hiddenGroups` store excluded curves and groups;
`groupOrder`, `defaultOperators` and `views` store ordering and custom views.
Legend clicks, group visibility changes, ordering and saved views submit an
authenticated preference PATCH immediately. Browser local storage remains a fallback;
a failed server save displays the local-preference warning without claiming disk persistence.

The backend and native window process serialize read-modify-write operations through
one instance file lock, read the latest YAML inside that lock and commit atomically.
Malformed existing YAML or a failed write preserves the original file and reports an
error. Before the first preference read or write, missing UI keys are seeded from
the old installation-wide `ui-state.json` in the update cache. Existing GUI keys win.
`ui_state_migrated` marks completion for each instance. The old shared file remains
available to seed other instances; subsequent preference changes stay instance-local.
Configuration imports preserve local GUI preferences as specified by the
[backup contract](config-backup.md#2-import-boundary).

## Failure behavior

When native input installation or a reported system operation fails, the adapter attempts to restore native decorations. The frontend hides its title bar only after restoration succeeds and the bridge reports the disabled capability. A connected bridge still accepts confirmed close commands after the custom title bar is hidden. If restoring decorations also fails, the available native or custom controls stay visible and the shared logger records the failure. Qt versions without system move and resize support use this same recovery path.

A refused or timed-out hit-region update invalidates the frontend's acknowledgement cache. A later layout observation resubmits the measured snapshot even if it matches an earlier successful layout. Failure alone does not start repeated retries.

## Focused verification

From the repository root, run:

```bash
python -m pytest arknights_mower/tests/window_state_tests.py arknights_mower/tests/window_frameless_tests.py arknights_mower/tests/window_regions_tests.py arknights_mower/tests/window_backend_tests.py arknights_mower/tests/window_shell_platform_tests.py arknights_mower/tests/cocoa_window_tests.py arknights_mower/tests/linux_window_tests.py arknights_mower/tests/webview_ui_tests.py arknights_mower/tests/desktop_process_tests.py
```

From `ui/`, run:

```bash
npm test -- src/window-shell/adapter.test.js src/window-shell/hit-regions.test.js src/components/WindowTitlebar.test.js src/App.test.js
```

Offline tests exercise bridge calls, native substitutes, state, saved proportions and cleanup. They do not establish real Cocoa, GTK or Qt event delivery. Native acceptance requires dragging, edge and corner resizing, double-click maximization, restoration, mixed display scaling, closing and tray reopening on macOS and Linux X11/Wayland. GTK window-manager cooperation and Qt platform-plugin support remain platform-dependent.
