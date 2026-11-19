import { describe, expect, it } from 'vitest'
import {
  addDays,
  buildCalendar,
  buildDayMap,
  buildFailureLog,
  buildSignInSlots,
  dateList,
  daysBetween,
  failureReasons,
  formatDate,
  formatDateLong,
  formatDateShort,
  formatMonthDay,
  formatMonthDayCN,
  formatRangeLabel,
  formatWeekday,
  groupRewardTotals,
  isAccountFailure,
  nextMilestone,
  number,
  percent,
  shiftMonth,
  sumRewardEntries,
  summarize,
  weekStart
} from './statistics'

const pair = (overrides = {}) => ({
  key: '138****8000::明日方舟官服',
  account: '138****8000',
  game: '明日方舟官服',
  game_group: '明日方舟',
  channel: '官服',
  first_date: '2026-11-01',
  last_date: '2026-11-03',
  record_days: 3,
  signed_days: 2,
  current_streak: 3,
  longest_streak: 3,
  last_outcome: 'signed',
  ...overrides
})

const record = (date, overrides = {}) => ({
  date,
  pair: '138****8000::明日方舟官服',
  account: '138****8000',
  game: '明日方舟官服',
  game_group: '明日方舟',
  outcome: 'signed',
  reward: '龙门币×1000',
  item: '龙门币',
  count: 1000,
  ...overrides
})

describe('签到日历格子', () => {
  const month = '2026-11-01'
  const slots = (count, done = 0) =>
    Array.from({ length: count }, (_, index) => ({
      index: index + 1,
      done: index < done,
      rewards: [{ item: `奖励${index + 1}`, count: index + 1 }]
    }))
  const snapshot = (overrides = {}) => ({
    account: '138****8000',
    game: '明日方舟官服',
    role_index: 1,
    progress_date: '2026-11-01',
    signed_today: false,
    reward_slots: slots(30),
    ...overrides
  })
  const brief = (result) => result.slots.map(({ index, state, date }) => [index, state, date])
  const receipt = (date, index, overrides = {}) =>
    record(date, { item: `奖励${index}`, count: index, ...overrides })

  it('快照之后的本机失败或无记录仍可能有实际签到，只将能确定的格子标为领不到', () => {
    const base = {
      month,
      records: [record('2026-11-30', { outcome: 'failed' })],
      rewardPair: snapshot({
        progress_date: '2026-11-28',
        signed_today: true,
        reward_slots: slots(30, 27)
      })
    }
    const current = buildSignInSlots({ ...base, today: '2026-11-30' })
    expect(current).toMatchObject({ claimed: 27, possibleClaimed: 29, todayIndex: null })
    expect(brief(current).slice(-3)).toEqual([
      [28, 'unknown', null],
      [29, 'unknown', null],
      [30, 'unreachable', null]
    ])
    const previous = buildSignInSlots({ ...base, today: '2026-12-01' })
    expect(brief(previous).slice(-3)).toEqual([
      [28, 'unknown', null],
      [29, 'unknown', null],
      [30, 'unclaimed', null]
    ])
  })

  it('漏签只让签到日历变慢，不留空格，月底排不下的格子本月领不到', () => {
    const records = [
      record('2026-11-01', { outcome: 'failed' }),
      receipt('2026-11-02', 1),
      record('2026-11-03', { outcome: 'repeated' })
    ]
    const result = buildSignInSlots({
      month,
      today: '2026-11-03',
      records,
      rewardPair: snapshot()
    })
    expect(result).toMatchObject({
      claimed: 2,
      total: 30,
      todayIndex: 2,
      todaySigned: true,
      lag: 1,
      source: 'cache',
      snapshotDate: '2026-11-01'
    })
    expect(brief(result).slice(0, 3)).toEqual([
      [1, 'claimed', '2026-11-02'],
      [2, 'today', '2026-11-03'],
      [3, 'upcoming', '2026-11-04']
    ])
    expect(brief(result).at(-2)).toEqual([29, 'upcoming', '2026-11-30'])
    expect(brief(result).at(-1)).toEqual([30, 'unreachable', null])
    expect(result.slots[0].rewards).toEqual([{ item: '奖励1', count: 1 }])
  })

  it('今天还没签到成功时，下一格是今天要领的格子并带出今天的失败', () => {
    const result = buildSignInSlots({
      month,
      today: '2026-11-04',
      records: [
        receipt('2026-11-03', 2),
        record('2026-11-04', { outcome: 'failed', reward: '网络错误' }),
        record('2026-11-04', { outcome: 'failed', reward: '网络错误' })
      ],
      rewardPair: snapshot({
        progress_date: '2026-11-04',
        signed_today: false,
        reward_slots: slots(30, 2)
      })
    })
    expect(result).toMatchObject({ claimed: 2, todayIndex: 3, todaySigned: false, lag: 1 })
    expect(result.todayRecord).toMatchObject({ outcome: 'failed', failedAttempts: 2 })
    expect(brief(result).slice(0, 4)).toEqual([
      [1, 'claimed', null],
      [2, 'claimed', '2026-11-03'],
      [3, 'today', '2026-11-04'],
      [4, 'upcoming', '2026-11-05']
    ])
    expect(result.slots[2].record).toMatchObject({ outcome: 'failed' })
  })

  it('同一账号区服有多个角色时只用归属明确的本机签到推进该角色', () => {
    const result = buildSignInSlots({
      month,
      today: '2026-11-04',
      records: [
        receipt('2026-11-01', 1),
        receipt('2026-11-03', 3, { role_key: 'other' }),
        receipt('2026-11-04', 3, { role_key: 'selected' })
      ],
      rewardPair: snapshot({
        progress_date: '2026-11-03',
        signed_today: true,
        role_key: 'selected',
        reward_slots: slots(30, 2)
      }),
      shared: true
    })
    expect(result).toMatchObject({ claimed: 3, possibleClaimed: 3, todaySigned: true })
    expect(brief(result).slice(0, 3)).toEqual([
      [1, 'claimed', null],
      [2, 'claimed', '2026-11-03'],
      [3, 'today', '2026-11-04']
    ])
  })

  it('只有一个已辨认角色时也不把旧记录算给这个角色', () => {
    const result = buildSignInSlots({
      month,
      today: month,
      records: [receipt(month, 1)],
      rewardPair: snapshot({ role_key: 'selected' })
    })
    expect(result).toMatchObject({ claimed: 0, todaySigned: false, todayIndex: 1 })
    expect(result.todayRecord).toBeNull()
  })

  it('保留快照前本机奖励的实际顺序，不将日期往最后已领取的格子对齐', () => {
    const result = buildSignInSlots({
      month,
      today: '2026-11-05',
      records: [receipt('2026-11-01', 1)],
      rewardPair: snapshot({
        progress_date: '2026-11-05',
        signed_today: true,
        reward_slots: slots(30, 3)
      })
    })
    expect(brief(result).slice(0, 3)).toEqual([
      [1, 'claimed', '2026-11-01'],
      [2, 'claimed', null],
      [3, 'today', '2026-11-05']
    ])
  })

  it('快照后有空档时，唯一匹配的本机奖励可以确定实际格号', () => {
    const result = buildSignInSlots({
      month,
      today: '2026-11-20',
      records: [receipt('2026-11-20', 17)],
      rewardPair: snapshot({
        progress_date: '2026-11-18',
        signed_today: true,
        reward_slots: slots(30, 15)
      })
    })
    expect(result).toMatchObject({ claimed: 17, possibleClaimed: 17, todayIndex: 17 })
    expect(brief(result).slice(14, 17)).toEqual([
      [15, 'claimed', '2026-11-18'],
      [16, 'claimed', '2026-11-19'],
      [17, 'today', '2026-11-20']
    ])
  })

  it('没有快照当天是否已签的证据时，同日记录不能直接配给快照所示末格', () => {
    const result = buildSignInSlots({
      month,
      today: '2026-11-03',
      records: [record('2026-11-03', { outcome: 'repeated' })],
      rewardPair: snapshot({
        progress_date: '2026-11-03',
        signed_today: null,
        reward_slots: slots(30, 1)
      })
    })
    expect(result).toMatchObject({
      claimed: 1,
      possibleClaimed: 2,
      todaySigned: true,
      todayIndex: null
    })
    expect(brief(result).slice(0, 2)).toEqual([
      [1, 'claimed', null],
      [2, 'unknown', null]
    ])
  })

  it('当天刷新失败后沿用旧快照时，不把快照中未领取的状态当作当前结果', () => {
    const today = '2026-11-03'
    const result = buildSignInSlots({
      month,
      today,
      records: [],
      rewardPair: snapshot({
        progress_date: today,
        signed_today: false,
        stale: true,
        reward_slots: slots(30, 2)
      })
    })
    expect(result).toMatchObject({
      claimed: 2,
      possibleClaimed: 3,
      todaySigned: null,
      todayIndex: null
    })
    expect(brief(result)[2]).toEqual([3, 'unknown', null])
  })

  it('使用森空岛给出的完整签到日期，保留日期间的漏签空档', () => {
    const result = buildSignInSlots({
      month,
      today: '2026-11-05',
      records: [],
      rewardPair: snapshot({
        progress_date: '2026-11-05',
        signed_today: true,
        signed_dates: ['2026-11-02', '2026-11-04', '2026-11-05'],
        reward_slots: slots(30, 3)
      })
    })
    expect(brief(result).slice(0, 3)).toEqual([
      [1, 'claimed', '2026-11-02'],
      [2, 'claimed', '2026-11-04'],
      [3, 'today', '2026-11-05']
    ])
  })

  it('没有奖励缓存时按本机签到排出已领取的格子，并留一格给今天', () => {
    const result = buildSignInSlots({
      month,
      today: '2026-11-03',
      records: [
        record('2026-11-01'),
        record('2026-11-02', { outcome: 'failed' }),
        record('2026-11-02', { outcome: 'repeated', item: null })
      ],
      rewardPair: null
    })
    expect(result).toMatchObject({ claimed: 2, total: null, lag: null, source: 'local' })
    expect(brief(result)).toEqual([
      [1, 'claimed', '2026-11-01'],
      [2, 'claimed', '2026-11-02'],
      [3, 'today', '2026-11-03']
    ])
    expect(result.slots[0].rewards).toEqual([{ item: '龙门币', count: 1000 }])
    expect(result.slots[1]).toMatchObject({ rewards: [], record: { hasFailure: true } })
    expect(result.slots[2].placeholder).toBe(true)
  })

  it('历史月份没有走到的格子记为月底未领取，并忽略其他月份的快照', () => {
    const result = buildSignInSlots({
      month: '2026-10-01',
      today: '2026-11-03',
      records: [receipt('2026-10-30', 6), receipt('2026-10-31', 7)],
      rewardPair: snapshot({ progress_date: '2026-10-29', reward_slots: slots(31, 5) })
    })
    expect(result).toMatchObject({ claimed: 7, todayIndex: null, lag: 24 })
    expect(brief(result).slice(4, 8)).toEqual([
      [5, 'claimed', null],
      [6, 'claimed', '2026-10-30'],
      [7, 'claimed', '2026-10-31'],
      [8, 'unclaimed', null]
    ])
    const stale = buildSignInSlots({
      month,
      today: '2026-11-03',
      records: [],
      rewardPair: snapshot({ progress_date: '2026-10-31' })
    })
    expect(stale.source).toBe('local')
  })

  it('按游戏大组汇总格子里的奖励', () => {
    expect(
      sumRewardEntries([
        { game: '明日方舟官服', rewards: [{ item: '龙门币', count: 500 }] },
        { game: '明日方舟bilibili服', rewards: [{ item: '龙门币', count: 300 }] },
        { game: '终末地官服', rewards: [{ item: '龙门币', count: 100 }] }
      ])
    ).toEqual([
      { name: '龙门币', game_group: '明日方舟', count: 800, days: 2 },
      { name: '龙门币', game_group: '终末地', count: 100, days: 1 }
    ])
  })
})

describe('日期工具', () => {
  it('跨月生成闭区间日期', () => {
    expect(dateList('2026-08-30', '2026-09-02')).toEqual([
      '2026-08-30',
      '2026-08-31',
      '2026-09-01',
      '2026-09-02'
    ])
    expect(daysBetween('2026-08-01', '2026-08-31')).toBe(30)
    expect(addDays('2026-12-31', 1)).toBe('2027-01-01')
  })

  it('以周一为一周起点', () => {
    expect(weekStart('2026-11-01')).toBe('2026-10-26')
    expect(weekStart('2026-11-02')).toBe('2026-11-02')
  })

  it('格式化日历表头、完整日期与跨年日期', () => {
    expect(formatMonthDay('2026-08-09')).toBe('8/9')
    expect(formatWeekday('2026-08-09')).toBe('日')
    expect(formatWeekday('2026-08-10')).toBe('一')
    expect(formatDate('2026-11-14')).toBe('2026/11/14')
    expect(formatMonthDayCN('2026-11-14')).toBe('11月14日')
    expect(formatDateLong('2026-11-14')).toBe('2026年11月14日')
    expect(formatDateShort('2026-11-14', '2026-11-30')).toBe('11月14日')
    expect(formatDateShort('2025-11-14', '2026-11-30')).toBe('2025/11/14')
  })

  it('同年区间省略年份，跨年区间显示完整日期', () => {
    expect(formatRangeLabel('2026-08-17', '2026-11-14')).toBe('8/17 – 11/14')
    expect(formatRangeLabel('2025-11-15', '2026-11-14')).toBe('2025/11/15 – 2026/11/14')
    expect(formatRangeLabel('', '')).toBe('所选日期')
  })
})

describe('签到日历', () => {
  it('同一天多条记录按成功优先合并并去重奖励', () => {
    const days = buildDayMap([
      record('2026-11-01'),
      record('2026-11-01'),
      record('2026-11-01', {
        outcome: 'repeated',
        reward: '请勿重复签到！',
        item: null,
        count: 0
      })
    ])
    const entry = days.get('138****8000::明日方舟官服::2026-11-01')
    expect(entry.outcome).toBe('signed')
    expect(entry.rewards).toEqual([{ item: '龙门币', count: 1000 }])
    expect(entry.rewardDetailsMissing).toBe(false)
  })

  it('不同角色领取同样的奖励分别计数，同一响应的重复行只计一次', () => {
    const first = record('2026-11-01', { role_key: 'first', event_id: '1' })
    const [entry] = buildDayMap([
      first,
      first,
      record('2026-11-01', { role_key: 'second', event_id: '2' }),
      record('2026-11-01', {
        role_key: 'third',
        event_id: '3',
        outcome: 'repeated',
        item: null,
        count: 0
      })
    ]).values()
    expect(entry.rewards).toEqual([
      { item: '龙门币', count: 1000 },
      { item: '龙门币', count: 1000 }
    ])
    expect(entry.rewardDetailsMissing).toBe(true)
  })

  it('没有记录的日期标记为 none，并带出每行覆盖率', () => {
    const calendar = buildCalendar(
      [pair()],
      [record('2026-11-01')],
      '2026-11-01',
      '2026-11-03',
      '2026-11-03'
    )
    expect(calendar.rows[0].cells.map((cell) => cell.outcome)).toEqual(['signed', 'none', 'none'])
    expect(calendar.rows[0]).toMatchObject({
      expectedDays: 3,
      signedDays: 1,
      coverage: 1 / 3
    })
  })

  it('失败记录保留失败信息', () => {
    const calendar = buildCalendar(
      [pair()],
      [
        record('2026-11-01', {
          outcome: 'failed',
          item: null,
          count: 0,
          reward: '网络错误'
        })
      ],
      '2026-11-01',
      '2026-11-01'
    )
    expect(calendar.rows[0].cells[0]).toMatchObject({
      outcome: 'failed',
      rewards: [],
      failedMessages: ['网络错误']
    })
  })

  it('首次记录之前的日期标记为尚未开始记录', () => {
    const calendar = buildCalendar(
      [pair({ first_date: '2026-11-03' })],
      [record('2026-11-03')],
      '2026-11-01',
      '2026-11-03'
    )
    expect(calendar.rows[0].cells.map((cell) => cell.outcome)).toEqual([
      'before',
      'before',
      'signed'
    ])
    expect(calendar.rows[0].expectedDays).toBe(1)
  })

  it('同日成功与失败并存时保留失败标记', () => {
    const calendar = buildCalendar(
      [pair()],
      [
        record('2026-11-01'),
        record('2026-11-01', {
          outcome: 'failed',
          item: null,
          count: 0,
          reward: '网络错误'
        })
      ],
      '2026-11-01',
      '2026-11-01'
    )
    expect(calendar.rows[0].cells[0]).toMatchObject({
      outcome: 'signed',
      hasFailure: true,
      failedMessages: ['网络错误']
    })
  })

  it('签到成功但没有奖励明细时不会把失败文本当作奖励', () => {
    const days = buildDayMap([
      record('2026-11-01', { item: null, count: 0, reward: '签到成功' }),
      record('2026-11-01', {
        outcome: 'failed',
        item: null,
        count: 0,
        reward: '网络错误'
      })
    ])
    const entry = days.get('138****8000::明日方舟官服::2026-11-01')
    expect(entry).toMatchObject({
      outcome: 'signed',
      rewards: [],
      rewardDetailsMissing: true,
      failedMessages: ['网络错误']
    })
  })
})

describe('统计汇总', () => {
  it('覆盖率从首次记录算起，不计入尚未开始使用的日期', () => {
    const pairs = [pair({ first_date: '2026-11-05', last_date: '2026-11-08' })]
    const records = [record('2026-11-05'), record('2026-11-06'), record('2026-11-08')]
    const options = { start: '2026-11-01', end: '2026-11-10', today: '2026-11-10' }
    const calendar = buildCalendar(pairs, records, options.start, options.end, options.today)
    const summary = summarize(calendar, records, options)
    expect(summary.coverage).toBeCloseTo(3 / 6)
    expect(summary.signedPairDays).toBe(3)
    expect(summary.failedPairDays).toBe(0)
    expect(summary.expectedPairDays).toBe(6)
    expect(summary.latestDate).toBe('2026-11-08')
  })

  it('汇总奖励数量、种类并选出最长当前连续', () => {
    const pairs = [pair({ current_streak: 5 })]
    const records = [
      record('2026-11-01'),
      record('2026-11-02', { item: '合成玉', count: 300, reward: '合成玉×300' })
    ]
    const options = { start: '2026-11-01', end: '2026-11-02', today: '2026-11-02' }
    const calendar = buildCalendar(pairs, records, options.start, options.end, options.today)
    const summary = summarize(calendar, records, options)
    expect(summary.rewardTotals).toEqual([
      { name: '龙门币', game_group: '明日方舟', count: 1000, days: 1 },
      { name: '合成玉', game_group: '明日方舟', count: 300, days: 1 }
    ])
    expect(summary.rewardKinds).toBe(2)
    expect(summary.streakPair.current_streak).toBe(5)
    expect(summary.milestone).toEqual({ target: 7, remaining: 2, progress: 5 / 7 })
  })

  it('签到成功但奖励无法解析时单独计数', () => {
    const pairs = [pair()]
    const records = [record('2026-11-01', { item: null, count: 0, reward: '签到成功' })]
    const options = { start: '2026-11-01', end: '2026-11-01', today: '2026-11-01' }
    const calendar = buildCalendar(pairs, records, options.start, options.end, options.today)
    const summary = summarize(calendar, records, options)
    expect(summary.unparsedRewards).toBe(1)
    expect(summary.rewardTotals).toEqual([])
  })

  it('账号早于所选区间时，覆盖率从区间起点算起', () => {
    const pairs = [pair({ first_date: '2026-08-01', last_date: '2026-11-10' })]
    const records = [record('2026-11-05')]
    const options = { start: '2026-11-01', end: '2026-11-10', today: '2026-11-10' }
    const calendar = buildCalendar(pairs, records, options.start, options.end, options.today)
    const summary = summarize(calendar, records, options)
    expect(summary.expectedPairDays).toBe(10)
    expect(summary.coverage).toBeCloseTo(0.1)
  })

  it('没有可统计日期时覆盖率为空', () => {
    const pairs = [pair({ first_date: '2026-09-01', last_date: '2026-09-01' })]
    const options = { start: '2026-08-01', end: '2026-08-10', today: '2026-08-10' }
    const calendar = buildCalendar(pairs, [], options.start, options.end, options.today)
    expect(summarize(calendar, [], options).coverage).toBeNull()
  })

  it('未来日期的签到行不会让覆盖率超过 100%', () => {
    const pairs = [pair({ first_date: '2026-11-01', last_date: '2026-11-03' })]
    const records = [record('2026-11-01'), record('2026-11-02'), record('2026-11-03')]
    const options = { start: '2026-11-01', end: '2026-11-03', today: '2026-11-02' }
    const calendar = buildCalendar(pairs, records, options.start, options.end, options.today)
    expect(summarize(calendar, records, options).coverage).toBe(1)
  })
})

describe('月份', () => {
  it('跨年翻月', () => {
    expect(shiftMonth('2026-01-01', -1)).toBe('2025-12-01')
    expect(shiftMonth('2025-12-01', 1)).toBe('2026-01-01')
  })
})

describe('奖励与失败', () => {
  it('按失败信息聚合次数、账号与最近日期', () => {
    const records = [
      record('2026-11-01', { outcome: 'failed', reward: '网络错误' }),
      record('2026-11-02', {
        outcome: 'failed',
        reward: '网络错误',
        account: '139****9000'
      }),
      record('2026-11-03', { outcome: 'failed', reward: '凭证失效' }),
      record('2026-11-04')
    ]
    const result = failureReasons(records, 1)
    expect(result.items).toEqual([
      {
        message: '网络错误',
        count: 2,
        accounts: ['138****8000', '139****9000'],
        lastDate: '2026-11-02'
      }
    ])
    expect(result.total).toBe(3)
    expect(result.kinds).toBe(2)
    expect(result.latest).toEqual({
      date: '2026-11-03',
      account: '138****8000',
      game: '明日方舟官服',
      message: '凭证失效'
    })
  })

  it('同一天的多次失败合并为一条，并标明重试结果', () => {
    const records = [
      record('2026-11-01', { outcome: 'failed', reward: '网络错误' }),
      record('2026-11-01', { outcome: 'failed', reward: '请求超时' }),
      record('2026-11-02', { outcome: 'failed', reward: '网络错误' }),
      record('2026-11-02'),
      record('2026-11-03'),
      record('2026-11-04', { outcome: 'failed', reward: '网络错误' })
    ]
    const calendar = buildCalendar([pair()], records, '2026-11-01', '2026-11-04', '2026-11-04')
    const log = buildFailureLog(calendar, records, '2026-11-04')
    expect(log.attempts).toBe(4)
    expect(log.recovered).toBe(1)
    expect(log.reasons.map((reason) => [reason.message, reason.count])).toEqual([
      ['网络错误', 3],
      ['请求超时', 1]
    ])
    expect(
      log.entries.map(({ date, attempts, recovered, pending }) => ({
        date,
        attempts,
        recovered,
        pending
      }))
    ).toEqual([
      { date: '2026-11-04', attempts: 1, recovered: false, pending: true },
      { date: '2026-11-02', attempts: 1, recovered: true, pending: false },
      { date: '2026-11-01', attempts: 2, recovered: false, pending: false }
    ])
    expect(log.entries[2].messages).toEqual(['网络错误', '请求超时'])
    expect(buildFailureLog(null, [], '2026-11-04')).toMatchObject({ entries: [], attempts: 0 })
  })

  it('同区服另一个角色签到成功时，失败角色仍保留当天的失败状态', () => {
    const today = '2026-11-01'
    const failure = record(today, {
      outcome: 'failed',
      role_key: 'second',
      event_id: 'failure',
      reward: '请求超时'
    })
    const records = [record(today, { role_key: 'first', event_id: 'success' }), failure, failure]
    const calendar = buildCalendar([pair()], records, today, today)
    expect(buildFailureLog(calendar, records, today)).toMatchObject({
      attempts: 1,
      recovered: 0,
      entries: [
        {
          date: today,
          roleKey: 'second',
          pending: true,
          recovered: false,
          messages: ['请求超时']
        }
      ]
    })
  })

  it('登录或凭证类失败需要先检查账号', () => {
    expect(isAccountFailure(['网络错误', '登录已过期'])).toBe(true)
    expect(isAccountFailure(['Invalid TOKEN'])).toBe(true)
    expect(isAccountFailure(['服务暂时不可用，签到失败'])).toBe(false)
    expect(isAccountFailure()).toBe(false)
  })

  it('没有失败时返回空列表与空最近记录', () => {
    expect(failureReasons([])).toEqual({ items: [], total: 0, kinds: 0, latest: null })
  })

  it('奖励按游戏大组分组，同名物品不跨游戏相加', () => {
    const groups = groupRewardTotals([
      { name: '合成玉', game_group: '明日方舟', count: 300, days: 1 },
      { name: '合成玉', game_group: '终末地', count: 100, days: 1 }
    ])
    expect(groups).toEqual([
      {
        group: '明日方舟',
        items: [{ name: '合成玉', game_group: '明日方舟', count: 300, days: 1 }]
      },
      {
        group: '终末地',
        items: [{ name: '合成玉', game_group: '终末地', count: 100, days: 1 }]
      }
    ])
  })
})

describe('里程碑与格式化', () => {
  it('选择下一个连续签到里程碑', () => {
    expect(nextMilestone(5)).toEqual({ target: 7, remaining: 2, progress: 5 / 7 })
    expect(nextMilestone(30)).toEqual({ target: 60, remaining: 30, progress: 0.5 })
    expect(nextMilestone(1000)).toEqual({ target: null, remaining: 0, progress: 1 })
  })

  it('处理空值和百分比', () => {
    expect(percent(0.9567)).toBe('95.7%')
    expect(percent(null)).toBe('—')
    expect(number(12000)).toBe('12,000')
    expect(number(null)).toBe('—')
  })
})
