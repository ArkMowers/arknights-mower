import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, effectScope, ref } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createMemoryHistory, createRouter } from 'vue-router'
import { THEME_KEY } from 'vue-echarts'
import Report from './report.vue'
import TradingAnalysis from './trading_analysis.vue'
const state = vi.hoisted(() => ({
  client: null,
  mounted: null,
  theme: null,
  provided: new Map(),
  media: null,
  report: null,
  tradingRange: null,
  tradingError: false
}))
vi.mock('vue', async (original) => {
  const library = await original()
  return {
    ...library,
    useSSRContext: () => ({ modules: new Set() }),
    inject: (key, ...args) => (key === 'axios' ? state.client : library.inject(key, ...args)),
    provide: (key, value) => state.provided.set(key, value),
    onMounted: (callback) => {
      state.mounted = callback
    }
  }
})
vi.mock('naive-ui', async (original) => {
  const library = await original()
  const wrapper = {
    setup:
      (_, { slots }) =>
      () =>
        slots.default?.()
  }
  return { ...library, NDropdown: wrapper, NTooltip: wrapper, NGrid: wrapper }
})
vi.mock('@/stores/config', () => ({ useConfigStore: () => ({ theme: state.theme }) }))
vi.mock('@/stores/report', () => ({
  useReportStore: () => ({
    getReportData: async () => state.report,
    getOrundumData: async () => [],
    getTradingHistory: async (start, end) => {
      state.tradingRange = [start, end]
      if (state.tradingError) throw new Error('offline')
      return [{ 日期: '2026-10-12', 龙舌兰: 1 }]
    }
  })
}))
describe('基报读取 Mower 收益设置', () => {
  beforeEach(() => {
    state.theme = ref('system')
    state.report = [{ 日期: '2026-10-12', 赤金: 1000, 龙门币订单: 10000, 作战录像: 2000 }]
    state.tradingRange = null
    state.tradingError = false
    state.provided.clear()
    const listeners = new Set()
    state.media = {
      matches: false,
      addEventListener: (_type, listener) => listeners.add(listener),
      removeEventListener: (_type, listener) => listeners.delete(listener),
      change(matches) {
        this.matches = matches
        for (const listener of listeners) listener({ matches })
      }
    }
    vi.stubGlobal('window', { matchMedia: () => state.media })
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
  afterEach(() => vi.unstubAllGlobals())

  it('收益设置入口保留会话凭证并定位全部设置的账号面板', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: ['/', '/task-settings'].map((path) => ({
        path,
        component: { render: () => null }
      }))
    })
    await router.push('/?token=session-token')
    const app = createSSRApp(Report)
    app.use(router)
    const html = await renderToString(app)
    expect(html).toContain('href="/task-settings?token=session-token#task-accounts"')
    expect(html).toContain('管理收益设置')
  })

  it.each([
    ['基建报表', Report],
    ['贸易订单分析', TradingAnalysis]
  ])('%s 的图表跟随系统变化，显式主题保留用户选择', (_name, component) => {
    const scope = effectScope()
    try {
      state.media.matches = true
      scope.run(() => component.setup({}, { expose: vi.fn() }))
      const chartTheme = state.provided.get(THEME_KEY)
      expect(chartTheme.value).toBe('dark')
      expect(state.theme.value).toBe('system')
      state.media.change(false)
      expect(chartTheme.value).toBe('roma')
      expect(state.theme.value).toBe('system')
      state.theme.value = 'dark'
      state.media.change(false)
      expect(chartTheme.value).toBe('dark')
      state.theme.value = 'light'
      state.media.change(true)
      expect(chartTheme.value).toBe('roma')
      expect(state.theme.value).toBe('light')
    } finally {
      scope.stop()
    }
  })
  it('使用服务器确认的系数计算包含特殊赤金的收益', async () => {
    const scope = effectScope()
    try {
      const page = scope.run(() => Report.setup({}, { expose: vi.fn() }))
      await state.mounted()
      expect(state.client.get.mock.calls[0][0]).toContain('/report/recycling_settings')
      expect(state.tradingRange).toEqual(['2026-10-12', '2026-10-12'])
      expect(page.allDays.value[0].income.total).toBeCloseTo(1.06)
      expect(page.loadError.value).toBe('')
      expect(page.ready.value).toBe(true)
      const tooltip = page.incomeOption.value.tooltip.formatter([{ dataIndex: 0 }])
      expect(tooltip).toContain('1.060')
      expect(tooltip).toContain('特殊赤金 500')
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
      expect(page.allDays.value[0].income.total).toBeCloseTo(0.52)
    } finally {
      scope.stop()
    }
  })
  it.each(['刷新先开始', '保存先开始'])('%s时刷新结果保留保存成功的收益算法', async (order) => {
    const scope = effectScope()
    try {
      const page = scope.run(() => Report.setup({}, { expose: vi.fn() }))
      await state.mounted()
      const rows = state.report
      let finishReport
      state.report = new Promise((resolve) => {
        finishReport = () => resolve(rows)
      })
      let finishSave
      state.client.put.mockImplementationOnce(
        (_url, data) =>
          new Promise((resolve) => {
            finishSave = () => resolve({ data })
          })
      )
      let refreshing
      let saving
      if (order === '刷新先开始') {
        refreshing = page.load()
        saving = page.selectAlgorithm(0)
      } else {
        saving = page.selectAlgorithm(0)
        refreshing = page.load()
      }
      finishSave()
      await saving
      expect(page.valuation.value.base_algorithm).toBe(0)
      expect(page.allDays.value[0].income.total).toBeCloseTo(0.52)
      finishReport()
      await refreshing
      expect(page.loadError.value).toBe('')
      expect(page.valuation.value.base_algorithm).toBe(0)
      expect(page.allDays.value[0].income.total).toBeCloseTo(0.52)
    } finally {
      scope.stop()
    }
  })
  it('收益和每单龙门币折线直接显示数字，缺失读数不显示为零', async () => {
    state.report[0]['龙门币订单数'] = 4
    const scope = effectScope()
    try {
      const page = scope.run(() => Report.setup({}, { expose: vi.fn() }))
      await state.mounted()
      const incomeLine = page.incomeOption.value.series.find((series) => series.type === 'line')
      const orderLine = page.orderOption.value.series.find((series) => series.type === 'line')
      expect(incomeLine.label.show).toBe(true)
      expect(incomeLine.label.formatter({ value: incomeLine.data[0] })).toBe('1.06')
      expect(incomeLine.label.formatter({ value: 0 })).toBe('0.00')
      expect(incomeLine.label.formatter({ value: null })).toBe('')
      expect(orderLine.label.show).toBe(true)
      expect(orderLine.label.formatter({ value: orderLine.data[0] })).toBe('2,500')
      expect(orderLine.label.formatter({ value: 0 })).toBe('0')
      expect(orderLine.label.formatter({ value: null })).toBe('')
    } finally {
      scope.stop()
    }
  })
  it('基报产出保留折算前各项数值，切换收益算法不改变产出对比', async () => {
    const scope = effectScope()
    try {
      const page = scope.run(() => Report.setup({}, { expose: vi.fn() }))
      await state.mounted()
      page.chartView.value = 'production'
      const outputs = () =>
        Object.fromEntries(
          page.mainChartOption.value.series.map((series) => [
            series.name,
            series.data.map((point) => point.value)
          ])
        )
      const expected = { 赤金: [1000], 特殊赤金: [500], 经验: [2000], 龙门币订单: [10000] }
      expect(outputs()).toEqual(expected)
      expect(
        page.productionOption.value.series.find((series) => series.name === '经验').color
      ).toBe('#f3e28f')
      await page.selectAlgorithm(0)
      expect(outputs()).toEqual(expected)
      expect(page.allDays.value[0].income.total).toBeCloseTo(0.52)
      page.chartView.value = 'income'
      expect(
        page.mainChartOption.value.series.find((series) => series.name === '收益').data
      ).toEqual([expect.closeTo(0.52)])
    } finally {
      scope.stop()
    }
  })
  it('各图保留保存图片入口，并使用当前主题的背景', async () => {
    state.theme.value = 'light'
    const scope = effectScope()
    try {
      const page = scope.run(() => Report.setup({}, { expose: vi.fn() }))
      await state.mounted()
      const charts = () => [
        page.incomeOption.value,
        page.productionOption.value,
        page.orderOption.value,
        page.orundumOption.value
      ]
      for (const chart of charts()) {
        expect(chart.toolbox.feature.saveAsImage.show).toBe(true)
        expect(chart.toolbox.feature.saveAsImage.title).toBe('保存为图片')
        expect(chart.toolbox.feature.saveAsImage.backgroundColor).toBe('#fff')
      }
      state.theme.value = 'dark'
      for (const chart of charts()) {
        expect(chart.toolbox.feature.saveAsImage.backgroundColor).toBe('#18181c')
      }
    } finally {
      scope.stop()
    }
  })
  it('原始产出区分未读到的数据和零产出，提示说明赤金与经验的单位', async () => {
    state.report[0]['赤金'] = null
    state.report[0]['作战录像'] = 0
    const scope = effectScope()
    try {
      const page = scope.run(() => Report.setup({}, { expose: vi.fn() }))
      await state.mounted()
      const series = page.productionOption.value.series
      expect(series.find((item) => item.name === '赤金').data[0].value).toBeNull()
      expect(series.find((item) => item.name === '经验').data[0].value).toBe(0)
      const tooltip = page.productionOption.value.tooltip.formatter([{ dataIndex: 0 }])
      expect(tooltip).toContain('赤金（制造价值）')
      expect(tooltip).toContain('特殊赤金（订单额外价值）')
      expect(tooltip).toContain('经验')
      expect(tooltip).toContain('—')
    } finally {
      scope.stop()
    }
  })
  it('全部数据未读到时说明收益无法计算，不提示已按零计算', async () => {
    state.report = [{ 日期: '2026-10-12', 赤金: null, 龙门币订单: null, 作战录像: null }]
    const scope = effectScope()
    try {
      const page = scope.run(() => Report.setup({}, { expose: vi.fn() }))
      await state.mounted()
      const tooltip = page.incomeOption.value.tooltip.formatter([{ dataIndex: 0 }])
      expect(tooltip).toContain('无法计算当天收益')
      expect(tooltip).not.toContain('按 0')
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
      expect(page.allDays.value[0].income.total).toBeCloseTo(1.06)
      await page.saveAlgorithm(-1, page.customRatios)
      expect(page.allDays.value[0].income.total).toBeCloseTo(0.76)
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
      expect(page.allDays.value[0].income.total).toBeCloseTo(1.06)
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
      expect(page.loadError.value).not.toBe('')
      expect(page.ready.value).toBe(false)
      expect(page.allDays.value).toEqual([])
    } finally {
      scope.stop()
    }
  })
  it('基报文件不存在时显示空状态而不是报错', async () => {
    state.report = false
    const scope = effectScope()
    try {
      const page = scope.run(() => Report.setup({}, { expose: vi.fn() }))
      await state.mounted()
      expect(page.loadError.value).toBe('')
      expect(page.ready.value).toBe(true)
      expect(page.hasData.value).toBe(false)
      expect(state.tradingRange).toBeNull()
    } finally {
      scope.stop()
    }
  })
  it('贸易记录读取失败仍显示基报并提示特殊赤金未计入', async () => {
    state.tradingError = true
    const scope = effectScope()
    try {
      const page = scope.run(() => Report.setup({}, { expose: vi.fn() }))
      await state.mounted()
      expect(page.allDays.value[0].income.total).toBeCloseTo(1.04)
      expect(page.partialWarning.value).toContain('特殊赤金未计入')
    } finally {
      scope.stop()
    }
  })
})
