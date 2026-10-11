import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'
import RecyclingStats from './RecyclingStats.vue'
const state = vi.hoisted(() => ({ client: null }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  inject: () => state.client,
  onMounted: vi.fn()
}))
vi.mock('@/stores/config', async () => {
  const { ref } = await import('vue')
  return { useConfigStore: () => ({ theme: ref('light') }) }
})
const settings = () => ({
  prices: { 装置: 8 },
  source: '内置快照',
  ratios: { experience: 1, gold: 0.8, order: 0.25, efficiency: 1 }
})
const report = { total: 0, materials: [], qualities: [], records: [], comparison: null }
describe('回收站收益配置', () => {
  let scope, page
  beforeEach(() => {
    state.client = {
      get: vi.fn().mockResolvedValue({ data: report }),
      put: vi.fn(),
      post: vi.fn(),
      delete: vi.fn()
    }
    scope = effectScope()
    page = scope.run(() => RecyclingStats.setup({}, { expose: vi.fn() }))
    page.applySettings(settings())
  })
  afterEach(() => {
    scope.stop()
    vi.restoreAllMocks()
  })
  it('提交比例快照并在保存成功后重新读取统计', async () => {
    page.ratios.experience = 2
    const saved = { ...settings(), ratios: { ...page.ratios } }
    let complete
    state.client.put.mockImplementation(
      () =>
        new Promise((resolve) => {
          complete = resolve
        })
    )
    const pending = page.updateSettings('ratios')
    page.ratios.experience = 3
    expect(state.client.put.mock.calls[0][1].ratios.experience).toBe(2)
    expect(page.settingsBusy.value).toBe(true)
    await page.updateSettings('reset')
    expect(state.client.delete).not.toHaveBeenCalled()
    complete({ data: saved })
    await pending
    expect(page.ratios.experience).toBe(2)
    expect(state.client.get.mock.calls[0][0]).toContain('/report/recycling_history')
    expect(page.settingsBusy.value).toBe(false)
  })
  it('导入新增材料显示合并结果，并允许再次选择同一文件', async () => {
    const next = {
      ...settings(),
      prices: { 装置: 8, 新材料: 20 },
      last_import: { updated: 1, added: 1, retained: 1, unpriced: [] }
    }
    state.client.post.mockResolvedValue({ data: next })
    const file = Object.assign(new Blob(['xlsx']), { name: 'values.xlsx' })
    const input = { files: [file], value: 'values.xlsx' }
    await page.importValues({ target: input })
    expect(state.client.post.mock.calls[0][0]).toContain('/recycling_settings/import')
    expect(state.client.post.mock.calls[0][1].get('file')).toBeInstanceOf(Blob)
    expect(page.valuation.value.prices.新材料).toBe(20)
    expect(page.settingsMessage.value).toContain('新增 1 项')
    expect(input.value).toBe('')
  })
  it('导入失败保留已确认配置并展示后端原因', async () => {
    state.client.post.mockRejectedValue({ response: { data: { error: '物品 ID 与名称不符' } } })
    await page.updateSettings('import', new Blob(['bad']))
    expect(page.valuation.value).toEqual(settings())
    expect(page.settingsError.value).toBe('物品 ID 与名称不符')
    expect(state.client.get).not.toHaveBeenCalled()
    expect(page.settingsBusy.value).toBe(false)
  })
  it('恢复默认值同步输入和收益，读取失败允许重试', async () => {
    page.ratios.gold = 2
    state.client.delete.mockResolvedValue({ data: settings() })
    await page.updateSettings('reset')
    expect(page.ratios.gold).toBe(0.8)
    state.client.get.mockRejectedValueOnce(new Error('offline'))
    await page.loadSettings()
    expect(page.settingsError.value).toContain('读取失败')
    state.client.get.mockResolvedValueOnce({ data: settings() })
    await page.loadSettings()
    expect(page.settingsError.value).toBe('')
  })
})
