import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, ref } from 'vue'
import { createPinia } from 'pinia'
import axios from 'axios'
import { useConfigStore } from './config'

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
let store
afterEach(() => {
  store?.$dispose()
  vi.resetAllMocks()
})

function setup() {
  const app = createApp({})
  const loaded = ref(false)
  app.use(createPinia())
  app.provide('loaded', loaded)
  store = app.runWithContext(() => useConfigStore())
  return loaded
}

describe('MAA restore theme config', () => {
  it('autosaves the target and enabled state and supports clearing the selection', async () => {
    const loaded = setup()
    for (const key of ['reload_room', 'maa_mall_buy', 'maa_mall_blacklist']) store[key] = []
    expect(store.maa_restore_theme_enable).toBe(false)
    expect(store.maa_restore_theme).toBe('')
    axios.post.mockResolvedValue({ data: {} })
    store.maa_restore_theme_enable = true
    store.maa_restore_theme = '夜间'
    loaded.value = true
    await vi.waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1))
    expect(axios.post.mock.calls[0][1]).toMatchObject({
      maa_restore_theme_enable: true,
      maa_restore_theme: '夜间'
    })
    store.maa_restore_theme_enable = false
    await vi.waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2))
    expect(axios.post.mock.calls[1][1]).toMatchObject({
      maa_restore_theme_enable: false,
      maa_restore_theme: '夜间'
    })
    store.maa_restore_theme = ''
    await vi.waitFor(() => expect(axios.post).toHaveBeenCalledTimes(3))
    expect(axios.post.mock.calls[2][1].maa_restore_theme).toBe('')
    loaded.value = false
  })

  it('loads saved settings and disables restore when loading an older config', async () => {
    setup()
    const legacy = {
      free_blacklist: '',
      reload_room: '',
      dorm_order: '',
      maa_mall_buy: '',
      maa_mall_blacklist: '',
      maa_weekly_plan_active: '默认',
      favorite: '',
      reclamation_algorithm: {},
      secret_front: {}
    }
    let config = { ...legacy, maa_restore_theme_enable: true, maa_restore_theme: '银凇' }
    axios.get.mockImplementation(async (url) => ({
      data: url.endsWith('/conf') ? config : { plans: ['默认'] }
    }))
    await store.load_config()
    expect(store.maa_restore_theme_enable).toBe(true)
    expect(store.maa_restore_theme).toBe('银凇')
    config = legacy
    await store.load_config()
    expect(store.maa_restore_theme_enable).toBe(false)
    expect(store.maa_restore_theme).toBe('')
    expect(axios.post).not.toHaveBeenCalled()
  })
})
