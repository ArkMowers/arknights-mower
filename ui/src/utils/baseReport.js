// 基建报表的纯数据模型：把基报、合成玉与贸易订单记录合并为逐日读数，并按收益系数折算。
// 未读取的读数保持 null，与真实的 0 区分；后端为凑满 15 天补的「-」占位行不进入模型。

export const TEQUILA_GOLD = 500
export const CLOSURE_GOLD = 200
export const ORUNDUM_PER_PULL = 600

export const reportRanges = [
  { value: '7', label: '7 天', days: 7 },
  { value: '14', label: '14 天', days: 14 },
  { value: '30', label: '30 天', days: 30 },
  { value: 'all', label: '全部', days: Infinity }
]

export function isReading(value) {
  return typeof value === 'number' && Number.isFinite(value)
}

function reading(value) {
  return isReading(value) ? value : null
}

function isPlaceholder(row) {
  return ['赤金', '作战录像', '龙门币订单'].every((key) => row[key] === '-')
}

function asList(value) {
  return Array.isArray(value) ? value : []
}

/** 合并三类记录为按日期升序的逐日读数。 */
export function buildReportDays(reportRows, orundumRows = [], tradingRows = []) {
  const orundum = new Map(
    asList(orundumRows)
      .filter((row) => row && row['合成玉'] !== '-')
      .map((row) => [row['日期'], row])
  )
  const trading = new Map(asList(tradingRows).map((row) => [row['日期'], row]))
  return asList(reportRows)
    .filter((row) => row && row['日期'] && !isPlaceholder(row))
    .map((row) => {
      const date = row['日期']
      const trade = trading.get(date) || {}
      const synthesis = orundum.get(date) || {}
      const tequila = reading(trade['龙舌兰']) || 0
      const closure = reading(trade['可露希尔']) || 0
      const orders = reading(row['龙门币订单'])
      const orderCount = reading(row['龙门币订单数'])
      return {
        date,
        gold: reading(row['赤金']),
        experience: reading(row['作战录像']),
        orders,
        orderCount,
        perOrder: orders !== null && orderCount ? Math.round(orders / orderCount) : null,
        tequilaGold: tequila * TEQUILA_GOLD,
        closureGold: closure * CLOSURE_GOLD,
        orundum: reading(synthesis['合成玉']),
        orundumOrders: reading(synthesis['合成玉订单数量'])
      }
    })
    .sort((a, b) => a.date.localeCompare(b.date))
}

/**
 * 按收益系数折算单日收益（单位：万）。
 * 三项读数全部缺失时收益未知；部分缺失按 0 计入并标记 partial。
 */
export function dayIncome(day, ratios) {
  const readings = [day.gold, day.orders, day.experience]
  if (!ratios || readings.every((value) => value === null)) {
    return { total: null, gold: null, special: null, order: null, experience: null, partial: true }
  }
  const scale = 1 / 10000
  const parts = {
    gold: (day.gold || 0) * ratios.gold * scale,
    special: (day.tequilaGold + day.closureGold) * ratios.gold * scale,
    order: (day.orders || 0) * ratios.order * scale,
    experience: (day.experience || 0) * ratios.experience * scale
  }
  return {
    total: parts.gold + parts.special + parts.order + parts.experience,
    ...parts,
    partial: readings.some((value) => value === null)
  }
}

export function withIncome(days, ratios) {
  return days.map((day) => ({ ...day, income: dayIncome(day, ratios) }))
}

export function selectRange(days, rangeValue) {
  const range = reportRanges.find((row) => row.value === rangeValue) || reportRanges[0]
  if (!Number.isFinite(range.days)) return days.slice()
  const datedDays = days.map((day) => ({
    day,
    time:
      typeof day.date === 'string' ? Date.parse(`${day.date.replaceAll('/', '-')}T00:00:00Z`) : NaN
  }))
  const end = datedDays.reduce(
    (latest, { time }) => (Number.isFinite(time) ? Math.max(latest, time) : latest),
    -Infinity
  )
  const start = end - (range.days - 1) * 86400000
  return datedDays.filter(({ time }) => time >= start && time <= end).map(({ day }) => day)
}

function sum(rows, pick) {
  const values = rows.map(pick).filter(isReading)
  return values.length ? values.reduce((total, value) => total + value, 0) : null
}

function average(rows, pick) {
  const values = rows.map(pick).filter(isReading)
  return values.length ? values.reduce((total, value) => total + value, 0) / values.length : null
}

export function relativeChange(current, base) {
  if (!isReading(current) || !isReading(base) || base === 0) return null
  return (current - base) / Math.abs(base)
}

/** 区间汇总：最近一日、前一日对比、区间均值与最佳日。days 需已带 income。 */
export function summarize(days) {
  const latest = days.at(-1) || null
  const previous = days.length > 1 ? days.at(-2) : null
  const incomes = days.filter((day) => isReading(day.income?.total))
  const best = incomes.reduce(
    (top, day) => (!top || day.income.total > top.income.total ? day : top),
    null
  )
  const orundum = sum(days, (day) => day.orundum)
  const orders = sum(days, (day) => day.orders)
  const orderCount = sum(days, (day) => day.orderCount)
  const pairedOrders = days.filter(
    (day) => isReading(day.orders) && isReading(day.orderCount) && day.orderCount > 0
  )
  const pairedOrderCount = sum(pairedOrders, (day) => day.orderCount)
  return {
    latest,
    previous,
    best,
    days: days.length,
    totalIncome: sum(days, (day) => day.income?.total),
    averageIncome: average(days, (day) => day.income?.total),
    dayOverDay: relativeChange(latest?.income?.total, previous?.income?.total),
    gold: sum(days, (day) => day.gold),
    specialGold: sum(days, (day) => day.tequilaGold + day.closureGold),
    experience: sum(days, (day) => day.experience),
    orders,
    orderCount,
    perOrder: pairedOrderCount
      ? Math.round(sum(pairedOrders, (day) => day.orders) / pairedOrderCount)
      : null,
    orundum,
    pulls: orundum === null ? null : orundum / ORUNDUM_PER_PULL,
    missingDays: days.filter((day) => day.income?.partial).length
  }
}

/** 贸易订单历史的查询区间：覆盖全部基报日期，保证更早日期的特殊赤金也能计入。 */
export function tradingRange(reportRows) {
  const dates = asList(reportRows)
    .filter((row) => row && row['日期'] && !isPlaceholder(row))
    .map((row) => row['日期'])
    .sort()
  return dates.length ? { start: dates[0], end: dates.at(-1) } : null
}

const numberFormat = new Intl.NumberFormat('zh-CN')

export function formatCount(value) {
  return isReading(value) ? numberFormat.format(Math.round(value)) : '—'
}

export function formatIncome(value, digits = 2) {
  return isReading(value) ? value.toFixed(digits) : '—'
}

export function formatPercent(value) {
  if (!isReading(value)) return ''
  const percent = Math.abs(value * 100)
  return `${value >= 0 ? '+' : '−'}${percent < 10 ? percent.toFixed(1) : Math.round(percent)}%`
}

/** 日期显示为「10-24 周五」，保留年份之外的信息。 */
export function formatDay(date) {
  const parsed = new Date(`${date.replaceAll('/', '-')}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) return date
  const week = '日一二三四五六'[parsed.getDay()]
  const month = String(parsed.getMonth() + 1).padStart(2, '0')
  const day = String(parsed.getDate()).padStart(2, '0')
  return `${month}-${day} 周${week}`
}
