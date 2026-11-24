export const OUTCOME_LABELS = {
  signed: '签到成功',
  repeated: '已签到',
  failed: '签到失败',
  pending: '无记录',
  before: '尚未开始记录',
  none: '无记录'
}

export const OUTCOME_PRIORITY = { signed: 3, repeated: 2, failed: 1, none: 0 }
export const SIGNED_OUTCOMES = ['signed', 'repeated']
export const GAME_GROUPS = ['明日方舟', '终末地']
export const STREAK_MILESTONES = [7, 14, 30, 60, 100, 180, 365, 1000]

export function addDays(date, delta) {
  const value = new Date(`${date}T00:00:00Z`)
  value.setUTCDate(value.getUTCDate() + delta)
  return value.toISOString().slice(0, 10)
}

export function daysBetween(start, end) {
  return (Date.parse(`${end}T00:00:00Z`) - Date.parse(`${start}T00:00:00Z`)) / 86400000
}

export function dateList(start, end) {
  const dates = []
  const total = daysBetween(start, end)
  for (let offset = 0; offset <= total; offset++) dates.push(addDays(start, offset))
  return dates
}

export function weekdayIndex(date) {
  return (new Date(`${date}T00:00:00Z`).getUTCDay() + 6) % 7
}

export function weekStart(date) {
  return addDays(date, -weekdayIndex(date))
}

export function monthStart(date) {
  return `${date.slice(0, 7)}-01`
}

export function shiftMonth(month, offset) {
  const [year, number] = month.split('-').map(Number)
  const date = new Date(0)
  date.setUTCFullYear(year, number - 1 + offset, 1)
  return date.toISOString().slice(0, 10)
}

export function monthEnd(month) {
  return addDays(shiftMonth(month, 1), -1)
}

function snapshotContainsClaim(before, after, done, signedToday) {
  // 快照可在当天签到之前或之后读取。
  if (signedToday === true) return after === done
  if (signedToday === false) return before === done
  return before === done || after === done
}

function matchesReceipt(slot, receipt) {
  return (
    slot.rewards.length > 0 &&
    slot.rewards.length === receipt.length &&
    slot.rewards.every((item) =>
      receipt.some((reward) => item.item === reward.item && item.count === reward.count)
    )
  )
}

function relatesToClaim(slot, date, day, rewardPair) {
  if (date === rewardPair.progress_date && rewardPair.signed_today === true) return true
  if (rewardPair.signed_dates?.includes(date)) return true
  return !day?.rewards.length || !slot.rewards.length || matchesReceipt(slot, day.rewards)
}

/** 根据快照和实际记录，按签到日推进所有可能的已领取格数。 */
function claimPaths({ dates, days, template, rewardPair, done, current, useRewards }) {
  const snapshot = rewardPair.progress_date
  const signedAtSnapshot = rewardPair.signed_today
  const providerDates = Array.isArray(rewardPair.signed_dates)
    ? new Set(rewardPair.signed_dates)
    : null
  const last = dates.at(-1)
  const timeline = []
  let counts = new Set([0])
  for (const date of dates) {
    const onSnapshot = date === snapshot
    const day = days.get(date)
    const recorded = SIGNED_OUTCOMES.includes(day?.outcome)
    let signedOptions = [false, true]
    if (providerDates?.has(date) || (onSnapshot && signedAtSnapshot === true)) {
      signedOptions = [true]
    } else if (providerDates && date < snapshot) {
      signedOptions = [false]
    } else if (recorded) {
      signedOptions = [true]
    } else if (
      current &&
      onSnapshot &&
      date === last &&
      signedAtSnapshot === false &&
      !rewardPair.stale
    ) {
      signedOptions = [false]
    }
    const receiptSlots =
      useRewards && !providerDates?.has(date) && day?.rewards.length
        ? template.filter((slot) => matchesReceipt(slot, day.rewards))
        : []
    const edges = []
    for (const before of counts) {
      for (const signed of signedOptions) {
        const after = Math.min(template.length, before + Number(signed))
        if (onSnapshot && !snapshotContainsClaim(before, after, done, signedAtSnapshot)) continue
        if (after > before && receiptSlots.length && !receiptSlots.includes(template[before]))
          continue
        edges.push({ before, after, signed })
      }
    }
    timeline.push({ date, edges })
    counts = new Set(edges.map(({ after }) => after))
  }
  return { counts, timeline }
}

function resolveClaimPaths(paths, length) {
  const { counts, timeline } = paths
  const datesBySlot = Array.from({ length }, () => new Set())
  let next = counts
  // 只保留能走到最后一天的路径，据此判断每个格子的领取日期是否唯一。
  for (const { date, edges } of timeline.toReversed()) {
    const predecessors = new Set()
    for (const { before, after } of edges) {
      if (!next.has(after)) continue
      predecessors.add(before)
      if (after > before) datesBySlot[before].add(date)
    }
    next = predecessors
  }
  const lastStates = new Set(timeline.at(-1)?.edges.map(({ signed }) => signed))
  return {
    claimed: Math.min(...counts),
    possibleClaimed: Math.max(...counts),
    lastSigned: lastStates.size === 1 ? lastStates.has(true) : null,
    claimDates: datesBySlot.map((possible) => (possible.size === 1 ? [...possible][0] : null))
  }
}

export function buildSignInSlots({
  month,
  today,
  records,
  rewardPair,
  shared = false,
  roleKey = rewardPair?.role_key
}) {
  const end = monthEnd(month)
  const current = monthStart(today) === month
  const last = today < end ? today : end
  const roleRecords = (records || []).filter((record) => {
    if (roleKey) return record.role_key === roleKey
    return !shared && !rewardPair?.progress_ambiguous
  })
  const days = new Map()
  for (const [key, entry] of buildDayMap(roleRecords)) days.set(key.slice(-10), entry)
  const dates = dateList(month, last)
  const snapshot = rewardPair?.progress_date
  const cached = Boolean(rewardPair?.reward_slots?.length) && snapshot >= month && snapshot <= last
  const todayRecord = current ? days.get(today) || null : null

  if (!cached) {
    const signedDates = dates.filter((date) => SIGNED_OUTCOMES.includes(days.get(date)?.outcome))
    const slots = signedDates.map((date, index) => ({
      index: index + 1,
      rewards: days.get(date).rewards,
      claimed: true,
      state: current && date === today ? 'today' : 'claimed',
      date,
      record: days.get(date)
    }))
    const todaySigned = current && signedDates.includes(today)
    if (current && !todaySigned) {
      slots.push({
        index: slots.length + 1,
        rewards: [],
        placeholder: true,
        claimed: false,
        state: 'today',
        date: today,
        record: todayRecord
      })
    }
    return {
      slots,
      claimed: signedDates.length,
      possibleClaimed: signedDates.length,
      total: null,
      todayIndex: slots.find((slot) => slot.state === 'today')?.index ?? null,
      todaySigned,
      todayRecord,
      lag: null,
      source: 'local',
      snapshotDate: null
    }
  }

  const template = rewardPair.reward_slots.map((slot, index) => ({
    index: slot.index ?? index + 1,
    rewards: slot.rewards || []
  }))
  const done = rewardPair.reward_slots.filter((slot) => slot.done).length
  const inputs = { dates, days, template, rewardPair, done, current }
  let paths = claimPaths({ ...inputs, useRewards: true })
  if (!paths.counts.size) paths = claimPaths({ ...inputs, useRewards: false })
  if (!paths.counts.size) paths = claimPaths({ ...inputs, days: new Map(), useRewards: false })
  const progress = paths.counts.size
    ? resolveClaimPaths(paths, template.length)
    : {
        claimed: done,
        possibleClaimed: Math.min(template.length, done + daysBetween(snapshot, last) + 1),
        lastSigned: null,
        claimDates: []
      }

  const { claimed, possibleClaimed, lastSigned, claimDates } = progress
  const todaySigned = current ? lastSigned : false
  const remaining = current ? daysBetween(today, end) + Number(todaySigned === false) : 0
  const exactProgress = claimed === possibleClaimed && todaySigned !== null
  const slots = template.map((slot, position) => {
    const ordinal = position + 1
    const isClaimed = ordinal <= claimed
    let date = isClaimed ? (claimDates[position] ?? null) : null
    let state = 'unknown'
    if (isClaimed) {
      if (date && !relatesToClaim(slot, date, days.get(date), rewardPair)) date = null
      state = current && date === today ? 'today' : 'claimed'
    } else if (ordinal > possibleClaimed + remaining) {
      state = current ? 'unreachable' : 'unclaimed'
    } else if (current && ordinal > possibleClaimed && ordinal <= claimed + remaining) {
      state = exactProgress && todaySigned === false && position === claimed ? 'today' : 'upcoming'
      if (exactProgress) date = addDays(today, position - claimed + Number(todaySigned))
    }
    const record = date && (isClaimed || state === 'today') ? days.get(date) || null : null
    return { ...slot, claimed: isClaimed, state, date, record }
  })
  const elapsed = current
    ? daysBetween(month, today) + Number(todaySigned)
    : daysBetween(month, end) + 1
  return {
    slots,
    claimed,
    possibleClaimed,
    total: template.length,
    todayIndex: slots.find((slot) => slot.state === 'today')?.index ?? null,
    todaySigned,
    todayRecord,
    lag: exactProgress ? Math.max(0, elapsed - claimed) : null,
    source: 'cache',
    snapshotClaimed: done,
    snapshotDate: snapshot
  }
}

// 渠道按钮上的名称：游戏和区服（bilibili服简称 B服），多个角色共用一个渠道时再加角色名。
export function channelChipLabel(channel) {
  const region = channel.channel === 'bilibili服' ? 'B服' : channel.channel
  const role = channel.shared ? ` · ${channel.display_name || `角色 ${channel.role_index}`}` : ''
  return `${channel.game_group} ${region}${role}`
}

// 估算一段文字的宽度（em）：汉字按 1em、空格按 0.3em、其他字符按 0.6em。读取中按上次的名称
// 长度画占位块时使用。
export function textWidthEm(text) {
  let width = 0
  for (const char of String(text ?? '')) {
    width += char === ' ' ? 0.3 : char.charCodeAt(0) > 0xff ? 1 : 0.6
  }
  return Math.round(width * 10) / 10
}

export function gameGroupOf(game) {
  return GAME_GROUPS.find((group) => game?.startsWith(group)) || game || '其他'
}

/** 汇总预计或领不到的奖励条目，按游戏大组和物品累加数量。 */
export function sumRewardEntries(entries) {
  const totals = new Map()
  for (const entry of entries || []) {
    const group = entry.game_group || gameGroupOf(entry.game)
    for (const reward of entry.rewards || []) {
      const key = `${group}::${reward.item}`
      const current = totals.get(key) || { name: reward.item, game_group: group, count: 0, days: 0 }
      current.count += reward.count
      current.days += 1
      totals.set(key, current)
    }
  }
  return [...totals.values()].sort(
    (left, right) =>
      gameGroupOrder(left.game_group) - gameGroupOrder(right.game_group) ||
      right.count - left.count ||
      left.name.localeCompare(right.name, 'zh')
  )
}

const ACCOUNT_FAILURE_MARKERS = [
  '登录',
  '凭证',
  '过期',
  '失效',
  '授权',
  '密码',
  '验证',
  'token',
  'cred'
]

/** 失败信息提到登录或凭证时，重新签到前需要先检查账号设置。 */
export function isAccountFailure(messages) {
  return (messages || []).some((message) =>
    ACCOUNT_FAILURE_MARKERS.some((marker) => String(message).toLowerCase().includes(marker))
  )
}

export function formatMonthDay(date) {
  const [, month, day] = date.split('-')
  return `${Number(month)}/${Number(day)}`
}

export function formatWeekday(date) {
  return '一二三四五六日'[weekdayIndex(date)]
}

export function formatDate(date) {
  const [year, month, day] = date.split('-')
  return `${year}/${Number(month)}/${Number(day)}`
}

export function outcomeLabel(outcome) {
  return OUTCOME_LABELS[outcome] || OUTCOME_LABELS.none
}

/** 同一日期的记录按账号区服归并，可保留已知角色归属。 */
export function buildDayMap(records, { byRole = false } = {}) {
  const days = new Map()
  for (const record of records || []) {
    const roleKey = record.role_key || null
    const key = byRole
      ? JSON.stringify([record.pair, roleKey, record.date])
      : `${record.pair}::${record.date}`
    let entry = days.get(key)
    if (!entry) {
      entry = {
        pair: record.pair,
        date: record.date,
        gameGroup: record.game_group || gameGroupOf(record.game),
        roleKey: byRole ? roleKey : null,
        outcome: 'none',
        signedRewards: new Map(),
        signedEvents: new Set(),
        rolesWithRewards: new Set(),
        repeatedRoles: new Set(),
        missingEvents: new Set(),
        failedMessages: new Set(),
        failedEvents: new Set(),
        legacyFailedAttempts: 0
      }
      days.set(key, entry)
    }
    if (OUTCOME_PRIORITY[record.outcome] > OUTCOME_PRIORITY[entry.outcome]) {
      entry.outcome = record.outcome
    }
    const event = JSON.stringify([roleKey, record.event_id || null])
    if (record.outcome === 'signed') {
      if (record.item) {
        const item = record.event_id ? [event, record.item] : [roleKey, record.item, record.count]
        entry.signedRewards.set(JSON.stringify(item), { item: record.item, count: record.count })
        entry.signedEvents.add(event)
        entry.rolesWithRewards.add(roleKey)
      } else {
        entry.missingEvents.add(event)
      }
    }
    if (record.outcome === 'repeated') entry.repeatedRoles.add(roleKey)
    if (record.outcome === 'failed') {
      if (record.event_id) entry.failedEvents.add(event)
      else entry.legacyFailedAttempts++
      if (record.reward) entry.failedMessages.add(record.reward)
    }
  }
  for (const [
    key,
    {
      signedRewards,
      signedEvents,
      rolesWithRewards,
      repeatedRoles,
      missingEvents,
      failedMessages,
      failedEvents,
      legacyFailedAttempts,
      ...entry
    }
  ] of days) {
    const failedAttempts = failedEvents.size + legacyFailedAttempts
    days.set(key, {
      ...entry,
      rewards: [...signedRewards.values()],
      hasFailure: failedAttempts > 0,
      failedAttempts,
      failedMessages: [...failedMessages],
      rewardDetailsMissing:
        [...missingEvents].some((event) => !signedEvents.has(event)) ||
        [...repeatedRoles].some((role) => !rolesWithRewards.has(role))
    })
  }
  return days
}

/** 每个账号/区服一行；缺失日期是 `none`，不假定已签到。 */
export function buildCalendar(pairs, records, start, end, today = end) {
  const dates = dateList(start, end)
  const days = buildDayMap(records)
  const rows = (pairs || []).map((pair) => {
    const cells = dates.map((date) => {
      const entry = days.get(`${pair.key}::${date}`)
      const before = date < pair.first_date
      return {
        date,
        outcome: before ? 'before' : entry?.outcome || 'none',
        rewards: before ? [] : entry?.rewards || [],
        hasFailure: !before && Boolean(entry?.hasFailure),
        failedAttempts: before ? 0 : entry?.failedAttempts || 0,
        failedMessages: before ? [] : entry?.failedMessages || []
      }
    })
    const first = pair.first_date > start ? pair.first_date : start
    const last = end < today ? end : today
    const expectedDays = first <= last ? daysBetween(first, last) + 1 : 0
    const elapsed = cells.filter((cell) => cell.date <= last)
    const signedDays = elapsed.filter((cell) => SIGNED_OUTCOMES.includes(cell.outcome)).length
    const failedDays = elapsed.filter((cell) => cell.outcome === 'failed').length
    return {
      ...pair,
      cells,
      expectedDays,
      signedDays,
      failedDays,
      coverage: expectedDays ? signedDays / expectedDays : null
    }
  })
  return { dates, rows }
}

export function summarize(calendar, records, { start, end, today }) {
  let signedPairDays = 0
  let failedPairDays = 0
  let expectedPairDays = 0
  let latestDate = ''
  for (const row of calendar.rows) {
    signedPairDays += row.signedDays
    failedPairDays += row.failedDays
    expectedPairDays += row.expectedDays
    if (row.last_date > latestDate) latestDate = row.last_date
  }

  const rewards = new Map()
  let unparsedRewards = 0
  for (const day of buildDayMap(records).values()) {
    if (day.date < start || day.date > end || day.date > today) continue
    unparsedRewards += Number(day.rewardDetailsMissing)
    for (const reward of day.rewards) {
      const key = `${day.gameGroup}::${reward.item}`
      const current = rewards.get(key) || {
        name: reward.item,
        game_group: day.gameGroup,
        count: 0,
        days: new Set()
      }
      current.count += reward.count
      current.days.add(day.date)
      rewards.set(key, current)
    }
  }

  const streakPair = (calendar.rows || []).reduce(
    (best, row) => (row.current_streak > best.current_streak ? row : best),
    { current_streak: 0 }
  )
  const historyPair = (calendar.rows || []).reduce(
    (best, row) => (row.longest_streak > best.longest_streak ? row : best),
    { longest_streak: 0 }
  )

  return {
    signedPairDays,
    failedPairDays,
    expectedPairDays,
    coverage: expectedPairDays ? Math.min(1, signedPairDays / expectedPairDays) : null,
    rewardTotals: [...rewards.values()]
      .map((item) => ({ ...item, days: item.days.size }))
      .sort(
        (left, right) =>
          gameGroupOrder(left.game_group) - gameGroupOrder(right.game_group) ||
          right.days - left.days ||
          right.count - left.count ||
          left.name.localeCompare(right.name, 'zh')
      ),
    rewardKinds: rewards.size,
    unparsedRewards,
    streakPair,
    historyPair,
    milestone: nextMilestone(streakPair.current_streak),
    activePairs: calendar.rows.length,
    latestDate,
    start,
    end,
    today
  }
}

/** 奖励按游戏大组分开呈现，避免同名物品跨游戏相加。 */
export function groupRewardTotals(items) {
  const groups = []
  for (const item of items || []) {
    const group = item.game_group || '其他'
    const last = groups[groups.length - 1]
    if (last && last.group === group) last.items.push(item)
    else groups.push({ group, items: [item] })
  }
  return groups
}

function gameGroupOrder(group) {
  const index = GAME_GROUPS.indexOf(group)
  return index === -1 ? GAME_GROUPS.length : index
}

export function failureReasons(records, limit = 5) {
  const counts = new Map()
  const events = new Set()
  let total = 0
  let latest = null
  for (const record of records || []) {
    if (record.outcome !== 'failed') continue
    if (record.event_id) {
      const event = JSON.stringify([record.pair, record.date, record.role_key, record.event_id])
      if (events.has(event)) continue
      events.add(event)
    }
    total += 1
    const message = record.reward || '未返回失败信息'
    const current = counts.get(message) || {
      message,
      count: 0,
      accounts: new Set(),
      lastDate: ''
    }
    current.count += 1
    current.accounts.add(record.account)
    if (record.date > current.lastDate) current.lastDate = record.date
    counts.set(message, current)
    if (!latest || record.date > latest.date) {
      latest = {
        date: record.date,
        account: record.account,
        game: record.game,
        message
      }
    }
  }
  const items = [...counts.values()]
    .map((item) => ({ ...item, accounts: [...item.accounts].sort() }))
    .sort(
      (left, right) => right.count - left.count || left.message.localeCompare(right.message, 'zh')
    )
  return { items: items.slice(0, limit), total, kinds: items.length, latest }
}

export function formatMonthDayCN(date) {
  if (!date) return ''
  const [, month, day] = date.split('-')
  return `${Number(month)}月${Number(day)}日`
}

export function formatDateLong(date) {
  if (!date) return ''
  const [year, month, day] = date.split('-')
  return `${year}年${Number(month)}月${Number(day)}日`
}

/** 与参考日期同一年时省略年份，跨年时显示完整日期。 */
export function formatDateShort(date, anchor = '') {
  if (!date) return ''
  if (anchor && date.slice(0, 4) !== anchor.slice(0, 4)) return formatDate(date)
  return formatMonthDayCN(date)
}

export function formatRangeLabel(start, end) {
  if (!start || !end) return '所选日期'
  return start.slice(0, 4) === end.slice(0, 4)
    ? `${formatMonthDay(start)} – ${formatMonthDay(end)}`
    : `${formatDate(start)} – ${formatDate(end)}`
}

/** 相对于今天的口语化日期：今天、昨天、N 天前。 */
export function relativeDay(date, today) {
  const days = daysBetween(date, today)
  if (days === 0) return '今天'
  if (days === 1) return '昨天'
  if (days < 0) return `${-days} 天后`
  return `${days} 天前`
}

/** 同一账号区服在同一天的多次失败尝试合并为一条，按日期从新到旧排列。 */
export function buildFailureLog(calendar, records, today) {
  const entries = []
  const rows = new Map((calendar?.rows || []).map((row) => [row.key, row]))
  const dates = new Set(calendar?.dates)
  let attempts = 0
  for (const [key, day] of buildDayMap(records, { byRole: true })) {
    const row = rows.get(day.pair)
    if (!row || !dates.has(day.date) || day.date < row.first_date || !day.hasFailure) continue
    attempts += day.failedAttempts
    const recovered = SIGNED_OUTCOMES.includes(day.outcome)
    entries.push({
      key,
      pair: row.key,
      roleKey: day.roleKey,
      date: day.date,
      account: row.account,
      game: row.game,
      game_group: row.game_group,
      channel: row.channel,
      attempts: day.failedAttempts,
      messages: day.failedMessages,
      recovered,
      pending: !recovered && day.date >= today
    })
  }
  entries.sort(
    (left, right) =>
      right.date.localeCompare(left.date) ||
      gameGroupOrder(left.game_group) - gameGroupOrder(right.game_group) ||
      left.account.localeCompare(right.account) ||
      left.game.localeCompare(right.game, 'zh')
  )
  return {
    entries,
    attempts,
    recovered: entries.filter((entry) => entry.recovered).length,
    reasons: failureReasons(records, 3).items
  }
}

export function nextMilestone(streak) {
  const target = STREAK_MILESTONES.find((value) => streak < value)
  if (!target) return { target: null, remaining: 0, progress: 1 }
  return { target, remaining: target - streak, progress: streak / target }
}

export function percent(value, digits = 1) {
  return value == null || Number.isNaN(value) ? '—' : `${(value * 100).toFixed(digits)}%`
}

export function number(value) {
  return value == null ? '—' : value.toLocaleString('zh-CN')
}
