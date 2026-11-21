import { describe, expect, it } from 'vitest'
import { buildRewardDistribution, buildRewardReport } from './rewardReport'

function record(date, item, count, overrides = {}) {
  const pair = overrides.pair || overrides.game || overrides.game_group || '明日方舟官服'
  return { date, item, count, pair, outcome: 'signed', game_group: '明日方舟', ...overrides }
}

describe('签到奖励汇总', () => {
  it('仅汇总实际奖励，按游戏分开同名道具，并记录道具出现的日期数', () => {
    const report = buildRewardReport(
      [
        record('2026-11-01', '合成玉', 20),
        record('2026-11-01', '合成玉', 30, { game: '明日方舟bilibili服' }),
        record('2026-11-02', '合成玉', 10),
        record('2026-11-02', '合成玉', 5, { game_group: '终末地' }),
        record('2026-11-02', '合成玉', 100, { outcome: 'failed' }),
        record('2026-11-02', '合成玉', 100, { outcome: 'repeated' }),
        record('2026-11-02', null, 0),
        record('2026-10-31', null, 0),
        record('2026-11-03', '合成玉', 100)
      ],
      '2026-11-01',
      '2026-11-02'
    )

    expect(report.unparsed).toBe(1)
    expect(report.signedDays).toBe(2)
    expect(report.items).toEqual([
      { name: '合成玉', game_group: '明日方舟', count: 60, days: 2 },
      { name: '合成玉', game_group: '终末地', count: 5, days: 1 }
    ])
  })

  it('跨年时包含日期范围的两个端点', () => {
    const report = buildRewardReport(
      [
        record('2025-12-30', '源岩', 100),
        record('2025-12-31', '源岩', 1),
        record('2026-02-02', '源岩', 2),
        record('2026-02-03', '源岩', 100)
      ],
      '2025-12-31',
      '2026-02-02'
    )
    expect(report).toEqual({
      items: [{ name: '源岩', game_group: '明日方舟', count: 3, days: 2 }],
      signedDays: 2,
      unparsed: 0
    })
  })
})

describe('奖励出现情况', () => {
  const official = {
    key: 'a::明日方舟官服',
    game_group: '明日方舟',
    channel: '官服',
    first_date: '2026-10-30'
  }
  const bilibili = {
    key: 'a::明日方舟bilibili服',
    game_group: '明日方舟',
    channel: 'bilibili服',
    first_date: '2026-11-02'
  }
  const endfield = { key: 'a::终末地官服', game_group: '终末地', first_date: '2026-10-01' }
  const row = (pair, date, item, count, overrides = {}) =>
    record(date, item, count, { pair: pair.key, game_group: pair.game_group, ...overrides })

  it('按真实日期区分获得、签到领到其他奖励、签到失败和无记录', () => {
    const distribution = buildRewardDistribution({
      records: [
        row(official, '2026-10-31', '龙门币', 1000),
        row(official, '2026-11-01', null, 0, { outcome: 'failed' }),
        row(official, '2026-11-01', null, 0, { outcome: 'failed' }),
        row(official, '2026-11-02', '赤金', 2),
        row(official, '2026-11-04', '龙门币', 2000),
        row(endfield, '2026-11-03', '龙门币', 5, { game_group: '终末地' })
      ],
      pairs: [official, endfield],
      start: '2026-10-31',
      end: '2026-11-30',
      today: '2026-11-04',
      item: { name: '龙门币', game_group: '明日方舟' }
    })

    expect(distribution).toMatchObject({ item: '龙门币', total: 3000, days: 2 })
    expect(distribution.months.map(({ label, total, days }) => [label, total, days])).toEqual([
      ['10月', 1000, 1],
      ['11月', 2000, 1]
    ])
    const [october, november] = distribution.months
    expect(october.cells[29]).toEqual({ date: '2026-10-30', state: 'outside' })
    expect(october.cells[30]).toMatchObject({ state: 'got', count: 1000, channels: [] })
    expect(november.cells.slice(0, 5).map((cell) => cell.state)).toEqual([
      'failed',
      'signed',
      'none',
      'got',
      'outside'
    ])
    expect(november.cells[30]).toBeNull()
  })

  it('同一游戏有多个区服时合计数量，并分别列出每个区服当天的结果', () => {
    const distribution = buildRewardDistribution({
      records: [
        row(official, '2026-11-02', '合成玉', 300),
        row(bilibili, '2026-11-02', null, 0, { outcome: 'failed' }),
        row(official, '2026-11-03', '合成玉', 300),
        row(bilibili, '2026-11-03', '合成玉', 300)
      ],
      pairs: [official, bilibili],
      start: '2025-12-31',
      end: '2026-11-03',
      today: '2026-11-03',
      item: { name: '合成玉', game_group: '明日方舟' }
    })

    expect(distribution.months[0].label).toBe('2025年12月')
    expect(distribution.months).toHaveLength(12)
    const november = distribution.months.at(-1)
    expect(november.cells[1]).toMatchObject({
      state: 'got',
      count: 300,
      channels: [
        { channel: '官服', count: 300, outcome: 'signed' },
        { channel: 'B服', count: 0, outcome: 'failed' }
      ]
    })
    expect(november.cells[2]).toMatchObject({ state: 'got', count: 600 })
    expect(november.cells[0].channels).toEqual([{ channel: '官服', count: 0, outcome: 'none' }])
    expect(distribution).toMatchObject({ total: 900, days: 2 })
  })

  it('没有选中奖励时不生成', () => {
    expect(
      buildRewardDistribution({ records: [], pairs: [], start: '', end: '', today: '' })
    ).toBeNull()
  })

  it('汇总和分布采用相同的角色奖励记录，已签到而缺奖励明细的日期显示未知', () => {
    const one = row(official, '2026-11-01', '龙门币', 1000, {
      role_key: 'first',
      event_id: 'claim-a'
    })
    const two = { ...one, role_key: 'second', event_id: 'claim-b' }
    const legacy = row(official, '2026-11-02', '龙门币', 1000)
    const records = [
      one,
      { ...one },
      two,
      legacy,
      { ...legacy },
      row(official, '2026-11-03', null, 0, { outcome: 'repeated' })
    ]
    const start = '2026-11-01'
    const end = '2026-11-03'
    const report = buildRewardReport(records, start, end)
    const distribution = buildRewardDistribution({
      records,
      pairs: [official],
      start,
      end,
      today: end,
      item: report.items[0]
    })
    expect(report.items[0].count).toBe(3000)
    expect(distribution.total).toBe(3000)
    expect(distribution.months[0].cells[0]).toMatchObject({ state: 'got', count: 2000 })
    expect(distribution.months[0].cells[1]).toMatchObject({ state: 'got', count: 1000 })
    expect(distribution.months[0].cells[2]).toMatchObject({ state: 'unknown', count: 0 })
  })
})
