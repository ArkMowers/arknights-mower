import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, effectScope, nextTick, reactive, ref } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createMemoryHistory, createRouter } from 'vue-router'
import { THEME_KEY } from 'vue-echarts'
import Report from './report.vue'
import { ORDER_COLORS, ORDER_TYPES } from '@/utils/baseReport'
const state = vi.hoisted(() => ({
  client: null,
  mounted: null,
  theme: null,
  provided: new Map(),
  media: null,
  report: null,
  trading: null,
  tradingRange: null,
  tradingError: false,
  calls: { report: 0, orundum: 0, trading: 0 },
  restores: 0,
  restoreFail: false
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
vi.mock('@/stores/gui', () => ({ useGuiStore: () => state.gui }))
vi.mock('@/stores/report', () => ({
  useReportStore: () => ({
    getReportData: async () => {
      state.calls.report += 1
      return state.report
    },
    getOrundumData: async () => {
      state.calls.orundum += 1
      return []
    },
    getTradingHistory: async (start, end) => {
      state.calls.trading += 1
      state.tradingRange = [start, end]
      if (state.tradingError) throw new Error('offline')
      return state.trading
    },
    getOrderCandles: (...args) => state.orderRequest(...args),
    restoreTradingHistory: vi.fn(async () => {
      state.restores = (state.restores || 0) + 1
      if (state.restoreFail) throw new Error('offline')
    })
  })
}))
describe('基报读取 Mower 收益设置', () => {
  beforeEach(() => {
    state.theme = ref('system')
    state.report = [{ 日期: '2026-10-12', 赤金: 1000, 龙门币订单: 10000, 作战录像: 2000 }]
    state.trading = [{ 日期: '2026-10-12', 龙舌兰: 1 }]
    state.tradingRange = null
    state.tradingError = false
    state.calls = { report: 0, orundum: 0, trading: 0 }
    state.restores = 0
    state.restoreFail = false
    state.orderRequest = vi.fn(async (startDate, endDate, period) => ({
      startDate,
      endDate,
      period,
      candles: [{ start: 1, count: 1, close: 2000 }]
    }))
    state.gui = reactive({
      baseReportMode: 'standard',
      loaded: true,
      loading: false,
      reportModeSaving: false,
      reportModeError: '',
      get reportModeDisabled() {
        return !this.loaded || this.loading || this.reportModeSaving
      },
      load: vi.fn(async () => true),
      setBaseReportMode: vi.fn(async (value) => {
        state.gui.baseReportMode = value
        return true
      }),
      retryReportMode: vi.fn(async () => true)
    })
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
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('仅选择订单指标时查询含当前游戏日的小时记录，并保留四小时默认周期', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-28T10:00:00+08:00'))
    const scope = effectScope()
    try {
      const page = scope.run(() => Report.setup({}, { expose: vi.fn() }))
      await state.mounted()
      expect(state.orderRequest).not.toHaveBeenCalled()
      await page.setMarketMetric('orders')
      expect(state.orderRequest).toHaveBeenCalledExactlyOnceWith('2026-10-15', '2026-10-28', '4h')
      expect(page.orderCandles.value).toEqual([{ start: 1, count: 1, close: 2000 }])
      expect(page.orderCandleRange.value).toEqual({
        startDate: '2026-10-15',
        endDate: '2026-10-28'
      })
      page.range.value = '7'
      await nextTick()
      await nextTick()
      expect(state.orderRequest).toHaveBeenLastCalledWith('2026-10-22', '2026-10-28', '4h')
      await page.setOrderPeriod('1h')
      expect(state.orderRequest).toHaveBeenLastCalledWith('2026-10-22', '2026-10-28', '1h')
      await page.setMarketMetric('income')
      page.range.value = '30'
      await nextTick()
      expect(state.orderRequest).toHaveBeenCalledTimes(3)
    } finally {
      scope.stop()
    }
  })

  it('更换周期立即移除旧桶，较晚返回的旧请求不能替换新周期', async () => {
    const pending = new Map()
    state.orderRequest.mockImplementation(
      (_start, _end, period) => new Promise((resolve) => pending.set(period, resolve))
    )
    const scope = effectScope()
    try {
      const page = scope.run(() => Report.setup({}, { expose: vi.fn() }))
      const older = page.setMarketMetric('orders')
      const newer = page.setOrderPeriod('1h')
      expect(page.orderCandles.value).toEqual([])
      pending.get('1h')({ period: '1h', candles: [{ start: 2, close: 1500 }] })
      await newer
      pending.get('4h')({ period: '4h', candles: [{ start: 1, close: 2500 }] })
      await older
      expect(page.orderCandles.value).toEqual([{ start: 2, close: 1500 }])
      expect(page.orderCandlesLoading.value).toBe(false)
    } finally {
      scope.stop()
    }
  })

  it('订单读取失败显示独立错误，重试与刷新不影响收益数据', async () => {
    state.orderRequest.mockRejectedValueOnce(new Error('offline'))
    const scope = effectScope()
    try {
      const page = scope.run(() => Report.setup({}, { expose: vi.fn() }))
      await state.mounted()
      const income = page.allDays.value[0].income.total
      await page.setMarketMetric('orders')
      expect(page.orderCandlesError.value).toContain('读取失败')
      expect(page.orderCandlesLoading.value).toBe(false)
      expect(page.allDays.value[0].income.total).toBe(income)
      await page.loadOrderCandles()
      expect(page.orderCandlesError.value).toBe('')
      expect(page.orderCandles.value).toHaveLength(1)
      await page.restoreHistory()
      expect(state.orderRequest).toHaveBeenCalledTimes(3)
    } finally {
      scope.stop()
    }
  })

  it('没有基报的实例仍可在股票终端切换查看订单记录', async () => {
    state.report = false
    state.gui.baseReportMode = 'stock'
    const scope = effectScope()
    try {
      const page = scope.run(() => Report.setup({}, { expose: vi.fn() }))
      await state.mounted()
      expect(page.hasData.value).toBe(false)
      expect(page.stockFill.value).toBe(true)
      await page.setMarketMetric('orders')
      expect(page.orderCandles.value).toHaveLength(1)
    } finally {
      scope.stop()
    }
  })

  it('退出订单指标或卸载后不接受仍在返回的订单结果', async () => {
    let finish
    state.orderRequest.mockImplementation(() => new Promise((resolve) => (finish = resolve)))
    const scope = effectScope()
    const page = scope.run(() => Report.setup({}, { expose: vi.fn() }))
    const opening = page.setMarketMetric('orders')
    await page.setMarketMetric('income')
    scope.stop()
    finish({ period: '4h', candles: [{ start: 1, close: 2500 }] })
    await opening
    expect(page.orderCandles.value).toEqual([])
  })

  it('收益设置入口保留会话凭证并定位全部设置的账号面板', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: ['/', '/settings'].map((path) => ({
        path,
        component: { render: () => null }
      }))
    })
    await router.push('/?token=session-token')
    const app = createSSRApp(Report)
    app.use(router)
    const html = await renderToString(app)
    expect(html).toContain('href="/settings?token=session-token#task-accounts"')
    expect(html).toContain('管理收益设置')
  })

  it('基建报表的图表跟随系统变化，显式主题保留用户选择', () => {
    const scope = effectScope()
    try {
      state.media.matches = true
      scope.run(() => Report.setup({}, { expose: vi.fn() }))
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
  it('股票终端按当前明暗主题选择终端皮肤', () => {
    state.theme.value = 'light'
    const scope = effectScope()
    try {
      const page = scope.run(() => Report.setup({}, { expose: vi.fn() }))
      expect(page.isDark.value).toBe(false)
      state.theme.value = 'dark'
      expect(page.isDark.value).toBe(true)
      state.theme.value = 'light'
      expect(page.isDark.value).toBe(false)
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
      const orderLine = page.tradingOption.value.series.find((series) => series.type === 'line')
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
        page.tradingOption.value,
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
  it('订单分布按贸易订单记录拆分金额并生成 dataset 与提示', async () => {
    state.report[0]['龙门币订单数'] = 5
    state.report[0]['每单获取龙门币'] = 2000
    state.trading = [{ 日期: '2026-10-12', 但书_2000: 2, 龙舌兰: 1 }]
    const scope = effectScope()
    try {
      const page = scope.run(() => Report.setup({}, { expose: vi.fn() }))
      await state.mounted()
      const [row] = page.orderRows.value
      expect(row['但书_2000']).toBe(4000)
      expect(row['龙舌兰']).toBe(2500)
      expect(row['未知订单']).toBe(3500)
      expect(row['未知订单数']).toBe(2)
      expect(row['订单质量']).toBe(2000)
      expect(page.unknownOrderTotal.value).toBe(3500)
      const option = page.orderOption.value
      expect(option.dataset.dimensions).toEqual([
        '日期',
        ...ORDER_TYPES,
        '未知订单',
        '订单质量',
        '赤金',
        '龙门币订单',
        '订单数',
        '未知订单数'
      ])
      expect(option.dataset.source).toBe(page.orderRows.value)
      expect(option.legend.selected).toEqual({ 赤金: false, 订单质量: true })
      expect(option.xAxis.type).toBe('category')
      expect(option.yAxis).toHaveLength(2)
      const typeBar = option.series.find((series) => series.name === '但书_2000')
      expect(typeBar.type).toBe('bar')
      expect(typeBar.stack).toBe('订单金额')
      expect(typeBar.color).toBe(ORDER_COLORS.light['但书_2000'])
      const unknownBar = option.series.find((series) => series.name === '未知订单')
      expect(unknownBar.stack).toBe('订单金额')
      expect(unknownBar.color).toBe(ORDER_COLORS.light['未知订单'])
      const qualityLine = option.series.find((series) => series.type === 'line')
      expect(qualityLine.name).toBe('订单质量')
      expect(qualityLine.yAxisIndex).toBe(1)
      expect(qualityLine.connectNulls).toBe(false)
      expect(qualityLine.label.formatter({ data: row })).toBe('2,000')
      expect(qualityLine.label.formatter({ data: {} })).toBe('')
      const tooltip = option.tooltip.formatter([{ dataIndex: 0 }])
      expect(tooltip).toContain('2026-10-12')
      expect(tooltip).toContain('总订单数')
      expect(tooltip).toContain('但书_2000')
      expect(tooltip).toContain('2 单')
      expect(tooltip).toContain('未知订单')
      expect(tooltip).toContain('3,500')
      expect(tooltip).toContain('10,000')
    } finally {
      scope.stop()
    }
  })
  it('订单分布跟随统计区间只保留区间内日期', async () => {
    state.report = Array.from({ length: 10 }, (_, index) => ({
      日期: `2026-10-${String(index + 3).padStart(2, '0')}`,
      赤金: 1000,
      龙门币订单: 10000,
      龙门币订单数: 4,
      每单获取龙门币: 2500,
      作战录像: 2000
    }))
    const scope = effectScope()
    try {
      const page = scope.run(() => Report.setup({}, { expose: vi.fn() }))
      await state.mounted()
      expect(page.orderRows.value).toHaveLength(10)
      page.range.value = '7'
      expect(page.orderRows.value.map((row) => row['日期'])).toEqual([
        '2026-10-06',
        '2026-10-07',
        '2026-10-08',
        '2026-10-09',
        '2026-10-10',
        '2026-10-11',
        '2026-10-12'
      ])
      expect(page.orderRows.value.some((row) => row['日期'] === '2026-10-05')).toBe(false)
    } finally {
      scope.stop()
    }
  })
  it('恢复历史后重新读取基报和贸易订单', async () => {
    const scope = effectScope()
    try {
      const page = scope.run(() => Report.setup({}, { expose: vi.fn() }))
      await state.mounted()
      expect(state.calls.report).toBe(1)
      expect(state.calls.trading).toBe(1)
      expect(page.restoreBusy.value).toBe(false)
      await page.restoreHistory()
      expect(state.restores).toBe(1)
      expect(page.restoreBusy.value).toBe(false)
      expect(page.restoreError.value).toBe('')
      expect(state.calls.report).toBe(2)
      expect(state.calls.orundum).toBe(2)
      expect(state.calls.trading).toBe(2)
    } finally {
      scope.stop()
    }
  })
  it('恢复历史失败时提示错误并保留当前数据', async () => {
    state.restoreFail = true
    const scope = effectScope()
    try {
      const page = scope.run(() => Report.setup({}, { expose: vi.fn() }))
      await state.mounted()
      await page.restoreHistory()
      expect(state.restores).toBe(1)
      expect(page.restoreError.value).toContain('恢复历史失败')
      expect(page.restoreBusy.value).toBe(false)
      expect(state.calls.report).toBe(1)
      expect(page.loadError.value).toBe('')
      expect(page.hasData.value).toBe(true)
      expect(page.orderRows.value).toHaveLength(1)
    } finally {
      scope.stop()
    }
  })
  it('没有贸易记录时未知订单等于基报金额且不出现 NaN', async () => {
    state.trading = []
    state.report[0]['龙门币订单数'] = 4
    const scope = effectScope()
    try {
      const page = scope.run(() => Report.setup({}, { expose: vi.fn() }))
      await state.mounted()
      const [row] = page.orderRows.value
      expect(row['未知订单']).toBe(10000)
      expect(row['未知订单数']).toBe(4)
      expect(row['但书_2000']).toBe(0)
      expect(row['订单质量']).toBeNull()
      expect(page.unknownOrderTotal.value).toBe(10000)
      for (const value of Object.values(row)) {
        expect(Number.isNaN(value)).toBe(false)
      }
    } finally {
      scope.stop()
    }
  })
  it('挂载时读取显示偏好并允许切换股票模式', async () => {
    const scope = effectScope()
    try {
      const page = scope.run(() => Report.setup({}, { expose: vi.fn() }))
      await state.mounted()
      expect(state.gui.load).toHaveBeenCalledOnce()
      expect(page.isStock.value).toBe(false)
      expect(page.modeDisabled.value).toBe(false)
      await page.switchMode('stock')
      expect(state.gui.setBaseReportMode).toHaveBeenCalledWith('stock')
      expect(page.isStock.value).toBe(true)
      await page.switchMode('standard')
      expect(state.gui.setBaseReportMode).toHaveBeenLastCalledWith('standard')
      expect(page.isStock.value).toBe(false)
    } finally {
      scope.stop()
    }
  })
  it('页头渲染标准与股票模式切换，股票模式沿用同一份数据', async () => {
    const renderPage = async () => {
      const router = createRouter({
        history: createMemoryHistory(),
        routes: ['/', '/settings'].map((path) => ({
          path,
          component: { render: () => null }
        }))
      })
      await router.push('/?token=session-token')
      const app = createSSRApp(Report)
      app.use(router)
      return await renderToString(app)
    }
    const standard = await renderPage()
    expect(standard).toContain('基建报表显示模式')
    expect(standard).toContain('标准')
    expect(standard).toContain('股票')
    expect(standard).toContain('正在读取基报')
    state.gui.baseReportMode = 'stock'
    const scope = effectScope()
    try {
      const page = scope.run(() => Report.setup({}, { expose: vi.fn() }))
      await state.mounted()
      expect(page.isStock.value).toBe(true)
      expect(page.hasData.value).toBe(true)
      expect(page.orderRows.value).toHaveLength(1)
    } finally {
      scope.stop()
    }
  })
  it('股票模式无数据时保留页头，有数据后才让终端占满内容区', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: ['/', '/settings'].map((path) => ({
        path,
        component: { render: () => null }
      }))
    })
    await router.push('/?token=session-token')
    state.gui.baseReportMode = 'stock'
    const app = createSSRApp(Report)
    app.use(router)
    const html = await renderToString(app)
    // 初次加载还没有行情：页头保留，标准/区间/刷新入口可达。
    expect(html).not.toContain('page--fill')
    expect(html).toContain('基建报表显示模式')
    expect(html).toContain('page-header')
    expect(html).toContain('正在读取基报')
    const scope = effectScope()
    try {
      const page = scope.run(() => Report.setup({}, { expose: vi.fn() }))
      await state.mounted()
      expect(page.isStock.value).toBe(true)
      expect(page.stockFill.value).toBe(true)
    } finally {
      scope.stop()
    }
  })

  it('终端帮助弹窗等待菜单关闭与全屏退出后再显示', async () => {
    const scope = effectScope()
    try {
      const page = scope.run(() => Report.setup({}, { expose: vi.fn() }))
      let finishClose
      const close = vi.fn(() => new Promise((resolve) => (finishClose = resolve)))
      const opening = page.openTerminalHelp(close)
      expect(close).toHaveBeenCalledOnce()
      expect(page.showTerminalHelp.value).toBe(false)
      finishClose()
      await opening
      expect(page.showTerminalHelp.value).toBe(true)
    } finally {
      scope.stop()
    }
  })
  it('保存显示偏好失败时保留原模式并显示错误', async () => {
    state.gui.setBaseReportMode = vi.fn(async () => {
      state.gui.reportModeError = '基建报表显示偏好保存失败，已恢复原来的显示。请重试。'
      return false
    })
    const scope = effectScope()
    try {
      const page = scope.run(() => Report.setup({}, { expose: vi.fn() }))
      await state.mounted()
      await page.switchMode('stock')
      expect(page.isStock.value).toBe(false)
      const router = createRouter({
        history: createMemoryHistory(),
        routes: ['/', '/settings'].map((path) => ({
          path,
          component: { render: () => null }
        }))
      })
      await router.push('/?token=session-token')
      const app = createSSRApp(Report)
      app.use(router)
      const html = await renderToString(app)
      expect(html).toContain('基建报表显示偏好保存失败')
      expect(html).toContain('重试')
      await page.retryMode()
      expect(state.gui.retryReportMode).toHaveBeenCalledOnce()
    } finally {
      scope.stop()
    }
  })
  it('偏好读取失败或保存中时禁用模式切换', async () => {
    state.gui.loaded = false
    const scope = effectScope()
    try {
      const page = scope.run(() => Report.setup({}, { expose: vi.fn() }))
      await state.mounted()
      expect(page.modeDisabled.value).toBe(true)
      await page.switchMode('stock')
      expect(state.gui.setBaseReportMode).not.toHaveBeenCalled()
      state.gui.loaded = true
      state.gui.reportModeSaving = true
      expect(page.modeDisabled.value).toBe(true)
    } finally {
      scope.stop()
    }
  })
  it('交易记录读取失败时股票模式仍可切换并显示未知订单', async () => {
    state.tradingError = true
    state.gui.baseReportMode = 'stock'
    const scope = effectScope()
    try {
      const page = scope.run(() => Report.setup({}, { expose: vi.fn() }))
      await state.mounted()
      expect(page.isStock.value).toBe(true)
      const [row] = page.orderRows.value
      expect(row['未知订单']).toBe(10000)
    } finally {
      scope.stop()
    }
  })
})
