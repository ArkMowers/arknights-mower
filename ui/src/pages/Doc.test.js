import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'
import DocPage from './Doc.vue'

const state = vi.hoisted(() => ({ config: null }))
vi.mock('@/stores/config', () => ({ useConfigStore: () => state.config }))
vi.mock('pinia', async (original) => ({
  ...(await original()),
  storeToRefs: (store) => store.refs
}))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))

const guide = readFileSync(new URL('../../Mower入门指北.html', import.meta.url), 'utf8')
const themeScript = guide.match(/<script>([\s\S]*?)<\/script>/)[1]

function openGuide(search, dark) {
  const media = { matches: dark, addEventListener: vi.fn() }
  const window = {
    location: { search, origin: 'https://mower.local' },
    parent: {},
    matchMedia: vi.fn(() => media),
    addEventListener: vi.fn()
  }
  const document = { documentElement: { dataset: {} } }
  runInNewContext(themeScript, { window, document, URLSearchParams })
  return {
    window,
    document,
    changeSystemTheme(dark) {
      media.matches = dark
      media.addEventListener.mock.calls.find(([event]) => event === 'change')[1]()
    },
    message(event) {
      window.addEventListener.mock.calls.find(([name]) => name === 'message')[1](event)
    }
  }
}

describe('standalone guide theme', () => {
  it.each([
    ['', false, 'light'],
    ['', true, 'dark'],
    ['?theme=invalid', true, 'dark'],
    ['?theme=light', true, 'light'],
    ['?theme=dark', false, 'dark']
  ])('selects %s with system dark=%s as %s', (search, dark, expected) => {
    const page = openGuide(search, dark)
    expect(page.document.documentElement.dataset.theme).toBe(expected)
  })

  it('tracks system changes only without an explicit theme', () => {
    const standalone = openGuide('', true)
    standalone.changeSystemTheme(false)
    expect(standalone.document.documentElement.dataset.theme).toBe('light')
    standalone.changeSystemTheme(true)
    expect(standalone.document.documentElement.dataset.theme).toBe('dark')
    const explicit = openGuide('?theme=light', true)
    explicit.changeSystemTheme(true)
    expect(explicit.document.documentElement.dataset.theme).toBe('light')
  })

  it('accepts valid parent themes and ignores unrelated messages', () => {
    const page = openGuide('?theme=light', false)
    const event = {
      source: page.window.parent,
      origin: page.window.location.origin,
      data: { type: 'mower-doc-theme', theme: 'dark' }
    }
    for (const invalid of [
      { ...event, source: {} },
      { ...event, origin: 'https://another.example' },
      { ...event, data: { type: 'unrelated', theme: 'dark' } },
      { ...event, data: { type: 'mower-doc-theme', theme: 'invalid' } },
      { ...event, data: null }
    ]) {
      page.message(invalid)
      expect(page.document.documentElement.dataset.theme).toBe('light')
    }
    page.message(event)
    expect(page.document.documentElement.dataset.theme).toBe('dark')
    page.changeSystemTheme(false)
    expect(page.document.documentElement.dataset.theme).toBe('dark')
    page.message({ ...event, data: { type: 'mower-doc-theme', theme: 'light' } })
    expect(page.document.documentElement.dataset.theme).toBe('light')
  })
})

describe('embedded guide theme', () => {
  let scope
  afterEach(() => {
    scope?.stop()
    vi.unstubAllGlobals()
  })

  it.each(['light', 'dark'])(
    'loads %s and switches without reloading the iframe',
    async (theme) => {
      state.config = { refs: { theme: ref(theme) } }
      vi.stubGlobal('window', { location: { origin: 'https://mower.local' } })
      scope = effectScope()
      const component = scope.run(() => DocPage.setup({}, { expose: vi.fn() }))
      expect(component.docSrc).toBe(`/docs/Mower入门指北.html?theme=${theme}`)
      expect(() => component.syncTheme()).not.toThrow()
      const frame = { postMessage: vi.fn() }
      component.guideFrame.value = { contentWindow: frame }
      component.syncTheme()
      expect(frame.postMessage).toHaveBeenLastCalledWith(
        { type: 'mower-doc-theme', theme },
        'https://mower.local'
      )
      const changed = theme === 'light' ? 'dark' : 'light'
      state.config.refs.theme.value = changed
      await nextTick()
      expect(frame.postMessage).toHaveBeenLastCalledWith(
        { type: 'mower-doc-theme', theme: changed },
        'https://mower.local'
      )
      expect(component.docSrc).toBe(`/docs/Mower入门指北.html?theme=${theme}`)
    }
  )
})
