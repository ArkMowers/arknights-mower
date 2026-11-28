import { computed, watch } from 'vue'

export const interfaceZoomLimits = { min: 0.5, max: 3, step: 0.25 }

const zoomBindings = {
  'zoom-in': { label: '=', codes: ['Equal', 'NumpadAdd'], keys: ['=', '+'] },
  'zoom-out': { label: '-', codes: ['Minus', 'NumpadSubtract'], keys: ['-'] },
  'actual-size': { label: '0', codes: ['Digit0', 'Numpad0'], keys: ['0'] }
}

export function interfaceZoomShortcuts(platform) {
  const prefix = platform === 'macos' ? 'Cmd+' : 'Ctrl+'
  return Object.fromEntries(
    Object.entries(zoomBindings).map(([action, binding]) => [action, prefix + binding.label])
  )
}

export function useInterfaceZoom(webview, desktopConnected, platform, loaded) {
  const { min, max, step } = interfaceZoomLimits
  const scale = computed(() => {
    const savedScale = Number(webview.value?.scale)
    return Number.isFinite(savedScale) && savedScale > 0 ? savedScale : 1
  })
  const available = computed(() => Boolean(loaded.value && webview.value))
  const canZoomIn = computed(() => available.value && scale.value < max)
  const canZoomOut = computed(() => available.value && scale.value > min)
  const canResetZoom = computed(() => available.value && scale.value !== 1)

  function changeZoom(action) {
    if (action === 'zoom-in' && canZoomIn.value) {
      const next = (Math.floor(scale.value / step) + 1) * step
      webview.value.scale = Math.max(min, Math.min(max, next))
    } else if (action === 'zoom-out' && canZoomOut.value) {
      const next = (Math.ceil(scale.value / step) - 1) * step
      webview.value.scale = Math.max(min, Math.min(max, next))
    } else if (action === 'actual-size' && canResetZoom.value) {
      webview.value.scale = 1
    }
  }

  function handleShortcut(event) {
    if (event.defaultPrevented || event.isComposing || event.altKey) return
    if (
      platform.value === 'macos' ? !event.metaKey || event.ctrlKey : !event.ctrlKey || event.metaKey
    )
      return
    const action = Object.keys(zoomBindings).find((action) => {
      const { codes, keys } = zoomBindings[action]
      if (event.shiftKey && action !== 'zoom-in') return false
      return codes.includes(event.code) || keys.includes(event.key)
    })
    if (!action) return
    event.preventDefault()
    changeZoom(action)
  }

  watch(
    desktopConnected,
    (connected, _previous, onCleanup) => {
      const window = globalThis.window
      if (!connected || !window) return
      window.addEventListener('keydown', handleShortcut)
      onCleanup(() => window.removeEventListener('keydown', handleShortcut))
    },
    { immediate: true, flush: 'sync' }
  )

  return { changeZoom, canZoomIn, canZoomOut, canResetZoom }
}
