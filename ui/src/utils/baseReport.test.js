import { describe, expect, it } from 'vitest'
import {
  ORDER_COLORS,
  ORDER_PRICES,
  ORDER_TYPES,
  buildOrderChartRows,
  buildReportDays,
  dayIncome,
  formatDay,
  formatPercent,
  selectRange,
  summarize,
  tradingRange,
  withIncome
} from './baseReport'

const ratios = { gold: 0.4, order: 0.6, experience: 2, efficiency: 1 }
const placeholder = { 日期: '2026-10-01', 赤金: '-', 作战录像: '-', 龙门币订单: '-' }

describe('基建报表数据模型', () => {
  it('合并基报、合成玉与特殊赤金并丢弃凑数占位行', () => {
    const days = buildReportDays(
      [
        { 日期: '2026-10-13', 赤金: 2000, 作战录像: 1000, 龙门币订单: 5000, 龙门币订单数: 4 },
        placeholder,
        { 日期: '2026-10-12', 赤金: 1000, 作战录像: 2000, 龙门币订单: 10000, 龙门币订单数: 0 }
      ],
      [
        { 日期: '2026-10-01', 合成玉: '-' },
        { 日期: '2026-10-13', 合成玉: 120, 合成玉订单数量: 3 }
      ],
      [{ 日期: '2026-10-12', 龙舌兰: 1, 可露希尔: 2 }]
    )
    expect(days.map((day) => day.date)).toEqual(['2026-10-12', '2026-10-13'])
    expect(days[0]).toMatchObject({ tequilaGold: 500, closureGold: 400, perOrder: null })
    expect(days[1]).toMatchObject({ perOrder: 1250, orundum: 120, orundumOrders: 3 })
    expect(days[0].orundum).toBeNull()
  })

  it('收益包含特殊赤金，缺失读数按 0 计入并标记不完整', () => {
    const [full, partial, unknown] = buildReportDays(
      [
        { 日期: '2026-10-12', 赤金: 1000, 龙门币订单: 10000, 作战录像: 2000 },
        { 日期: '2026-10-13', 赤金: null, 龙门币订单: 10000, 作战录像: 2000 },
        { 日期: '2026-10-14', 赤金: null, 龙门币订单: null, 作战录像: null }
      ],
      [],
      [{ 日期: '2026-10-12', 龙舌兰: 1 }]
    )
    const income = dayIncome(full, ratios)
    expect(income.total).toBeCloseTo(1.06)
    expect(income.special).toBeCloseTo(0.02)
    expect(income.partial).toBe(false)
    expect(dayIncome(partial, ratios)).toMatchObject({ partial: true })
    expect(dayIncome(partial, ratios).total).toBeCloseTo(1)
    expect(dayIncome(unknown, ratios).total).toBeNull()
  })

  it('区间汇总给出前一日变化、均值与最佳日，未知收益不参与', () => {
    const days = withIncome(
      buildReportDays([
        { 日期: '2026-10-11', 赤金: null, 龙门币订单: null, 作战录像: null },
        { 日期: '2026-10-12', 赤金: 10000, 龙门币订单: 0, 作战录像: 0 },
        { 日期: '2026-10-13', 赤金: 20000, 龙门币订单: 0, 作战录像: 0 },
        { 日期: '2026-10-14', 赤金: 15000, 龙门币订单: 0, 作战录像: 0 }
      ]),
      ratios
    )
    const summary = summarize(days)
    expect(summary.best.date).toBe('2026-10-13')
    expect(summary.averageIncome).toBeCloseTo(0.6)
    expect(summary.dayOverDay).toBeCloseTo(-0.25)
    expect(summary.gold).toBe(45000)
    expect(summary.missingDays).toBe(1)
    expect(selectRange(days, '7')).toHaveLength(4)
    expect(selectRange(days, 'all')).toHaveLength(4)
  })

  it.each([
    [
      '7',
      ['2026-10-10', '2026-10-17', '2026-10-18', '2026-10-22', '2026-10-24'],
      ['2026-10-18', '2026-10-22', '2026-10-24']
    ],
    [
      '14',
      ['2026-09-20', '2026-09-23', '2026-09-24', '2026-10-01', '2026-10-07'],
      ['2026-09-24', '2026-10-01', '2026-10-07']
    ],
    [
      '30',
      ['2026/12/11', '2026/12/12', '2027-01-01', '2027-01-10'],
      ['2026/12/12', '2027-01-01', '2027-01-10']
    ]
  ])('%s 天区间按最近产出日计算自然日，读取日期断档不延长区间', (range, dates, expected) => {
    const days = Object.freeze(dates.map((date) => Object.freeze({ date })))
    const selected = selectRange(days, range)
    expect(selected.map((day) => day.date)).toEqual(expected)
    expect(days.map((day) => day.date)).toEqual(dates)
    expect(selected).not.toBe(days)
  })

  it('有限区间以最近有效日期为截止日，全部区间保留原数组中的记录', () => {
    const days = Object.freeze([
      Object.freeze({ date: '2026/10/18' }),
      Object.freeze({ date: null }),
      Object.freeze({ date: '2026-10-24' }),
      Object.freeze({ date: 'invalid' }),
      Object.freeze({ date: '2026/09/30' }),
      Object.freeze({})
    ])
    expect(selectRange(days, '7').map((day) => day.date)).toEqual(['2026/10/18', '2026-10-24'])
    const all = selectRange(days, 'all')
    expect(all).toEqual(days)
    expect(all).not.toBe(days)
    expect(selectRange([], '14')).toEqual([])
    expect(selectRange([{ date: null }, { date: 'invalid' }], '30')).toEqual([])
  })

  it('区间每单使用金额与正单数均已知的成对记录，保留零金额并按单数加权', () => {
    const days = buildReportDays([
      { 日期: '2026-10-19', 龙门币订单: null, 龙门币订单数: 10 },
      { 日期: '2026-10-20', 龙门币订单: 90000, 龙门币订单数: null },
      { 日期: '2026-10-21', 龙门币订单: 1200, 龙门币订单数: 0 },
      { 日期: '2026-10-22', 龙门币订单: 0, 龙门币订单数: 4 },
      { 日期: '2026-10-23', 龙门币订单: 10000, 龙门币订单数: 5 },
      { 日期: '2026-10-24', 龙门币订单: 4000, 龙门币订单数: 1 }
    ])
    const summary = summarize(days)
    expect(summary.perOrder).toBe(1400)
    expect(summary.orders).toBe(105200)
    expect(summary.orderCount).toBe(20)
  })

  it('金额和单数不在同一天时区间每单保持未知', () => {
    const days = buildReportDays([
      { 日期: '2026-10-23', 龙门币订单: null, 龙门币订单数: 10 },
      { 日期: '2026-10-24', 龙门币订单: 10000, 龙门币订单数: null }
    ])
    expect(summarize(days).perOrder).toBeNull()
  })

  it.each([
    [null, 5, null],
    [10000, null, null],
    [10000, 0, null],
    [10000, -1, null],
    [0, 4, 0]
  ])('区间每单保留金额 %s、单数 %s 的有效性', (orders, orderCount, expected) => {
    const days = buildReportDays([
      { 日期: '2026-10-24', 龙门币订单: orders, 龙门币订单数: orderCount }
    ])
    expect(summarize(days).perOrder).toBe(expected)
  })

  it('贸易记录的查询区间覆盖全部基报日期', () => {
    expect(
      tradingRange([placeholder, { 日期: '2026-10-20' }, { 日期: '2026-09-30', 赤金: 1 }])
    ).toEqual({ start: '2026-09-30', end: '2026-10-20' })
    expect(tradingRange([placeholder])).toBeNull()
    expect(tradingRange(false)).toBeNull()
  })

  it('格式化日期与涨跌幅', () => {
    expect(formatDay('2026-10-24')).toBe('10-24 周六')
    expect(formatDay('2026/10/05')).toBe('10-05 周一')
    expect(formatPercent(0.0512)).toBe('+5.1%')
    expect(formatPercent(-0.25)).toBe('−25%')
    expect(formatPercent(null)).toBe('')
  })
})
describe('贸易订单分布模型', () => {
  const orderTypes = [
    '但书_2000',
    '但书_2500',
    '漏单_1000',
    '漏单_1500',
    '漏单_2000',
    '龙舌兰',
    '佩佩',
    '可露希尔'
  ]

  it('订单类型与单价覆盖后端记录组合，四套配色都有定义', () => {
    expect(ORDER_TYPES).toEqual(orderTypes)
    expect(ORDER_PRICES).toEqual({
      但书_2000: 2000,
      但书_2500: 2500,
      漏单_1000: 1000,
      漏单_1500: 1500,
      漏单_2000: 2000,
      龙舌兰: 2500,
      佩佩: 1000,
      可露希尔: 1200
    })
    for (const mode of ['light', 'dark', 'stock', 'stockLight']) {
      for (const name of [...orderTypes, '未知订单']) {
        expect(ORDER_COLORS[mode][name]).toMatch(/^#[0-9a-f]{6}$/i)
      }
    }
  })

  it('把订单计数折算为金额并计算未知订单', () => {
    const [row] = buildOrderChartRows(
      [
        {
          日期: '2026-10-12',
          赤金: 1000,
          龙门币订单: 10000,
          龙门币订单数: 5,
          每单获取龙门币: 2000
        }
      ],
      [{ 日期: '2026-10-12', 但书_2000: 2, 龙舌兰: 1, 可露希尔: 2 }]
    )
    expect(row).toMatchObject({
      日期: '2026-10-12',
      但书_2000: 4000,
      但书_2500: 0,
      龙舌兰: 2500,
      可露希尔: 2400,
      龙门币订单: 10000,
      订单数: 5,
      订单质量: 2000,
      赤金: 1000,
      未知订单: 1100,
      未知订单数: 0
    })
  })

  it('缺少贸易记录时全部订单金额记为未知', () => {
    const [row] = buildOrderChartRows(
      [{ 日期: '2026-10-12', 龙门币订单: 10000, 龙门币订单数: 4 }],
      []
    )
    expect(row['未知订单']).toBe(10000)
    expect(row['未知订单数']).toBe(4)
    expect(row['但书_2000']).toBe(0)
    expect(buildOrderChartRows([], [])).toEqual([])
  })

  it('未知订单不为负，读数缺失保持未知且不产生 NaN', () => {
    const rows = buildOrderChartRows(
      [
        { 日期: '2026-10-11', 龙门币订单: 1000, 龙门币订单数: 1 },
        { 日期: '2026-10-12', 龙门币订单: null, 龙门币订单数: null, 赤金: null }
      ],
      [
        { 日期: '2026-10-11', 但书_2000: 3, 龙舌兰: 2 },
        { 日期: '2026-10-12', 漏单_1000: 1 }
      ]
    )
    expect(rows[0]['未知订单']).toBe(0)
    expect(rows[0]['未知订单数']).toBe(0)
    expect(rows[1]['未知订单']).toBeNull()
    expect(rows[1]['未知订单数']).toBeNull()
    expect(rows[1]['漏单_1000']).toBe(1000)
    expect(rows[1]['龙门币订单']).toBeNull()
    expect(rows[1]['赤金']).toBeNull()
    for (const value of Object.values(rows[1])) {
      expect(value === null || Number.isNaN(value)).toBe(value === null)
    }
  })

  it('按统计区间对齐日期并丢弃占位行', () => {
    const reportRows = [
      { 日期: '2026-10-13', 龙门币订单: 5000, 龙门币订单数: 2, 作战录像: 1 },
      { 日期: '2026-10-12', 龙门币订单: 9000, 龙门币订单数: 3, 作战录像: 1 },
      { 日期: '2026-10-11', 赤金: '-', 作战录像: '-', 龙门币订单: '-' }
    ]
    const days = [{ date: '2026-10-12' }, { date: '2026-10-13' }, { date: '2026-10-14' }]
    const rows = buildOrderChartRows(reportRows, [], days)
    expect(rows.map((row) => row['日期'])).toEqual(['2026-10-12', '2026-10-13', '2026-10-14'])
    expect(rows[0]['未知订单']).toBe(9000)
    expect(rows[2]).toMatchObject({
      日期: '2026-10-14',
      未知订单: null,
      龙门币订单: null,
      赤金: null
    })
    expect(rows[2]['但书_2000']).toBeNull()
    expect(buildOrderChartRows(reportRows, [], []).map((row) => row['日期'])).toEqual([
      '2026-10-12',
      '2026-10-13'
    ])
  })

  it('非数值订单计数按零处理，忽略没有日期的记录', () => {
    const [row] = buildOrderChartRows(
      [{ 日期: '2026-10-12', 龙门币订单: 0, 龙门币订单数: 0 }],
      [{ 日期: '2026-10-12', 但书_2000: '2', 龙舌兰: null }, { 但书_2000: 9 }]
    )
    expect(row['但书_2000']).toBe(0)
    expect(row['龙舌兰']).toBe(0)
    expect(row['未知订单']).toBe(0)
    expect(row['未知订单数']).toBe(0)
  })
})
