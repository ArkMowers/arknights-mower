import { ref } from 'vue'

// A manual UI guard; no inactivity, background or navigation auto-lock.
const KEY = 'mower.planEditLocked.v1'

function safeStorage() {
  try {
    return typeof window === 'undefined' ? null : window.localStorage
  } catch {
    return null
  }
}

export function usePlanEditLock({ storage = safeStorage() } = {}) {
  let initiallyLocked = false
  try {
    initiallyLocked = storage?.getItem(KEY) === 'locked'
  } catch {
    /* storage unavailable */
  }
  const locked = ref(initiallyLocked)

  function remember(active) {
    try {
      if (active) storage?.setItem(KEY, 'locked')
      else storage?.removeItem(KEY)
    } catch {
      /* in-memory state remains usable */
    }
  }

  function lock() {
    locked.value = true
    remember(true)
  }
  function unlock() {
    locked.value = false
    remember(false)
  }
  function isEditable() {
    return !locked.value
  }
  function noteActivity() {
    return isEditable()
  }
  function dispose() {
    /* never change a manual choice on navigation */
  }

  return { locked, lock, unlock, isEditable, noteActivity, dispose }
}
