import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, nextTick, ref } from 'vue'
import { createPinia } from 'pinia'
import axios from 'axios'
import { useConfigStore } from './config'

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }))
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

describe('MAA ordinary Copilot config', () => {
  it('autosaves the complete queue and formation options', async () => {
    const loaded = setup()
    for (const key of ['reload_room', 'maa_mall_buy', 'maa_mall_blacklist']) store[key] = []
    axios.patch.mockResolvedValue({ data: {} })
    loaded.value = true
    await nextTick()
    await store.flush_config_saves()
    store.maa_long_task_type = 'copilot'
    store.copilot.scripts.push({ id: 'a'.repeat(64), is_raid: true, nav_name_override: '1-7' })
    store.copilot.formation = true
    store.copilot.support_unit_usage = 2
    store.copilot.support_unit_name = '棘刺'
    store.copilot.run_id = 'manual-round'
    await vi.waitFor(() => expect(axios.patch).toHaveBeenCalledOnce())
    expect(axios.patch.mock.calls[0][1]).toMatchObject({
      maa_long_task_type: 'copilot',
      copilot: {
        run_id: 'manual-round',
        scripts: store.copilot.scripts,
        formation: true,
        support_unit_usage: 2,
        support_unit_name: '棘刺'
      }
    })
    loaded.value = false
  })
  it('restores saved choices and supplies defaults when loading old config', async () => {
    setup()
    const legacy = {
      free_blacklist: '',
      reload_room: '',
      maa_mall_buy: '',
      maa_mall_blacklist: '',
      maa_weekly_plan_active: '默认',
      favorite: '',
      reclamation_algorithm: {},
      secret_front: {}
    }
    let config = {
      ...legacy,
      sss: { scripts: [{ id: 'b'.repeat(64), type: 2, ec: 3, times: 4 }], run_id: 'sss-round' },
      copilot: { scripts: [{ id: 'a'.repeat(64), is_raid: true }], formation: true }
    }
    axios.get.mockImplementation(async (url) => ({
      data: url.endsWith('/conf') ? config : { plans: ['默认'] }
    }))
    await store.load_config()
    expect(store.sss.scripts[0]).toEqual({ id: 'b'.repeat(64), type: 2, ec: 3, times: 4 })
    expect(store.sss.run_id).toBe('sss-round')
    expect(store.copilot.formation).toBe(true)
    expect(store.copilot.scripts[0].is_raid).toBe(true)
    expect(store.copilot.use_sanity_potion).toBe(false)
    config = legacy
    await store.load_config()
    expect(store.sss.scripts).toEqual([])
    expect(store.sss.run_id).toBe('')
    expect(store.copilot.scripts).toEqual([])
    expect(store.copilot.formation).toBe(false)
    expect(store.copilot.support_unit_usage).toBe(0)
    expect(store.copilot.run_id).toBe('')
    expect(axios.patch).not.toHaveBeenCalled()
  })
})

describe('SSS queue autosave', () => {
  it('saves independent navigation and successful round targets with manual restart', async () => {
    const loaded = setup()
    for (const key of ['reload_room', 'maa_mall_buy', 'maa_mall_blacklist']) store[key] = []
    axios.patch.mockResolvedValue({ data: {} })
    loaded.value = true
    await nextTick()
    await store.flush_config_saves()
    store.maa_long_task_type = 'sss'
    store.sss.scripts.push({ id: 'a'.repeat(64), type: 1, ec: 2, times: 2 })
    store.sss.scripts.push({ id: 'b'.repeat(64), type: 2, ec: 3, times: 3 })
    store.sss.run_id = 'sss-new-round'
    await vi.waitFor(() => expect(axios.patch).toHaveBeenCalledOnce())
    expect(axios.patch.mock.calls[0][1]).toMatchObject({
      maa_long_task_type: 'sss',
      sss: { scripts: store.sss.scripts, run_id: 'sss-new-round' }
    })
    loaded.value = false
  })
})
