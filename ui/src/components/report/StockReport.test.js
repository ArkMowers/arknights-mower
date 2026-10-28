import { readFileSync } from 'node:fs'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, effectScope, h, reactive } from 'vue'
import { renderToString } from 'vue/server-renderer'
import StockReport from './StockReport.vue'
import { ORDER_COLORS, ORDER_TYPES } from '@/utils/baseReport'

vi.mock('vue', async (original) => {
  const library = await original()
  return { ...library, useSSRContext: () => ({ modules: new Set() }) }
})

function makeDay(date, total, index = 0) {
  return {
    date,
    gold: 70000 + index * 100,
    experience: 30000 + index * 100,
    orders: 30000 + index * 100,
    orderCount: 12,
    tequilaGold: 500,
    closureGold: 200,
    orundum: 60,
    income: {
      total,
      gold: total * 0.4,
      special: total * 0.1,
      order: total * 0.3,
      experience: total * 0.2,
      partial: false
    }
  }
}
function dateAt(index) {
  return '2026-10-' + String(index + 1).padStart(2, '0')
}
const totals = [
  9, 8.6, 8.2, 7.8, 7.4, 7, 7.2, 7.6, 8, 8.4, 8.8, 9.2, 9.6, 8.2, 3.2, 8.6, 8.8, 9, 8.6, 8.2, 8.4,
  8.8
]
const fixtureDays = totals.map((total, index) => makeDay(dateAt(index), total, index))
const fixtureOrderRows = fixtureDays.map((day) => ({
  日期: day.date,
  但书_2000: 8000,
  订单质量: 2500,
  订单数: 12,
  赤金: 70000,
  未知订单: 22000,
  未知订单数: 8
}))
const baseProps = {
  days: fixtureDays,
  historyDays: fixtureDays,
  selectedDay: fixtureDays.at(-1),
  previousDay: fixtureDays.at(-2),
  summary: { best: fixtureDays[12] },
  orderRows: fixtureOrderRows,
  metric: 'income',
  orderPeriod: '4h',
  orderCandles: [],
  orderCandlesLoading: false,
  orderCandlesError: '',
  algorithmLabel: '0.23456 算法',
  rangeLabel: '14 天',
  range: '14'
}
const bucketStart = Date.parse('2026-10-22T04:00:00+08:00') / 1000
const fixtureCandles = [
  {
    start: bucketStart,
    end: bucketStart + 14400,
    label: '2026-10-22 04:00',
    open: 1000,
    high: 2500,
    low: 1000,
    close: 1500,
    mean: 5000 / 3,
    count: 3,
    amount: 5000
  },
  {
    start: bucketStart + 14400,
    end: bucketStart + 28800,
    label: '2026-10-22 08:00',
    open: null,
    high: null,
    low: null,
    close: null,
    mean: null,
    count: 0,
    amount: 0
  },
  {
    start: bucketStart + 28800,
    end: bucketStart + 43200,
    label: '2026-10-22 12:00',
    open: 2000,
    high: 2000,
    low: 2000,
    close: 2000,
    mean: 2000,
    count: 1,
    amount: 2000
  },
  {
    start: bucketStart + 43200,
    end: bucketStart + 57600,
    label: '2026-10-22 16:00',
    open: 2500,
    high: 2500,
    low: 1000,
    close: 1000,
    mean: 1750,
    count: 2,
    amount: 3500
  }
]
function mount(overrides = {}) {
  const scope = effectScope()
  const emit = vi.fn()
  const props = reactive({ ...baseProps, ...overrides })
  const page = scope.run(() => StockReport.setup(props, { expose: vi.fn(), emit }))
  return { page, emit, props, scope }
}
function render(props) {
  return renderToString(createSSRApp({ render: () => h(StockReport, props) }))
}
afterEach(() => vi.unstubAllGlobals())

describe('StockReport 指标、周期与视图', () => {
  it('默认每日收益走势，收益只提供周月真实 K 线周期', () => {
    const { page, scope } = mount()
    try {
      expect(page.activeMetric.value).toBe('income')
      expect(page.activePeriod.value).toBe('trend')
      expect(page.isTrend.value).toBe(true)
      expect(page.periodOptions.value.map((row) => row.value)).toEqual(['trend', 'week', 'month'])
      expect(page.NAV_TABS.map((row) => row.key)).toEqual(['chart', 'heat', 'list'])
    } finally {
      scope.stop()
    }
  })

  it('指标和订单周期通过父状态更新，收益周期独立保留', () => {
    const { page, props, emit, scope } = mount()
    try {
      page.setPeriod('week')
      expect(page.activePeriod.value).toBe('week')
      page.setMetric('orders')
      expect(emit).toHaveBeenCalledWith('change-metric', 'orders')
      expect(page.activeMetric.value).toBe('income')
      props.metric = 'orders'
      expect(page.activePeriod.value).toBe('4h')
      expect(page.periodOptions.value.map((row) => row.value)).toEqual(['1h', '4h', 'day'])
      page.setPeriod('1h')
      expect(emit).toHaveBeenCalledWith('change-order-period', '1h')
      props.orderPeriod = '1h'
      page.setPeriod('day')
      expect(emit).toHaveBeenLastCalledWith('change-order-period', 'day')
      props.metric = 'income'
      expect(page.activePeriod.value).toBe('week')
      page.setPeriod('day')
      expect(page.activePeriod.value).toBe('week')
      page.setMetric('income')
      expect(emit).toHaveBeenCalledTimes(3)
    } finally {
      scope.stop()
    }
  })

  it('图表、热力和列表切换时复位滚动，区间变更交给父页面', async () => {
    const { page, emit, scope } = mount()
    try {
      page.bodyRef.value = { scrollTop: 80 }
      await page.setNav('heat')
      expect(page.chartViewActive.value).toBe(false)
      expect(page.bodyRef.value.scrollTop).toBe(0)
      await page.setNav('list')
      expect(page.navActive.value).toBe('list')
      await page.setNav('chart')
      expect(page.chartViewActive.value).toBe(true)
      page.setRange('7')
      expect(emit).toHaveBeenCalledWith('change-range', '7')
      page.setRange('14')
      expect(emit).toHaveBeenCalledTimes(1)
    } finally {
      scope.stop()
    }
  })

  it('标准模式、算法和恢复历史沿用现有页面动作', async () => {
    const { page, emit, scope } = mount()
    try {
      page.switchToStandard()
      await page.selectAlgorithm(1)
      await page.restoreHistory()
      await page.refresh()
      expect(emit.mock.calls).toEqual([
        ['change-mode', 'standard'],
        ['select-algorithm', 1],
        ['restore-history'],
        ['refresh']
      ])
      page.menuOpen.value = true
      await page.closeMenu()
      expect(page.menuOpen.value).toBe(false)
    } finally {
      scope.stop()
    }
    const disabled = mount({ modeDisabled: true })
    try {
      disabled.page.switchToStandard()
      expect(disabled.emit).not.toHaveBeenCalled()
    } finally {
      disabled.scope.stop()
    }
  })
})

describe('StockReport 实际收益周月 K 线', () => {
  const history = [
    makeDay('2026-09-28', 7),
    makeDay('2026-09-29', 9),
    makeDay('2026-09-30', 8),
    makeDay('2026-10-01', 6),
    makeDay('2026-10-02', 10),
    { ...makeDay('2026-10-03', 3), income: { ...makeDay('', 3).income, partial: true } },
    makeDay('2026-10-04', 5),
    makeDay('2026-10-05', 12)
  ]

  it('周K使用同周完整日收益首末和极值，保留可见区间之外的周内记录', () => {
    const { page, emit, scope } = mount({
      days: history.slice(6),
      historyDays: history,
      selectedDay: history[6]
    })
    try {
      page.setPeriod('week')
      const option = page.candleOption.value
      expect(option.series[0].type).toBe('candlestick')
      expect(option.series[0].data).toEqual([
        [7, 5, 5, 10],
        [12, 12, 12, 12]
      ])
      expect(option.series.find((row) => row.name === '日收益均值').data[0]).toBe(7.5)
      expect(option.series.find((row) => row.name === '完整读数天数').data[0].value).toBe(6)
      expect(page.displayQuote.value.closeText).toBe('5.00')
      expect(page.displayDetails.value.find((row) => row.key === 'missing').value).toBe('1')
      expect(option.tooltip.formatter([{ dataIndex: 0 }])).toContain('1 天读数不完整')
      page.onChartClick({ dataIndex: 1 })
      expect(page.selectedBucket.value.close).toBe(12)
      expect(emit).not.toHaveBeenCalled()
    } finally {
      scope.stop()
    }
  })

  it('月K的开收来自同月首末日，不使用上月收盘伪造当月开盘', () => {
    const days = [
      makeDay('2026-09-29', 7),
      makeDay('2026-09-30', 9),
      makeDay('2026-10-01', 5),
      makeDay('2026-10-02', 9)
    ]
    const { page, scope } = mount({ days, historyDays: days, selectedDay: days[3] })
    try {
      page.setPeriod('month')
      const option = page.candleOption.value
      expect(option.series[0].data).toEqual([
        [7, 9, 7, 9],
        [5, 9, 5, 9]
      ])
      expect(option.series[1].data).toEqual([8, 7])
      expect(page.displayDetails.value.find((row) => row.key === 'open').value).toBe('5.00')
      expect(page.displayRows.value[0].closeText).toBe('9.00')
      expect(page.displayHeat.value[1].isSelected).toBe(true)
    } finally {
      scope.stop()
    }
  })
})

describe('StockReport 已记录订单 K 线', () => {
  it('实际 OHLC、每笔均价和记录笔数分别展示，空桶留空、单笔为横杠', () => {
    const { page, scope } = mount({ metric: 'orders', orderCandles: fixtureCandles })
    try {
      const option = page.candleOption.value
      expect(option.series[0].data).toEqual([
        [1000, 1500, 1000, 2500],
        '-',
        [2000, 2000, 2000, 2000],
        [2500, 1000, 1000, 2500]
      ])
      expect(option.series.find((row) => row.name === '每笔均价').data).toEqual([
        5000 / 3,
        null,
        2000,
        1750
      ])
      expect(
        option.series.find((row) => row.name === '已记录笔数').data.map((row) => row.value)
      ).toEqual([3, 0, 1, 2])
      expect(option.series[0].itemStyle.borderColorDoji).toBe('#8a8a8a')
      expect(option.tooltip.formatter([{ dataIndex: 1 }])).toContain('无记录')
      const tooltip = option.tooltip.formatter([{ dataIndex: 0 }])
      expect(tooltip).toContain('样本不覆盖全部订单')
      expect(tooltip).toContain('1,667')
      expect(option.series.map((row) => row.name)).not.toContain('MACD')
    } finally {
      scope.stop()
    }
  })

  it('订单 bucket 的选中、报价与样本详情独立于基报选中日', () => {
    const { page, emit, scope } = mount({
      metric: 'orders',
      orderCandles: fixtureCandles,
      selectedDay: fixtureDays[0]
    })
    try {
      page.onChartClick({ dataIndex: 0 })
      expect(page.selectedBucket.value.start).toBe(bucketStart)
      expect(page.displayQuote.value.closeText).toBe('1,500')
      expect(page.displayQuote.value.deltaText).toBe('+500')
      expect(page.displayQuote.value.tone).toBe('is-up')
      const details = Object.fromEntries(
        page.displayDetails.value.map((row) => [row.key, row.value])
      )
      expect(details).toMatchObject({
        open: '1,000',
        close: '1,500',
        high: '2,500',
        low: '1,000',
        mean: '1,667',
        count: '3',
        amount: '5,000',
        report: '2,500'
      })
      expect(page.displayRows.value.find((row) => row.isSelected).date).toBe(String(bucketStart))
      expect(page.displayHeat.value[0].isSelected).toBe(true)
      page.onRowKeydown(page.displayRows.value[1], { key: 'Enter', preventDefault: vi.fn() })
      expect(page.selectedBucket.value.start).toBe(fixtureCandles[2].start)
      expect(emit).not.toHaveBeenCalled()
    } finally {
      scope.stop()
    }
  })

  it('选中无记录小时不沿用上一桶报价或伪造零价格', () => {
    const { page, scope } = mount({ metric: 'orders', orderCandles: fixtureCandles })
    try {
      page.onChartClick({ dataIndex: 1 })
      expect(page.displayQuote.value.closeText).toBe('—')
      expect(page.displayQuote.value.changeText).toBe('—')
      expect(page.candleOption.value.series[0].markPoint.data).toEqual([])
      expect(page.candleOption.value.series[0].markLine.data[0].xAxis).toBe(1)
      expect(page.displayHeat.value[1].changeText).toBe('无记录')
    } finally {
      scope.stop()
    }
  })

  it('换周期后的旧选中桶不污染新桶选择', () => {
    const { page, props, scope } = mount({ metric: 'orders', orderCandles: fixtureCandles })
    try {
      page.onChartClick({ dataIndex: 0 })
      page.setPeriod('1h')
      props.orderPeriod = '1h'
      props.orderCandles = [fixtureCandles[3]]
      expect(page.selectedBucket.value.start).toBe(fixtureCandles[3].start)
      props.metric = 'income'
      expect(page.currentDay.value.date).toBe('2026-10-22')
    } finally {
      scope.stop()
    }
  })

  it('订单模式显示采样说明、限制范围和真实单位，隐藏每日收益构成', async () => {
    const html = await render({
      ...baseProps,
      metric: 'orders',
      orderCandles: fixtureCandles,
      range: 'all',
      orderCandleRange: { startDate: '2025-10-22', endDate: '2026-10-22' }
    })
    for (const label of [
      '已记录订单质量',
      '1 小时K',
      '4 小时K',
      '日K',
      '龙门币/单',
      '不代表全部订单均价',
      '最多 366 天',
      '同日基报均价'
    ])
      expect(html).toContain(label)
    expect(html).not.toContain('aria-label="收益构成"')
    expect(html).not.toContain('aria-label="资金分析"')
    expect(html).not.toContain('aria-label="订单分布"')
  })

  it('读取失败提供独立重试，加载与无记录状态可辨认', async () => {
    const loading = await render({ ...baseProps, metric: 'orders', orderCandlesLoading: true })
    expect(loading).toContain('正在读取订单记录')
    const failed = await render({
      ...baseProps,
      metric: 'orders',
      orderCandlesError: '订单记录读取超时'
    })
    expect(failed).toContain('订单记录读取超时')
    expect(failed).toContain('重试读取')
    const empty = await render({ ...baseProps, metric: 'orders', orderCandles: [] })
    expect(empty).toContain('所选范围没有已记录订单')
  })

  it('没有基报记录时仍能查看已记录订单，订单加载失败也不被基报空态遮住', async () => {
    const props = {
      ...baseProps,
      days: [],
      historyDays: [],
      selectedDay: null,
      previousDay: null,
      metric: 'orders'
    }
    const html = await render({ ...props, orderCandles: fixtureCandles })
    expect(html).toContain('MOWER-ORDER')
    expect(html).toContain('首笔价格')
    expect(html).not.toContain('还没有基报记录')
    expect(await render({ ...props, orderCandlesLoading: true })).toContain('正在读取订单记录')
    expect(await render({ ...props, orderCandlesError: '离线读取失败' })).toContain('离线读取失败')
  })

  it('初次查看选中最后有数据的桶，尾部空桶保持可手动选择', () => {
    const candles = [
      ...fixtureCandles,
      {
        ...fixtureCandles[1],
        start: bucketStart + 57600,
        end: bucketStart + 72000,
        label: '2026-10-22 20:00'
      }
    ]
    const { page, scope } = mount({ metric: 'orders', orderCandles: candles })
    try {
      expect(page.selectedBucket.value.start).toBe(fixtureCandles[3].start)
      expect(page.displayQuote.value.closeText).toBe('1,000')
      expect(page.displayTradeRows.value.every((row) => !row.isPartial)).toBe(true)
      expect(page.displayTradeRows.value).toHaveLength(3)
      page.onChartClick({ dataIndex: 4 })
      expect(page.selectedBucket.value.count).toBe(0)
      expect(page.displayQuote.value.closeText).toBe('—')
    } finally {
      scope.stop()
    }
  })

  it('长范围提供缩放，热力和列表每页最多 200 条并可访问全部记录', async () => {
    const candles = Array.from({ length: 450 }, (_, index) => ({
      ...fixtureCandles[2],
      start: bucketStart + index * 3600,
      end: bucketStart + (index + 1) * 3600,
      label: '订单时段 ' + index
    }))
    const { page, scope } = mount({ metric: 'orders', orderCandles: candles })
    try {
      const zoom = page.candleOption.value.dataZoom
      expect(zoom.map((row) => row.type)).toEqual(['inside', 'slider'])
      expect(zoom[0].startValue).toBe(390)
      expect(zoom[0].endValue).toBe(449)
      expect(page.marketPageCount.value).toBe(3)
      expect(page.pagedRows.value).toHaveLength(200)
      expect(page.pagedHeat.value).toHaveLength(200)
      page.stepMarketPage(1)
      expect(page.pagedRows.value[0].code).toBe('订单时段 249')
      page.stepMarketPage(1)
      expect(page.pagedRows.value).toHaveLength(50)
      expect(page.pagedRows.value.at(-1).code).toBe('订单时段 0')
      expect(page.pagedHeat.value[0].shortDate).toBe('订单时段 0')
      page.selectRow(candles[0].start)
      expect(page.candleOption.value.dataZoom[0].startValue).toBe(0)
      expect(page.candleOption.value.dataZoom[0].endValue).toBe(59)
    } finally {
      scope.stop()
    }
    const html = await render({ ...baseProps, metric: 'orders', orderCandles: candles })
    expect(html.match(/<button[^>]*heat-block/g)).toHaveLength(200)
    expect(html.match(/<tr[^>]*quote-table__row/g)).toHaveLength(200)
    expect(html).toContain('共 450 条')
    expect(html).toContain('下一页')
  })
})

describe('StockReport 每日收益走势与缺失读数', () => {
  it('收益走势保留全历史 MA5，与所选日、收益构成和日记录一致', () => {
    const { page, emit, scope } = mount({ days: fixtureDays.slice(-7) })
    try {
      const option = page.intradayOption.value
      expect(option.series.find((row) => row.name === '收益').data).toEqual(totals.slice(-7))
      expect(option.series.find((row) => row.name === 'MA5').data[0]).toBe(7.76)
      expect(option.series.find((row) => row.name === 'MA5').data.at(-1)).toBe(8.6)
      expect(page.displayQuote.value.closeText).toBe('8.80')
      expect(page.displayDetails.value.find((row) => row.key === 'previous').value).toBe('8.40')
      expect(page.composition.value).toHaveLength(5)
      expect(page.fundRows.value.map((row) => row.percentText)).toEqual([
        '40%',
        '10%',
        '30%',
        '20%'
      ])
      expect(page.indexStrip.value).toHaveLength(6)
      expect(page.displayRows.value[0].date).toBe('2026-10-22')
      page.onChartClick({ dataIndex: 0 })
      expect(emit).toHaveBeenCalledWith('select', '2026-10-16')
    } finally {
      scope.stop()
    }
  })

  it('缺失日留空，下一日与前次完整收益比较，均线不计入缺失日', () => {
    const days = [
      makeDay('2026-10-01', 8),
      {
        ...makeDay('2026-10-02', 2),
        gold: null,
        income: { ...makeDay('', 2).income, partial: true }
      },
      makeDay('2026-10-03', 10)
    ]
    const { page, scope } = mount({
      days,
      historyDays: days,
      selectedDay: days[2],
      previousDay: days[1]
    })
    try {
      expect(page.intradayOption.value.series.find((row) => row.name === '收益').data).toEqual([
        8,
        null,
        10
      ])
      expect(page.displayQuote.value.changeText).toBe('+25%')
      expect(page.displayHeat.value[1].changeText).toBe('缺')
      expect(page.marketStats.value.missing).toBe(1)
    } finally {
      scope.stop()
    }
  })

  it('跨年相同月日的走势标记按记录位置定位', () => {
    const days = [makeDay('2025-10-22', 9), makeDay('2026-10-22', 10)]
    const { page, scope } = mount({
      days,
      historyDays: days,
      selectedDay: days[0],
      previousDay: null
    })
    try {
      const series = page.intradayOption.value.series.find((row) => row.name === '收益')
      expect(series.markLine.data.at(-1).xAxis).toBe(0)
      expect(series.markPoint.data).toEqual([{ coord: [0, 9] }])
    } finally {
      scope.stop()
    }
  })

  it('真实零收益起点隐藏百分比轴，轴边界保持有限', () => {
    const days = [makeDay('2026-10-01', 0), makeDay('2026-10-02', 1)]
    const { page, scope } = mount({ days, historyDays: days })
    try {
      const axis = page.intradayOption.value.yAxis[2]
      expect(axis.show).toBe(false)
      expect(Number.isFinite(axis.min)).toBe(true)
      expect(Number.isFinite(axis.max)).toBe(true)
    } finally {
      scope.stop()
    }
  })

  it.each([
    [9, 1, 7.4],
    [1, 9, 2.6]
  ])('轴范围包含此前 %s、当前 %s 算出的 MA5', (prior, current, expected) => {
    const history = Array.from({ length: 11 }, (_, index) =>
      makeDay(dateAt(index), index < 4 ? prior : current)
    )
    const { page, scope } = mount({
      historyDays: history,
      days: history.slice(4),
      selectedDay: history.at(-1)
    })
    try {
      const option = page.intradayOption.value
      expect(option.series.find((row) => row.name === 'MA5').data[0]).toBe(expected)
      expect(option.yAxis[0].min).toBeLessThanOrEqual(expected)
      expect(option.yAxis[0].max).toBeGreaterThanOrEqual(expected)
    } finally {
      scope.stop()
    }
  })

  it('无基报记录和已有记录刷新使用不同状态，订单分布保留原始类型', async () => {
    expect(await render({ days: [], loading: true })).toContain('行情加载中')
    expect(await render({ days: [], loading: false })).toContain('还没有基报记录')
    const html = await render({ ...baseProps, loading: true, refreshing: true })
    expect(html).not.toContain('行情加载中')
    expect(html).toContain('刷新中')
    const { page, scope } = mount()
    try {
      expect(page.orderOption.value.dataset.source).toEqual(fixtureOrderRows)
      expect(
        page.orderOption.value.series.find((row) => row.name === ORDER_TYPES[0]).itemStyle.color
      ).toBe(ORDER_COLORS.stock[ORDER_TYPES[0]])
    } finally {
      scope.stop()
    }
  })
})

describe('StockReport 明暗主题与减少动态', () => {
  it('收益和订单图随主题更新，红涨绿跌与均值色保持可见', () => {
    const { page, props, scope } = mount({
      metric: 'orders',
      orderCandles: fixtureCandles,
      dark: false
    })
    try {
      expect(page.candleOption.value.backgroundColor).toBe('#ffffff')
      expect(page.candleOption.value.series[0].itemStyle.borderColor).toBe('#c62828')
      expect(page.candleOption.value.series[0].itemStyle.borderColor0).toBe('#067045')
      expect(page.candleOption.value.series[1].lineStyle.color).toBe('#8f6400')
      expect(page.intradayOption.value.backgroundColor).toBe('#ffffff')
      props.dark = true
      expect(page.candleOption.value.backgroundColor).toBe('#000000')
      expect(page.candleOption.value.series[0].itemStyle.borderColor).toBe('#ff3232')
      expect(page.candleOption.value.series[0].itemStyle.borderColor0).toBe('#00d26a')
      expect(
        page.intradayOption.value.series.find((row) => row.name === '收益').lineStyle.color
      ).toBe('#ffffff')
    } finally {
      scope.stop()
    }
  })

  it('减少动态设置关闭两类主图动画，K线在窄屏保持主图和样本量图', () => {
    vi.stubGlobal('window', {
      matchMedia: (query) => ({
        matches: query.includes('prefers-reduced-motion') || query.includes('max-width')
      })
    })
    const { page, scope } = mount()
    try {
      expect(page.intradayOption.value.animation).toBe(false)
      expect(page.candleOption.value.animation).toBe(false)
      expect(page.candleOption.value.grid).toHaveLength(2)
      const style = readTermStyle()
      expect(
        styleBlock(style.slice(style.indexOf('@media (max-width: 720px)')), '.market-switch button')
      ).toContain('min-height: 36px')
    } finally {
      scope.stop()
    }
  })

  it('SSR 标识明暗皮肤并提供所有视图和周期控件', async () => {
    const light = await render({ ...baseProps, dark: false })
    expect(light).toContain('term--light')
    for (const label of [
      '基建收益',
      '已记录订单质量',
      '每日走势',
      '周K',
      '月K',
      '板块热力',
      '行情列表',
      '收益构成',
      '资金分析'
    ])
      expect(light).toContain(label)
    expect(light).not.toContain('>日K<')
    expect(await render(baseProps)).not.toContain('term--light')
  })
})

describe('StockReport 全屏与图中选中标记', () => {
  it('全屏 API 不可用时退回页面内沉浸模式，再次点击退出', async () => {
    const { page, scope } = mount()
    try {
      expect(page.isFullscreen.value).toBe(false)
      await page.toggleFullscreen()
      expect(page.isFullscreen.value).toBe(true)
      expect(page.immersive.value).toBe(true)
      await page.toggleFullscreen()
      expect(page.isFullscreen.value).toBe(false)
      expect(page.immersive.value).toBe(false)
    } finally {
      scope.stop()
    }
  })

  it('浏览器支持元素全屏时使用全屏 API，并在退出后同步状态', async () => {
    const element = {}
    const documentStub = {
      fullscreenElement: null,
      exitFullscreen: vi.fn(async () => {
        documentStub.fullscreenElement = null
      })
    }
    element.requestFullscreen = vi.fn(async () => {
      documentStub.fullscreenElement = element
    })
    vi.stubGlobal('document', documentStub)
    const { page, scope } = mount()
    try {
      page.termRef.value = element
      await page.toggleFullscreen()
      expect(element.requestFullscreen).toHaveBeenCalledOnce()
      expect(page.isFullscreen.value).toBe(true)
      expect(page.nativeFullscreen.value).toBe(true)
      await page.toggleFullscreen()
      expect(documentStub.exitFullscreen).toHaveBeenCalledOnce()
      expect(page.isFullscreen.value).toBe(false)
    } finally {
      scope.stop()
    }
  })

  it('请求全屏被拒绝时改走页面内沉浸模式', async () => {
    const element = {
      requestFullscreen: vi.fn(async () => {
        throw new Error('denied')
      })
    }
    vi.stubGlobal('document', { fullscreenElement: null, exitFullscreen: vi.fn() })
    const { page, scope } = mount()
    try {
      page.termRef.value = element
      await page.toggleFullscreen()
      expect(element.requestFullscreen).toHaveBeenCalledOnce()
      expect(page.immersive.value).toBe(true)
      expect(page.nativeFullscreen.value).toBe(false)
    } finally {
      scope.stop()
    }
  })

  it.each([
    ['selectAlgorithm', -1, 'select-algorithm'],
    ['restoreHistory', undefined, 'restore-history'],
    ['refresh', undefined, 'refresh'],
    ['closeMenu', undefined, null]
  ])('%s 等原生全屏退出后再打开页面外部控件或提示', async (method, value, event) => {
    const element = {}
    let finishExit
    const documentStub = {
      fullscreenElement: null,
      exitFullscreen: vi.fn(
        () =>
          new Promise((resolve) => {
            finishExit = () => {
              documentStub.fullscreenElement = null
              resolve()
            }
          })
      )
    }
    element.requestFullscreen = async () => {
      documentStub.fullscreenElement = element
    }
    vi.stubGlobal('document', documentStub)
    const { page, emit, scope } = mount()
    try {
      page.termRef.value = element
      await page.toggleFullscreen()
      page.menuOpen.value = true
      const overlayReady = vi.fn()
      const action = page[method](value).then(overlayReady)
      expect(documentStub.exitFullscreen).toHaveBeenCalledOnce()
      expect(page.menuOpen.value).toBe(false)
      expect(emit).not.toHaveBeenCalled()
      expect(overlayReady).not.toHaveBeenCalled()
      finishExit()
      await action
      expect(page.isFullscreen.value).toBe(false)
      expect(overlayReady).toHaveBeenCalledOnce()
      if (event === 'select-algorithm') expect(emit).toHaveBeenCalledWith(event, -1)
      else if (event) expect(emit).toHaveBeenCalledWith(event)
      else expect(emit).not.toHaveBeenCalled()
    } finally {
      scope.stop()
    }
  })

  it.each(['selectAlgorithm', 'restoreHistory', 'refresh', 'closeMenu'])(
    '%s 退出沉浸模式，让页面外部控件或提示可见',
    async (method) => {
      const { page, scope } = mount()
      try {
        await page.toggleFullscreen()
        expect(page.immersive.value).toBe(true)
        await page[method](-1)
        expect(page.immersive.value).toBe(false)
        expect(page.isFullscreen.value).toBe(false)
      } finally {
        scope.stop()
      }
    }
  )
})

// ---- 终端调色板与 CSS 变量一致性 ----
function readTermStyle() {
  const source = readFileSync(new URL('./StockReport.vue', import.meta.url), 'utf8')
  return source.slice(source.indexOf('<style scoped>'))
}
function styleBlock(style, selector) {
  const start = style.indexOf(selector)
  if (start < 0) throw new Error('缺少样式块 ' + selector)
  const end = style.indexOf('\n}', start)
  if (end < 0) throw new Error('样式块未闭合 ' + selector)
  return style.slice(start, end)
}
function parseTermVariables(body) {
  const variables = {}
  for (const match of body.matchAll(/--term-([a-z0-9-]+):\s*([^;]+);/g)) {
    variables[match[1]] = match[2].trim()
  }
  return variables
}
function colorChannels(value) {
  const hex = value.match(/^#([0-9a-f]{6})$/i)
  if (hex) {
    const number = parseInt(hex[1], 16)
    return [(number >> 16) & 255, (number >> 8) & 255, number & 255]
  }
  const rgba = value.match(/^rgba?\(([^)]+)\)$/)
  if (!rgba) throw new Error('无法解析颜色 ' + value)
  const parts = rgba[1].split(',').map((part) => Number(part.trim()))
  return [parts[0], parts[1], parts[2], parts[3] ?? 1]
}
function blendOver(color, base) {
  if (color.length === 3) return color
  return [0, 1, 2].map((index) =>
    Math.round(color[index] * color[3] + base[index] * (1 - color[3]))
  )
}
function channelLuminance(value) {
  const channel = value / 255
  return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
}
function relativeLuminance(color) {
  return (
    0.2126 * channelLuminance(color[0]) +
    0.7152 * channelLuminance(color[1]) +
    0.0722 * channelLuminance(color[2])
  )
}
function contrastRatio(foreground, background) {
  const first = relativeLuminance(foreground)
  const second = relativeLuminance(background)
  const [high, low] = first > second ? [first, second] : [second, first]
  return (high + 0.05) / (low + 0.05)
}

describe('StockReport 调色板与样式变量', () => {
  const variableNames = {
    bg: 'bg',
    surface: 'surface',
    surface2: 'surface-2',
    hover: 'hover',
    line: 'line',
    lineSoft: 'line-soft',
    text: 'text',
    muted: 'muted',
    up: 'up',
    down: 'down',
    cyan: 'cyan',
    blue: 'blue',
    yellow: 'yellow',
    magenta: 'magenta'
  }

  it('图表调色板与 .term / .term--light 的 CSS 变量逐项相等', () => {
    const style = readTermStyle()
    const dark = parseTermVariables(styleBlock(style, '.term {'))
    const light = parseTermVariables(styleBlock(style, '.term--light {'))
    const { page, scope } = mount()
    try {
      for (const [key, variable] of Object.entries(variableNames)) {
        expect(dark[variable]).toBe(page.TERM_PALETTES.dark[key])
        expect(light[variable]).toBe(page.TERM_PALETTES.light[key])
      }
    } finally {
      scope.stop()
    }
  })

  it('亮色主题的次要文字、涨跌、热力块与移动端涨跌单元格达到 AA 对比度', () => {
    const light = parseTermVariables(styleBlock(readTermStyle(), '.term--light {'))
    const white = [255, 255, 255]
    const surface = colorChannels(light.surface)
    const surfaceAlt = colorChannels(light['surface-2'])
    const selected = colorChannels(light.selected)
    const hover = colorChannels(light.hover)
    expect(contrastRatio(colorChannels(light.text), white)).toBeGreaterThanOrEqual(7)
    expect(contrastRatio(colorChannels(light.muted), surfaceAlt)).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio(colorChannels(light.up), surface)).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio(colorChannels(light.up), selected)).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio(colorChannels(light.up), hover)).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio(colorChannels(light.down), white)).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio(colorChannels(light.down), selected)).toBeGreaterThanOrEqual(4.5)
    // 选中行里的“最新”徽标和成交明细箭头也使用这些前景色。
    expect(contrastRatio(colorChannels(light.blue), selected)).toBeGreaterThanOrEqual(4.5)
    const tabBackground = blendOver(colorChannels(light['tab-active']), surface)
    expect(contrastRatio(colorChannels(light['tab-text']), tabBackground)).toBeGreaterThanOrEqual(
      4.5
    )
    for (const tone of ['up', 'down']) {
      const heatLevel4 = blendOver(colorChannels(light['heat-' + tone + '-4']), white)
      expect(
        contrastRatio(colorChannels(light['heat-' + tone + '-text']), heatLevel4)
      ).toBeGreaterThanOrEqual(4.5)
      const cellBackground = blendOver(colorChannels(light['cell-' + tone]), selected)
      expect(
        contrastRatio(colorChannels(light['cell-' + tone + '-text']), cellBackground)
      ).toBeGreaterThanOrEqual(4.5)
    }
  })

  it('分类轴显式关闭竖网格线，不继承报告页注入的图表主题', () => {
    const { page, scope } = mount()
    try {
      const intraday = page.intradayOption.value
      expect(intraday.xAxis[0].splitLine.show).toBe(false)
      expect(intraday.xAxis[1].splitLine.show).toBe(false)
      for (const axis of page.candleOption.value.xAxis) expect(axis.splitLine.show).toBe(false)
      expect(page.orderOption.value.xAxis.splitLine.show).toBe(false)
    } finally {
      scope.stop()
    }
  })
})
