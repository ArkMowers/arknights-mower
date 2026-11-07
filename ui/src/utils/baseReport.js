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

/** 贸易订单类型与单笔龙门币价值：key 与后端 trading_history 的 type/price 组合一致。 */
export const ORDER_PRICES = {
  但书_2000: 2000,
  但书_2500: 2500,
  漏单_1000: 1000,
  漏单_1500: 1500,
  漏单_2000: 2000,
  龙舌兰: 2500,
  佩佩: 1000,
  可露希尔: 1200
}

export const ORDER_TYPES = Object.keys(ORDER_PRICES)

/**
 * 订单分布图配色：标准模式明暗主题各一套，股票模式另按行情皮肤区分深色与亮色底。
 * 亮色行情用加深后的色阶，保证浅色图例和柱段在白色背景上可分辨。
 */
export const ORDER_COLORS = {
  light: {
    但书_2000: '#80cfa9',
    但书_2500: '#a3c1da',
    漏单_1000: '#e57373',
    漏单_1500: '#ffb74d',
    漏单_2000: '#7986cb',
    龙舌兰: '#ffd580',
    佩佩: '#f06292',
    可露希尔: '#34495e',
    未知订单: '#64bfec'
  },
  dark: {
    但书_2000: '#7fe0b0',
    但书_2500: '#8fb8dd',
    漏单_1000: '#ef7f7f',
    漏单_1500: '#ffc266',
    漏单_2000: '#8f9cf0',
    龙舌兰: '#ffe099',
    佩佩: '#f47ba6',
    可露希尔: '#7e9bb8',
    未知订单: '#7ccbf0'
  },
  stock: {
    但书_2000: '#2ebd85',
    但书_2500: '#4a9eda',
    漏单_1000: '#e5484d',
    漏单_1500: '#f0a44b',
    漏单_2000: '#7b83eb',
    龙舌兰: '#f0c95c',
    佩佩: '#e05a8a',
    可露希尔: '#6e8ca8',
    未知订单: '#4aa8e8'
  },
  stockLight: {
    但书_2000: '#1f8a63',
    但书_2500: '#2f7fbe',
    漏单_1000: '#c93a3a',
    漏单_1500: '#a96a00',
    漏单_2000: '#5a5fd0',
    龙舌兰: '#8f6b00',
    佩佩: '#c03a78',
    可露希尔: '#34495e',
    未知订单: '#1f7fa8'
  }
}

function emptyOrderRow(date) {
  const row = {
    日期: date,
    未知订单: null,
    未知订单数: null,
    龙门币订单: null,
    订单数: null,
    订单质量: null,
    赤金: null
  }
  for (const type of ORDER_TYPES) row[type] = null
  return row
}

/**
 * 把基报与贸易订单记录对齐为订单分布图行。
 * 金额按订单类型的单笔龙门币价值折算；未知订单取基报总额与已知金额之差。
 * days 传入时按统计区间对齐并保持区间顺序，缺失日期不补造读数。
 */
export function buildOrderChartRows(reportRows, tradingRows = [], days = null) {
  const trading = new Map(
    asList(tradingRows)
      .filter((row) => row && row['日期'])
      .map((row) => [row['日期'], row])
  )
  const rows = asList(reportRows)
    .filter((row) => row && row['日期'] && !isPlaceholder(row))
    .map((row) => {
      const date = row['日期']
      const trade = trading.get(date) || {}
      const amounts = {}
      let knownAmount = 0
      let knownCount = 0
      for (const type of ORDER_TYPES) {
        const count = isReading(trade[type]) ? trade[type] : 0
        amounts[type] = count * ORDER_PRICES[type]
        knownAmount += amounts[type]
        knownCount += count
      }
      const totalAmount = reading(row['龙门币订单'])
      const totalOrders = reading(row['龙门币订单数'])
      return {
        日期: date,
        ...amounts,
        未知订单: totalAmount === null ? null : Math.max(totalAmount - knownAmount, 0),
        未知订单数: totalOrders === null ? null : Math.max(totalOrders - knownCount, 0),
        龙门币订单: totalAmount,
        订单数: totalOrders,
        订单质量: reading(row['每单获取龙门币']),
        赤金: reading(row['赤金'])
      }
    })
    .sort((a, b) => a.日期.localeCompare(b.日期))
  const range = asList(days)
  if (!range.length) return rows
  const byDate = new Map(rows.map((row) => [row.日期, row]))
  return range.map((day) => byDate.get(day.date) || emptyOrderRow(day.date))
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
