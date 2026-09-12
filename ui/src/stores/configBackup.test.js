import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, nextTick, ref } from 'vue'
import { createPinia } from 'pinia'
import axios from 'axios'
import { useConfigStore } from './config'
import { usePlanStore } from './plan'
import { createSaveCoordinator, drainConfigurationSaves } from '@/utils/configPersistence'

vi.mock('axios', () => ({ default: { post: vi.fn(), get: vi.fn() } }))
let stores = []
afterEach(() => {
  for (const store of stores) store.$dispose()
  stores = []
  vi.clearAllMocks()
})

function setup() {
  const loaded = ref(false)
  const app = createApp({})
  app.use(createPinia())
  app.provide('loaded', loaded)
  const config = app.runWithContext(() => useConfigStore())
  const plan = app.runWithContext(() => usePlanStore())
  stores = [config, plan]
  for (const name of ['reload_room', 'maa_mall_buy', 'maa_mall_blacklist']) config[name] = []
  plan.plan = plan.fill_empty({})
  axios.post.mockResolvedValue({ data: {} })
  return { config, plan, loaded }
}

describe('configuration restore autosave coordination', () => {
  it('clears the browser dorm order after a changed plan is saved', async () => {
    const { config, plan } = setup()
    config.dorm_order = ['dormitory_1_2']
    axios.post.mockResolvedValueOnce({ data: { dorm_order_reset: true } })
    await plan.save_plan()
    expect(config.dorm_order).toEqual([])
    config.dorm_order = ['dormitory_2_3']
    axios.post.mockResolvedValueOnce({ data: { dorm_order_reset: false } })
    await plan.save_plan()
    expect(config.dorm_order).toEqual(['dormitory_2_3'])
  })

  it('preserves the browser dorm order when saving a plan fails', async () => {
    const { config, plan } = setup()
    config.dorm_order = ['dormitory_1_2']
    axios.post.mockRejectedValueOnce(new Error('offline'))
    await expect(plan.save_plan()).rejects.toThrow('offline')
    expect(config.dorm_order).toEqual(['dormitory_1_2'])
  })

  it('drains scheduled edits then prevents old stores from overwriting restored values', async () => {
    const { config, plan, loaded } = setup()
    loaded.value = true
    await vi.waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2))
    config.account = 'latest draft'
    await nextTick()
    const saves = createSaveCoordinator(config, plan)
    await saves.pauseAndDrain()
    expect(axios.post.mock.calls.findLast(([url]) => url.endsWith('/conf'))[1].account).toBe(
      'latest draft'
    )
    const count = axios.post.mock.calls.length
    config.account = 'stale value'
    plan.ling_xi = 2
    await nextTick()
    expect(axios.post).toHaveBeenCalledTimes(count)
  })

  it('restart drains requests without resubmitting stale browser settings', async () => {
    const { config, plan, loaded } = setup()
    loaded.value = true
    await drainConfigurationSaves(config, plan)
    axios.post.mockClear()
    // A manually restored file can now differ from this unchanged page.
    await drainConfigurationSaves(config, plan)
    expect(axios.post).not.toHaveBeenCalled()
  })

  it('preserves imported dorm order at startup and resets it only for a new plan', async () => {
    const { config, plan } = setup()
    axios.get.mockResolvedValue({
      data: { conf: { ling_xi: 1 }, plan1: {}, backup_plans: [] }
    })
    config.dorm_order = ['dormitory_3', 'dormitory_1']
    await plan.load_plan({ resetDormOrder: false })
    expect(config.dorm_order).toEqual(['dormitory_3', 'dormitory_1'])
    await plan.load_plan()
    expect(config.dorm_order).toEqual([])
  })
})

describe('maintenance save coordination', () => {
  it('keeps edits paused after drain until the operation explicitly resumes', async () => {
    const { config, plan, loaded } = setup()
    loaded.value = true
    await drainConfigurationSaves(config, plan)
    const saves = createSaveCoordinator(config, plan)
    await saves.pauseAndDrain()
    axios.post.mockClear()
    config.account = 'edit during restart'
    plan.ling_xi = 2
    await nextTick()
    expect(axios.post).not.toHaveBeenCalled()
    expect(saves.paused.value).toBe(true)
    saves.resume()
    await drainConfigurationSaves(config, plan)
    expect(axios.post.mock.calls.find(([url]) => url.endsWith('/conf'))[1].account).toBe(
      'edit during restart'
    )
    expect(axios.post.mock.calls.find(([url]) => url.endsWith('/plan'))[1].conf.ling_xi).toBe(2)
  })

  it('waits for in-flight requests before starting maintenance', async () => {
    const { config, plan } = setup()
    let finish
    axios.post.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve
        })
    )
    const pending = config.save_config()
    const saves = createSaveCoordinator(config, plan)
    let drained = false
    const draining = saves.pauseAndDrain().then(() => {
      drained = true
    })
    await vi.waitFor(() => expect(finish).toBeTypeOf('function'))
    expect(drained).toBe(false)
    expect(saves.paused.value).toBe(true)
    finish({ data: {} })
    await pending
    await draining
    expect(drained).toBe(true)
  })

  it('releases its pause when a queued save fails', async () => {
    const { config, plan } = setup()
    axios.post.mockRejectedValueOnce(new Error('save failed'))
    const saving = config.save_config().catch(() => {})
    const saves = createSaveCoordinator(config, plan)
    await expect(saves.pauseAndDrain()).rejects.toThrow('save failed')
    await saving
    expect(saves.paused.value).toBe(false)
    expect(config.autosave_paused).toBe(false)
    expect(plan.autosave_paused).toBe(false)
  })

  it('does not release a pause held by another component', async () => {
    const { config, plan } = setup()
    const importing = createSaveCoordinator(config, plan)
    const restarting = createSaveCoordinator(config, plan)
    await importing.pauseAndDrain()
    await expect(restarting.pauseAndDrain()).rejects.toThrow('正在进行')
    restarting.resume()
    expect(config.autosave_paused).toBe(true)
    expect(plan.autosave_paused).toBe(true)
    importing.resume()
    expect(config.autosave_paused).toBe(false)
  })

  it('keeps the pause when reattaching to a persisted process operation', async () => {
    const { config, plan } = setup()
    await createSaveCoordinator(config, plan).pauseAndDrain()
    const remounted = createSaveCoordinator(config, plan)
    remounted.pause({ pendingOperation: true })
    expect(remounted.paused.value).toBe(true)
    expect(config.autosave_paused).toBe(true)
    expect(plan.autosave_paused).toBe(true)
  })

  it('drains a config save triggered by plan completion', async () => {
    const { config, plan, loaded } = setup()
    loaded.value = true
    await drainConfigurationSaves(config, plan)
    config.dorm_order = ['dormitory_1_2']
    await nextTick()
    await config.flush_config_saves()
    axios.post.mockResolvedValueOnce({ data: { dorm_order_reset: true } })
    const saving = plan.save_plan()
    await drainConfigurationSaves(config, plan)
    await saving
    expect(axios.post.mock.calls.findLast(([url]) => url.endsWith('/conf'))[1].dorm_order).toBe('')
  })
})
