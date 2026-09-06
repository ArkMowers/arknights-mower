import { computed, ref } from 'vue'

export const WINDOW_RESIZE_EDGES = Object.freeze([
  'left',
  'right',
  'top',
  'bottom',
  'top-left',
  'top-right',
  'bottom-left',
  'bottom-right'
])

const VALID_PLATFORMS = new Set(['windows', 'macos', 'linux'])
const REQUIRED_METHODS = [
  'minimize',
  'maximize',
  'restore',
  'close',
  'start_resize',
  'get_window_state',
  'get_platform'
]
const CONTROL_METHODS = new Set(['minimize', 'maximize', 'restore', 'close'])
const RESIZE_EDGES = new Set(WINDOW_RESIZE_EDGES)

const NORMAL_STATE = Object.freeze({
  state: 'normal',
  maximized: false,
  minimized: false,
  width: 0,
  height: 0
})

function hasBridgeContract(api) {
  return Boolean(api && REQUIRED_METHODS.every((method) => typeof api[method] === 'function'))
}

function validState(state, protocol) {
  return Boolean(
    state &&
    state.protocol === protocol &&
    ['normal', 'maximized', 'minimized'].includes(state.state) &&
    typeof state.maximized === 'boolean' &&
    typeof state.minimized === 'boolean' &&
    Number.isFinite(state.width) &&
    Number.isFinite(state.height)
  )
}

function withTimeout(promise, timeoutMs) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('window shell bridge timed out')), timeoutMs)
    Promise.resolve(promise).then(
      (value) => {
        clearTimeout(timer)
        resolve(value)
      },
      (error) => {
        clearTimeout(timer)
        reject(error)
      }
    )
  })
}

function readBridge(windowObject) {
  return windowObject?.pywebview?.api
}

function waitForBridge(windowObject, timeoutMs) {
  const existing = readBridge(windowObject)
  if (hasBridgeContract(existing)) return Promise.resolve(existing)

  return new Promise((resolve) => {
    let settled = false
    const finish = (api) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      windowObject?.removeEventListener?.('pywebviewready', onReady)
      resolve(api)
    }
    const onReady = () => {
      const api = readBridge(windowObject)
      finish(hasBridgeContract(api) ? api : null)
    }
    const timer = setTimeout(() => finish(null), timeoutMs)
    windowObject?.addEventListener?.('pywebviewready', onReady, { once: true })
  })
}

export function readWindowShellMetadata(locationObject) {
  const params = new URLSearchParams(locationObject?.search || '')
  const bootstrapTheme = params.get('window_theme')
  return Object.freeze({
    requested: params.get('window_shell') === '1',
    version: params.get('mower_version') || '',
    instanceName: params.get('instance_name') || '',
    bootstrapTheme: ['light', 'dark'].includes(bootstrapTheme) ? bootstrapTheme : 'light'
  })
}

export function formatWindowTitle({ version = '', instanceName = '' } = {}) {
  const parts = [version ? `Mower ${version}` : 'Mower']
  parts.push(instanceName || '默认实例')
  return parts.join(' · ')
}

export function createWindowShellAdapter({
  windowObject = window,
  readyTimeoutMs = 1200,
  callTimeoutMs = 1000
} = {}) {
  const active = ref(false)
  const platform = ref(null)
  const state = ref({ ...NORMAL_STATE })
  const busy = ref({
    minimize: false,
    maximize: false,
    restore: false,
    close: false
  })
  const metadata = readWindowShellMetadata(windowObject?.location)
  let bridge = null
  let initializePromise = null
  let activeProtocol = null
  let listeningEvent = null

  const controlSide = computed(() => (platform.value === 'macos' ? 'start' : 'end'))
  const controls = computed(() => {
    if (!active.value) return []
    const maximizeControl = state.value.maximized
      ? { id: 'maximize', action: 'restore', label: '还原', icon: 'restore' }
      : { id: 'maximize', action: 'maximize', label: '最大化', icon: 'maximize' }
    const standard = [
      { id: 'minimize', action: 'minimize', label: '最小化', icon: 'minimize' },
      maximizeControl,
      { id: 'close', action: 'close', label: '关闭', icon: 'close' }
    ]
    return platform.value === 'macos' ? [standard[2], standard[0], standard[1]] : standard
  })

  const onNativeState = (event) => {
    if (validState(event?.detail, activeProtocol)) state.value = { ...event.detail }
  }

  async function initializeOnce() {
    try {
      if (!metadata.requested) return false
      const candidate = await waitForBridge(windowObject, readyTimeoutMs)
      if (!candidate) return false

      const [platformResult, stateResult] = await Promise.all([
        withTimeout(candidate.get_platform(), callTimeoutMs),
        withTimeout(candidate.get_window_state(), callTimeoutMs)
      ])
      const protocol = platformResult?.protocol
      const event = platformResult?.event
      if (
        !protocol ||
        !event ||
        !VALID_PLATFORMS.has(platformResult.platform) ||
        protocol !== stateResult?.protocol ||
        !validState(stateResult, protocol)
      ) {
        disposeListener()
        return false
      }

      // Subscribe to the event name the Python side actually dispatches. This is
      // the single source of truth for the bridge contract, so renaming it on the
      // backend cannot silently leave the client listening for a stale name.
      activeProtocol = protocol
      bridge = candidate
      platform.value = platformResult.platform
      state.value = { ...stateResult }
      active.value = true
      windowObject?.addEventListener?.(event, onNativeState)
      listeningEvent = event
      return true
    } catch {
      disposeListener()
      return false
    }
  }

  function initialize() {
    if (!initializePromise) initializePromise = initializeOnce()
    return initializePromise
  }

  async function runControl(action) {
    if (!active.value || !bridge || !CONTROL_METHODS.has(action)) return false
    busy.value = { ...busy.value, [action]: true }
    try {
      return (await withTimeout(bridge[action](), callTimeoutMs)) === true
    } catch {
      return false
    } finally {
      busy.value = { ...busy.value, [action]: false }
    }
  }

  const minimize = () => runControl('minimize')
  const maximize = () => runControl('maximize')
  const restore = () => runControl('restore')
  const close = () => runControl('close')
  const toggleMaximize = () => (state.value.maximized ? restore() : maximize())

  async function startResize(edge) {
    if (!active.value || !bridge || !RESIZE_EDGES.has(edge) || state.value.maximized) {
      return false
    }
    try {
      return (await withTimeout(bridge.start_resize(edge), callTimeoutMs)) === true
    } catch {
      return false
    }
  }

  function disposeListener() {
    if (!listeningEvent) return
    windowObject?.removeEventListener?.(listeningEvent, onNativeState)
    listeningEvent = null
  }

  function dispose() {
    disposeListener()
    active.value = false
    activeProtocol = null
    bridge = null
  }

  return {
    active,
    platform,
    state,
    busy,
    metadata,
    controlSide,
    controls,
    initialize,
    runControl,
    minimize,
    maximize,
    restore,
    close,
    toggleMaximize,
    startResize,
    dispose
  }
}
