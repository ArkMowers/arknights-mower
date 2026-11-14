import { afterEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'
import { interfaceZoomShortcuts, useInterfaceZoom } from './interfaceZoom'

let scope

afterEach(() => {
  scope?.stop()
  vi.unstubAllGlobals()
})

function setup({ scale = 1, desktop = false, platform = 'windows', loaded = true } = {}) {
  const window = new EventTarget()
  vi.stubGlobal('window', window)
  const webview = ref({ scale, tray: true })
  const desktopConnected = ref(desktop)
  const ready = ref(loaded)
  scope = effectScope()
  const zoom = scope.run(() => useInterfaceZoom(webview, desktopConnected, ref(platform), ready))

  function keydown(key, modifiers = {}) {
    const event = Object.assign(new Event('keydown', { cancelable: true }), { key, ...modifiers })
    window.dispatchEvent(event)
    return event
  }

  return { ...zoom, webview, desktopConnected, ready, keydown }
}

describe('interface zoom', () => {
  it('uses the settings scale steps and preserves the other window settings', () => {
    const zoom = setup({ scale: 1.15 })

    zoom.changeZoom('zoom-in')
    expect(zoom.webview.value).toEqual({ scale: 1.25, tray: true })
    zoom.changeZoom('zoom-out')
    zoom.changeZoom('zoom-out')
    expect(zoom.webview.value.scale).toBe(0.75)
    zoom.changeZoom('actual-size')
    expect(zoom.webview.value.scale).toBe(1)
    expect(zoom.canResetZoom.value).toBe(false)
  })

  it.each([
    { scale: 0.5, action: 'zoom-out', availability: 'canZoomOut' },
    { scale: 3, action: 'zoom-in', availability: 'canZoomIn' }
  ])('stops $action at the $scale scale limit', ({ scale, action, availability }) => {
    const zoom = setup({ scale })
    expect(zoom[availability].value).toBe(false)
    zoom.changeZoom(action)
    expect(zoom.webview.value.scale).toBe(scale)
  })

  it('handles shortcuts only while connected to the desktop bridge', () => {
    const zoom = setup()
    expect(zoom.keydown('+', { ctrlKey: true, shiftKey: true }).defaultPrevented).toBe(false)

    zoom.desktopConnected.value = true
    expect(zoom.keydown('+', { ctrlKey: true, shiftKey: true }).defaultPrevented).toBe(true)
    expect(zoom.webview.value.scale).toBe(1.25)
    zoom.keydown('-', { ctrlKey: true })
    expect(zoom.webview.value.scale).toBe(1)
    zoom.keydown('=', { ctrlKey: true })
    expect(zoom.webview.value.scale).toBe(1.25)
    zoom.keydown('0', { ctrlKey: true })
    expect(zoom.webview.value.scale).toBe(1)

    zoom.desktopConnected.value = false
    expect(zoom.keydown('+', { ctrlKey: true, shiftKey: true }).defaultPrevented).toBe(false)

    zoom.desktopConnected.value = true
    scope.stop()
    expect(zoom.keydown('+', { ctrlKey: true, shiftKey: true }).defaultPrevented).toBe(false)
    expect(zoom.webview.value.scale).toBe(1)
  })

  it('uses Command on macOS and ignores composing and Alt shortcuts', () => {
    const zoom = setup({ desktop: true, platform: 'macos' })
    expect(zoom.keydown('=', { ctrlKey: true }).defaultPrevented).toBe(false)
    expect(zoom.keydown('=', { metaKey: true, altKey: true }).defaultPrevented).toBe(false)
    expect(zoom.keydown('=', { metaKey: true, isComposing: true }).defaultPrevented).toBe(false)
    expect(zoom.webview.value.scale).toBe(1)
    expect(zoom.keydown('=', { metaKey: true }).defaultPrevented).toBe(true)
    expect(zoom.webview.value.scale).toBe(1.25)
  })

  it.each([
    ['windows', { ctrlKey: true }, 'Ctrl+'],
    ['linux', { ctrlKey: true }, 'Ctrl+'],
    ['macos', { metaKey: true }, 'Cmd+']
  ])('uses the menu key combinations on %s', (platform, modifier, label) => {
    const zoom = setup({ desktop: true, platform })
    expect(interfaceZoomShortcuts(platform)).toEqual({
      'zoom-in': `${label}=`,
      'zoom-out': `${label}-`,
      'actual-size': `${label}0`
    })

    zoom.keydown('=', { ...modifier, code: 'Equal' })
    expect(zoom.webview.value.scale).toBe(1.25)
    expect(zoom.keydown('_', { ...modifier, code: 'Minus', shiftKey: true }).defaultPrevented).toBe(
      false
    )
    zoom.keydown('−', { ...modifier, code: 'Minus' })
    expect(zoom.webview.value.scale).toBe(1)
    zoom.keydown('Unidentified', { ...modifier, code: 'Equal', shiftKey: true })
    expect(zoom.webview.value.scale).toBe(1.25)
    zoom.keydown('0', { ...modifier, code: 'Digit0' })
    expect(zoom.webview.value.scale).toBe(1)
    zoom.keydown('+', { ...modifier, code: 'NumpadAdd' })
    zoom.keydown('+', { ...modifier, code: 'NumpadAdd' })
    zoom.keydown('−', { ...modifier, code: 'NumpadSubtract' })
    expect(zoom.webview.value.scale).toBe(1.25)
    zoom.keydown('à', { ...modifier, code: 'Digit0' })
    expect(zoom.webview.value.scale).toBe(1)
  })

  it('waits for saved settings before letting menu actions or shortcuts change the scale', () => {
    const zoom = setup({ desktop: true, loaded: false })
    expect(zoom.canZoomOut.value).toBe(false)
    zoom.changeZoom('zoom-out')
    zoom.keydown('-', { ctrlKey: true })
    expect(zoom.webview.value.scale).toBe(1)

    zoom.webview.value = { scale: 1.5 }
    zoom.ready.value = true
    zoom.keydown('-', { ctrlKey: true })
    expect(zoom.webview.value.scale).toBe(1.25)
  })
})
