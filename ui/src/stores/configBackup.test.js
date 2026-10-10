import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, nextTick, ref } from 'vue'
import { createPinia } from 'pinia'
import axios from 'axios'
import { useConfigStore } from './config'
import { usePlanStore } from './plan'
import { createSaveCoordinator, drainConfigurationSaves } from '@/utils/configPersistence'
import { readFileSync } from 'node:fs'
import { compileScript, parse } from '@vue/compiler-sfc'

// Execute the page's actual handler with isolated stores and transport.
const { descriptor } = parse(readFileSync(new URL('../pages/Plan.vue', import.meta.url), 'utf8'))
const script = compileScript(descriptor, { id: 'restore-running-plan-test' })
const restoreNode = script.scriptSetupAst.find((node) => node.id?.name === 'restoreRunningPlan')
const restoreCode = descriptor.scriptSetup.content
  .slice(restoreNode.start, restoreNode.end)
  .replaceAll('import.meta.env.VITE_HTTP_URL', JSON.stringify('/api'))

function pageRestoreHandler(dependencies) {
  return new Function(...Object.keys(dependencies), `${restoreCode}; return restoreRunningPlan`)(
    ...Object.values(dependencies)
  )
}

vi.mock('axios', () => ({ default: { post: vi.fn(), patch: vi.fn(), get: vi.fn() } }))
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
  axios.patch.mockResolvedValue({ data: {} })
  return { config, plan, loaded }
}

describe('configuration restore autosave coordination', () => {
  it('restores startup advanced settings and reloads both stores before autosave resumes', async () => {
    const { config, plan, loaded } = setup()
    plan.set_advanced_settings_source(() => config.build_advanced_settings())
    config.drone_count_limit = 20
    config.drone_interval = 3
    loaded.value = true
    await drainConfigurationSaves(config, plan)
    const restoredConfig = {
      ...config.build_config(),
      drone_count_limit: 150,
      drone_interval: 2,
      maa_weekly_plan_active: '默认'
    }
    const restoredPlan = plan.build_plan()
    restoredPlan.advanced_settings.drone_count_limit = 150
    restoredPlan.advanced_settings.drone_interval = 2
    const saves = createSaveCoordinator(config, plan)
    const busy = ref(false)
    const message = { success: vi.fn(), error: vi.fn() }
    axios.get.mockImplementation(async (url) => {
      expect(saves.paused.value).toBe(true)
      if (url.endsWith('/conf')) return { data: restoredConfig }
      if (url.endsWith('/plan')) return { data: restoredPlan }
      if (url.endsWith('/weekly-plans')) return { data: { plans: ['默认'] } }
      throw new Error(`Unexpected read: ${url}`)
    })
    const restore = pageRestoreHandler({
      rescue: false,
      running: ref(true),
      restoring_running_plan: busy,
      edit_locked: saves.paused,
      import_saves: saves,
      axios,
      sub_plan: ref('main'),
      config_store: config,
      load_plan: () => plan.load_plan(),
      message
    })
    axios.post.mockClear()
    axios.patch.mockClear()

    await restore()
    await drainConfigurationSaves(config, plan)

    expect(config.drone_count_limit).toBe(150)
    expect(config.drone_interval).toBe(2)
    expect(saves.paused.value).toBe(false)
    expect(busy.value).toBe(false)
    expect(message.error).not.toHaveBeenCalled()
    expect(message.success).toHaveBeenCalledWith('已还原为当前运行排班表及高级设置')
    expect(axios.patch).not.toHaveBeenCalled()
    expect(
      axios.post.mock.calls.filter(([url]) => url.endsWith('/plan/restore-running'))
    ).toHaveLength(1)
    const savedPlans = axios.post.mock.calls.filter(([url]) => url.endsWith('/plan'))
    expect(savedPlans).toHaveLength(1)
    expect(savedPlans[0][1].advanced_settings.drone_count_limit).toBe(150)
    loaded.value = false
  })

  it.each(['write', 'config read', 'plan read'])(
    'handles %s failure without saving stale restored settings',
    async (stage) => {
      const paused = ref(false)
      const busy = ref(false)
      const configRead = vi.fn().mockResolvedValue(undefined)
      const planRead = vi.fn().mockResolvedValue(undefined)
      const saves = {
        pauseAndDrain: vi.fn(async () => {
          paused.value = true
        }),
        resume: vi.fn(() => {
          paused.value = false
        })
      }
      const message = { success: vi.fn(), error: vi.fn() }
      axios.post.mockResolvedValue({ data: {} })
      if (stage === 'write') axios.post.mockRejectedValue(new Error('write failed'))
      if (stage === 'config read') configRead.mockRejectedValue(new Error('read failed'))
      if (stage === 'plan read') planRead.mockRejectedValue(new Error('read failed'))
      const restore = pageRestoreHandler({
        rescue: false,
        running: ref(true),
        restoring_running_plan: busy,
        edit_locked: paused,
        import_saves: saves,
        axios,
        sub_plan: ref('backup'),
        config_store: { load_config: configRead },
        load_plan: planRead,
        message
      })

      await restore()

      expect(busy.value).toBe(false)
      expect(message.success).not.toHaveBeenCalled()
      if (stage === 'write') {
        expect(configRead).not.toHaveBeenCalled()
        expect(planRead).not.toHaveBeenCalled()
        expect(saves.resume).toHaveBeenCalledOnce()
        expect(paused.value).toBe(false)
      } else {
        expect(saves.resume).not.toHaveBeenCalled()
        expect(paused.value).toBe(true)
        expect(message.error.mock.lastCall[0]).toContain('请刷新页面；自动保存已暂停')
        if (stage === 'config read') expect(planRead).not.toHaveBeenCalled()
      }
    }
  )

  it('includes current advanced settings in saved plans without the drone room', async () => {
    const { config, plan } = setup()
    plan.set_advanced_settings_source(() => config.build_advanced_settings())
    config.drone_room = 'room_1_1'
    config.drone_count_limit = 140
    config.resting_threshold = 75
    config.product_switching = { waiting_seconds: 5 }
    await plan.save_plan()
    const saved = axios.post.mock.lastCall[1].advanced_settings
    expect(saved.drone_count_limit).toBe(140)
    expect(saved.resting_threshold).toBe(0.75)
    expect(saved.product_switching.waiting_seconds).toBe(5)
    expect(saved).not.toHaveProperty('drone_room')
  })

  it('saves and reloads dorm order as part of the plan', async () => {
    const { plan } = setup()
    plan.dorm_order = ['dormitory_1', 'dormitory_2', 'dormitory_3', 'dormitory_4']
    await plan.save_plan()
    expect(axios.post.mock.lastCall[1].conf.dorm_order).toBe(
      'dormitory_1,dormitory_2,dormitory_3,dormitory_4'
    )
    axios.get.mockResolvedValue({
      data: {
        conf: { ling_xi: 1, dorm_order: 'dormitory_2_3' },
        plan1: {},
        backup_plans: []
      }
    })
    await plan.load_plan()
    expect(plan.dorm_order).toEqual(['dormitory_2', 'dormitory_1', 'dormitory_3', 'dormitory_4'])
  })

  it('drains scheduled edits then prevents old stores from overwriting restored values', async () => {
    const { config, plan, loaded } = setup()
    loaded.value = true
    await vi.waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1))
    config.account = 'latest draft'
    await nextTick()
    const saves = createSaveCoordinator(config, plan)
    await saves.pauseAndDrain()
    expect(axios.patch.mock.calls.findLast(([url]) => url.endsWith('/conf'))[1].account).toBe(
      'latest draft'
    )
    const count = axios.post.mock.calls.length
    const patchCount = axios.patch.mock.calls.length
    config.account = 'stale value'
    plan.ling_xi = 2
    await nextTick()
    expect(axios.post).toHaveBeenCalledTimes(count)
    expect(axios.patch).toHaveBeenCalledTimes(patchCount)
  })

  it('restart drains requests without resubmitting stale browser settings', async () => {
    const { config, plan, loaded } = setup()
    loaded.value = true
    await drainConfigurationSaves(config, plan)
    axios.post.mockClear()
    axios.patch.mockClear()
    // A manually restored file can now differ from this unchanged page.
    await drainConfigurationSaves(config, plan)
    expect(axios.post).not.toHaveBeenCalled()
    expect(axios.patch).not.toHaveBeenCalled()
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
    axios.patch.mockClear()
    config.account = 'edit during restart'
    plan.ling_xi = 2
    await nextTick()
    expect(axios.post).not.toHaveBeenCalled()
    expect(axios.patch).not.toHaveBeenCalled()
    expect(saves.paused.value).toBe(true)
    saves.resume()
    await drainConfigurationSaves(config, plan)
    expect(axios.patch.mock.calls.find(([url]) => url.endsWith('/conf'))[1].account).toBe(
      'edit during restart'
    )
    expect(axios.post.mock.calls.find(([url]) => url.endsWith('/plan'))[1].conf.ling_xi).toBe(2)
  })

  it('waits for in-flight requests before starting maintenance', async () => {
    const { config, plan } = setup()
    let finish
    axios.patch.mockImplementationOnce(
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
    axios.patch.mockRejectedValueOnce(new Error('save failed'))
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

  it('saves dorm order only in the plan', async () => {
    const { config, plan, loaded } = setup()
    loaded.value = true
    await drainConfigurationSaves(config, plan)
    plan.dorm_order = ['dormitory_2', 'dormitory_1', 'dormitory_3', 'dormitory_4']
    await nextTick()
    await drainConfigurationSaves(config, plan)
    expect(axios.patch).not.toHaveBeenCalled()
    const confPayload = config.build_config()
    const planPayload = axios.post.mock.calls.findLast(([url]) => url.endsWith('/plan'))[1]
    expect(confPayload).not.toHaveProperty('dorm_order')
    expect(planPayload.conf.dorm_order).toBe('dormitory_2,dormitory_1,dormitory_3,dormitory_4')
  })
})
