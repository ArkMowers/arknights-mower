import { afterEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'
import { useResolvedTheme } from './theme'

let scope
afterEach(() => {
  scope?.stop()
  vi.unstubAllGlobals()
})

function mediaPreference(dark, legacy = false) {
  const listeners = new Set()
  const add = vi.fn((listener) => listeners.add(listener))
  const remove = vi.fn((listener) => listeners.delete(listener))
  const media = {
    matches: dark,
    change(value) {
      this.matches = value
      for (const listener of listeners) listener({ matches: value })
    },
    ...(legacy
      ? { addListener: add, removeListener: remove }
      : {
          addEventListener: vi.fn((_event, listener) => add(listener)),
          removeEventListener: vi.fn((_event, listener) => remove(listener))
        })
  }
  vi.stubGlobal('window', { matchMedia: vi.fn(() => media) })
  return { media, add, remove }
}

describe('resolved display theme', () => {
  it.each([false, true])(
    'follows system changes without replacing the saved preference (initial dark %s)',
    (dark) => {
      const { media, add, remove } = mediaPreference(dark)
      const preference = ref('system')
      scope = effectScope()
      const theme = scope.run(() => useResolvedTheme(preference))
      expect(theme.value).toBe(dark ? 'dark' : 'light')
      expect(window.matchMedia).toHaveBeenCalledWith('(prefers-color-scheme: dark)')
      media.change(!dark)
      expect(theme.value).toBe(dark ? 'light' : 'dark')
      expect(preference.value).toBe('system')
      scope.stop()
      expect(remove).toHaveBeenCalledExactlyOnceWith(add.mock.calls[0][0])
      media.change(dark)
      expect(theme.value).toBe(dark ? 'light' : 'dark')
    }
  )

  it('keeps explicit choices through system changes and uses the latest system colour when selected again', () => {
    const { media } = mediaPreference(true)
    const preference = ref('light')
    scope = effectScope()
    const theme = scope.run(() => useResolvedTheme(preference))
    expect(theme.value).toBe('light')
    media.change(false)
    preference.value = 'dark'
    expect(theme.value).toBe('dark')
    preference.value = 'system'
    expect(theme.value).toBe('light')
    media.change(true)
    expect(theme.value).toBe('dark')
  })

  it('releases legacy media listeners on scope disposal', () => {
    const { media, add, remove } = mediaPreference(false, true)
    scope = effectScope()
    const theme = scope.run(() => useResolvedTheme(ref('system')))
    media.change(true)
    expect(theme.value).toBe('dark')
    scope.stop()
    expect(remove).toHaveBeenCalledExactlyOnceWith(add.mock.calls[0][0])
  })

  it('uses light for system mode when the media API is unavailable while preserving explicit dark', () => {
    vi.stubGlobal('window', undefined)
    const preference = ref('system')
    scope = effectScope()
    const theme = scope.run(() => useResolvedTheme(preference))
    expect(theme.value).toBe('light')
    preference.value = 'dark'
    expect(theme.value).toBe('dark')
  })
})
