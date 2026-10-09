import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'
import { darkTheme, lightTheme } from 'naive-ui'
import { mowerDarkThemeOverrides, mowerLightThemeOverrides } from '@/theme/mower'
import DocPage from './Doc.vue'

const state = vi.hoisted(() => ({ config: null, colors: null }))
vi.mock('naive-ui', async (original) => ({
  ...(await original()),
  useThemeVars: () => state.colors
}))
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
  const colors = new Map()
  const document = {
    documentElement: {
      dataset: {},
      style: {
        setProperty: (name, value) => colors.set(name, value),
        removeProperty: (name) => colors.delete(name)
      }
    }
  }
  const CSS = { supports: (property, value) => /^(#|rgb)/.test(value) }
  runInNewContext(themeScript, { window, document, URLSearchParams, CSS })
  return {
    window,
    document,
    colors,
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

  it('accepts only color tokens from the same-origin parent and clears stale overrides', () => {
    const page = openGuide('?theme=light', false)
    const event = {
      source: page.window.parent,
      origin: page.window.location.origin,
      data: {
        type: 'mower-doc-theme',
        theme: 'dark',
        colors: {
          '--page-bg': 'rgb(16, 16, 20)',
          '--card-bg': 'url(untrusted)',
          '--arbitrary-property': '#ffffff'
        }
      }
    }
    page.message({ ...event, origin: 'https://another.example' })
    page.message({ ...event, source: {} })
    expect(page.colors.size).toBe(0)
    page.message(event)
    expect([...page.colors]).toEqual([['--page-bg', 'rgb(16, 16, 20)']])
    page.message({ ...event, data: { type: 'mower-doc-theme', theme: 'light' } })
    expect(page.colors.size).toBe(0)
    expect(page.document.documentElement.dataset.theme).toBe('light')
  })
})

const palettes = {
  light: { ...lightTheme.common, ...mowerLightThemeOverrides.common },
  dark: { ...darkTheme.common, ...mowerDarkThemeOverrides.common }
}

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
      state.colors = ref(palettes[theme])
      vi.stubGlobal('window', { location: { origin: 'https://mower.local' } })
      scope = effectScope()
      const component = scope.run(() => DocPage.setup({}, { expose: vi.fn() }))
      expect(component.docSrc).toBe(`/docs/Mower入门指北.html?theme=${theme}`)
      expect(() => component.syncTheme()).not.toThrow()
      const frame = { postMessage: vi.fn() }
      component.guideFrame.value = { contentWindow: frame }
      component.syncTheme()
      expect(frame.postMessage).toHaveBeenLastCalledWith(
        expect.objectContaining({ type: 'mower-doc-theme', theme }),
        'https://mower.local'
      )
      const page = openGuide('', false)
      function applyLastMessage() {
        const [data, origin] = frame.postMessage.mock.lastCall
        page.message({ data, origin, source: page.window.parent })
      }
      applyLastMessage()
      expect(page.colors.get('--page-bg')).toBe(palettes[theme].bodyColor)
      expect(page.colors.get('--card-bg')).toBe(palettes[theme].cardColor)
      expect(page.colors.get('--code-bg')).toBe(palettes[theme].actionColor)
      const changed = theme === 'light' ? 'dark' : 'light'
      state.config.refs.theme.value = changed
      state.colors.value = palettes[changed]
      await nextTick()
      expect(frame.postMessage).toHaveBeenLastCalledWith(
        expect.objectContaining({ type: 'mower-doc-theme', theme: changed }),
        'https://mower.local'
      )
      applyLastMessage()
      expect(page.document.documentElement.dataset.theme).toBe(changed)
      expect(page.colors.get('--page-bg')).toBe(palettes[changed].bodyColor)
      expect(page.colors.get('--card-bg')).toBe(palettes[changed].cardColor)
      expect(component.docSrc).toBe(`/docs/Mower入门指北.html?theme=${theme}`)
      state.colors.value = { ...palettes[changed], bodyColor: '#123456' }
      await nextTick()
      applyLastMessage()
      expect(page.colors.get('--page-bg')).toBe('#123456')
    }
  )
})
