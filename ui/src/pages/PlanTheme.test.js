import { readFileSync } from 'node:fs'
import { compileScript, parse } from '@vue/compiler-sfc'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'
import { useResolvedTheme } from '@/composables/theme'

const { descriptor } = parse(readFileSync(new URL('./Plan.vue', import.meta.url), 'utf8'))
const script = compileScript(descriptor, { id: 'plan-export-theme-test' })
const saveNode = script.scriptSetupAst.find((node) => node.id?.name === 'save')
const saveCode = descriptor.scriptSetup.content
  .slice(saveNode.start, saveNode.end)
  .replaceAll('import.meta.env.VITE_HTTP_URL', JSON.stringify('/api'))

let scope
afterEach(() => {
  scope?.stop()
  vi.unstubAllGlobals()
})

describe('plan image theme', () => {
  it.each([
    [false, 'light', '#ffffff'],
    [true, 'dark', '#000000']
  ])('exports system dark=%s using the captured appearance', async (dark, mode, background) => {
    const media = { matches: dark, addEventListener: vi.fn(), removeEventListener: vi.fn() }
    const link = { setAttribute: vi.fn(), click: vi.fn() }
    const document = {
      createElement: vi.fn(() => link),
      body: { appendChild: vi.fn(), removeChild: vi.fn() }
    }
    const window = {
      matchMedia: vi.fn(() => media),
      navigator: { userAgent: 'offline-test' },
      URL: { createObjectURL: vi.fn(() => 'blob:preview'), revokeObjectURL: vi.fn() }
    }
    vi.stubGlobal('window', window)
    scope = effectScope()
    const preference = ref('system')
    const theme = scope.run(() => useResolvedTheme(preference))
    const image = new Blob(['image'], { type: 'image/png' })
    const toBlob = vi.fn(async () => {
      media.matches = !dark
      media.addEventListener.mock.calls.find(([event]) => event === 'change')[1]({
        matches: !dark
      })
      return image
    })
    const post = vi.fn(async () => ({ data: image }))
    const dependencies = {
      drainConfigurationSaves: vi.fn(),
      config_store: {},
      plan_store: { save_plan: vi.fn() },
      generating_image: ref(false),
      loading_bar: { start: vi.fn(), finish: vi.fn() },
      facility: ref(''),
      sleep: vi.fn(),
      Bowser: { getParser: () => ({ getEngine: () => ({ name: 'Blink' }) }) },
      window,
      document,
      toBlob,
      plan_editor: ref({ outer: {} }),
      theme,
      axios: { post },
      rescue: false
    }
    const save = new Function(...Object.keys(dependencies), `${saveCode}; return save`)(
      ...Object.values(dependencies)
    )

    await save()

    expect(toBlob).toHaveBeenCalledWith(
      dependencies.plan_editor.value.outer,
      expect.objectContaining({ backgroundColor: background })
    )
    const [url, payload] = post.mock.lastCall
    expect(url).toBe('/api/dialog/save/img')
    expect(payload.get('theme')).toBe(mode)
    expect(payload.get('img').type).toBe('image/png')
    expect(preference.value).toBe('system')
    expect(theme.value).toBe(dark ? 'light' : 'dark')
  })
})
