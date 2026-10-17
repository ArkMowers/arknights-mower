import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, createSSRApp, nextTick, ref } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createPinia, setActivePinia } from 'pinia'
import axios from 'axios'
import { useConfigStore } from '@/stores/config'
import TrustSettings from './TrustSettings.vue'

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }))
let store
afterEach(() => {
  store?.$dispose()
  vi.clearAllMocks()
})

describe('daily trust settings', () => {
  it.each([false, true])(
    'renders the daily options and dependent controls enabled=%s',
    async (enabled) => {
      const app = createSSRApp(TrustSettings)
      app.use(createPinia())
      app.provide('loaded', ref(false))
      store = app.runWithContext(() => useConfigStore())
      store.trust_rotation_enable = enabled
      store.trust_rotation_prefer_low = enabled
      const html = await renderToString(app)
      expect(html).toContain('自动切换信赖')
      expect(html).toContain('检查间隔')
      expect(html).toContain('优先信赖阈值')
      const threshold = html.match(/<input[^>]*aria-label="优先信赖阈值"[^>]*>/)?.[0]
      expect(threshold).toBeTruthy()
      expect(/\sdisabled(?:[=>\s])/.test(threshold)).toBe(!enabled)
    }
  )
  it('defaults off and saves each edit without submitting ordinary staffing settings', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const app = createApp({})
    app.use(pinia)
    const loaded = ref(false)
    app.provide('loaded', loaded)
    store = app.runWithContext(() => useConfigStore())
    for (const name of ['reload_room', 'maa_mall_buy', 'maa_mall_blacklist']) store[name] = []
    expect(store.trust_rotation_enable).toBe(false)
    expect(store.trust_rotation_prefer_low).toBe(false)
    expect(store.trust_rotation_threshold).toBe(100)
    expect(store.trust_rotation_interval).toBe(24)
    expect(store.build_advanced_settings()).not.toHaveProperty('trust_rotation_enable')
    axios.patch.mockResolvedValue({ data: {} })
    loaded.value = true
    await nextTick()
    await store.flush_config_saves()
    for (const [key, value] of Object.entries({
      trust_rotation_enable: true,
      trust_rotation_prefer_low: true,
      trust_rotation_threshold: 80,
      trust_rotation_interval: 48
    })) {
      axios.patch.mockClear()
      store[key] = value
      await vi.waitFor(() => expect(axios.patch).toHaveBeenCalledOnce())
      expect(axios.patch.mock.calls[0][1]).toEqual({ [key]: value })
    }
    loaded.value = false
  })
})
