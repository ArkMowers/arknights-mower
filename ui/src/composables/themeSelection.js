import { nextTick, onScopeDispose, unref, watch } from 'vue'

export const themeSelectionKey = Symbol('theme-selection')

export function useThemeSelection(preference, resolvedTheme) {
  const document = globalThis.document
  const root = document?.documentElement
  let active = null
  let writingPreference = false
  let disposed = false

  function release(request) {
    if (active !== request) return
    active = null
    root?.classList.remove('mower-theme-transition')
  }

  function cancel() {
    const request = active
    if (!request) return
    release(request)
    request.transition?.skipTransition()
  }

  function writePreference(value) {
    writingPreference = true
    try {
      preference.value = value
    } finally {
      writingPreference = false
    }
  }

  watch(
    preference,
    () => {
      if (!writingPreference) cancel()
    },
    { flush: 'sync' }
  )
  onScopeDispose(() => {
    disposed = true
    cancel()
  })

  return function setTheme(nextPreference) {
    if (disposed) return
    cancel()
    if (nextPreference === unref(preference)) return

    const media = globalThis.window?.matchMedia
    const systemDark = media?.call(window, '(prefers-color-scheme: dark)')?.matches
    const nextTheme =
      nextPreference === 'dark' || (nextPreference === 'system' && systemDark) ? 'dark' : 'light'
    const reducedMotion = media?.call(window, '(prefers-reduced-motion: reduce)')?.matches
    if (
      !document?.startViewTransition ||
      document.visibilityState === 'hidden' ||
      reducedMotion ||
      nextTheme === unref(resolvedTheme)
    ) {
      writePreference(nextPreference)
      return
    }

    const request = { transition: null, committed: false }
    active = request
    root?.classList.add('mower-theme-transition')
    function commit() {
      if (disposed || active !== request || request.committed) return nextTick()
      request.committed = true
      writePreference(nextPreference)
      return nextTick()
    }
    function fail() {
      if (active !== request) return
      void commit().catch(() => {})
      cancel()
    }

    try {
      const transition = document.startViewTransition(commit)
      request.transition = transition
      void transition.ready.catch(fail)
      void transition.updateCallbackDone.catch(fail)
      void transition.finished.then(() => release(request), fail)
    } catch {
      fail()
    }
  }
}
