import { afterEach, describe, expect, it, vi } from 'vitest'
import { computed, effectScope, nextTick, ref, watch } from 'vue'
import { useThemeSelection } from './themeSelection'

let scope

afterEach(() => {
  scope?.stop()
  vi.unstubAllGlobals()
})

function deferred() {
  let resolve
  let reject
  const promise = new Promise((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}

function setup({ native = true, reduced = false, hidden = false, systemDark = false } = {}) {
  const classes = new Set()
  const requests = []
  const preference = ref('light')
  const dark = ref(systemDark)
  const resolved = computed(() =>
    preference.value === 'dark' || (preference.value === 'system' && dark.value) ? 'dark' : 'light'
  )
  const startViewTransition = vi.fn((callback) => {
    const ready = deferred()
    const updated = deferred()
    const finished = deferred()
    const request = {
      ready: ready.promise,
      updateCallbackDone: updated.promise,
      finished: finished.promise,
      skipTransition: vi.fn(() => {
        ready.reject(new Error('Skipped transition'))
        finished.resolve()
      }),
      async update() {
        await callback()
        updated.resolve()
        ready.resolve()
      },
      finish: finished.resolve,
      failReady: ready.reject,
      failUpdate: updated.reject,
      failFinished: finished.reject
    }
    requests.push(request)
    return request
  })
  vi.stubGlobal('document', {
    visibilityState: hidden ? 'hidden' : 'visible',
    documentElement: {
      classList: {
        add: (name) => classes.add(name),
        remove: (name) => classes.delete(name)
      }
    },
    ...(native ? { startViewTransition } : {})
  })
  vi.stubGlobal('window', {
    matchMedia: (query) => ({
      matches: query === '(prefers-reduced-motion: reduce)' ? reduced : dark.value
    })
  })
  scope = effectScope()
  const setTheme = scope.run(() => useThemeSelection(preference, resolved))
  return { preference, dark, classes, requests, setTheme, startViewTransition }
}

describe('theme selection transition', () => {
  it.each([{ native: false }, { reduced: true }, { hidden: true }])(
    'commits directly when a visual transition is unavailable: %j',
    (options) => {
      const page = setup(options)
      page.setTheme('dark')
      expect(page.preference.value).toBe('dark')
      expect(page.startViewTransition).not.toHaveBeenCalled()
      expect(page.classes.size).toBe(0)
    }
  )

  it('updates inside the snapshot callback and waits for Vue to commit before capturing', async () => {
    const page = setup()
    let rendered = 'light'
    scope.run(() => watch(page.preference, (value) => (rendered = value), { flush: 'post' }))

    page.setTheme('dark')
    expect(page.preference.value).toBe('light')
    expect(page.classes.has('mower-theme-transition')).toBe(true)
    const committing = page.requests[0].update()
    expect(page.preference.value).toBe('dark')
    expect(rendered).toBe('light')
    await committing
    expect(rendered).toBe('dark')
    expect(page.requests[0].skipTransition).not.toHaveBeenCalled()
    expect(page.classes.has('mower-theme-transition')).toBe(true)
    page.requests[0].finish()
    await nextTick()
    expect(page.classes.size).toBe(0)
  })

  it('saves another preference without capturing an unchanged appearance', () => {
    const page = setup()
    page.setTheme('system')
    expect(page.preference.value).toBe('system')
    page.dark.value = true
    page.setTheme('dark')
    expect(page.preference.value).toBe('dark')
    expect(page.startViewTransition).not.toHaveBeenCalled()
  })

  it('cancels a pending change when the user selects the current preference again', async () => {
    const page = setup()
    page.setTheme('dark')
    page.setTheme('light')
    expect(page.requests[0].skipTransition).toHaveBeenCalledOnce()
    await page.requests[0].update()
    expect(page.preference.value).toBe('light')
    expect(page.classes.size).toBe(0)
  })

  it('keeps the latest choice when a skipped callback arrives after a newer one', async () => {
    const page = setup({ systemDark: true })
    page.setTheme('dark')
    page.setTheme('system')
    await page.requests[1].update()
    await page.requests[0].update()
    expect(page.preference.value).toBe('system')
    expect(page.classes.has('mower-theme-transition')).toBe(true)
    page.requests[1].finish()
    await nextTick()
    expect(page.classes.size).toBe(0)
  })

  it('cancels pending visual work when another caller changes the saved preference', async () => {
    const page = setup()
    page.setTheme('dark')
    page.preference.value = 'system'
    expect(page.requests[0].skipTransition).toHaveBeenCalledOnce()
    expect(page.classes.size).toBe(0)
    await page.requests[0].update()
    expect(page.preference.value).toBe('system')
  })

  it.each([false, true])(
    'commits once when the native API throws (callback ran %s)',
    async (ran) => {
      const page = setup()
      const changed = vi.fn()
      scope.run(() => watch(page.preference, changed, { flush: 'sync' }))
      page.startViewTransition.mockImplementation((callback) => {
        if (ran) void callback()
        throw new Error('Native snapshots unavailable')
      })
      page.setTheme('dark')
      await nextTick()
      expect(page.preference.value).toBe('dark')
      expect(changed).toHaveBeenCalledOnce()
      expect(page.classes.size).toBe(0)
    }
  )

  it.each(['failReady', 'failUpdate', 'failFinished'])(
    'preserves the selection and releases state when %s rejects',
    async (failure) => {
      const page = setup()
      page.setTheme('dark')
      page.requests[0][failure](new Error('Transition failed'))
      await nextTick()
      expect(page.preference.value).toBe('dark')
      expect(page.classes.size).toBe(0)
      await page.requests[0].update()
      expect(page.preference.value).toBe('dark')
    }
  )

  it('skips visual work on disposal and ignores delayed callbacks and later calls', async () => {
    const page = setup()
    page.setTheme('dark')
    scope.stop()
    expect(page.requests[0].skipTransition).toHaveBeenCalledOnce()
    expect(page.classes.size).toBe(0)
    await page.requests[0].update()
    page.setTheme('dark')
    expect(page.preference.value).toBe('light')
  })
})
