import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, effectScope, nextTick, ref } from 'vue'
import { createPinia } from 'pinia'
import axios from 'axios'
import ConfigBackup from './ConfigBackup.vue'
import { useConfigStore } from '@/stores/config'
import { usePlanStore, useRescuePlanStore } from '@/stores/plan'
import { reloadImportedConfiguration } from '@/utils/configBackup'
import { drainConfigurationSaves } from '@/utils/configPersistence'

vi.mock('axios', () => ({ default: { post: vi.fn(), patch: vi.fn(), get: vi.fn() } }))
vi.mock('@/utils/configBackup', () => ({
  consumeImportResult: () => null,
  reloadImportedConfiguration: vi.fn()
}))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))

let scope, component, config, plan, rescuePlan, loaded

beforeEach(() => {
  vi.clearAllMocks()
  const app = createApp({})
  app.use(createPinia())
  loaded = ref(false)
  app.provide('loaded', loaded)
  app.provide('axios', axios)
  config = app.runWithContext(() => useConfigStore())
  plan = app.runWithContext(() => usePlanStore())
  rescuePlan = app.runWithContext(() => useRescuePlanStore())
  for (const key of ['reload_room', 'maa_mall_buy', 'maa_mall_blacklist']) config[key] = []
  plan.plan = plan.fill_empty({})
  rescuePlan.plan = rescuePlan.fill_empty({})
  axios.post.mockResolvedValue({ data: { ok: true, message: '配置已导入' } })
  axios.patch.mockResolvedValue({ data: {} })
  scope = effectScope()
  component = scope.run(() => app.runWithContext(() => ConfigBackup.setup({}, { expose: vi.fn() })))
  component.selected.value = new File(['zip'], 'backup.zip')
})

afterEach(() => {
  scope.stop()
  for (const store of [config, plan, rescuePlan]) store.$dispose()
})

describe('backup import save boundary', () => {
  it('drains a pending rescue-plan save before importing and keeps every store paused', async () => {
    let finish
    axios.post.mockImplementationOnce(
      () => new Promise((resolve) => (finish = () => resolve({ data: {} })))
    )
    const rescueSaving = rescuePlan.save_plan()
    const wait = vi.spyOn(rescuePlan, 'wait_for_plan_save')
    const importing = component.importConfig()
    try {
      await vi.waitFor(() => expect(wait).toHaveBeenCalledOnce())
      expect(axios.post.mock.calls.map(([url]) => url)).toEqual([
        expect.stringContaining('/rescue-plan')
      ])
      for (const store of [config, plan, rescuePlan]) expect(store.autosave_paused).toBe(true)
    } finally {
      finish()
      await rescueSaving
      await importing
    }
    expect(axios.post.mock.calls.map(([url]) => url)).toEqual([
      expect.stringContaining('/rescue-plan'),
      expect.stringContaining('/config-backup/import')
    ])
    for (const store of [config, plan, rescuePlan]) expect(store.autosave_paused).toBe(true)
    expect(reloadImportedConfiguration).toHaveBeenCalledOnce()
  })

  it.each([
    new Error('连接中断'),
    { response: { status: 500, data: { message: '响应未完成' } } },
    { response: { status: 409, data: { code: 'configuration_changed' } } }
  ])('keeps all old drafts paused when import outcome requires a reload: %j', async (failure) => {
    axios.get.mockResolvedValueOnce({ data: { conf: {}, plan1: {}, backup_plans: [] } })
    await rescuePlan.load_plan()
    loaded.value = true
    await drainConfigurationSaves(config, plan, [rescuePlan])
    axios.post.mockClear()
    axios.patch.mockClear()
    axios.post.mockRejectedValueOnce(failure)
    await component.importConfig()
    expect(component.pendingReload.value).toBe(false)
    for (const store of [config, plan, rescuePlan]) expect(store.autosave_paused).toBe(true)
    config.account = 'old account draft'
    rescuePlan.ling_xi = 2
    await nextTick()
    await drainConfigurationSaves(config, plan, [rescuePlan])
    await component.importConfig()
    expect(axios.post).toHaveBeenCalledOnce()
    expect(axios.patch).not.toHaveBeenCalled()
    expect(reloadImportedConfiguration).not.toHaveBeenCalled()
    const actual = await vi.importActual('@/utils/configBackup')
    const entries = new Map([['mower-config-import-result', '{"message":"earlier import"}']])
    const session = {
      setItem: (key, value) => entries.set(key, value),
      removeItem: (key) => entries.delete(key)
    }
    const location = { reload: vi.fn() }
    reloadImportedConfiguration.mockImplementationOnce((result) =>
      actual.reloadImportedConfiguration(result, { session, location })
    )
    component.reload()
    expect(reloadImportedConfiguration).toHaveBeenCalledExactlyOnceWith(null)
    expect(entries.get('mower-config-imported')).toBe('1')
    expect(entries.has('mower-config-import-result')).toBe(false)
    expect(location.reload).toHaveBeenCalledOnce()
  })

  it('resumes after a validation rejection and allows a corrected import', async () => {
    axios.post.mockRejectedValueOnce({ response: { status: 400, data: { message: '备份无效' } } })
    await component.importConfig()
    for (const store of [config, plan, rescuePlan]) expect(store.autosave_paused).toBe(false)
    expect(component.error.value).toBe('备份无效')
    await component.importConfig()
    expect(axios.post).toHaveBeenCalledTimes(2)
    expect(component.pendingReload.value).toBe(true)
  })

  it('retains reload recovery if a successful import cannot reload automatically', async () => {
    reloadImportedConfiguration.mockImplementationOnce(() => {
      throw new Error('刷新失败')
    })
    await component.importConfig()
    expect(component.pendingReload.value).toBe(true)
    for (const store of [config, plan, rescuePlan]) expect(store.autosave_paused).toBe(true)
    expect(component.error.value).toContain('自动刷新未完成')
    component.reload()
    expect(reloadImportedConfiguration).toHaveBeenCalledTimes(2)
  })
})
