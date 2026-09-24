import { ref } from 'vue'

const KEY = 'mower.planEditLocked.v1'
const IDLE_TIMEOUT = 3 * 60 * 1000
const ACTIVITY_EVENTS = ['pointerdown', 'pointermove', 'keydown', 'wheel', 'touchstart']

function safeStorage() {
  try {
    return typeof window === 'undefined' ? null : window.localStorage
  } catch {
    return null
  }
}

export function usePlanEditLock({
  storage = safeStorage(),
  documentTarget = typeof document === 'undefined' ? null : document
} = {}) {
  let initiallyLocked = false
  try {
    initiallyLocked = storage?.getItem(KEY) === 'locked'
  } catch {
    /* storage unavailable */
  }
  const locked = ref(initiallyLocked)
  let started = false
  let timeout = null
  let lastActivity = Date.now()

  function remember(active) {
    try {
      if (active) storage?.setItem(KEY, 'locked')
      else storage?.removeItem(KEY)
    } catch {
      /* in-memory state remains usable */
    }
  }

  function clearIdleTimeout() {
    if (timeout !== null) clearTimeout(timeout)
    timeout = null
  }

  function lock() {
    locked.value = true
    clearIdleTimeout()
    remember(true)
  }

  function checkIdle() {
    timeout = null
    if (locked.value) return
    const remaining = IDLE_TIMEOUT - (Date.now() - lastActivity)
    if (remaining <= 0) lock()
    else timeout = setTimeout(checkIdle, remaining)
  }

  function scheduleIdleTimeout() {
    if (started && !locked.value && timeout === null) {
      timeout = setTimeout(checkIdle, IDLE_TIMEOUT)
    }
  }

  function unlock() {
    locked.value = false
    lastActivity = Date.now()
    remember(false)
    scheduleIdleTimeout()
  }

  function isEditable() {
    if (!locked.value && started && Date.now() - lastActivity >= IDLE_TIMEOUT) lock()
    return !locked.value
  }

  function noteActivity() {
    if (!isEditable()) return false
    lastActivity = Date.now()
    scheduleIdleTimeout()
    return true
  }

  function start() {
    if (started) return
    started = true
    lastActivity = Date.now()
    for (const event of ACTIVITY_EVENTS) documentTarget?.addEventListener(event, noteActivity, true)
    scheduleIdleTimeout()
  }

  function dispose() {
    if (!started) return
    started = false
    clearIdleTimeout()
    for (const event of ACTIVITY_EVENTS)
      documentTarget?.removeEventListener(event, noteActivity, true)
  }

  return { locked, lock, unlock, isEditable, noteActivity, start, dispose }
}
