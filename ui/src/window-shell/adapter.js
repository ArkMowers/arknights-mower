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
// start_move is deliberately absent from that list. It is the one capability the
// shell can do without: the controls and the resize grips still work, only the
// drag is gone. Requiring it would reject the whole shell instead, and on a
// frameless window that leaves no title bar, no controls and no drag at all.
// connect() warns when it is missing, so the gap is not silent.
const CONTROL_METHODS = new Set(['minimize', 'maximize', 'restore', 'close'])
const RESIZE_EDGES = new Set(WINDOW_RESIZE_EDGES)

// Every signal the page can get that the bridge may have been injected since the
// last look. They all feed the same connect attempt, so the number of ways to
// notice a late bridge does not change what happens when one is noticed.
const READINESS_EVENTS = ['pywebviewready', 'visibilitychange', 'focus', 'resize']
// WebView2 injects window.pywebview after NavigationCompleted, which on a cold
// start can take far longer than the initial readiness timeout. Keep looking in
// the background: every 100ms for the first 3s, then every 500ms for a minute.
const POLL_FAST_MS = 100
const POLL_FAST_ROUNDS = 30
const POLL_SLOW_MS = 500
const POLL_WINDOW_MS = 60000

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
  const metadata = readWindowShellMetadata(windowObject?.location)
  // A frameless desktop window draws its own title bar, so the bar is active
  // from the first frame instead of waiting for the bridge. Showing it early and
  // connecting late are separate concerns; only `connected` gates the controls.
  const active = ref(Boolean(metadata.requested))
  const connected = ref(false)
  const platform = ref(null)
  const state = ref({ ...NORMAL_STATE })
  const busy = ref({
    minimize: false,
    maximize: false,
    restore: false,
    close: false
  })

  let bridge = null
  let activeProtocol = null
  let listeningEvent = null
  let initialSyncTimer = null
  let disposed = false
  let pollTimer = null
  let pollStartedAt = 0
  let connectAttempt = null
  let connectPromise = null
  let rejectedCandidate = null
  let pendingReadiness = []
  let warnedMessages = new Set()

  const makeControl = (action, label) => ({
    id: action === 'restore' ? 'maximize' : action,
    action,
    label,
    icon: action,
    disabled: !connected.value
  })

  const controlSide = computed(() => (platform.value === 'macos' ? 'start' : 'end'))
  const controls = computed(() => {
    if (!active.value) return []
    const maximizeControl = state.value.maximized
      ? makeControl('restore', '还原')
      : makeControl('maximize', '最大化')
    const standard = [
      makeControl('minimize', '最小化'),
      maximizeControl,
      makeControl('close', '关闭')
    ]
    return platform.value === 'macos' ? [standard[2], standard[0], standard[1]] : standard
  })

  const onNativeState = (event) => {
    if (validState(event?.detail, activeProtocol)) state.value = { ...event.detail }
  }

  // A bridge problem is worth saying once: the polling that follows would repeat
  // the same line on every tick, and the log is not the place to count them.
  function warnOnce(message, ...details) {
    if (warnedMessages.has(message)) return
    warnedMessages.add(message)
    console.warn(message, ...details)
  }

  function settleReadiness(result) {
    const waiting = pendingReadiness
    pendingReadiness = []
    waiting.forEach((settle) => settle(result))
  }

  async function connectCandidate(candidate) {
    try {
      const [platformResult, stateResult] = await Promise.all([
        withTimeout(candidate.get_platform(), callTimeoutMs),
        withTimeout(candidate.get_window_state(), callTimeoutMs)
      ])
      const protocol = platformResult?.protocol
      const event = platformResult?.event
      // Two kinds of no. A bridge that does not speak this contract will never
      // start speaking it, so it is refused for good. A state that cannot be read
      // yet may be a window still coming up, and keeps the rest of the poll budget.
      const wrongContract =
        !protocol ||
        !event ||
        !VALID_PLATFORMS.has(platformResult.platform) ||
        protocol !== stateResult?.protocol
      const unusableState = !validState(stateResult, protocol)
      if (wrongContract || unusableState) {
        warnOnce('window shell bridge validation failed:', platformResult, stateResult)
        if (wrongContract) {
          rejectedCandidate = candidate
          stopPolling()
        }
        disposeListener()
        return false
      }

      if (disposed) return false

      activeProtocol = protocol
      bridge = candidate
      platform.value = platformResult.platform
      state.value = { ...stateResult }
      connected.value = true

      if (typeof candidate.start_move !== 'function') {
        warnOnce('window shell cannot drag the window: start_move is missing')
      }

      // Subscribe to the event name the Python side actually dispatches. This is
      // the single source of truth for the bridge contract, so renaming it on the
      // backend cannot silently leave the client listening for a stale name.
      disposeListener()
      windowObject?.addEventListener?.(event, onNativeState)
      listeningEvent = event

      stopPolling()
      if (initialSyncTimer) clearTimeout(initialSyncTimer)
      // The first maximize can happen while WebView2 is still initializing,
      // before the page receives its native state event. One later read is
      // sufficient; the bridge is connected by now, so this is not a state poll.
      initialSyncTimer = setTimeout(async () => {
        if (bridge !== candidate || !active.value) return
        try {
          const current = await withTimeout(candidate.get_window_state(), callTimeoutMs)
          if (bridge === candidate && validState(current, activeProtocol)) {
            state.value = { ...current }
          }
        } catch {
          // A closing WebView has no state to synchronize.
        }
      }, 350)
      settleReadiness(true)
      return true
    } catch (error) {
      // A timeout or a throw can be a cold WebView2 rather than a wrong bridge,
      // so polling keeps going. The warning is enough to explain the silence.
      warnOnce('window shell failed to connect bridge candidate:', error)
      disposeListener()
      return false
    }
  }

  // One connect at a time, and only for a bridge that has not already been
  // rejected. Readiness signals arrive in bursts (a focus, a resize and a
  // pywebviewready can land in the same frame), and each of them must not pay
  // for its own round trip to a bridge that is still starting up.
  function connectIfPossible() {
    if (disposed || connected.value) return Promise.resolve(connected.value)
    if (connectAttempt) return connectAttempt
    const candidate = readBridge(windowObject)
    if (!hasBridgeContract(candidate) || candidate === rejectedCandidate) {
      return Promise.resolve(false)
    }
    connectAttempt = connectCandidate(candidate).finally(() => {
      connectAttempt = null
    })
    return connectAttempt
  }

  const onReadinessSignal = () => {
    void connectIfPossible()
  }

  function nextPollDelay(elapsedMs) {
    return elapsedMs < POLL_FAST_MS * POLL_FAST_ROUNDS ? POLL_FAST_MS : POLL_SLOW_MS
  }

  function schedulePoll() {
    if (pollTimer || disposed || connected.value) return
    const elapsed = Date.now() - pollStartedAt
    if (elapsed >= POLL_WINDOW_MS) {
      stopPolling()
      return
    }
    pollTimer = setTimeout(() => {
      pollTimer = null
      if (disposed || connected.value) return
      void connectIfPossible()
      schedulePoll()
    }, nextPollDelay(elapsed))
  }

  function stopPolling() {
    if (pollTimer) clearTimeout(pollTimer)
    pollTimer = null
  }

  function watchForBridge() {
    READINESS_EVENTS.forEach((name) => windowObject?.addEventListener?.(name, onReadinessSignal))
    pollStartedAt = Date.now()
    schedulePoll()
  }

  function unwatchBridge() {
    READINESS_EVENTS.forEach((name) => windowObject?.removeEventListener?.(name, onReadinessSignal))
    stopPolling()
  }

  if (metadata.requested) {
    watchForBridge()
  }

  // Resolves once the bridge is usable, or false when the initial wait runs out.
  // Running out is not a failure: the title bar is already up and the readiness
  // listeners and polling keep working in the background.
  function waitForReadiness(timeoutMs) {
    return new Promise((resolve) => {
      const timer = setTimeout(() => {
        pendingReadiness = pendingReadiness.filter((entry) => entry !== settle)
        console.warn(
          `window shell bridge did not arrive within ${timeoutMs}ms; continuing to wait in background.`
        )
        settle(false)
      }, timeoutMs)
      function settle(result) {
        clearTimeout(timer)
        resolve(result)
      }
      pendingReadiness.push(settle)
      void connectIfPossible()
    })
  }

  async function initialize() {
    if (!metadata.requested) {
      active.value = false
      return false
    }

    if (connected.value) return true

    if (!connectPromise) connectPromise = waitForReadiness(readyTimeoutMs)
    return connectPromise
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
  const toggleMaximize = async () => {
    // The startup maximize event can precede listener registration. Query the
    // existing bridge immediately before deciding which native action to send.
    if (bridge) {
      try {
        const current = await withTimeout(bridge.get_window_state(), callTimeoutMs)
        if (validState(current, activeProtocol)) state.value = { ...current }
      } catch {
        // Fall back to the last native event if the window is already closing.
      }
    }
    return state.value.maximized ? restore() : maximize()
  }

  async function startMove() {
    if (!active.value || !bridge) return false
    let handover
    try {
      handover = bridge.start_move()
    } catch (error) {
      // The call never reached the shell, so nothing owns the drag.
      console.warn('window shell drag handover failed', error)
      return false
    }
    // The shell's move loop owns the mouse until the button comes up, so this
    // settles only after the drag has already ended. Report the handover straight
    // away, but do not let a late refusal disappear either: a title bar that hands
    // the drag to nobody leaves the window unable to move at all.
    Promise.resolve(handover).then(
      (started) => {
        if (started !== true) console.warn('window shell refused the drag handover')
      },
      (error) => console.warn('window shell drag handover failed', error)
    )
    return true
  }

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
    disposed = true
    unwatchBridge()
    if (initialSyncTimer) clearTimeout(initialSyncTimer)
    initialSyncTimer = null
    disposeListener()
    // Anything still waiting on initialize() would otherwise sit there until its
    // timeout. There is no bridge coming: the adapter is gone.
    settleReadiness(false)
    connectAttempt = null
    connectPromise = null
    rejectedCandidate = null
    active.value = false
    connected.value = false
    activeProtocol = null
    bridge = null
  }

  return {
    active,
    connected,
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
    startMove,
    startResize,
    dispose
  }
}
