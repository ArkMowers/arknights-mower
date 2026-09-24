import { afterEach, describe, expect, it, vi } from 'vitest'
import { createWindowShellAdapter } from './adapter.js'

// These mirror the bridge contract the Python side serves via get_platform();
// the adapter must agree with whatever the backend reports, not with these.
const PROTOCOL = 'mower-window-shell-v1'
const EVENT = 'mower-window-state'

function makeBridge(platform = 'windows') {
  return {
    minimize: vi.fn(async () => true),
    maximize: vi.fn(async () => true),
    restore: vi.fn(async () => true),
    close: vi.fn(async () => true),
    start_move: vi.fn(async () => true),
    start_resize: vi.fn(async () => true),
    get_platform: vi.fn(async () => ({ protocol: PROTOCOL, event: EVENT, platform })),
    get_window_state: vi.fn(async () => ({
      protocol: PROTOCOL,
      state: 'normal',
      maximized: false,
      minimized: false,
      width: 1450,
      height: 850
    }))
  }
}

function makeWindow() {
  const windowObject = new EventTarget()
  windowObject.location = { search: '?window_shell=1' }
  return windowObject
}

describe('window shell adapter', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('leaves a normal browser inactive with no user-agent guessing', async () => {
    const browserWindow = makeWindow()
    browserWindow.location.search = ''
    const adapter = createWindowShellAdapter({ windowObject: browserWindow, readyTimeoutMs: 5 })

    await expect(adapter.initialize()).resolves.toBe(false)
    expect(adapter.active.value).toBe(false)
    expect(adapter.controls.value).toEqual([])
  })

  it('rejects a matching-looking bridge without the Python desktop marker', async () => {
    const browserWindow = makeWindow()
    browserWindow.location.search = ''
    browserWindow.pywebview = { api: makeBridge() }
    const adapter = createWindowShellAdapter({ windowObject: browserWindow })

    await expect(adapter.initialize()).resolves.toBe(false)
    expect(adapter.active.value).toBe(false)
  })

  it('waits for pywebviewready and activates only after validating the bridge contract', async () => {
    const desktopWindow = makeWindow()
    const bridge = makeBridge('windows')
    const adapter = createWindowShellAdapter({ windowObject: desktopWindow, readyTimeoutMs: 50 })
    const initializing = adapter.initialize()

    desktopWindow.pywebview = { api: bridge }
    desktopWindow.dispatchEvent(new Event('pywebviewready'))

    await expect(initializing).resolves.toBe(true)
    expect(adapter.active.value).toBe(true)
    expect(adapter.controlSide.value).toBe('end')
    expect(adapter.controls.value.map((control) => control.id)).toEqual([
      'minimize',
      'maximize',
      'close'
    ])
  })

  it('centralizes macOS control placement and ordering', async () => {
    const desktopWindow = makeWindow()
    desktopWindow.pywebview = { api: makeBridge('macos') }
    const adapter = createWindowShellAdapter({ windowObject: desktopWindow })

    await adapter.initialize()

    expect(adapter.controlSide.value).toBe('start')
    expect(adapter.controls.value.map((control) => control.id)).toEqual([
      'close',
      'minimize',
      'maximize'
    ])
  })

  it('uses native events rather than command success to change the maximize control', async () => {
    const desktopWindow = makeWindow()
    const bridge = makeBridge()
    desktopWindow.pywebview = { api: bridge }
    const adapter = createWindowShellAdapter({ windowObject: desktopWindow })
    await adapter.initialize()

    await adapter.maximize()
    expect(adapter.state.value.maximized).toBe(false)
    expect(adapter.controls.value[1].icon).toBe('maximize')

    desktopWindow.dispatchEvent(
      new CustomEvent(EVENT, {
        detail: {
          protocol: PROTOCOL,
          state: 'maximized',
          maximized: true,
          minimized: false,
          width: 1920,
          height: 1040
        }
      })
    )

    expect(adapter.state.value.maximized).toBe(true)
    expect(adapter.controls.value[1].icon).toBe('restore')
    bridge.get_window_state.mockResolvedValue({
      protocol: PROTOCOL,
      state: 'maximized',
      maximized: true,
      minimized: false,
      width: 1920,
      height: 1040
    })
    await adapter.toggleMaximize()
    expect(bridge.restore).toHaveBeenCalledOnce()
    adapter.dispose()
  })

  it('checks real state before clicking if the initial maximize event was missed', async () => {
    const desktopWindow = makeWindow()
    const bridge = makeBridge()
    const maximizedState = {
      protocol: PROTOCOL,
      state: 'maximized',
      maximized: true,
      minimized: false,
      width: 1920,
      height: 1040
    }
    bridge.get_window_state
      .mockResolvedValueOnce({
        protocol: PROTOCOL,
        state: 'normal',
        maximized: false,
        minimized: false,
        width: 1450,
        height: 850
      })
      .mockResolvedValue(maximizedState)
    desktopWindow.pywebview = { api: bridge }
    const adapter = createWindowShellAdapter({ windowObject: desktopWindow })
    await adapter.initialize()
    expect(adapter.state.value.maximized).toBe(false)

    await adapter.toggleMaximize()
    expect(bridge.restore).toHaveBeenCalledOnce()
    expect(bridge.maximize).not.toHaveBeenCalled()
    adapter.dispose()
  })

  it('fails a control call safely without dropping the shell', async () => {
    const desktopWindow = makeWindow()
    const bridge = makeBridge()
    bridge.close.mockRejectedValue(new Error('bridge unavailable'))
    desktopWindow.pywebview = { api: bridge }
    const adapter = createWindowShellAdapter({ windowObject: desktopWindow })
    await adapter.initialize()

    await expect(adapter.close()).resolves.toBe(false)
    expect(adapter.busy.value.close).toBe(false)
    expect(adapter.active.value).toBe(true)
  })

  it('keeps the title bar up when the injected bridge is not the desktop shell', async () => {
    // A frameless window whose title bar hides itself has no controls and no way
    // back, so a bridge we refuse costs the controls and nothing else.
    const desktopWindow = makeWindow()
    const refused = makeBridge('unknown')
    desktopWindow.pywebview = { api: refused }
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const adapter = createWindowShellAdapter({ windowObject: desktopWindow, readyTimeoutMs: 50 })

    await expect(adapter.initialize()).resolves.toBe(false)
    expect(adapter.active.value).toBe(true)
    expect(adapter.connected.value).toBe(false)
    expect(adapter.controls.value.map((control) => control.id)).toEqual([
      'minimize',
      'maximize',
      'close'
    ])
    expect(adapter.controls.value.every((control) => control.disabled)).toBe(true)
    expect(warn).toHaveBeenCalled()

    // The refused bridge is not asked again on every poll tick...
    const asked = refused.get_platform.mock.calls.length
    await new Promise((resolve) => setTimeout(resolve, 150))
    expect(refused.get_platform).toHaveBeenCalledTimes(asked)

    // ...nor by a later readiness signal.
    desktopWindow.dispatchEvent(new Event('focus'))
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(refused.get_platform).toHaveBeenCalledTimes(asked)

    // A replacement bridge is still picked up, and the controls come alive with it.
    desktopWindow.pywebview = { api: makeBridge('windows') }
    desktopWindow.dispatchEvent(new Event('focus'))
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(adapter.connected.value).toBe(true)
    expect(adapter.active.value).toBe(true)
    expect(adapter.controls.value.some((control) => !control.disabled)).toBe(true)

    warn.mockRestore()
    adapter.dispose()
  })

  it('keeps polling when the bridge answers with a state it cannot read yet', async () => {
    const desktopWindow = makeWindow()
    const bridge = makeBridge()
    bridge.get_window_state.mockResolvedValueOnce({
      protocol: PROTOCOL,
      state: 'starting',
      maximized: false,
      minimized: false,
      width: Number.NaN,
      height: Number.NaN
    })
    desktopWindow.pywebview = { api: bridge }
    const adapter = createWindowShellAdapter({ windowObject: desktopWindow, readyTimeoutMs: 50 })
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})

    await expect(adapter.initialize()).resolves.toBe(false)
    expect(adapter.connected.value).toBe(false)

    // An unreadable state is not a wrong contract: the same bridge keeps its
    // remaining poll budget instead of being written off.
    await new Promise((resolve) => setTimeout(resolve, 250))
    expect(adapter.connected.value).toBe(true)
    expect(adapter.active.value).toBe(true)

    warn.mockRestore()
    adapter.dispose()
  })

  it('delegates valid resize edges to the native window frame', async () => {
    const desktopWindow = makeWindow()
    const bridge = makeBridge()
    desktopWindow.pywebview = { api: bridge }
    const adapter = createWindowShellAdapter({ windowObject: desktopWindow })
    await adapter.initialize()

    await expect(adapter.startResize('bottom-right')).resolves.toBe(true)
    await expect(adapter.startResize('unexpected')).resolves.toBe(false)
    expect(bridge.start_resize).toHaveBeenCalledOnce()
    expect(bridge.start_resize).toHaveBeenCalledWith('bottom-right')
  })

  it('reports a title bar drag as started without waiting for the drag to end', async () => {
    const desktopWindow = makeWindow()
    const bridge = makeBridge()
    // The shell's move loop holds the mouse until the button comes up, so the
    // bridge call settles only after the user lets go.
    let finishDrag
    bridge.start_move = vi.fn(
      () =>
        new Promise((resolve) => {
          finishDrag = resolve
        })
    )
    desktopWindow.pywebview = { api: bridge }
    const adapter = createWindowShellAdapter({ windowObject: desktopWindow })
    await adapter.initialize()

    await expect(adapter.startMove()).resolves.toBe(true)
    expect(bridge.start_move).toHaveBeenCalledOnce()
    finishDrag(true)
  })

  it('still reports the handover when the shell refuses the drag', async () => {
    // A refused handover must not turn into an unhandled rejection: the drag is
    // already gone at that point, so the only thing left to do is say so.
    const desktopWindow = makeWindow()
    const bridge = makeBridge()
    bridge.start_move = vi.fn(async () => {
      throw new Error('no move loop here')
    })
    desktopWindow.pywebview = { api: bridge }
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const adapter = createWindowShellAdapter({ windowObject: desktopWindow })
    await adapter.initialize()

    await expect(adapter.startMove()).resolves.toBe(true)
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(warn).toHaveBeenCalled()
    warn.mockRestore()
  })

  it('reports a drag the bridge could not even start', async () => {
    // A synchronous throw means nothing owns the drag, so this is a refusal and
    // not a handover -- and it must not escape as an unhandled rejection.
    const desktopWindow = makeWindow()
    const bridge = makeBridge()
    bridge.start_move = vi.fn(() => {
      throw new Error('bridge is gone')
    })
    desktopWindow.pywebview = { api: bridge }
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const adapter = createWindowShellAdapter({ windowObject: desktopWindow })
    await adapter.initialize()

    await expect(adapter.startMove()).resolves.toBe(false)
    expect(warn).toHaveBeenCalled()
    warn.mockRestore()
  })

  it('keeps the shell usable when the backend cannot drag the window', async () => {
    // A missing start_move costs the drag and nothing else. Rejecting the whole
    // contract instead would leave a frameless window with no title bar, no
    // controls and no way to move it, so the shell comes up and names the gap.
    const desktopWindow = makeWindow()
    const bridge = makeBridge()
    delete bridge.start_move
    desktopWindow.pywebview = { api: bridge }
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const adapter = createWindowShellAdapter({ windowObject: desktopWindow })

    await expect(adapter.initialize()).resolves.toBe(true)
    expect(adapter.active.value).toBe(true)
    expect(adapter.controls.value).toHaveLength(3)
    await expect(adapter.startMove()).resolves.toBe(false)
    expect(warn).toHaveBeenCalled()
    warn.mockRestore()
  })

  it('keeps the title bar up and connects when the bridge lands after the 1200ms readiness timeout', async () => {
    vi.useFakeTimers()
    const desktopWindow = makeWindow()
    const bridge = makeBridge('windows')
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const adapter = createWindowShellAdapter({ windowObject: desktopWindow })

    // The bar is usable from the first frame; only the controls wait for the bridge.
    expect(adapter.active.value).toBe(true)
    expect(adapter.connected.value).toBe(false)
    expect(adapter.controls.value[0].disabled).toBe(true)

    const initializing = adapter.initialize()
    await vi.advanceTimersByTimeAsync(1500)
    await expect(initializing).resolves.toBe(false)
    expect(adapter.active.value).toBe(true)
    expect(adapter.connected.value).toBe(false)
    expect(warn).toHaveBeenCalled()

    // WebView2 injects the bridge late, with no event to announce it: the
    // background poll is the only thing that can notice.
    desktopWindow.pywebview = { api: bridge }
    await vi.advanceTimersByTimeAsync(500)

    expect(adapter.connected.value).toBe(true)
    expect(adapter.active.value).toBe(true)
    expect(adapter.controls.value[0].disabled).toBe(false)
    await expect(adapter.minimize()).resolves.toBe(true)
    expect(bridge.minimize).toHaveBeenCalledOnce()

    warn.mockRestore()
    adapter.dispose()
  })

  it('stops polling a missing bridge after a minute, and a readiness signal still connects it', async () => {
    vi.useFakeTimers()
    const desktopWindow = makeWindow()
    const bridge = makeBridge()
    const adapter = createWindowShellAdapter({ windowObject: desktopWindow })

    await vi.advanceTimersByTimeAsync(59000)
    expect(adapter.connected.value).toBe(false)

    // Just inside the poll window, the poll still finds it.
    desktopWindow.pywebview = { api: bridge }
    await vi.advanceTimersByTimeAsync(1000)
    expect(adapter.connected.value).toBe(true)
    adapter.dispose()

    // Past the window there is no poll left to fire, so only an event connects.
    const lateWindow = makeWindow()
    const lateBridge = makeBridge()
    const lateAdapter = createWindowShellAdapter({ windowObject: lateWindow })
    await vi.advanceTimersByTimeAsync(61000)
    expect(lateAdapter.connected.value).toBe(false)

    lateWindow.pywebview = { api: lateBridge }
    await vi.advanceTimersByTimeAsync(2000)
    expect(lateAdapter.connected.value).toBe(false)

    lateWindow.dispatchEvent(new Event('focus'))
    await vi.advanceTimersByTimeAsync(20)
    expect(lateAdapter.connected.value).toBe(true)
    lateAdapter.dispose()
  })

  it('validates the bridge once when several readiness signals land in the same frame', async () => {
    const desktopWindow = makeWindow()
    const bridge = makeBridge()
    desktopWindow.pywebview = { api: bridge }
    const adapter = createWindowShellAdapter({ windowObject: desktopWindow, readyTimeoutMs: 50 })

    const initializing = adapter.initialize()
    desktopWindow.dispatchEvent(new Event('pywebviewready'))
    desktopWindow.dispatchEvent(new Event('focus'))
    desktopWindow.dispatchEvent(new Event('resize'))

    await expect(initializing).resolves.toBe(true)
    expect(bridge.get_platform).toHaveBeenCalledOnce()
    expect(bridge.get_window_state).toHaveBeenCalledOnce()
    adapter.dispose()
  })

  it('stops waiting for a bridge as soon as the adapter is disposed', async () => {
    vi.useFakeTimers()
    const desktopWindow = makeWindow()
    const adapter = createWindowShellAdapter({ windowObject: desktopWindow })
    const initializing = adapter.initialize()

    adapter.dispose()

    // Timers are frozen here, so this only settles because dispose released it.
    await expect(initializing).resolves.toBe(false)
    expect(adapter.active.value).toBe(false)

    desktopWindow.pywebview = { api: makeBridge() }
    desktopWindow.dispatchEvent(new Event('focus'))
    await vi.advanceTimersByTimeAsync(1000)
    expect(adapter.connected.value).toBe(false)
  })
})
