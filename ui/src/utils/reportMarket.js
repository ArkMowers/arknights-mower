import { isReading } from './baseReport.js'

const DAY = 86400000
const GAME_OFFSET = 4 * 3600000

function dayTime(date) {
  if (typeof date !== 'string') return NaN
  const normalized = date.replaceAll('/', '-')
  if (!/^\d{4}-\d{2}-\d{2}$/.test(normalized)) return NaN
  const time = Date.parse(`${normalized}T00:00:00Z`)
  return Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === normalized
    ? time
    : NaN
}

const dateText = (time) => new Date(time).toISOString().slice(0, 10)

function periodStart(time, period) {
  const date = new Date(time)
  if (period === 'month') date.setUTCDate(1)
  else date.setUTCDate(date.getUTCDate() - ((date.getUTCDay() + 6) % 7))
  return date.getTime()
}

function periodEnd(start, period) {
  const date = new Date(start)
  if (period === 'month') date.setUTCMonth(date.getUTCMonth() + 1)
  else date.setUTCDate(date.getUTCDate() + 7)
  return date.getTime()
}

/** 用周期内真实的完整日收益生成周/月 K，裁剪显示范围不裁剪周期样本。 */
export function buildIncomeCandles(historyDays, period, visibleDays = historyDays) {
  if (!['week', 'month'].includes(period)) return []
  const visible = (Array.isArray(visibleDays) ? visibleDays : [])
    .map((day) => dayTime(day?.date))
    .filter(Number.isFinite)
  if (!visible.length) return []
  const grouped = new Map()
  for (const day of Array.isArray(historyDays) ? historyDays : []) {
    const time = dayTime(day?.date)
    if (!Number.isFinite(time)) continue
    const key = periodStart(time, period)
    if (!grouped.has(key)) grouped.set(key, new Map())
    grouped.get(key).set(time, day)
  }
  const lastVisible = Math.max(...visible)
  const result = []
  for (let start = periodStart(Math.min(...visible), period); start <= lastVisible;) {
    const end = periodEnd(start, period)
    const rows = [...(grouped.get(start)?.entries() || [])].sort((a, b) => a[0] - b[0])
    const complete = rows.filter(([, day]) => isReading(day.income?.total) && !day.income.partial)
    const values = complete.map(([, day]) => day.income.total)
    const amount = values.reduce((sum, value) => sum + value, 0)
    const missingCount = Math.round((end - start) / DAY) - complete.length
    const counts = rows.map(([, day]) => day.orderCount).filter(isReading)
    result.push({
      start: (start - GAME_OFFSET) / 1000,
      end: (end - GAME_OFFSET) / 1000,
      label: dateText(start),
      open: values[0] ?? null,
      high: values.length ? Math.max(...values) : null,
      low: values.length ? Math.min(...values) : null,
      close: values.at(-1) ?? null,
      mean: values.length ? amount / values.length : null,
      count: values.length,
      amount,
      orderCount: counts.length ? counts.reduce((sum, value) => sum + value, 0) : null,
      firstDate: dateText(start),
      lastDate: dateText(end - DAY),
      missingCount,
      incomplete: missingCount > 0
    })
    start = end
  }
  return result
}

/** 订单查询包含当前游戏日；全部范围最多保留最近 366 天。now 为 Unix 毫秒。 */
export function orderCandleQuery(rangeValue, now = Date.now()) {
  const days = { 7: 7, 14: 14, 30: 30, all: 366 }[rangeValue] || 14
  const currentDay = Math.floor((now + GAME_OFFSET) / DAY) * DAY
  return { startDate: dateText(currentDay - (days - 1) * DAY), endDate: dateText(currentDay) }
}
