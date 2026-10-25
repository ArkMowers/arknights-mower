import { describe, expect, it } from 'vitest'
import {
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
