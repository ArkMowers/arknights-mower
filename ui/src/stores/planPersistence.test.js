import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, nextTick, reactive, ref } from 'vue'
import { createPinia } from 'pinia'
import axios from 'axios'
import { usePlanStore, useRescuePlanStore } from './plan'
import { createSaveCoordinator } from '@/utils/configPersistence'

vi.mock('axios', () => ({ default: { post: vi.fn(), get: vi.fn() } }))

let stores = []
afterEach(() => {
  stores.forEach((store) => store.$dispose())
  stores = []
  vi.restoreAllMocks()
  vi.resetAllMocks()
})

function deferred() {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

function setup() {
  const loaded = ref(false)
  const app = createApp({})
  app.use(createPinia())
  app.provide('loaded', loaded)
  const [normal, rescue] = app.runWithContext(() => [usePlanStore(), useRescuePlanStore()])
  stores = [normal, rescue]
  for (const store of stores) store.plan = store.fill_empty({})
  axios.post.mockResolvedValue({ data: {} })
  return { normal, rescue, loaded }
}

describe('schedule save coalescing', () => {
  it('serializes and sends only the first and latest of eight edits while a request is pending', async () => {
    const { normal, loaded } = setup()
    const first = deferred()
    axios.post.mockReturnValueOnce(first.promise)
    normal.plan.central.plans[0].agent = '阿米娅'
    loaded.value = true
    await vi.waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1))
    const stringify = vi.spyOn(JSON, 'stringify')

    for (let index = 1; index < 8; index += 1) {
      normal.plan.central.plans[0].group = `编组${index}`
      await nextTick()
    }
    const draining = normal.wait_for_plan_save()
    expect(axios.post).toHaveBeenCalledTimes(1)
    expect(axios.post.mock.calls[0][1].plan1.central.plans[0].group).toBe('')
    const queuedSerializations = stringify.mock.calls.filter(
      ([value]) => value?.default === 'plan1'
    ).length

    first.resolve({ data: { saved: 'first' } })
    await draining

    expect(axios.post).toHaveBeenCalledTimes(2)
    expect(queuedSerializations).toBe(0)
    expect(axios.post.mock.lastCall[1].plan1.central.plans[0].group).toBe('编组7')
    expect(stringify.mock.calls.filter(([value]) => value?.default === 'plan1')).toHaveLength(1)
  })

  it('resolves merged callers with the latest response and propagates its failure', async () => {
    const { normal } = setup()
    const first = deferred()
    const latest = deferred()
    axios.post.mockReturnValueOnce(first.promise).mockReturnValueOnce(latest.promise)
    const saving = normal.save_plan()
    await vi.waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1))
    normal.ling_xi = 2
    const pending = normal.save_plan()
    normal.ling_xi = 3
    const merged = normal.save_plan()
    const failures = [
      expect(pending).rejects.toThrow('save failed'),
      expect(merged).rejects.toThrow('save failed')
    ]

    first.resolve({ data: { saved: 'first' } })
    await expect(saving).resolves.toEqual({ data: { saved: 'first' } })
    await vi.waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2))
    expect(axios.post.mock.lastCall[1].conf.ling_xi).toBe(3)
    latest.reject(new Error('save failed'))
    await Promise.all(failures)
    await expect(normal.wait_for_plan_save()).rejects.toThrow('save failed')

    axios.post.mockResolvedValue({ data: { saved: 'retry' } })
    await expect(normal.save_plan()).resolves.toEqual({ data: { saved: 'retry' } })
  })

  it('continues saving the latest draft after the in-flight request fails', async () => {
    const { normal } = setup()
    const first = deferred()
    axios.post.mockReturnValueOnce(first.promise)
    const failure = expect(normal.save_plan()).rejects.toThrow('old save failed')
    await vi.waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1))
    normal.ling_xi = 2
    const saving = normal.save_plan()
    first.reject(new Error('old save failed'))
    await failure
    await saving
    expect(axios.post).toHaveBeenCalledTimes(2)
    expect(axios.post.mock.lastCall[1].conf.ling_xi).toBe(2)
  })

  it('drains the latest queued draft before paused stores can reload', async () => {
    const { normal, loaded } = setup()
    const first = deferred()
    const latest = deferred()
    axios.post.mockReturnValueOnce(first.promise).mockReturnValueOnce(latest.promise)
    loaded.value = true
    await vi.waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1))
    normal.ling_xi = 2
    await nextTick()
    normal.ling_xi = 3
    await nextTick()
    const config = reactive({ autosave_paused: false, flush_config_saves: vi.fn(async () => {}) })
    const coordinator = createSaveCoordinator(config, normal)
    let drained = false
    const draining = coordinator.pauseAndDrain().then(() => {
      drained = true
    })
    await nextTick()
    expect(normal.autosave_paused).toBe(true)
    first.resolve({ data: {} })
    await vi.waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2))
    expect(drained).toBe(false)
    expect(axios.post.mock.lastCall[1].conf.ling_xi).toBe(3)
    latest.resolve({ data: {} })
    await draining
    normal.ling_xi = 1
    await nextTick()
    expect(axios.post).toHaveBeenCalledTimes(2)
    coordinator.resume()
    await nextTick()
    await normal.wait_for_plan_save()
    expect(axios.post.mock.lastCall[1].conf.ling_xi).toBe(1)
  })

  it('keeps tracking nested plan and advanced-setting edits after a pending save completes', async () => {
    const { normal, loaded } = setup()
    const advanced = reactive({ dorm_isolation: [['红', '砾']] })
    normal.set_advanced_settings_source(() => advanced)
    axios.get.mockResolvedValue({
      data: { conf: {}, plan1: {}, backup_plans: [{ name: '副表', conf: {}, plan: {} }] }
    })
    await normal.load_plan()
    loaded.value = true
    await nextTick()
    await normal.wait_for_plan_save()
    normal.plan.central.plans[0].agent = '阿米娅'
    normal.plan.central.plans[0].replacement.push('红')
    normal.backup_plans[0].plan.central.plans[0].agent = '陈'
    advanced.dorm_isolation[0].push('斑点')
    await nextTick()
    await normal.wait_for_plan_save()

    const saved = axios.post.mock.lastCall[1]
    expect(saved.plan1.central.plans[0].replacement).toEqual(['红'])
    expect(saved.backup_plans[0].plan.central.plans[0].agent).toBe('陈')
    expect(saved.advanced_settings.dorm_isolation).toEqual([['红', '砾', '斑点']])
  })

  it('keeps normal and rescue pending requests independent', async () => {
    const { normal, rescue } = setup()
    const firstNormal = deferred()
    axios.post.mockImplementation((url) =>
      url.endsWith('/plan') ? firstNormal.promise : Promise.resolve({ data: {} })
    )
    const saving = normal.save_plan()
    await vi.waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1))
    normal.ling_xi = 2
    const pendingNormal = normal.save_plan()
    rescue.ling_xi = 3
    await rescue.save_plan()
    expect(axios.post.mock.lastCall[0]).toBe(`${import.meta.env.VITE_HTTP_URL}/rescue-plan`)
    expect(axios.post.mock.lastCall[1].conf.ling_xi).toBe(3)
    firstNormal.resolve({ data: {} })
    await saving
    await pendingNormal
    expect(axios.post.mock.lastCall[0]).toBe(`${import.meta.env.VITE_HTTP_URL}/plan`)
    expect(axios.post.mock.lastCall[1].conf.ling_xi).toBe(2)
  })
})
