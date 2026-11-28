import { describe, expect, it } from 'vitest'
import { buildIncomeCandles, orderCandleQuery } from './reportMarket.js'

const day = (date, total, partial = false) => ({
  date,
  orderCount: 2,
  income: { total, partial }
})

describe('真实日收益周月聚合', () => {
  it('周一划周，按日期取首末与极值并保留真实零', () => {
    const history = [
      day('2026-10-21', 0),
      day('2026-10-19', 4),
      day('2026-10-20', 9),
      day('2026-10-25', 6)
    ]
    const [row] = buildIncomeCandles(history, 'week')
    expect(row).toMatchObject({
      label: '2026-10-19',
      open: 4,
      close: 6,
      high: 9,
      low: 0,
      count: 4,
      amount: 19,
      mean: 4.75,
      missingCount: 3,
      incomplete: true,
      orderCount: 8
    })
    expect(row.start).toBe(Date.parse('2026-10-19T04:00:00+08:00') / 1000)
    expect(row.end).toBe(Date.parse('2026-10-26T04:00:00+08:00') / 1000)
  })
  it('可见区间截在周中仍使用同周全部历史，不把收益合计当作收盘', () => {
    const history = [day('2026-10-19', 3), day('2026-10-20', 11), day('2026-10-25', 5)]
    expect(buildIncomeCandles(history, 'week', [history[2]])[0]).toMatchObject({
      open: 3,
      high: 11,
      close: 5,
      amount: 19,
      count: 3
    })
  })
  it('部分读数和缺失日不作为零，整个缺失周期保留空价格', () => {
    const history = [day('2026-10-19', 100, true), day('2026-10-26', null), day('2026-11-02', 8)]
    const rows = buildIncomeCandles(history, 'week')
    expect(rows).toHaveLength(3)
    expect(rows[0]).toMatchObject({
      open: null,
      high: null,
      low: null,
      close: null,
      count: 0,
      mean: null,
      missingCount: 7
    })
    expect(rows[1].close).toBeNull()
    expect(rows[2].close).toBe(8)
  })
  it('跨年周仍按周一归组，月 K 按月初划分并识别闰年天数', () => {
    const crossing = [day('2025-12-31', 6), day('2026-01-01', 8)]
    expect(buildIncomeCandles(crossing, 'week')).toHaveLength(1)
    expect(buildIncomeCandles(crossing, 'month').map((row) => row.label)).toEqual([
      '2025-12-01',
      '2026-01-01'
    ])
    const [february] = buildIncomeCandles([day('2024-02-01', 1), day('2024-02-29', 3)], 'month')
    expect(february).toMatchObject({ open: 1, close: 3, mean: 2, missingCount: 27 })
  })
  it('完整一周没有缺失标记，输入顺序和无效日期不改变结果', () => {
    const history = Array.from({ length: 7 }, (_, i) => day(`2026-10-${19 + i}`, i + 1))
    const [row] = buildIncomeCandles([...history].reverse().concat(day('2026-02-30', 999)), 'week')
    expect(row).toMatchObject({
      open: 1,
      high: 7,
      low: 1,
      close: 7,
      count: 7,
      mean: 4,
      missingCount: 0,
      incomplete: false
    })
    expect(buildIncomeCandles(history, 'day')).toEqual([])
    expect(buildIncomeCandles(history, 'week', [])).toEqual([])
  })
})

describe('订单查询游戏日', () => {
  it('北京时间凌晨 4 点才切换日期，包含当前游戏日', () => {
    expect(orderCandleQuery('7', Date.parse('2026-10-28T03:59:59+08:00'))).toEqual({
      startDate: '2026-10-21',
      endDate: '2026-10-27'
    })
    expect(orderCandleQuery('7', Date.parse('2026-10-28T04:00:00+08:00'))).toEqual({
      startDate: '2026-10-22',
      endDate: '2026-10-28'
    })
  })
  it('全部最多包含 366 个日历日且跨年独立于浏览器时区', () => {
    const now = Date.parse('2026-10-28T10:00:00+08:00')
    expect(orderCandleQuery('14', now)).toEqual({ startDate: '2026-10-15', endDate: '2026-10-28' })
    const all = orderCandleQuery('all', now)
    expect((Date.parse(all.endDate) - Date.parse(all.startDate)) / 86400000 + 1).toBe(366)
    expect(orderCandleQuery('30', Date.parse('2026-01-02T04:00:00+08:00'))).toEqual({
      startDate: '2025-12-04',
      endDate: '2026-01-02'
    })
  })
})
