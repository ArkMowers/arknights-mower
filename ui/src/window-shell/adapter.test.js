import { describe, expect, it, vi } from 'vitest'
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
    await adapter.toggleMaximize()
    expect(bridge.restore).toHaveBeenCalledOnce()
  })

  it('degrades safely when bridge validation or a control call fails', async () => {
    const invalidWindow = makeWindow()
    invalidWindow.pywebview = { api: makeBridge('unknown') }
    const invalidAdapter = createWindowShellAdapter({ windowObject: invalidWindow })
    await expect(invalidAdapter.initialize()).resolves.toBe(false)
    expect(invalidAdapter.active.value).toBe(false)

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
})
