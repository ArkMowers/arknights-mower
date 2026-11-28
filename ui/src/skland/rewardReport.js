import {
  buildDayMap,
  GAME_GROUPS,
  monthEnd,
  monthStart,
  shiftMonth,
  SIGNED_OUTCOMES
} from './statistics'

function gameOrder(group) {
  const index = GAME_GROUPS.indexOf(group)
  return index === -1 ? GAME_GROUPS.length : index
}

/** 汇总范围内的实际奖励；签到天数按成功或已签到的不同日期计算。 */
export function buildRewardReport(records, start, end) {
  const items = new Map()
  const signedDates = new Set()
  const range = records.filter((row) => row.date >= start && row.date <= end)
  const unparsed = range.filter((row) => row.outcome === 'signed' && !row.item).length
  for (const entry of buildDayMap(range).values()) {
    if (SIGNED_OUTCOMES.includes(entry.outcome)) signedDates.add(entry.date)
    const game = entry.gameGroup || '其他'
    for (const reward of entry.rewards) {
      const key = JSON.stringify([game, reward.item])
      if (!items.has(key)) {
        items.set(key, { name: reward.item, game_group: game, count: 0, days: new Set() })
      }
      const item = items.get(key)
      item.count += reward.count
      item.days.add(entry.date)
    }
  }

  return {
    items: [...items.values()]
      .map((item) => ({ ...item, days: item.days.size }))
      .sort(
        (left, right) =>
          gameOrder(left.game_group) - gameOrder(right.game_group) ||
          right.days - left.days ||
          right.count - left.count ||
          left.name.localeCompare(right.name, 'zh')
      ),
    signedDays: signedDates.size,
    unparsed
  }
}

function channelName(pair) {
  const channel = pair.channel || pair.game
  return channel === 'bilibili服' ? 'B服' : channel
}

/**
 * 一种奖励在所选范围内每天的出现情况，按本机签到记录的真实日期排列。
 * 漏签或签到失败会让游戏内的签到日历比现实日期慢，签到列表的第 N 格不一定在第 N 天领取，
 * 早先月份的签到列表也不一定有缓存，所以这里不按签到列表推算，只看实际领到了什么。
 * 奖励明细缺失的签到显示为奖励未知。
 */
export function buildRewardDistribution({ records, pairs, start, end, today, item }) {
  if (!item) return null
  const group = item.game_group || '其他'
  const relevant = (pairs || []).filter((pair) => (pair.game_group || '其他') === group)
  const keys = new Set(relevant.map((pair) => pair.key))
  const last = end < today ? end : today
  const dayMap = buildDayMap(
    (records || []).filter(
      (record) => keys.has(record.pair) && record.date >= start && record.date <= last
    )
  )

  function cellFor(date) {
    if (date < start || date > last) return { date, state: 'outside' }
    let count = 0
    let signed = false
    let unknown = false
    let failed = false
    let started = false
    const channels = []
    for (const pair of relevant) {
      if (date < pair.first_date) continue
      started = true
      const entry = dayMap.get(`${pair.key}::${date}`)
      const own = (entry?.rewards || [])
        .filter((reward) => reward.item === item.name)
        .reduce((sum, reward) => sum + reward.count, 0)
      const outcome = entry?.rewardDetailsMissing ? 'unknown' : entry?.outcome || 'none'
      count += own
      signed ||= SIGNED_OUTCOMES.includes(outcome)
      unknown ||= outcome === 'unknown'
      failed ||= outcome === 'failed'
      channels.push({ channel: channelName(pair), count: own, outcome })
    }
    if (!started) return { date, state: 'outside' }
    let state = 'none'
    if (count) state = 'got'
    else if (unknown) state = 'unknown'
    else if (signed) state = 'signed'
    else if (failed) state = 'failed'
    return { date, state, count, channels: relevant.length > 1 ? channels : [] }
  }

  const months = []
  if (start <= last) {
    const multiYear = start.slice(0, 4) !== last.slice(0, 4)
    for (let month = monthStart(start); month <= last; month = shiftMonth(month, 1)) {
      const length = Number(monthEnd(month).slice(8))
      const cells = Array.from({ length: 31 }, (_, index) =>
        index < length ? cellFor(`${month.slice(0, 8)}${String(index + 1).padStart(2, '0')}`) : null
      )
      const got = cells.filter((cell) => cell?.state === 'got')
      const [year, number] = month.split('-').map(Number)
      months.push({
        month,
        label: multiYear ? `${year}年${number}月` : `${number}月`,
        cells,
        total: got.reduce((sum, cell) => sum + cell.count, 0),
        days: got.length
      })
    }
  }

  return {
    item: item.name,
    game_group: group,
    months,
    total: months.reduce((sum, month) => sum + month.total, 0),
    days: months.reduce((sum, month) => sum + month.days, 0)
  }
}
