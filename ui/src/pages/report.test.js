import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'
import Report from './report.vue'
const state = vi.hoisted(() => ({ client: null, mounted: null }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  inject: () => state.client,
  onMounted: (callback) => {
    state.mounted = callback
  }
}))
vi.mock('@/stores/config', async () => {
  const { ref } = await import('vue')
  return { useConfigStore: () => ({ theme: ref('light') }) }
})
vi.mock('@/stores/report', () => ({
  useReportStore: () => ({
    getReportData: async () => [
      { 日期: '2026-10-12', 赤金: 1000, 龙门币订单: 10000, 作战录像: 2000 }
    ],
    getOrundumData: async () => [],
    getTradingHistory: async () => [{ 日期: '2026-10-12', 龙舌兰: 1 }]
  })
}))
describe('基报读取 Mower 收益设置', () => {
  beforeEach(() => {
    state.client = {
      put: vi.fn().mockImplementation(async (_url, data) => ({ data })),
      get: vi.fn().mockResolvedValue({
        data: {
          base_algorithm: -1,
          base_algorithm_saved: true,
          ratios: { gold: 0.4, order: 0.6, experience: 2, efficiency: 1 }
        }
      })
    }
  })
  it('使用服务器确认的系数计算包含特殊赤金的收益', async () => {
    const scope = effectScope()
    try {
      const page = scope.run(() => Report.setup({}, { expose: vi.fn() }))
      await state.mounted()
      expect(state.client.get.mock.calls[0][0]).toContain('/report/recycling_settings')
      expect(page.ReportData.value[0].收益).toBe(1.06)
      expect(page.show_alert.value).toBe(false)
      const tooltip = page.option_manufactor.value.tooltip.formatter([
        { data: page.ReportData.value[0], marker: '', seriesName: '赤金' },
        { marker: '', seriesName: '经验' },
        { marker: '', seriesName: '订单' }
      ])
      expect(tooltip).toContain('收益:10600')
    } finally {
      scope.stop()
    }
  })
  it('报表原入口选择预设会保存共用算法并刷新收益', async () => {
    const scope = effectScope()
    try {
      const page = scope.run(() => Report.setup({}, { expose: vi.fn() }))
      await state.mounted()
      await page.selectAlgorithm(0)
      expect(state.client.put).toHaveBeenCalledWith(
        expect.stringContaining('/report/recycling_settings'),
        {
          base_algorithm: 0,
          ratios: { experience: 1, gold: 0.8, order: 0.2, efficiency: 1 }
        }
      )
      expect(page.valuation.value.base_algorithm).toBe(0)
      expect(page.ReportData.value[0].收益).toBe(0.52)
    } finally {
      scope.stop()
    }
  })
  it('自定义系数在确认保存前不修改共用设置', async () => {
    const scope = effectScope()
    try {
      const page = scope.run(() => Report.setup({}, { expose: vi.fn() }))
      await state.mounted()
      page.selectAlgorithm(-1)
      page.customRatios.order = 0.3
      expect(state.client.put).not.toHaveBeenCalled()
      expect(page.ReportData.value[0].收益).toBe(1.06)
      await page.saveAlgorithm(-1, page.customRatios)
      expect(page.ReportData.value[0].收益).toBe(0.76)
      expect(page.showCustomAlgorithm.value).toBe(false)
    } finally {
      scope.stop()
    }
  })
  it('保存失败保留当前算法、收益和自定义草稿以便重试', async () => {
    state.client.put.mockRejectedValue(new Error('offline'))
    const scope = effectScope()
    try {
      const page = scope.run(() => Report.setup({}, { expose: vi.fn() }))
      await state.mounted()
      page.selectAlgorithm(-1)
      page.customRatios.order = 0.3
      await page.saveAlgorithm(-1, page.customRatios)
      expect(page.ReportData.value[0].收益).toBe(1.06)
      expect(page.valuation.value.ratios.order).toBe(0.6)
      expect(page.showCustomAlgorithm.value).toBe(true)
      expect(page.algorithmError.value).toContain('保存失败')
      expect(page.algorithmBusy.value).toBe(false)
    } finally {
      scope.stop()
    }
  })
  it('设置读取失败不按默认算法显示收益', async () => {
    state.client.get.mockRejectedValue(new Error('offline'))
    const scope = effectScope()
    try {
      const page = scope.run(() => Report.setup({}, { expose: vi.fn() }))
      await state.mounted()
      expect(page.show_alert.value).toBe(true)
      expect(page.show_earnings_chart.value).toBe(false)
    } finally {
      scope.stop()
    }
  })
})
