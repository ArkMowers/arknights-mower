<script setup>
defineOptions({ name: 'StockReport' })

import { computed, getCurrentInstance, nextTick, onBeforeUnmount, onMounted, ref, toRaw } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, CandlestickChart, LineChart } from 'echarts/charts'
import {
  AriaComponent,
  DataZoomComponent,
  DatasetComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  MarkPointComponent,
  TitleComponent,
  TooltipComponent
} from 'echarts/components'
import VChart from 'vue-echarts'
import { buildIncomeCandles } from '@/utils/reportMarket'
import {
  ORDER_COLORS,
  ORDER_PRICES,
  ORDER_TYPES,
  formatCount,
  formatDay,
  formatIncome,
  formatPercent,
  isReading,
  relativeChange,
  reportRanges
} from '@/utils/baseReport'

use([
  AriaComponent,
  DataZoomComponent,
  BarChart,
  CandlestickChart,
  CanvasRenderer,
  DatasetComponent,
  GridComponent,
  LegendComponent,
  LineChart,
  MarkLineComponent,
  MarkPointComponent,
  TitleComponent,
  TooltipComponent
])

const props = defineProps({
  days: { type: Array, default: () => [] },
  summary: { type: Object, default: null },
  selectedDay: { type: Object, default: null },
  previousDay: { type: Object, default: null },
  orderRows: { type: Array, default: () => [] },
  historyDays: { type: Array, default: () => [] },
  metric: { type: String, default: 'income' },
  orderPeriod: { type: String, default: '4h' },
  orderCandles: { type: Array, default: () => [] },
  orderCandlesLoading: { type: Boolean, default: false },
  orderCandlesError: { type: String, default: '' },
  orderCandleRange: { type: Object, default: null },
  algorithmLabel: { type: String, default: '' },
  rangeLabel: { type: String, default: '' },
  range: { type: String, default: '14' },
  algorithmOptions: { type: Array, default: () => [] },
  algorithmValue: { type: [Number, String], default: null },
  loading: { type: Boolean, default: false },
  refreshing: { type: Boolean, default: false },
  restoreBusy: { type: Boolean, default: false },
  modeDisabled: { type: Boolean, default: false },
  dark: { type: Boolean, default: true }
})
const emit = defineEmits([
  'select',
  'change-metric',
  'change-order-period',
  'retry-order-candles',
  'change-range',
  'change-mode',
  'refresh',
  'select-algorithm',
  'restore-history'
])

// 行情终端双主题：深色沿用经典黑底；亮色按白底重新校准涨跌与指标色。
// 取值与 .term / .term--light 的 CSS 变量保持一致，改一处要同时改另一处。
const TERM_PALETTES = {
  dark: {
    bg: '#000000',
    surface: '#050505',
    surface2: '#0a0a0a',
    hover: '#101010',
    line: '#2a2a2a',
    lineSoft: '#171717',
    grid: 'rgba(255, 255, 255, 0.08)',
    text: '#d7d7d7',
    muted: '#8a8a8a',
    up: '#ff3232',
    down: '#00d26a',
    cyan: '#54fcfc',
    blue: '#3399ff',
    yellow: '#f5e663',
    magenta: '#ff5fd2',
    purple: '#b06cff',
    ma5: '#ffffff',
    lineMain: '#ffffff',
    tipBg: '#000000',
    tipShadow: 'rgba(0,0,0,.6)'
  },
  light: {
    bg: '#ffffff',
    surface: '#f7f8fa',
    surface2: '#f0f3f7',
    hover: '#eef2f7',
    line: '#d6dce4',
    lineSoft: '#e7ebf0',
    grid: 'rgba(31, 34, 37, 0.1)',
    text: '#1f2225',
    muted: '#5b6675',
    up: '#c62828',
    down: '#067045',
    cyan: '#0a6fc2',
    blue: '#1557b0',
    yellow: '#8f6400',
    magenta: '#b51fa0',
    purple: '#6b3fd4',
    ma5: '#4b5563',
    lineMain: '#1f2225',
    tipBg: '#ffffff',
    tipShadow: 'rgba(31,34,37,.16)'
  }
}
// dark 省略时按深色处理：终端自身默认皮肤是黑底，只有显式传 false 才切亮色。
const COLOR = computed(() => (props.dark === false ? TERM_PALETTES.light : TERM_PALETTES.dark))
const NAV_TABS = [
  { key: 'chart', label: '图表' },
  { key: 'heat', label: '板块热力' },
  { key: 'list', label: '行情列表' }
]
const METRICS = [
  { value: 'income', label: '基建收益' },
  { value: 'orders', label: '已记录订单质量' }
]
const INCOME_PERIODS = [
  { value: 'trend', label: '每日走势' },
  { value: 'week', label: '周K' },
  { value: 'month', label: '月K' }
]
const ORDER_PERIODS = [
  { value: '1h', label: '1 小时K' },
  { value: '4h', label: '4 小时K' },
  { value: 'day', label: '日K' }
]
// 资金分析的类别只定义"是什么"，颜色统一由 COMPOSITION_COLORS 给出。
const FUND_PARTS = [
  { key: 'gold', label: '赤金' },
  { key: 'special', label: '特殊赤金' },
  { key: 'order', label: '订单' },
  { key: 'experience', label: '经验' }
]

function isReducedMotion() {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}
const reducedMotion = isReducedMotion()

// ---- 终端视图、全屏与工具菜单 ----
const navActive = ref('chart')
const incomePeriod = ref('trend')
const selectedIncomeBucket = ref(null)
const selectedOrderBucket = ref(null)
const marketPage = ref(1)
const MARKET_PAGE_SIZE = 200
const activeMetric = computed(() => (props.metric === 'orders' ? 'orders' : 'income'))
const isOrders = computed(() => activeMetric.value === 'orders')
const periodOptions = computed(() => (isOrders.value ? ORDER_PERIODS : INCOME_PERIODS))
const activePeriod = computed(() =>
  isOrders.value ? props.orderPeriod || '4h' : incomePeriod.value
)
const isTrend = computed(() => !isOrders.value && incomePeriod.value === 'trend')
const periodLabel = computed(
  () => periodOptions.value.find((row) => row.value === activePeriod.value)?.label || ''
)
const metricLabel = computed(() => METRICS.find((row) => row.value === activeMetric.value).label)
const termRef = ref(null)
const bodyRef = ref(null)
const menuRef = ref(null)
const menuTriggerRef = ref(null)
const menuOpen = ref(false)
const nativeFullscreen = ref(false)
const immersive = ref(false)
const isFullscreen = computed(() => nativeFullscreen.value || immersive.value)
const chartViewActive = computed(() => navActive.value === 'chart')
const rangeTabs = computed(() =>
  reportRanges.map((row) => ({ value: row.value, label: row.label }))
)
const activeRange = computed(() => props.range || '14')

// 顶栏 tab 现在是整个主区的视图切换：热力/列表不再滚到页面下方。
async function setNav(key) {
  const tab = NAV_TABS.find((item) => item.key === key)
  if (!tab) return
  navActive.value = key
  // 切换视图时回到主区顶部，避免沿用上一个视图的滚动位置。
  await nextTick()
  if (bodyRef.value) bodyRef.value.scrollTop = 0
}
function setMetric(value) {
  if (METRICS.some((row) => row.value === value) && value !== activeMetric.value) {
    marketPage.value = 1
    emit('change-metric', value)
  }
}
function setPeriod(value) {
  if (!periodOptions.value.some((row) => row.value === value) || value === activePeriod.value)
    return
  marketPage.value = 1
  if (isOrders.value) {
    selectedOrderBucket.value = null
    emit('change-order-period', value)
  } else {
    selectedIncomeBucket.value = null
    incomePeriod.value = value
  }
}
function setRange(value) {
  if (value !== activeRange.value) emit('change-range', value)
}
function toggleMenu() {
  menuOpen.value = !menuOpen.value
}
async function closeMenu() {
  menuOpen.value = false
  if (isFullscreen.value) await exitFullscreen()
}
async function selectAlgorithm(value) {
  menuOpen.value = false
  if (isFullscreen.value) await exitFullscreen()
  emit('select-algorithm', value)
}
async function restoreHistory() {
  menuOpen.value = false
  if (isFullscreen.value) await exitFullscreen()
  emit('restore-history')
}
async function refresh() {
  menuOpen.value = false
  if (isFullscreen.value) await exitFullscreen()
  emit('refresh')
}
function switchToStandard() {
  if (props.modeDisabled) return
  emit('change-mode', 'standard')
}
function standardFromMenu() {
  menuOpen.value = false
  switchToStandard()
}
async function fullscreenFromMenu() {
  menuOpen.value = false
  await toggleFullscreen()
}

function syncFullscreenState() {
  const doc = globalThis.document
  if (!doc) return
  nativeFullscreen.value = doc.fullscreenElement === toRaw(termRef.value)
  if (nativeFullscreen.value) immersive.value = false
}
async function exitFullscreen() {
  const doc = globalThis.document
  if (doc?.fullscreenElement) {
    try {
      await doc.exitFullscreen()
    } catch {
      // 浏览器已经退出全屏时忽略这次失败。
    }
  }
  nativeFullscreen.value = false
  immersive.value = false
}
async function toggleFullscreen() {
  if (isFullscreen.value) {
    await exitFullscreen()
    return
  }
  const element = toRaw(termRef.value)
  if (element && typeof element.requestFullscreen === 'function') {
    try {
      await element.requestFullscreen()
      syncFullscreenState()
      return
    } catch {
      // 非用户手势或被浏览器策略拒绝时，退回页面内沉浸模式。
    }
  }
  immersive.value = true
}
function onDocumentPointerDown(event) {
  if (!menuOpen.value) return
  const target = event.target
  if (menuRef.value?.contains(target) || menuTriggerRef.value?.contains(target)) return
  menuOpen.value = false
}
function onDocumentKeydown(event) {
  if (event.key !== 'Escape') return
  if (menuOpen.value) {
    menuOpen.value = false
    return
  }
  if (immersive.value) immersive.value = false
}
// 单元测试会直接调用 setup，此时没有组件实例，也没有需要清理的全局监听。
if (getCurrentInstance()) {
  onMounted(() => {
    syncFullscreenState()
    globalThis.document.addEventListener('pointerdown', onDocumentPointerDown)
    globalThis.document.addEventListener('keydown', onDocumentKeydown)
    globalThis.document.addEventListener('fullscreenchange', syncFullscreenState)
  })
  onBeforeUnmount(() => {
    globalThis.document.removeEventListener('pointerdown', onDocumentPointerDown)
    globalThis.document.removeEventListener('keydown', onDocumentKeydown)
    globalThis.document.removeEventListener('fullscreenchange', syncFullscreenState)
    if (globalThis.document.fullscreenElement === toRaw(termRef.value)) {
      try {
        const exited = globalThis.document.exitFullscreen()
        if (exited && typeof exited.catch === 'function') exited.catch(() => {})
      } catch {
        // 卸载时浏览器可能已自行退出全屏。
      }
    }
  })
}

function asList(value) {
  return Array.isArray(value) ? value : []
}
function dayLabel(date) {
  return typeof date === 'string' && date ? formatDay(date) : '—'
}
function shortDate(date) {
  return typeof date === 'string' && date.length >= 10 ? date.slice(5) : '—'
}
function signedText(value, formatter) {
  if (!isReading(value)) return '—'
  if (value === 0) return `±${formatter(0)}`
  return `${value > 0 ? '+' : '−'}${formatter(Math.abs(value))}`
}
function deltaClass(row) {
  if (!row || !isReading(row.delta) || row.delta === 0) return 'is-flat'
  return row.delta > 0 ? 'is-up' : 'is-down'
}
function toneOf(value) {
  if (!isReading(value) || value === 0) return 'is-flat'
  return value > 0 ? 'is-up' : 'is-down'
}
function arrowOf(value) {
  if (!isReading(value) || value === 0) return ''
  return value > 0 ? '▲' : '▼'
}
function changeTextOf(change) {
  if (!isReading(change)) return '—'
  return change === 0 ? '±0.0%' : formatPercent(change)
}
function earlier(left, right) {
  if (typeof left !== 'string' || typeof right !== 'string') return false
  return left.replaceAll('/', '-') < right.replaceAll('/', '-')
}
function round4(value) {
  return Math.round(value * 10000) / 10000
}
function movingAverage(values, period) {
  return values.map((value, index) => {
    if (index < period - 1) return null
    const windowValues = values.slice(index - period + 1, index + 1)
    if (!windowValues.every(isReading)) return null
    return round4(windowValues.reduce((sum, item) => sum + item, 0) / period)
  })
}
// ---- 选中日与对照日 ----
const days = computed(() => asList(props.days))
const currentDay = computed(() => props.selectedDay || days.value.at(-1) || null)
const hasDays = computed(() => days.value.length > 0)
// 缺失读数按 0 计入的 partial 日不能当作行情收盘：股票模式把它视为停牌缺口，
// 避免把"部分读数缺失"渲染成暴跌，也从涨跌幅与振幅中排除。
function totalOf(day) {
  if (!day || day.income?.partial) return null
  const total = day.income?.total
  return isReading(total) ? total : null
}
// 盘口与指数栏的对照基准取"当前日之前最近一次完整读数"：
// 前一条记录是 partial 日时不能把涨跌幅断成 "—"。
const previousValidDay = computed(() => {
  const current = currentDay.value
  if (!current) return null
  const history = asList(props.historyDays)
  const list = history.length ? history : days.value
  const index = list.findIndex((day) => day.date === current.date)
  if (index >= 0) {
    for (let i = index - 1; i >= 0; i -= 1) {
      if (totalOf(list[i]) !== null) return list[i]
    }
  }
  const fallback = props.previousDay
  if (
    fallback &&
    fallback.date !== current.date &&
    earlier(fallback.date, current.date) &&
    totalOf(fallback) !== null
  ) {
    return fallback
  }
  return null
})
const previousClose = computed(() => totalOf(previousValidDay.value))

// ---- 报价 ----
const quote = computed(() => {
  const close = totalOf(currentDay.value)
  const base = previousClose.value
  const delta = isReading(close) && isReading(base) ? close - base : null
  const change = relativeChange(close, base)
  return {
    close,
    base,
    delta,
    change,
    partial: Boolean(currentDay.value?.income?.partial),
    closeText: formatIncome(close),
    deltaText: signedText(delta, (value) => formatIncome(value)),
    changeText: changeTextOf(change),
    arrowText: arrowOf(delta),
    tone: deltaClass({ delta }),
    color: !isReading(close)
      ? COLOR.value.muted
      : !isReading(delta) || delta === 0
        ? COLOR.value.text
        : delta > 0
          ? COLOR.value.up
          : COLOR.value.down
  }
})

// ---- 指数栏 ----
const indexStrip = computed(() => {
  const day = currentDay.value
  const base = previousValidDay.value
  const parts = [
    {
      key: 'income',
      label: '基报指数',
      pick: (row) => totalOf(row),
      formatter: (value) => formatIncome(value)
    },
    {
      key: 'gold',
      label: '赤金',
      pick: (row) => row.gold,
      formatter: (value) => formatCount(value)
    },
    {
      key: 'special',
      label: '特殊赤金',
      pick: (row) =>
        isReading(row.tequilaGold) || isReading(row.closureGold)
          ? (row.tequilaGold || 0) + (row.closureGold || 0)
          : null,
      formatter: (value) => formatCount(value)
    },
    {
      key: 'orders',
      label: '龙门币订单',
      pick: (row) => row.orders,
      formatter: (value) => formatCount(value)
    },
    {
      key: 'experience',
      label: '经验',
      pick: (row) => row.experience,
      formatter: (value) => formatCount(value)
    },
    {
      key: 'orundum',
      label: '合成玉',
      pick: (row) => row.orundum,
      formatter: (value) => formatCount(value)
    }
  ]
  return parts.map((part) => {
    const value = day ? part.pick(day) : null
    const baseValue = base ? part.pick(base) : null
    const change = relativeChange(value, baseValue)
    const delta = isReading(value) && isReading(baseValue) ? value - baseValue : null
    return {
      key: part.key,
      label: part.label,
      valueText: part.formatter(value),
      change,
      changeText: changeTextOf(change),
      arrowText: arrowOf(delta),
      tone: deltaClass({ delta })
    }
  })
})

// ---- 盘口数据 ----
const orderRowByDate = computed(() => {
  const map = new Map()
  for (const row of asList(props.orderRows)) {
    if (row && row['日期']) map.set(row['日期'], row)
  }
  return map
})
function qualityForDate(date) {
  const value = orderRowByDate.value.get(date)?.['订单质量']
  return isReading(value) ? value : null
}
function qualityOf(day) {
  return day ? qualityForDate(day.date) : null
}
// 收益构成条与资金分析环共用一套类别颜色，避免红绿同时表达"类别"和"涨跌"。
const COMPOSITION_COLORS = computed(() => ({
  experience: COLOR.value.purple,
  order: COLOR.value.blue,
  special: COLOR.value.yellow,
  gold: COLOR.value.up,
  orundum: COLOR.value.muted
}))
const composition = computed(() => {
  const day = currentDay.value
  // 与盘口一致：分项变化对比最近一次完整读数，避免和 partial 日的 0 值比较。
  const base = previousValidDay.value
  // 分项缺失时显示 "—"，不能把 baseReport 按 0 计入的缺失项当真实读数。
  const items = [
    {
      key: 'experience',
      label: '经验',
      pick: (row) => row.income?.experience,
      missing: (row) => !isReading(row.experience)
    },
    {
      key: 'order',
      label: '龙门币订单',
      pick: (row) => row.income?.order,
      missing: (row) => !isReading(row.orders)
    },
    { key: 'special', label: '特殊赤金', pick: (row) => row.income?.special },
    {
      key: 'gold',
      label: '赤金',
      pick: (row) => row.income?.gold,
      missing: (row) => !isReading(row.gold)
    },
    {
      key: 'orundum',
      label: '合成玉',
      pick: (row) => (isReading(row.orundum) ? row.orundum : null),
      missing: (row) => !isReading(row.orundum),
      raw: true
    }
  ]
  const values = items.map((item) => (day ? item.pick(day) : null))
  const maxIncome = Math.max(...values.slice(0, 4).filter(isReading), 0)
  return items.map((item, index) => {
    const missing = day ? Boolean(item.missing?.(day)) : true
    const value = missing ? null : values[index]
    const baseValue = !missing && base ? item.pick(base) : null
    const delta = isReading(value) && isReading(baseValue) ? value - baseValue : null
    const formatter = item.raw ? (amount) => formatCount(amount) : (amount) => formatIncome(amount)
    const width = !isReading(value)
      ? 0
      : item.raw
        ? Math.max(2, Math.min(100, Math.round((value / 600) * 100)))
        : maxIncome > 0
          ? Math.max(2, Math.round((value / maxIncome) * 100))
          : 0
    return {
      key: item.key,
      label: item.label,
      value,
      valueText: missing ? '—' : formatter(value),
      deltaText: missing ? '—' : signedText(delta, formatter),
      width,
      color: missing ? COLOR.value.muted : COMPOSITION_COLORS.value[item.key],
      tone: missing ? 'is-flat' : deltaClass({ delta })
    }
  })
})

const fundIncomplete = computed(() => Boolean(currentDay.value?.income?.partial))
const fundRows = computed(() => {
  if (fundIncomplete.value) {
    return FUND_PARTS.map((part) => ({
      ...part,
      color: COMPOSITION_COLORS.value[part.key],
      value: 0,
      percentText: '—'
    }))
  }
  const income = currentDay.value?.income || {}
  const values = FUND_PARTS.map((part) => {
    const value = income[part.key]
    return isReading(value) && value > 0 ? value : 0
  })
  const total = values.reduce((sum, value) => sum + value, 0)
  return FUND_PARTS.map((part, index) => ({
    ...part,
    color: COMPOSITION_COLORS.value[part.key],
    value: values[index],
    percentText: total > 0 ? `${Math.round((values[index] / total) * 100)}%` : '—'
  }))
})
const fundRingStyle = computed(() => {
  const rows = fundRows.value
  const total = rows.reduce((sum, row) => sum + row.value, 0)
  if (fundIncomplete.value || !total) return { background: COLOR.value.surface2 }
  let start = 0
  const stops = rows.map((row) => {
    const end = start + (row.value / total) * 360
    const stop = `${row.color} ${start.toFixed(1)}deg ${end.toFixed(1)}deg`
    start = end
    return stop
  })
  return { background: `conic-gradient(${stops.join(', ')})` }
})

// ---- 逐日序列与指标 ----
// open 取上一有效收盘：partial 日没有收盘，下一根蜡烛不能从缺失日的折半值起跳。
function buildDailyRows(list, seedDay) {
  const first = list[0]
  let lastClose =
    seedDay && totalOf(seedDay) !== null && first && earlier(seedDay.date, first.date)
      ? totalOf(seedDay)
      : null
  return list.map((day) => {
    const close = totalOf(day)
    const open = isReading(lastClose) ? lastClose : close
    const available = isReading(open) && isReading(close)
    const row = {
      date: day.date,
      label: dayLabel(day.date),
      shortDate: shortDate(day.date),
      open,
      close,
      high: available ? Math.max(open, close) : null,
      low: available ? Math.min(open, close) : null,
      delta: available ? close - open : null,
      change: available ? relativeChange(close, open) : null,
      volume: isReading(day.orderCount) ? day.orderCount : null,
      up: available ? close >= open : null,
      available,
      isPartial: Boolean(day.income?.partial)
    }
    if (isReading(close)) lastClose = close
    return row
  })
}
// 均线基于完整历史计算，缩短可见区间不截断 MA5 的取样窗口。
const historyList = computed(() => {
  const history = asList(props.historyDays)
  if (!history.length) return days.value
  const dates = new Set(history.map((day) => day.date))
  return days.value.every((day) => dates.has(day.date)) ? history : days.value
})
const fullSeries = computed(() => buildDailyRows(historyList.value, props.previousDay))
const dailySeries = computed(() => {
  const wanted = new Set(days.value.map((day) => day.date))
  return fullSeries.value.filter((row) => wanted.has(row.date))
})
// 缺失日不进入均线与 EMA 窗口，指标线段在缺口处保持空缺。
function indicatorSeries(rows, pick) {
  const indexes = []
  const values = []
  rows.forEach((row, index) => {
    const value = pick(row)
    if (isReading(value)) {
      indexes.push(index)
      values.push(value)
    }
  })
  return { indexes, values }
}
const candleRows = computed(() => {
  const full = fullSeries.value
  const closeSeries = indicatorSeries(full, (row) => row.close)
  const volumeSeries = indicatorSeries(full, (row) => row.volume)
  const ma5 = movingAverage(closeSeries.values, 5)
  const volumeMa5 = movingAverage(volumeSeries.values, 5)
  const byDate = new Map()
  closeSeries.indexes.forEach((rowIndex, slot) => {
    byDate.set(full[rowIndex].date, ma5[slot])
  })
  const volumeByDate = new Map()
  volumeSeries.indexes.forEach((rowIndex, slot) => {
    volumeByDate.set(full[rowIndex].date, volumeMa5[slot])
  })
  return dailySeries.value.map((row) => ({
    ...row,
    ma5: byDate.get(row.date) ?? null,
    volumeMa5: volumeByDate.get(row.date) ?? null
  }))
})
const currentCandle = computed(
  () => candleRows.value.find((row) => row.date === currentDay.value?.date) || null
)
// 选中日标记：主图上的竖虚线与菱形点，和右侧盘口、行情列表保持同一天。
function selectedMarker(yKey = 'close') {
  const row = currentCandle.value
  if (!row) return { line: [], point: [] }
  const index = candleRows.value.findIndex((item) => item.date === row.date)
  return {
    line: [
      {
        xAxis: index,
        lineStyle: { color: COLOR.value.cyan, type: 'dashed', width: 1 }
      }
    ],
    point: isReading(row[yKey]) ? [{ coord: [index, row[yKey]] }] : []
  }
}
// 区间走势的起点：面积与区间涨跌幅都以区间内第一个有效收盘为基准。
const lineBase = computed(() => {
  const first = candleRows.value.find((row) => isReading(row.close))
  return first ? first.close : previousClose.value
})
// 指标图例跟随选中日，与右侧盘口、行情列表保持同一天。
const intradayStats = computed(() => ({
  ma5Text: formatIncome(currentCandle.value?.ma5),
  baseText: formatIncome(lineBase.value),
  latestText: formatIncome(currentCandle.value?.close)
}))
const marketStats = computed(() => {
  let up = 0
  let down = 0
  let flat = 0
  let missing = 0
  for (const row of dailySeries.value) {
    if (!isReading(row.change)) {
      missing += 1
      continue
    }
    if (row.change > 0) up += 1
    else if (row.change < 0) down += 1
    else flat += 1
  }
  return { up, down, flat, missing }
})
const missingDays = computed(() => days.value.filter((day) => Boolean(day.income?.partial)).length)
// 算法标签本身带"算法"后缀，状态栏再写一次会得到"算法 0.23456 算法"。
const algorithmText = computed(() => {
  const label = (props.algorithmLabel || '').replace(/\s*算法\s*$/, '').trim()
  return label || '—'
})

// ---- 热力块与行情列表 ----
const bestDate = computed(() => {
  if (props.summary?.best?.date) return props.summary.best.date
  const readings = days.value.filter((day) => totalOf(day) !== null)
  const best = readings.reduce(
    (top, day) => (!top || totalOf(day) > totalOf(top) ? day : top),
    null
  )
  return best?.date || ''
})
const latestDate = computed(() => days.value.at(-1)?.date || '')

const heatBlocks = computed(() =>
  dailySeries.value.map((row) => {
    const partial = row.isPartial
    const magnitude = isReading(row.change) ? Math.abs(row.change) : null
    const level =
      partial || magnitude === null
        ? 0
        : magnitude >= 0.03
          ? 4
          : magnitude >= 0.015
            ? 3
            : magnitude >= 0.005
              ? 2
              : 1
    return {
      date: row.date,
      shortDate: row.shortDate,
      closeText: formatIncome(row.close),
      changeText: partial ? '缺' : changeTextOf(row.change),
      tone: partial ? 'is-flat' : toneOf(row.change),
      level,
      isSelected: row.date === currentDay.value?.date
    }
  })
)

const rows = computed(() =>
  days.value
    .map((day, index) => {
      const candle = dailySeries.value[index]
      const close = totalOf(day)
      const delta = isReading(candle?.delta) ? candle.delta : null
      const change = isReading(candle?.change) ? candle.change : null
      const partial = Boolean(day.income?.partial)
      return {
        date: day.date,
        code: day.date,
        weekLabel: dayLabel(day.date),
        weekText: dayLabel(day.date).split(' ')[1] || '',
        shortDate: shortDate(day.date),
        close,
        closeText: formatIncome(close),
        delta,
        deltaText: signedText(delta, (value) => formatIncome(value)),
        change,
        changeText: partial ? '缺' : changeTextOf(change),
        arrowText: arrowOf(delta),
        orderCountText: formatCount(day.orderCount),
        ordersText: formatCount(day.orders),
        highText: formatIncome(candle?.high),
        lowText: formatIncome(candle?.low),
        qualityText: formatCount(qualityForDate(day.date)),
        tone: partial ? 'is-flat' : deltaClass({ delta }),
        isPartial: partial,
        isSelected: day.date === currentDay.value?.date,
        isBest: day.date === bestDate.value,
        isLatest: day.date === latestDate.value
      }
    })
    .reverse()
)

function selectRow(date) {
  if (isTrend.value) {
    if (typeof date === 'string' && date) emit('select', date)
    return
  }
  const row = bucketRows.value.find((item) => String(item.start) === String(date))
  if (!row) return
  if (isOrders.value) selectedOrderBucket.value = row.start
  else selectedIncomeBucket.value = row.start
}
function onRowKeydown(row, event) {
  if (!row || !event) return
  if (event.key === 'Enter' || event.key === ' ' || event.key === 'Spacebar') {
    event.preventDefault?.()
    selectRow(row.date)
  }
}
function onChartClick(params) {
  if (!isTrend.value) {
    const row = bucketRows.value[params?.dataIndex]
    if (row) selectRow(row.start)
    return
  }
  const day = days.value[params?.dataIndex]
  if (day) selectRow(day.date)
}

// ---- 图表公共 ----
function tipBase() {
  return {
    trigger: 'axis',
    confine: true,
    backgroundColor: COLOR.value.tipBg,
    borderColor: COLOR.value.line,
    borderWidth: 1,
    padding: [6, 8],
    textStyle: { color: COLOR.value.text, fontSize: 11 },
    extraCssText: `border-radius:0;box-shadow:0 6px 16px ${COLOR.value.tipShadow};`
  }
}
function tipMarker(color) {
  return `<span style="display:inline-block;width:6px;height:6px;border-radius:0;margin-right:5px;background:${color}"></span>`
}
function tipRow(color, label, value) {
  return `<div style="display:flex;justify-content:space-between;gap:18px;line-height:1.55;font-size:11px"><span>${tipMarker(color)}${label}</span><b style="font-variant-numeric:tabular-nums">${value}</b></div>`
}
function tipHeader(text) {
  return `<div style="margin-bottom:3px;padding-bottom:2px;border-bottom:1px solid ${COLOR.value.line};font-size:11px;color:${COLOR.value.cyan}">${text}</div>`
}
function tipIndex(params) {
  const list = Array.isArray(params) ? params : [params]
  return list[0]?.dataIndex ?? 0
}
function axisLabelStyle() {
  return { color: COLOR.value.muted, fontSize: 10 }
}
function splitLineStyle() {
  return { lineStyle: { color: COLOR.value.grid, type: 'dotted' } }
}
function crossPointer() {
  return {
    type: 'cross',
    lineStyle: { color: COLOR.value.muted, type: 'dashed', width: 1 },
    crossStyle: { color: COLOR.value.muted, type: 'dashed', width: 1 },
    label: {
      backgroundColor: COLOR.value.tipBg,
      borderColor: COLOR.value.line,
      borderWidth: 1,
      color: COLOR.value.text
    }
  }
}

function intradayTooltip(params) {
  const row = candleRows.value[tipIndex(params)]
  if (!row) return ''
  const pct = relativeChange(row.close, lineBase.value)
  return [
    tipHeader(`${row.date} ${row.label}`),
    tipRow(COLOR.value.lineMain, '收益', formatIncome(row.close)),
    tipRow(COLOR.value.yellow, 'MA5', formatIncome(row.ma5)),
    tipRow(COLOR.value.muted, '起点', formatIncome(lineBase.value)),
    tipRow(
      isReading(pct) && pct < 0 ? COLOR.value.down : COLOR.value.up,
      '区间涨跌幅',
      isReading(pct) ? formatPercent(pct) : '—'
    ),
    tipRow(COLOR.value.muted, '成交量', formatCount(row.volume))
  ].join('')
}
// ---- 区间走势图 ----
const intradayOption = computed(() => {
  const rows = candleRows.value
  const base = lineBase.value
  // 价格轴与右侧百分比轴共用同一组上下界，保证 0% 与前收/起点虚线严格对齐。
  const values = rows.flatMap((row) => [row.close, row.ma5]).filter(isReading)
  const rawLow = values.length ? Math.min(...values, isReading(base) ? base : Infinity) : 0
  const rawHigh = values.length ? Math.max(...values, isReading(base) ? base : -Infinity) : 1
  const span = Math.max(rawHigh - rawLow, 0.01)
  const lineMin = Math.floor((rawLow - span * 0.05) * 2) / 2
  const lineMax = Math.ceil((rawHigh + span * 0.05) * 2) / 2
  const hasPercentBase = isReading(base) && base !== 0
  const area = (color) => ({
    origin: isReading(base) ? base : 'start',
    color: {
      type: 'linear',
      x: 0,
      y: 0,
      x2: 0,
      y2: 1,
      colorStops: [
        { offset: 0, color: `${color}22` },
        { offset: 1, color: `${color}01` }
      ]
    }
  })
  const maskUp = rows.map((row) => {
    if (!isReading(base) || !isReading(row.close)) return null
    return row.close >= base ? row.close : base
  })
  const maskDown = rows.map((row) => {
    if (!isReading(base) || !isReading(row.close)) return null
    return row.close < base ? row.close : base
  })
  const marker = selectedMarker()
  return {
    backgroundColor: COLOR.value.bg,
    animation: !reducedMotion,
    textStyle: { color: COLOR.value.text, fontSize: 11 },
    aria: { enabled: true, description: '基建报表收益区间走势、MA5 与成交量' },
    // 两个 grid 用同一组 left/right，走势点与成交量柱严格同列；右侧留给百分比轴标签。
    grid: [
      { left: 38, right: 46, top: 8, height: '68%' },
      { left: 38, right: 46, top: '82%', height: '15%' }
    ],
    tooltip: { ...tipBase(), axisPointer: crossPointer(), formatter: intradayTooltip },
    xAxis: [
      {
        type: 'category',
        data: rows.map((row) => row.shortDate),
        gridIndex: 0,
        boundaryGap: true,
        axisLine: { lineStyle: { color: COLOR.value.line } },
        axisTick: { show: false },
        axisLabel: { show: false },
        axisPointer: { label: { show: false } },
        // 报告页按明暗主题注入 ECharts 主题，这里的网格必须显式关闭，亮暗布局才一致。
        splitLine: { show: false }
      },
      {
        type: 'category',
        data: rows.map((row) => row.shortDate),
        gridIndex: 1,
        boundaryGap: true,
        axisLine: { lineStyle: { color: COLOR.value.line } },
        axisTick: { show: false },
        axisLabel: axisLabelStyle(),
        splitLine: { show: false }
      }
    ],
    yAxis: [
      {
        gridIndex: 0,
        min: lineMin,
        max: lineMax,
        splitNumber: 4,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { ...axisLabelStyle(), formatter: (value) => formatIncome(value) },
        splitLine: splitLineStyle()
      },
      {
        gridIndex: 1,
        splitNumber: 1,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { show: false },
        splitLine: { show: false }
      },
      {
        show: hasPercentBase,
        scale: true,
        gridIndex: 0,
        position: 'right',
        min: hasPercentBase ? round4((lineMin - base) / Math.abs(base)) : -0.1,
        max: hasPercentBase ? round4((lineMax - base) / Math.abs(base)) : 0.1,
        splitNumber: 4,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          fontSize: 10,
          showMinLabel: false,
          showMaxLabel: false,
          color: (value) =>
            value > 0 ? COLOR.value.up : value < 0 ? COLOR.value.down : COLOR.value.muted,
          formatter: (value) => `${value > 0 ? '+' : ''}${(value * 100).toFixed(2)}%`
        },
        splitLine: { show: false }
      }
    ],
    series: [
      {
        name: '高于起点',
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: maskUp,
        symbol: 'none',
        silent: true,
        tooltip: { show: false },
        lineStyle: { width: 0, opacity: 0 },
        areaStyle: area(COLOR.value.up),
        z: 1
      },
      {
        name: '低于起点',
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: maskDown,
        symbol: 'none',
        silent: true,
        tooltip: { show: false },
        lineStyle: { width: 0, opacity: 0 },
        areaStyle: area(COLOR.value.down),
        z: 1
      },
      {
        name: '收益',
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: rows.map((row) => row.close),
        symbol: 'none',
        lineStyle: { width: 1.4, color: COLOR.value.lineMain },
        itemStyle: { color: COLOR.value.lineMain },
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: COLOR.value.muted, type: 'dashed', width: 1 },
          label: { show: false },
          data: [...(isReading(base) ? [{ yAxis: base }] : []), ...marker.line]
        },
        markPoint: {
          silent: true,
          symbol: 'diamond',
          symbolSize: 8,
          itemStyle: { color: COLOR.value.cyan },
          label: {
            show: true,
            formatter: '选中',
            color: COLOR.value.cyan,
            fontSize: 9,
            position: 'top',
            distance: 4
          },
          data: marker.point
        },
        z: 4
      },
      {
        name: 'MA5',
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: rows.map((row) => row.ma5),
        symbol: 'none',
        lineStyle: { width: 1.1, color: COLOR.value.yellow },
        itemStyle: { color: COLOR.value.yellow },
        z: 3
      },
      {
        name: '成交量',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        barWidth: '50%',
        barMaxWidth: 38,
        data: rows.map((row) => ({
          value: row.volume,
          itemStyle: {
            color:
              row.up === false
                ? COLOR.value.down
                : row.up === true
                  ? COLOR.value.up
                  : COLOR.value.muted
          }
        }))
      },
      {
        name: 'MAVOL5',
        type: 'line',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: rows.map((row) => row.volumeMa5),
        symbol: 'none',
        lineStyle: { width: 1, color: COLOR.value.yellow },
        itemStyle: { color: COLOR.value.yellow },
        z: 2
      }
    ]
  }
})

// ---- 按实际样本聚合的周/月收益与订单 K 线 ----
const bucketRows = computed(() => {
  const source = isOrders.value
    ? asList(props.orderCandles)
    : incomePeriod.value === 'trend'
      ? []
      : buildIncomeCandles(historyList.value, incomePeriod.value, days.value)
  return source.map((row) => ({
    ...row,
    available: row.count > 0 && [row.open, row.high, row.low, row.close].every(isReading),
    delta: isReading(row.open) && isReading(row.close) ? row.close - row.open : null,
    change: relativeChange(row.close, row.open)
  }))
})
const selectedBucket = computed(() => {
  const key = isOrders.value ? selectedOrderBucket.value : selectedIncomeBucket.value
  const rows = bucketRows.value
  if (key !== null) {
    const selected = rows.find((row) => row.start === key)
    if (selected) return selected
  }
  if (!isOrders.value && currentDay.value) {
    const selected = rows.find(
      (row) => row.firstDate <= currentDay.value.date && currentDay.value.date <= row.lastDate
    )
    if (selected) return selected
  }
  return rows.findLast((row) => row.available) || rows.at(-1) || null
})
function bucketMarker() {
  const row = selectedBucket.value
  if (!row) return { line: [], point: [] }
  const index = bucketRows.value.findIndex((item) => item.start === row.start)
  return {
    line: [{ xAxis: index, lineStyle: { color: COLOR.value.cyan, type: 'dashed', width: 1 } }],
    point: row.available ? [{ coord: [index, row.high] }] : []
  }
}
const bucketFormatter = computed(() => (isOrders.value ? formatCount : formatIncome))
function bucketTooltip(params) {
  const row = bucketRows.value[tipIndex(params)]
  if (!row) return ''
  if (!row.available) return tipHeader(row.label) + '无记录'
  const format = bucketFormatter.value
  const tone = row.delta < 0 ? COLOR.value.down : COLOR.value.up
  return [
    tipHeader(row.label),
    tipRow(COLOR.value.muted, isOrders.value ? '首笔' : '首日收益', format(row.open)),
    tipRow(tone, isOrders.value ? '末笔' : '末日收益', format(row.close)),
    tipRow(COLOR.value.up, '最高', format(row.high)),
    tipRow(COLOR.value.down, '最低', format(row.low)),
    tipRow(COLOR.value.yellow, isOrders.value ? '每笔均价' : '日收益均值', format(row.mean)),
    tipRow(
      COLOR.value.muted,
      isOrders.value ? '已记录笔数' : '完整读数天数',
      formatCount(row.count)
    ),
    !isOrders.value && row.missingCount
      ? '<div>另有 ' + formatCount(row.missingCount) + ' 天读数不完整</div>'
      : '',
    isOrders.value ? '<div>按记录时刻统计，样本不覆盖全部订单</div>' : ''
  ].join('')
}
const candleOption = computed(() => {
  const rows = bucketRows.value
  const marker = bucketMarker()
  const selectedIndex = rows.findIndex((row) => row.start === selectedBucket.value?.start)
  const zoomEnd = Math.min(rows.length - 1, Math.max(59, selectedIndex))
  const zoomStart = Math.max(0, zoomEnd - 59)
  const meanLabel = isOrders.value ? '每笔均价' : '日收益均值'
  const countLabel = isOrders.value ? '已记录笔数' : '完整读数天数'
  return {
    backgroundColor: COLOR.value.bg,
    animation: !reducedMotion,
    textStyle: { color: COLOR.value.text, fontSize: 11 },
    aria: {
      enabled: true,
      description: metricLabel.value + periodLabel.value + '，均值与样本数量'
    },
    grid: [
      { left: 46, right: 10, top: 12, height: '60%' },
      { left: 46, right: 10, top: '76%', height: rows.length > 60 ? '10%' : '16%' }
    ],
    dataZoom:
      rows.length > 60
        ? [
            { type: 'inside', xAxisIndex: [0, 1], startValue: zoomStart, endValue: zoomEnd },
            {
              type: 'slider',
              xAxisIndex: [0, 1],
              startValue: zoomStart,
              endValue: zoomEnd,
              bottom: 1,
              height: 12,
              left: 46,
              right: 10,
              showDetail: false,
              borderColor: COLOR.value.line,
              backgroundColor: COLOR.value.surface2,
              fillerColor: props.dark === false ? 'rgba(21,87,176,.15)' : 'rgba(51,153,255,.2)',
              handleStyle: { color: COLOR.value.blue, borderColor: COLOR.value.blue }
            }
          ]
        : [],
    tooltip: { ...tipBase(), axisPointer: crossPointer(), formatter: bucketTooltip },
    xAxis: [0, 1].map((index) => ({
      type: 'category',
      data: rows.map((row) => row.label),
      gridIndex: index,
      boundaryGap: true,
      axisLine: { lineStyle: { color: COLOR.value.line } },
      axisTick: { show: false },
      axisLabel: index === 1 ? { ...axisLabelStyle(), hideOverlap: true } : { show: false },
      splitLine: { show: false }
    })),
    yAxis: [
      {
        scale: true,
        gridIndex: 0,
        splitNumber: 4,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { ...axisLabelStyle(), formatter: bucketFormatter.value },
        splitLine: splitLineStyle()
      },
      {
        gridIndex: 1,
        minInterval: 1,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: axisLabelStyle(),
        splitLine: { show: false }
      }
    ],
    series: [
      {
        name: metricLabel.value,
        type: 'candlestick',
        barWidth: '55%',
        barMaxWidth: 34,
        data: rows.map((row) => (row.available ? [row.open, row.close, row.low, row.high] : '-')),
        itemStyle: {
          color: COLOR.value.bg,
          color0: COLOR.value.down,
          borderColor: COLOR.value.up,
          borderColor0: COLOR.value.down,
          borderColorDoji: COLOR.value.muted
        },
        markLine: { silent: true, symbol: 'none', label: { show: false }, data: marker.line },
        markPoint: {
          silent: true,
          symbol: 'diamond',
          symbolSize: 8,
          itemStyle: { color: COLOR.value.cyan },
          label: {
            show: true,
            formatter: '选中',
            color: COLOR.value.cyan,
            fontSize: 9,
            position: 'top'
          },
          data: marker.point
        }
      },
      {
        name: meanLabel,
        type: 'line',
        data: rows.map((row) => (row.available ? row.mean : null)),
        symbol: 'none',
        lineStyle: { width: 1.2, color: COLOR.value.yellow },
        itemStyle: { color: COLOR.value.yellow }
      },
      {
        name: countLabel,
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: rows.map((row) => ({
          value: row.count,
          itemStyle: { color: row.delta < 0 ? COLOR.value.down : COLOR.value.up }
        })),
        barWidth: '55%',
        barMaxWidth: 34
      }
    ]
  }
})

const displayQuote = computed(() => {
  if (isTrend.value) return quote.value
  const row = selectedBucket.value
  const close = row?.available ? row.close : null
  const delta = row?.delta ?? null
  return {
    close,
    delta,
    change: row?.change ?? null,
    partial: !row?.available,
    closeText: bucketFormatter.value(close),
    deltaText: signedText(delta, bucketFormatter.value),
    changeText: changeTextOf(row?.change),
    arrowText: arrowOf(delta),
    tone: toneOf(delta),
    color: !isReading(close)
      ? COLOR.value.muted
      : delta > 0
        ? COLOR.value.up
        : delta < 0
          ? COLOR.value.down
          : COLOR.value.text
  }
})
const displayDate = computed(() =>
  isTrend.value ? currentDay.value?.date || '—' : selectedBucket.value?.label || '—'
)
const displayDetails = computed(() => {
  if (isTrend.value) {
    return [
      { key: 'previous', label: '前次完整收益', value: formatIncome(previousClose.value) },
      { key: 'orders', label: '订单金额', value: formatCount(currentDay.value?.orders) },
      { key: 'count', label: '订单数量', value: formatCount(currentDay.value?.orderCount) },
      { key: 'quality', label: '基报订单均价', value: formatCount(qualityOf(currentDay.value)) },
      { key: 'orundum', label: '合成玉', value: formatCount(currentDay.value?.orundum) },
      { key: 'days', label: '记录天数', value: formatCount(days.value.length) }
    ]
  }
  const row = selectedBucket.value
  const format = bucketFormatter.value
  const details = [
    { key: 'open', label: isOrders.value ? '首笔价格' : '首日收益', value: format(row?.open) },
    { key: 'close', label: isOrders.value ? '末笔价格' : '末日收益', value: format(row?.close) },
    { key: 'high', label: '最高', value: format(row?.high) },
    { key: 'low', label: '最低', value: format(row?.low) },
    { key: 'mean', label: isOrders.value ? '每笔均价' : '日收益均值', value: format(row?.mean) },
    {
      key: 'count',
      label: isOrders.value ? '已记录笔数' : '完整读数天数',
      value: formatCount(row?.count)
    }
  ]
  if (isOrders.value) {
    const reportDate = row ? new Date((row.start + 4 * 3600) * 1000).toISOString().slice(0, 10) : ''
    details.push(
      { key: 'amount', label: '记录金额合计', value: formatCount(row?.amount) },
      { key: 'report', label: '同日基报均价', value: formatCount(qualityForDate(reportDate)) }
    )
  } else {
    details.push(
      { key: 'amount', label: '已知收益合计', value: formatIncome(row?.amount) },
      { key: 'missing', label: '缺失读数天数', value: formatCount(row?.missingCount) }
    )
  }
  return details
})
const displayRows = computed(() => {
  if (isTrend.value) return rows.value
  return bucketRows.value
    .map((row, index) => ({
      date: String(row.start),
      code: row.label,
      shortDate: row.label,
      weekText: '',
      closeText: bucketFormatter.value(row.available ? row.close : null),
      changeText: row.available ? changeTextOf(row.change) : '无记录',
      deltaText: signedText(row.delta, bucketFormatter.value),
      arrowText: arrowOf(row.delta),
      orderCountText: formatCount(row.count),
      ordersText: isOrders.value ? formatCount(row.amount) : formatIncome(row.amount),
      highText: bucketFormatter.value(row.high),
      lowText: bucketFormatter.value(row.low),
      qualityText: bucketFormatter.value(row.mean),
      tone: toneOf(row.delta),
      isPartial: !row.available,
      isSelected: row.start === selectedBucket.value?.start,
      isBest: false,
      isLatest: index === bucketRows.value.length - 1
    }))
    .reverse()
})
const displayHeat = computed(() => {
  if (isTrend.value) return heatBlocks.value
  return bucketRows.value.map((row) => {
    const magnitude = isReading(row.change) ? Math.abs(row.change) : null
    return {
      date: String(row.start),
      shortDate: row.label,
      closeText: bucketFormatter.value(row.available ? row.close : null),
      changeText: row.available ? changeTextOf(row.change) : '无记录',
      tone: toneOf(row.delta),
      level:
        magnitude === null
          ? 0
          : magnitude >= 0.03
            ? 4
            : magnitude >= 0.015
              ? 3
              : magnitude >= 0.005
                ? 2
                : 1,
      isSelected: row.start === selectedBucket.value?.start
    }
  })
})
const displayTradeRows = computed(() =>
  (isOrders.value ? displayRows.value.filter((row) => !row.isPartial) : displayRows.value).slice(
    0,
    8
  )
)
const marketPageCount = computed(() =>
  Math.max(1, Math.ceil(displayRows.value.length / MARKET_PAGE_SIZE))
)
const visiblePage = computed(() => Math.min(marketPage.value, marketPageCount.value))
const pagedRows = computed(() =>
  displayRows.value.slice(
    (visiblePage.value - 1) * MARKET_PAGE_SIZE,
    visiblePage.value * MARKET_PAGE_SIZE
  )
)
const pagedHeat = computed(() => {
  const end = Math.max(0, displayHeat.value.length - (visiblePage.value - 1) * MARKET_PAGE_SIZE)
  return displayHeat.value.slice(Math.max(0, end - MARKET_PAGE_SIZE), end)
})
function stepMarketPage(offset) {
  marketPage.value = Math.max(1, Math.min(marketPageCount.value, visiblePage.value + offset))
}
const orderRangeText = computed(() => {
  const range = props.orderCandleRange
  if (!range?.startDate || !range?.endDate) return ''
  return range.startDate + ' 至 ' + range.endDate + (props.range === 'all' ? '（最多 366 天）' : '')
})

// ---- 订单分布（保留） ----
// 订单类型色在深色行情里沿用 stock 皮肤，亮色行情改用标准报表的亮色盘，保证白底可读。
const orderTypeColors = computed(() => ORDER_COLORS[props.dark === false ? 'stockLight' : 'stock'])
const orderTooltip = (params) => {
  const index = tipIndex(params)
  const row = asList(props.orderRows)[index]
  if (!row) return ''
  const colors = orderTypeColors.value
  const lines = [tipHeader(`${row['日期']} ${dayLabel(row['日期'])} 订单分布`)]
  for (const type of ORDER_TYPES) {
    const amount = isReading(row[type]) ? row[type] : null
    const count = isReading(amount) ? amount / ORDER_PRICES[type] : null
    lines.push(
      tipRow(
        colors[type] || COLOR.value.muted,
        type,
        `${formatCount(amount)} · ${formatCount(count)} 单`
      )
    )
  }
  lines.push(
    tipRow(
      colors['未知订单'] || COLOR.value.muted,
      '未知订单',
      `${formatCount(row['未知订单'])} · ${formatCount(row['未知订单数'])} 单`
    )
  )
  lines.push(tipRow(COLOR.value.yellow, '订单质量', formatCount(row['订单质量'])))
  lines.push(tipRow(COLOR.value.muted, '总订单数', formatCount(row['订单数'])))
  return lines.join('')
}
const orderOption = computed(() => {
  const names = [...ORDER_TYPES, '未知订单']
  return {
    backgroundColor: COLOR.value.bg,
    animation: !reducedMotion,
    textStyle: { color: COLOR.value.text, fontSize: 11 },
    aria: { enabled: true, description: '基建报表订单类型金额分布与订单质量' },
    color: names.map((name) => orderTypeColors.value[name]),
    grid: { left: 4, right: 4, top: 34, bottom: 2, containLabel: true },
    legend: {
      type: 'scroll',
      top: 2,
      left: 2,
      right: 22,
      padding: [2, 4],
      itemWidth: 9,
      itemHeight: 7,
      itemGap: 8,
      textStyle: { color: COLOR.value.muted, fontSize: 10 },
      pageIconColor: COLOR.value.muted,
      pageIconInactiveColor: COLOR.value.line,
      pageTextStyle: { color: COLOR.value.muted, fontSize: 10 },
      data: [...names, '订单质量', '赤金'],
      selected: { 赤金: false, 订单质量: true }
    },
    tooltip: { ...tipBase(), axisPointer: { type: 'shadow' }, formatter: orderTooltip },
    dataset: {
      dimensions: ['日期', ...ORDER_TYPES, '未知订单', '订单质量', '赤金', '龙门币订单', '订单数'],
      source: asList(props.orderRows)
    },
    xAxis: {
      type: 'category',
      axisLine: { lineStyle: { color: COLOR.value.line } },
      axisTick: { show: false },
      axisLabel: { ...axisLabelStyle(), formatter: (value) => shortDate(value) },
      // 与走势图一致：不继承报告页 ECharts 主题的竖网格线。
      splitLine: { show: false }
    },
    yAxis: [
      {
        type: 'value',
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { ...axisLabelStyle(), formatter: (value) => formatCount(value) },
        splitLine: splitLineStyle()
      },
      {
        type: 'value',
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { ...axisLabelStyle(), formatter: (value) => formatCount(value) },
        splitLine: { show: false }
      }
    ],
    series: [
      {
        name: '赤金',
        type: 'bar',
        yAxisIndex: 0,
        barMaxWidth: 12,
        itemStyle: { color: COLOR.value.yellow },
        encode: { x: '日期', y: '赤金' },
        emphasis: { focus: 'series' }
      },
      ...ORDER_TYPES.map((type) => ({
        name: type,
        type: 'bar',
        stack: '订单',
        yAxisIndex: 0,
        barMaxWidth: 16,
        itemStyle: { color: orderTypeColors.value[type] },
        encode: { x: '日期', y: type },
        emphasis: { focus: 'series' }
      })),
      {
        name: '未知订单',
        type: 'bar',
        stack: '订单',
        yAxisIndex: 0,
        barMaxWidth: 16,
        itemStyle: { color: orderTypeColors.value['未知订单'] },
        encode: { x: '日期', y: '未知订单' },
        emphasis: { focus: 'series' }
      },
      {
        name: '订单质量',
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 1.2, color: COLOR.value.yellow },
        itemStyle: { color: COLOR.value.yellow },
        encode: { x: '日期', y: '订单质量' },
        emphasis: { focus: 'series' }
      }
    ]
  }
})
</script>

<template>
  <section
    ref="termRef"
    class="term"
    :class="{ 'is-immersive': immersive, 'term--light': dark === false }"
    aria-label="基建报表股票模式"
  >
    <header class="term-head">
      <div class="term-head__left">
        <span class="term-head__brand">MOWER 行情终端</span>
        <nav class="term-head__nav" aria-label="终端导航">
          <button
            v-for="tab in NAV_TABS"
            :key="tab.key"
            type="button"
            class="term-nav__item"
            :class="{ 'is-active': navActive === tab.key }"
            :aria-pressed="navActive === tab.key ? 'true' : 'false'"
            @click="setNav(tab.key)"
          >
            {{ tab.label }}
          </button>
        </nav>
      </div>
      <div class="term-head__right">
        <span class="term-head__date">{{ displayDate }}</span>
        <span class="term-head__tag">股票模式</span>
        <span class="term-head__index" :class="displayQuote.tone">
          {{ displayQuote.closeText
          }}<i v-if="isReading(displayQuote.change)"
            >{{ displayQuote.arrowText }} {{ displayQuote.changeText }}</i
          >
        </span>
        <div class="term-range" role="group" aria-label="统计区间">
          <button
            v-for="tab in rangeTabs"
            :key="tab.value"
            type="button"
            class="term-range__item"
            :class="{ 'is-active': activeRange === tab.value }"
            :aria-pressed="activeRange === tab.value ? 'true' : 'false'"
            @click="setRange(tab.value)"
          >
            {{ tab.label }}
          </button>
        </div>
        <div class="term-tools" role="group" aria-label="终端操作">
          <button
            type="button"
            class="term-tool term-tool--refresh"
            :disabled="refreshing"
            :title="refreshing ? '正在刷新行情' : '刷新行情'"
            :aria-label="refreshing ? '正在刷新行情' : '刷新行情'"
            @click="refresh"
          >
            {{ refreshing ? '刷新中' : '刷新' }}
          </button>
          <button
            type="button"
            class="term-tool term-tool--standard"
            :disabled="modeDisabled"
            title="切换标准显示模式"
            @click="switchToStandard"
          >
            标准
          </button>
          <button
            type="button"
            class="term-tool term-tool--fullscreen"
            :aria-pressed="isFullscreen ? 'true' : 'false'"
            :title="isFullscreen ? '退出全屏' : '全屏显示终端'"
            @click="toggleFullscreen"
          >
            {{ isFullscreen ? '退出全屏' : '全屏' }}
          </button>
          <button
            ref="menuTriggerRef"
            type="button"
            class="term-tool term-tool--menu"
            aria-haspopup="menu"
            :aria-expanded="menuOpen ? 'true' : 'false'"
            title="收益算法与数据工具"
            @click="toggleMenu"
          >
            工具
          </button>
        </div>
        <div v-if="menuOpen" ref="menuRef" class="term-menu" role="menu" aria-label="终端工具">
          <section class="term-menu__section">
            <h3 class="term-menu__title">终端</h3>
            <button
              type="button"
              role="menuitem"
              class="term-menu__item"
              :disabled="refreshing"
              @click="refresh"
            >
              {{ refreshing ? '正在刷新行情…' : '刷新行情' }}
            </button>
            <button
              type="button"
              role="menuitem"
              class="term-menu__item"
              :disabled="modeDisabled"
              @click="standardFromMenu"
            >
              返回标准模式
            </button>
            <button
              type="button"
              role="menuitem"
              class="term-menu__item"
              @click="fullscreenFromMenu"
            >
              {{ isFullscreen ? '退出全屏' : '全屏显示' }}
            </button>
          </section>
          <section v-if="algorithmOptions.length" class="term-menu__section">
            <h3 class="term-menu__title">收益算法</h3>
            <button
              v-for="option in algorithmOptions"
              :key="option.value"
              type="button"
              role="menuitemradio"
              :aria-checked="algorithmValue === option.value ? 'true' : 'false'"
              class="term-menu__item"
              :class="{ 'is-active': algorithmValue === option.value }"
              @click="selectAlgorithm(option.value)"
            >
              {{ option.label }}
            </button>
          </section>
          <section class="term-menu__section">
            <h3 class="term-menu__title">数据</h3>
            <button
              type="button"
              role="menuitem"
              class="term-menu__item"
              :disabled="restoreBusy"
              @click="restoreHistory"
            >
              {{ restoreBusy ? '正在恢复历史…' : '恢复历史' }}
            </button>
          </section>
          <slot name="menu-extra" :close="closeMenu" />
        </div>
      </div>
    </header>

    <div class="market-controls">
      <div class="market-switch" role="group" aria-label="行情指标">
        <button
          v-for="item in METRICS"
          :key="item.value"
          type="button"
          :class="{ 'is-active': activeMetric === item.value }"
          :aria-pressed="activeMetric === item.value"
          @click="setMetric(item.value)"
        >
          {{ item.label }}
        </button>
      </div>
      <div class="market-switch" role="group" aria-label="K线周期">
        <button
          v-for="item in periodOptions"
          :key="item.value"
          type="button"
          :class="{ 'is-active': activePeriod === item.value }"
          :aria-pressed="activePeriod === item.value"
          @click="setPeriod(item.value)"
        >
          {{ item.label }}
        </button>
      </div>
      <p v-if="isOrders" class="market-caveat">
        仅已记录龙门币订单 · 按记录时刻 · 不代表全部订单均价<span v-if="orderRangeText">
          · {{ orderRangeText }}</span
        >
      </p>
      <p v-else-if="!isTrend" class="market-caveat">
        首末完整日收益为开收，周期内完整日收益取最高与最低；单位：万。
      </p>
    </div>

    <div v-if="!isOrders && loading && !hasDays" class="term-notice" role="status">行情加载中…</div>
    <div v-else-if="!isOrders && !hasDays" class="term-notice term-notice--empty" role="status">
      <strong>还没有基报记录</strong>
      <span>采集基建报表后显示行情终端</span>
    </div>
    <template v-else>
      <div v-if="isTrend" class="index-strip" role="list" aria-label="指数行情">
        <div v-for="item in indexStrip" :key="item.key" class="index-strip__item" role="listitem">
          <span class="index-strip__name">{{ item.label }}</span>
          <b class="index-strip__value" :class="item.tone">{{ item.valueText }}</b>
          <span v-if="isReading(item.change)" class="index-strip__change" :class="item.tone">
            {{ item.arrowText }} {{ item.changeText }}
          </span>
        </div>
      </div>
      <div v-else class="index-strip" role="list" aria-label="当前周期报价">
        <div
          v-for="item in displayDetails.slice(0, 6)"
          :key="item.key"
          class="index-strip__item"
          role="listitem"
        >
          <span class="index-strip__name">{{ item.label }}</span>
          <b class="index-strip__value">{{ item.value }}</b>
        </div>
      </div>

      <div ref="bodyRef" class="term-body">
        <div
          v-if="
            isOrders &&
            !chartViewActive &&
            (orderCandlesLoading || orderCandlesError || !bucketRows.some((row) => row.available))
          "
          class="market-state"
          :role="orderCandlesError ? 'alert' : 'status'"
        >
          <template v-if="orderCandlesLoading">正在读取订单记录…</template>
          <template v-else-if="orderCandlesError">
            <p>{{ orderCandlesError }}</p>
            <button type="button" @click="$emit('retry-order-candles')">重试读取</button>
          </template>
          <template v-else>所选范围没有已记录订单</template>
        </div>
        <div v-show="chartViewActive" class="view view--charts">
          <div class="main-grid">
            <section class="panel chart-panel" aria-label="收益主图">
              <header class="panel-bar">
                <span class="panel-bar__title">{{ metricLabel }} · {{ periodLabel }}</span>
                <span class="panel-bar__meta">红涨绿跌 · 十字光标查看明细</span>
              </header>
              <div class="chart-indicators">
                <template v-if="isTrend">
                  <span
                    >MA5 <b class="is-yellow">{{ intradayStats.ma5Text }}</b></span
                  >
                  <span
                    >起点 <b>{{ intradayStats.baseText }}</b></span
                  >
                  <span
                    >选中 <b :class="displayQuote.tone">{{ intradayStats.latestText }}</b></span
                  >
                </template>
                <template v-else>
                  <span
                    >{{ isOrders ? '每笔均价' : '日收益均值' }}
                    <b class="is-yellow">{{ bucketFormatter(selectedBucket?.mean) }}</b>
                  </span>
                  <span
                    >{{ isOrders ? '已记录' : '完整读数' }}
                    <b>{{ formatCount(selectedBucket?.count) }}</b
                    >{{ isOrders ? ' 笔' : ' 天' }}
                  </span>
                </template>
                <span class="chart-indicators__spacer"></span>
                <span class="chart-indicators__hint">
                  {{ isTrend ? '黄线为 MA5 · 面积相对区间起点' : '首末样本成 K 线 · 黄线为均值' }}
                </span>
              </div>
              <div class="chart-body">
                <div v-if="isOrders && orderCandlesLoading" class="market-state" role="status">
                  正在读取订单记录…
                </div>
                <div v-else-if="isOrders && orderCandlesError" class="market-state" role="alert">
                  <p>{{ orderCandlesError }}</p>
                  <button type="button" @click="$emit('retry-order-candles')">重试读取</button>
                </div>
                <div
                  v-else-if="isOrders && !bucketRows.some((row) => row.available)"
                  class="market-state market-state--empty"
                  role="status"
                >
                  所选范围没有已记录订单
                </div>
                <v-chart
                  v-if="isTrend"
                  class="chart chart--intraday"
                  :option="intradayOption"
                  autoresize
                  @click="onChartClick"
                />
                <v-chart
                  v-else-if="!isOrders || (!orderCandlesLoading && !orderCandlesError)"
                  class="chart chart--candles"
                  :option="candleOption"
                  autoresize
                  @click="onChartClick"
                />
              </div>
            </section>

            <aside class="panel book" aria-label="盘口">
              <header class="panel-bar panel-bar--book">
                <span class="book__name"
                  >{{ metricLabel }}
                  <b class="book__code">{{ isOrders ? 'MOWER-ORDER' : 'MOWER-BASE' }}</b></span
                >
              </header>
              <div class="book__quote">
                <div
                  class="book__price"
                  :class="displayQuote.tone"
                  :style="{ color: displayQuote.color }"
                >
                  {{ displayQuote.closeText
                  }}<small v-if="isReading(displayQuote.close)">{{
                    isOrders ? '龙门币/单' : '万'
                  }}</small>
                </div>
                <div v-if="!displayQuote.partial" class="book__change" :class="displayQuote.tone">
                  {{ displayQuote.arrowText }} {{ displayQuote.deltaText }}
                  {{ displayQuote.changeText }}
                </div>
                <p v-if="displayQuote.partial" class="book__partial">
                  {{ isTrend ? '读数不完整，收益未知' : '此周期无可用记录' }}
                </p>
                <p
                  v-if="!isTrend && !isOrders && selectedBucket?.missingCount"
                  class="book__partial"
                >
                  有 {{ selectedBucket.missingCount }} 天读数不完整，K 线仅使用完整日收益
                </p>
                <p v-if="isOrders" class="book__partial">
                  按记录时刻统计，样本不覆盖全部订单；同日基报均价仅供参考。
                </p>
                <dl class="book__grid">
                  <div v-for="item in displayDetails" :key="item.key" class="book__cell">
                    <dt>{{ item.label }}</dt>
                    <dd :class="item.tone">{{ item.value }}</dd>
                  </div>
                </dl>
              </div>

              <section v-if="isTrend" class="book__section" aria-label="收益构成">
                <h3 class="book__title">收益构成</h3>
                <div v-for="item in composition" :key="item.key" class="order-row">
                  <span class="order-row__name">{{ item.label }}</span>
                  <span class="order-row__track">
                    <i
                      class="order-row__bar"
                      :class="item.tone"
                      :style="{ width: item.width + '%', background: item.color }"
                    ></i>
                  </span>
                  <span class="order-row__value" :class="item.tone">{{ item.valueText }}</span>
                  <span class="order-row__delta" :class="item.tone">{{ item.deltaText }}</span>
                </div>
              </section>

              <section v-if="isTrend" class="book__section" aria-label="资金分析">
                <h3 class="book__title">资金分析</h3>
                <div class="fund">
                  <div class="fund__ring" :style="fundRingStyle">
                    <span class="fund__hole"
                      ><template v-if="fundIncomplete">数据<br />不足</template
                      ><template v-else>收益<br />构成</template></span
                    >
                  </div>
                  <ul class="fund__legend">
                    <li v-for="item in fundRows" :key="item.key">
                      <i :style="{ background: item.color }"></i>
                      <span>{{ item.label }}</span>
                      <b>{{ item.percentText }}</b>
                    </li>
                  </ul>
                </div>
                <p v-if="fundIncomplete" class="fund__notice">读数不完整，资金占比暂不可用</p>
                <div class="fund__breadth">
                  上涨 <b class="is-up">{{ marketStats.up }}</b> · 下跌
                  <b class="is-down">{{ marketStats.down }}</b> · 平
                  <b class="is-flat">{{ marketStats.flat }}</b>
                  <template v-if="marketStats.missing">
                    · 缺 <b class="is-flat">{{ marketStats.missing }}</b>
                  </template>
                </div>
              </section>

              <section class="book__section book__section--trades" aria-label="最近记录">
                <h3 class="book__title">最近记录</h3>
                <div class="trades__head" aria-hidden="true">
                  <span>日期</span>
                  <span>{{ isTrend ? '收益' : '末值' }}</span>
                  <span>{{ isOrders ? '笔数' : isTrend ? '订单数' : '天数' }}</span>
                  <span></span>
                </div>
                <ul class="trades">
                  <li
                    v-for="row in displayTradeRows"
                    :key="row.date"
                    class="trades__row"
                    :class="{ 'is-selected': row.isSelected }"
                    tabindex="0"
                    :aria-selected="row.isSelected ? 'true' : 'false'"
                    @click="selectRow(row.date)"
                    @keydown="onRowKeydown(row, $event)"
                  >
                    <span class="trades__time">{{ row.shortDate }}</span>
                    <span class="trades__price" :class="row.tone">{{
                      row.isPartial ? (isTrend ? '缺' : '无记录') : row.closeText
                    }}</span>
                    <span class="trades__qty">{{ row.orderCountText }}</span>
                    <span class="trades__arrow" :class="row.tone">{{ row.arrowText }}</span>
                  </li>
                </ul>
              </section>
            </aside>
          </div>

          <section v-if="!isOrders" class="panel order-panel" aria-label="订单分布">
            <header class="panel-bar">
              <span class="panel-bar__title">订单分布</span>
              <span class="panel-bar__meta">金额堆叠（左轴） · 订单质量（右轴）</span>
            </header>
            <div class="chart-body chart-body--orders">
              <v-chart class="chart chart--orders" :option="orderOption" autoresize />
            </div>
          </section>
        </div>

        <div v-show="navActive === 'heat'" class="view view--heat">
          <section class="panel heat-panel" aria-label="涨跌分布">
            <header class="panel-bar">
              <span class="panel-bar__title">涨跌分布</span>
              <span class="panel-bar__meta">区块越深波动越大 · 点击选择记录</span>
            </header>
            <div v-if="marketPageCount > 1" class="market-pagination" aria-label="记录分页">
              <span
                >第 {{ visiblePage }} / {{ marketPageCount }} 页 · 共 {{ displayRows.length }} 条 ·
                每页最多 200 条，最近记录在前页</span
              >
              <button type="button" :disabled="visiblePage <= 1" @click="stepMarketPage(-1)">
                上一页
              </button>
              <button
                type="button"
                :disabled="visiblePage >= marketPageCount"
                @click="stepMarketPage(1)"
              >
                下一页
              </button>
            </div>
            <div class="heat-grid">
              <button
                v-for="block in pagedHeat"
                :key="block.date"
                type="button"
                class="heat-block"
                :class="[
                  block.tone,
                  'heat-block--' + block.level,
                  { 'is-selected': block.isSelected }
                ]"
                :aria-pressed="block.isSelected ? 'true' : 'false'"
                @click="selectRow(block.date)"
              >
                <span class="heat-block__date">{{ block.shortDate }}</span>
                <b class="heat-block__close">{{ block.closeText }}</b>
                <span class="heat-block__change">{{ block.changeText }}</span>
              </button>
            </div>
          </section>
        </div>

        <div v-show="navActive === 'list'" class="view view--list">
          <section class="panel list-panel" aria-label="行情列表">
            <header class="panel-bar">
              <span class="panel-bar__title">行情列表</span>
              <span class="panel-bar__meta"
                >最新在上 · 共 {{ displayRows.length }} 条 · 点击或按 Enter 选择记录</span
              >
            </header>
            <div v-if="marketPageCount > 1" class="market-pagination" aria-label="记录分页">
              <span
                >第 {{ visiblePage }} / {{ marketPageCount }} 页 · 共 {{ displayRows.length }} 条 ·
                每页最多 200 条，最近记录在前页</span
              >
              <button type="button" :disabled="visiblePage <= 1" @click="stepMarketPage(-1)">
                上一页
              </button>
              <button
                type="button"
                :disabled="visiblePage >= marketPageCount"
                @click="stepMarketPage(1)"
              >
                下一页
              </button>
            </div>
            <div class="list-wrap">
              <table class="quote-table" role="grid" aria-label="行情列表">
                <thead>
                  <tr>
                    <th scope="col">{{ isTrend ? '日期' : '周期起点' }}</th>
                    <th scope="col">标记</th>
                    <th scope="col">{{ isTrend ? '收益' : '末值' }}</th>
                    <th scope="col">涨跌幅</th>
                    <th scope="col">涨跌额</th>
                    <th scope="col">
                      {{ isOrders ? '已记录笔数' : isTrend ? '订单数量' : '完整读数天数' }}
                    </th>
                    <th scope="col">
                      {{ isOrders ? '记录金额合计' : isTrend ? '订单金额' : '已知收益合计' }}
                    </th>
                    <th v-if="!isTrend" scope="col">最高</th>
                    <th v-if="!isTrend" scope="col">最低</th>
                    <th scope="col">
                      {{ isTrend ? '基报订单均价' : isOrders ? '每笔均价' : '日收益均值' }}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="row in pagedRows"
                    :key="row.date"
                    class="quote-table__row"
                    :class="{ 'is-selected': row.isSelected }"
                    tabindex="0"
                    :aria-selected="row.isSelected ? 'true' : 'false'"
                    :aria-current="row.isSelected ? 'true' : undefined"
                    @click="selectRow(row.date)"
                    @keydown="onRowKeydown(row, $event)"
                  >
                    <td class="quote-table__code">{{ row.code }}</td>
                    <td class="quote-table__name">
                      <span>{{ row.weekText }}</span>
                      <span
                        v-if="row.isPartial"
                        class="quote-table__badge quote-table__badge--muted"
                        >缺</span
                      >
                      <span v-if="row.isBest" class="quote-table__star" title="收益最高">★</span>
                      <span v-if="row.isLatest" class="quote-table__badge">最新</span>
                    </td>
                    <td class="num quote-table__close" :class="row.tone">{{ row.closeText }}</td>
                    <td class="num quote-table__change" :class="row.tone">{{ row.changeText }}</td>
                    <td class="num" :class="row.tone">{{ row.deltaText }}</td>
                    <td class="num">{{ row.orderCountText }}</td>
                    <td class="num">{{ row.ordersText }}</td>
                    <td v-if="!isTrend" class="num">{{ row.highText }}</td>
                    <td v-if="!isTrend" class="num">{{ row.lowText }}</td>
                    <td class="num">{{ row.qualityText }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </div>

      <footer class="term-status" aria-label="终端状态栏">
        <span class="term-status__left">
          {{ metricLabel }} · {{ periodLabel }}
          <template v-if="isOrders">
            · {{ orderRangeText || rangeLabel }} · 按记录时刻 · 样本不完整</template
          >
          <template v-else>
            · 算法 {{ algorithmText }} · 区间 {{ rangeLabel || '—' }}
            <template v-if="missingDays"> · 缺失 {{ missingDays }} 天</template>
          </template>
        </span>
        <span class="term-status__right">
          {{ isOrders ? '末笔价格' : '基建收益' }}
          <b :class="displayQuote.tone"
            >{{ displayQuote.closeText
            }}<template v-if="!displayQuote.partial">
              {{ displayQuote.arrowText }} {{ displayQuote.changeText }}</template
            ></b
          >
          <i>|</i
          >{{
            isTrend
              ? '订单 ' + formatCount(currentDay?.orderCount) + ' 单'
              : '样本 ' + formatCount(selectedBucket?.count) + (isOrders ? ' 笔' : ' 天')
          }}
        </span>
      </footer>
    </template>
  </section>
</template>

<style scoped>
.term {
  --term-bg: #000000;
  --term-surface: #050505;
  --term-surface-2: #0a0a0a;
  --term-hover: #101010;
  --term-line: #2a2a2a;
  --term-line-soft: #171717;
  --term-text: #d7d7d7;
  --term-muted: #8a8a8a;
  --term-up: #ff3232;
  --term-down: #00d26a;
  --term-cyan: #54fcfc;
  --term-blue: #3399ff;
  --term-yellow: #f5e663;
  --term-magenta: #ff5fd2;
  /* 下列语义色只用于固定底色（悬停文字、热力块、选中行等），随主题整体切换。 */
  --term-strong: #ffffff;
  --term-tab-active: rgba(255, 50, 50, 0.14);
  --term-tab-text: #ff3232;
  --term-shadow: 0 10px 26px rgba(0, 0, 0, 0.65);
  --term-track: #141414;
  --term-selected: #061a2c;
  --term-row-alt: #080808;
  --term-heat-border: rgba(255, 255, 255, 0.06);
  --term-heat-flat: rgba(138, 138, 138, 0.14);
  --term-heat-up-1: rgba(255, 50, 50, 0.14);
  --term-heat-up-2: rgba(255, 50, 50, 0.26);
  --term-heat-up-3: rgba(255, 50, 50, 0.4);
  --term-heat-up-4: rgba(255, 50, 50, 0.56);
  --term-heat-down-1: rgba(0, 210, 106, 0.14);
  --term-heat-down-2: rgba(0, 210, 106, 0.24);
  --term-heat-down-3: rgba(0, 210, 106, 0.36);
  --term-heat-down-4: rgba(0, 210, 106, 0.5);
  --term-heat-up-text: #ff8c8c;
  --term-heat-down-text: #7dffb9;
  --term-cell-up: rgba(255, 50, 50, 0.16);
  --term-cell-down: rgba(0, 210, 106, 0.16);
  --term-cell-up-text: #ff3232;
  --term-cell-down-text: #00d26a;
  --term-badge-border: rgba(51, 153, 255, 0.5);

  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  height: 100%;
  min-height: 0;
  box-sizing: border-box;
  border: 1px solid var(--term-line);
  background: var(--term-bg);
  color: var(--term-text);
  font-size: 11px;
  line-height: 1.35;
  font-variant-numeric: tabular-nums;
  text-align: left;
}

/* 亮色终端：白底、深色文字，涨跌与指标线按白底重新校准，仍保持红涨绿跌。 */
.term--light {
  --term-bg: #ffffff;
  --term-surface: #f7f8fa;
  --term-surface-2: #f0f3f7;
  --term-hover: #eef2f7;
  --term-line: #d6dce4;
  --term-line-soft: #e7ebf0;
  --term-text: #1f2225;
  --term-muted: #5b6675;
  --term-up: #c62828;
  --term-down: #067045;
  --term-cyan: #0a6fc2;
  --term-blue: #1557b0;
  --term-yellow: #8f6400;
  --term-magenta: #b51fa0;
  --term-strong: #111827;
  --term-tab-active: rgba(217, 43, 43, 0.08);
  --term-tab-text: #b42318;
  --term-shadow: 0 10px 26px rgba(31, 34, 37, 0.16);
  --term-track: #eceff3;
  --term-selected: #e8f2fb;
  --term-row-alt: #f7f9fc;
  --term-heat-border: rgba(31, 34, 37, 0.08);
  --term-heat-flat: rgba(105, 117, 134, 0.12);
  --term-heat-up-1: rgba(217, 43, 43, 0.1);
  --term-heat-up-2: rgba(217, 43, 43, 0.18);
  --term-heat-up-3: rgba(217, 43, 43, 0.28);
  --term-heat-up-4: rgba(217, 43, 43, 0.42);
  --term-heat-down-1: rgba(6, 112, 69, 0.1);
  --term-heat-down-2: rgba(6, 112, 69, 0.18);
  --term-heat-down-3: rgba(6, 112, 69, 0.28);
  --term-heat-down-4: rgba(6, 112, 69, 0.42);
  --term-heat-up-text: #8f1d14;
  --term-heat-down-text: #034d2d;
  --term-cell-up: rgba(217, 43, 43, 0.08);
  --term-cell-down: rgba(6, 112, 69, 0.08);
  --term-cell-up-text: #b42318;
  --term-cell-down-text: #055736;
  --term-badge-border: rgba(21, 87, 176, 0.45);
}

/* 浏览器全屏或页面内沉浸模式：终端独占视口，Esc 退出。 */
.term:fullscreen {
  height: 100vh;
  border: 0;
}

.term.is-immersive {
  position: fixed;
  inset: 0;
  z-index: 2000;
  height: auto;
  border: 0;
}

.term *,
.term *::before,
.term *::after {
  box-sizing: border-box;
}

/* 只清零原生按钮外观，让各组件类名继续拥有自己的 padding 与边框。 */
.term :where(button) {
  padding: 0;
  border: 0;
  border-radius: 0;
  background: none;
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.term .is-up {
  color: var(--term-up);
}

.term .is-down {
  color: var(--term-down);
}

.term .is-flat {
  color: var(--term-muted);
}

.term .is-yellow {
  color: var(--term-yellow);
}

/* ---------- 终端顶栏 ---------- */
.term-head {
  display: flex;
  flex: 0 0 auto;
  align-items: stretch;
  justify-content: space-between;
  min-height: 30px;
  border-bottom: 1px solid var(--term-line);
  background: var(--term-surface);
}

.term-head__left {
  display: flex;
  align-items: stretch;
  min-width: 0;
}

.term-head__brand {
  display: flex;
  align-items: center;
  padding: 0 12px;
  color: var(--term-cyan);
  font-weight: 600;
  letter-spacing: 0.04em;
  white-space: nowrap;
}

.term-head__nav {
  display: flex;
  align-items: stretch;
  overflow-x: auto;
  scrollbar-width: none;
}

.term-head__nav::-webkit-scrollbar {
  display: none;
}

.term-nav__item {
  padding: 0 12px;
  border-left: 1px solid var(--term-line);
  color: var(--term-text);
  white-space: nowrap;
}

.term-nav__item:hover {
  background: var(--term-hover);
  color: var(--term-strong);
}

.term-nav__item.is-active {
  background: var(--term-tab-active);
  color: var(--term-tab-text);
  font-weight: 600;
  box-shadow: inset 0 -1px 0 var(--term-up);
}

.term-head__right {
  position: relative;
  display: flex;
  align-items: center;
  align-self: stretch;
  gap: 10px;
  padding: 0 10px;
  white-space: nowrap;
}

.term-head__date {
  color: var(--term-muted);
  font-family: Consolas, 'Courier New', monospace;
}

.term-head__tag {
  padding: 1px 5px;
  border: 1px solid var(--term-up);
  color: var(--term-up);
  font-size: 10px;
}

.term-head__index {
  font-size: 13px;
  font-weight: 700;
}

.term-head__index i {
  margin-left: 5px;
  font-size: 11px;
  font-style: normal;
  font-weight: 500;
}

/* ---- 顶栏区间与工具按钮 ---- */
.term-range,
.term-tools {
  display: flex;
  align-items: stretch;
  align-self: stretch;
  border-left: 1px solid var(--term-line);
}

.term-range__item,
.term-tool {
  display: flex;
  align-items: center;
  padding: 0 6px;
  color: var(--term-text);
  font-size: 11px;
  white-space: nowrap;
}

.term-range__item + .term-range__item,
.term-tool + .term-tool {
  border-left: 1px solid var(--term-line-soft);
}

.term-range__item:hover,
.term-tool:hover {
  background: var(--term-hover);
  color: var(--term-strong);
}

.term-range__item.is-active {
  color: var(--term-cyan);
  box-shadow: inset 0 -1px 0 var(--term-cyan);
}

.term-tool:disabled {
  color: var(--term-muted);
  cursor: default;
}

.term-tool[aria-pressed='true'] {
  color: var(--term-yellow);
  box-shadow: inset 0 -1px 0 var(--term-yellow);
}

/* ---- 工具菜单 ---- */
.term-menu {
  position: absolute;
  top: 100%;
  right: 0;
  z-index: 20;
  width: 240px;
  max-height: min(360px, 70vh);
  overflow-y: auto;
  border: 1px solid var(--term-line);
  background: var(--term-surface);
  box-shadow: var(--term-shadow);
}

.term-menu__section {
  padding: 4px 0;
  border-bottom: 1px solid var(--term-line-soft);
}

.term-menu__section:last-child {
  border-bottom: 0;
}

.term-menu__title {
  margin: 2px 8px;
  color: var(--term-muted);
  font-size: 10px;
  font-weight: 400;
  letter-spacing: 0.08em;
}

.term-menu__item {
  display: block;
  width: 100%;
  padding: 4px 8px;
  color: var(--term-text);
  font-size: 11px;
  text-align: left;
  white-space: normal;
}

.term-menu__item:hover {
  background: var(--term-hover);
  color: var(--term-strong);
}

.term-menu__item.is-active {
  box-shadow: inset 2px 0 0 var(--term-cyan);
  color: var(--term-cyan);
}

.term-menu__item:disabled {
  color: var(--term-muted);
  cursor: default;
}

/* ---------- 加载 / 空态 ---------- */
.term-notice {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 260px;
  padding: 32px 16px;
  border-top: 1px solid var(--term-line);
  color: var(--term-muted);
  text-align: center;
}

.term-notice--empty strong {
  color: var(--term-text);
  font-size: 14px;
  font-weight: 500;
}

/* ---------- 指数栏 ---------- */
.index-strip {
  display: grid;
  flex: 0 0 auto;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  border-bottom: 1px solid var(--term-line);
}

.index-strip__item {
  display: flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
  padding: 4px 8px;
  border-right: 1px solid var(--term-line-soft);
  white-space: nowrap;
}

.index-strip__item:last-child {
  border-right: 0;
}

.index-strip__name {
  color: var(--term-muted);
  font-size: 11px;
}

.index-strip__value {
  font-size: 12px;
  font-weight: 700;
}

.index-strip__change {
  font-size: 11px;
}

/* ---------- 视图区：顶栏与状态栏固定，主区内部滚动 ---------- */
.term-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
}

.view {
  display: flex;
  flex-direction: column;
  min-height: 100%;
  box-sizing: border-box;
}

/* 桌面端视图固定在终端可视区内，主图与盘口各自撑满，超出部分只滚盘口/列表。 */
@media (min-width: 1101px) {
  .view {
    height: 100%;
    min-height: 0;
  }
}

.view--charts {
  gap: 3px;
  padding: 3px;
  background: var(--term-line-soft);
}

.view--charts .main-grid {
  flex: 1 1 auto;
  min-height: 0;
  padding: 0;
  background: none;
  gap: 3px;
}

.view--charts .chart-body {
  min-height: 240px;
}

.view--charts .order-panel {
  flex: 0 0 auto;
  height: 188px;
  margin: 0;
}

.view--charts .chart-body--orders {
  height: 160px;
  min-height: 0;
}

.view--heat,
.view--list {
  padding: 3px;
  background: var(--term-line-soft);
}

.view--heat .heat-panel,
.view--list .list-panel {
  flex: 1 1 auto;
  min-height: 0;
  margin: 0;
}

.view--heat .heat-grid {
  flex: 1 1 auto;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  grid-auto-rows: minmax(88px, 1fr);
  align-content: stretch;
  gap: 4px;
  padding: 6px;
}

.view--heat .heat-block {
  height: auto;
  min-height: 80px;
  gap: 2px;
}

.view--heat .heat-block__date {
  font-size: 12px;
}

.view--heat .heat-block__close {
  font-size: 18px;
}

.view--heat .heat-block__change {
  font-size: 12px;
}

.view--list .list-wrap {
  flex: 1 1 auto;
  min-height: 0;
  max-height: none;
  overflow: auto;
}

/* ---------- 主区 ---------- */
.main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  align-items: stretch;
  gap: 3px;
  padding: 3px;
  background: var(--term-line-soft);
}

.panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  border: 1px solid var(--term-line);
  border-radius: 0;
  background: var(--term-bg);
}

/* 主图与盘口共用一行：盘口内容超出时自己滚动，不把整页撑高。 */
.chart-panel,
.book {
  min-height: 0;
}

.book {
  overflow-y: auto;
}

.panel-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 24px;
  padding: 0 6px;
  border-bottom: 1px solid var(--term-line);
  background: var(--term-surface-2);
}

.panel-bar__title {
  color: var(--term-text);
  font-size: 11px;
  font-weight: 600;
}

.panel-bar__meta {
  margin-left: auto;
  overflow: hidden;
  color: var(--term-muted);
  font-size: 10px;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.chart-indicators {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 14px;
  padding: 2px 6px;
  border-bottom: 1px solid var(--term-line-soft);
  color: var(--term-muted);
  font-size: 11px;
}

.chart-indicators b {
  color: var(--term-text);
  font-weight: 600;
}

.chart-indicators__spacer {
  flex: 1 1 auto;
}

.chart-indicators__hint {
  overflow: hidden;
  color: var(--term-muted);
  font-size: 11px;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.chart-body {
  position: relative;
  flex: 1 1 auto;
  min-height: 430px;
  background: var(--term-bg);
}

.chart-body .chart {
  width: 100%;
  height: 100%;
}

.chart-body--orders {
  flex: 0 0 auto;
  height: 220px;
  min-height: 0;
}

/* ---------- 右侧盘口 ---------- */
.panel-bar--book {
  justify-content: space-between;
}

.book__name {
  color: var(--term-cyan);
  font-weight: 600;
}

.book__code {
  margin-left: 4px;
  color: var(--term-text);
  font-weight: 400;
  letter-spacing: 0.04em;
}

.book__quote {
  padding: 6px 8px 8px;
  border-bottom: 1px solid var(--term-line);
}

.book__price {
  font-size: 38px;
  font-weight: 700;
  line-height: 1.05;
  letter-spacing: -0.02em;
}

.book__price small {
  margin-left: 3px;
  color: var(--term-muted);
  font-size: 12px;
  font-weight: 400;
}

.book__change {
  margin-top: 1px;
  font-size: 13px;
  font-weight: 600;
}

.book__partial {
  margin: 2px 0 0;
  color: var(--term-yellow);
  font-size: 10px;
  line-height: 1.3;
}

.book__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 12px;
  margin: 6px 0 0;
}

.book__cell {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  min-width: 0;
  border-bottom: 1px dotted var(--term-line-soft);
  line-height: 20px;
}

.book__cell dt {
  color: var(--term-muted);
  font-size: 11px;
}

.book__cell dd {
  margin: 0;
  overflow: hidden;
  color: var(--term-text);
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}

.book__section {
  padding: 2px 8px 5px;
  border-bottom: 1px solid var(--term-line);
}

.book__section:last-child {
  border-bottom: 0;
}

.book__title {
  margin: 2px 0 2px;
  color: var(--term-cyan);
  font-size: 11px;
  font-weight: 400;
  letter-spacing: 0.08em;
}

.order-row {
  display: grid;
  grid-template-columns: 58px minmax(0, 1fr) 52px 52px;
  align-items: center;
  gap: 6px;
  line-height: 20px;
}

.order-row__name {
  overflow: hidden;
  color: var(--term-muted);
  font-size: 11px;
  white-space: nowrap;
}

.order-row__track {
  position: relative;
  height: 9px;
  overflow: hidden;
  background: var(--term-track);
}

.order-row__bar {
  display: block;
  height: 100%;
  background: var(--term-up);
}

.order-row__value {
  color: var(--term-text);
  font-size: 11px;
  font-weight: 600;
  text-align: right;
}

.order-row__delta {
  font-size: 11px;
  text-align: right;
}

.fund {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 2px 0 4px;
}

.fund__ring {
  position: relative;
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: 82px;
  height: 82px;
  border-radius: 50%;
}

.fund__hole {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: var(--term-bg);
  color: var(--term-muted);
  font-size: 9px;
  line-height: 1.2;
  text-align: center;
}

.fund__legend {
  flex: 1 1 auto;
  min-width: 0;
  margin: 0;
  padding: 0;
  list-style: none;
}

.fund__legend li {
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--term-muted);
  font-size: 11px;
  line-height: 17px;
}

.fund__legend i {
  width: 7px;
  height: 7px;
  flex: 0 0 auto;
}

.fund__legend b {
  margin-left: auto;
  color: var(--term-text);
  font-weight: 600;
}

.fund__breadth {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  padding-top: 2px;
  color: var(--term-muted);
  font-size: 11px;
}

.fund__notice {
  margin: 2px 0 0;
  color: var(--term-yellow);
  font-size: 10px;
}

/* ---------- 成交明细 ---------- */
.trades__head {
  display: grid;
  grid-template-columns: 112px 52px minmax(0, 1fr) 16px;
  gap: 6px;
  padding: 0 4px;
  border-bottom: 1px dotted var(--term-line-soft);
  color: var(--term-muted);
  font-size: 10px;
  line-height: 16px;
}

.trades__head span:nth-child(2),
.trades__head span:nth-child(3) {
  text-align: right;
}

.trades {
  margin: 0;
  padding: 0;
  list-style: none;
}

.trades__row {
  display: grid;
  grid-template-columns: 112px 52px minmax(0, 1fr) 16px;
  align-items: center;
  gap: 6px;
  padding: 0 4px;
  border-bottom: 1px dotted var(--term-line-soft);
  line-height: 18px;
  cursor: pointer;
}

.trades__row:hover {
  background: var(--term-hover);
}

.trades__row:focus-visible {
  outline: 1px solid var(--term-blue);
  outline-offset: -1px;
}

.trades__row.is-selected {
  background: var(--term-selected);
  box-shadow: inset 2px 0 0 var(--term-blue);
}

.trades__time {
  color: var(--term-muted);
  font-family: Consolas, 'Courier New', monospace;
  font-size: 11px;
}

.trades__price {
  font-size: 11px;
  font-weight: 600;
  text-align: right;
}

.trades__qty {
  color: var(--term-text);
  font-size: 11px;
  text-align: right;
}

.trades__arrow {
  font-size: 9px;
  text-align: center;
}

/* ---------- 涨跌分布 ---------- */
.heat-panel {
  margin: 3px;
}

.heat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(64px, 1fr));
  gap: 3px;
  padding: 6px;
}

.heat-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1px;
  height: 56px;
  border: 1px solid var(--term-heat-border);
  color: var(--term-text);
}

.heat-block:hover {
  border-color: var(--term-cyan);
}

.heat-block:focus-visible {
  outline: 1px solid var(--term-cyan);
  outline-offset: -1px;
}

.heat-block.is-selected {
  outline: 1px solid var(--term-blue);
  outline-offset: -1px;
}

.heat-block.is-up {
  background: var(--term-heat-up-1);
}

.heat-block.is-down {
  background: var(--term-heat-down-1);
}

.heat-block.is-flat {
  background: var(--term-heat-flat);
}

.heat-block.is-flat .heat-block__change {
  color: var(--term-muted);
}

.heat-block--2.is-up {
  background: var(--term-heat-up-2);
}

.heat-block--2.is-down {
  background: var(--term-heat-down-2);
}

.heat-block--3.is-up {
  background: var(--term-heat-up-3);
}

.heat-block--3.is-down {
  background: var(--term-heat-down-3);
}

.heat-block--4.is-up {
  background: var(--term-heat-up-4);
}

.heat-block--4.is-down {
  background: var(--term-heat-down-4);
}

.heat-block__date {
  color: var(--term-text);
  font-family: Consolas, 'Courier New', monospace;
  font-size: 10px;
}

.heat-block__close {
  font-size: 12px;
  font-weight: 700;
}

.heat-block__change {
  color: var(--term-text);
  font-size: 9px;
}

.heat-block.is-up .heat-block__close,
.heat-block.is-up .heat-block__change {
  color: var(--term-heat-up-text);
}

.heat-block.is-down .heat-block__close,
.heat-block.is-down .heat-block__change {
  color: var(--term-heat-down-text);
}

/* ---------- 行情列表 ---------- */
.list-panel {
  margin: 0 3px;
}

.list-wrap {
  max-height: 520px;
  overflow: auto;
}

.quote-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 11px;
}

.quote-table th,
.quote-table td {
  padding: 3px 8px;
  text-align: right;
  white-space: nowrap;
}

.quote-table th:first-child,
.quote-table td:first-child,
.quote-table th:nth-child(2),
.quote-table td:nth-child(2) {
  text-align: left;
}

.quote-table thead th {
  position: sticky;
  top: 0;
  z-index: 1;
  border-bottom: 1px solid var(--term-line);
  background: var(--term-surface-2);
  color: var(--term-muted);
  font-size: 11px;
  font-weight: 400;
}

.quote-table__row {
  cursor: pointer;
}

.quote-table__row:nth-child(even) {
  background: var(--term-row-alt);
}

.quote-table__row th,
.quote-table__row td {
  border-bottom: 1px solid var(--term-line-soft);
}

.quote-table__row:hover {
  background: var(--term-hover);
}

.quote-table__row:focus-visible {
  outline: 1px solid var(--term-blue);
  outline-offset: -1px;
}

.quote-table__row.is-selected {
  background: var(--term-selected);
}

.quote-table__row.is-selected > td:first-child {
  box-shadow: inset 2px 0 0 var(--term-blue);
}

.quote-table__code {
  color: var(--term-cyan);
  font-family: Consolas, 'Courier New', monospace;
}

.quote-table__name {
  color: var(--term-text);
}

.quote-table__star {
  margin-left: 3px;
  color: var(--term-yellow);
}

.quote-table__badge {
  margin-left: 4px;
  padding: 0 3px;
  border: 1px solid var(--term-badge-border);
  color: var(--term-blue);
  font-size: 9px;
}

.quote-table__badge--muted {
  border-color: var(--term-line);
  color: var(--term-muted);
}

.quote-table__close {
  font-weight: 700;
}

.quote-table__change {
  font-weight: 700;
}

.num {
  font-variant-numeric: tabular-nums;
}

/* ---------- 订单分布 ---------- */
.order-panel {
  margin: 3px;
}

/* ---------- 底部状态栏 ---------- */
.term-status {
  display: flex;
  flex: 0 0 auto;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 4px 12px;
  min-height: 26px;
  padding: 4px 10px;
  border-top: 1px solid var(--term-line);
  background: var(--term-surface);
  color: var(--term-muted);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.term-status__right i {
  margin: 0 6px;
  color: var(--term-line);
  font-style: normal;
}

.term-status__right b {
  font-weight: 600;
}

.market-controls {
  display: flex;
  flex: 0 0 auto;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 12px;
  padding: 4px 8px;
  border-bottom: 1px solid var(--term-line);
  background: var(--term-surface);
}

.market-switch {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 2px;
}

.market-switch button {
  min-height: 28px;
  padding: 4px 8px;
  color: var(--term-muted);
}

.market-switch button:hover,
.market-switch button.is-active {
  background: var(--term-hover);
  color: var(--term-cyan);
}

.market-switch button.is-active {
  box-shadow: inset 0 -1px 0 var(--term-cyan);
}

.market-caveat {
  flex-basis: 100%;
  margin: 0;
  color: var(--term-muted);
  font-size: 10px;
}

.market-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 180px;
  padding: 12px;
  color: var(--term-muted);
  text-align: center;
}

.market-state button {
  min-height: 36px;
  padding: 6px 12px;
  border: 1px solid var(--term-cyan);
  color: var(--term-cyan);
}

.market-state--empty {
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
}

.market-pagination {
  display: flex;
  flex: 0 0 auto;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
  padding: 2px 6px;
  border-bottom: 1px solid var(--term-line);
  color: var(--term-muted);
}

.market-pagination span {
  flex: 1 1 auto;
}

.market-pagination button {
  min-height: 36px;
  padding: 4px 8px;
  color: var(--term-cyan);
}

.market-pagination button:disabled {
  color: var(--term-muted);
  cursor: default;
}

/* ---------- 响应式 ---------- */
@media (max-width: 1100px) {
  .main-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .index-strip {
    display: flex;
    overflow-x: auto;
  }

  .index-strip__item {
    flex: 0 0 auto;
    min-width: 104px;
  }

  .term-head {
    flex-wrap: wrap;
  }

  .term-head__date,
  .term-head__tag {
    display: none;
  }

  .term-head__right {
    width: 100%;
    flex-wrap: wrap;
    align-self: stretch;
    justify-content: flex-end;
    gap: 4px 8px;
    padding: 1px 8px;
  }

  .term-range,
  .term-tools {
    border-left: 0;
  }

  .term-range__item,
  .term-tool {
    min-height: 36px;
    padding: 0 8px;
  }

  .view--charts .chart-panel .chart-body {
    min-height: 300px;
  }
}

@media (max-width: 720px) {
  .market-controls {
    gap: 2px 8px;
    padding: 2px 4px;
  }

  .market-switch button {
    min-height: 36px;
    padding: 6px 8px;
  }

  .term-head {
    flex-wrap: wrap;
    min-height: 28px;
  }

  .term-head__brand {
    padding: 0 8px;
    font-size: 11px;
  }

  .term-nav__item {
    padding: 0 8px;
    font-size: 11px;
  }

  .term-head__right {
    width: 100%;
    flex-wrap: wrap;
    align-self: stretch;
    justify-content: flex-end;
    gap: 4px 8px;
    padding: 1px 8px;
  }

  .term-head__date,
  .term-head__tag,
  .term-head__index {
    display: none;
  }

  .term-range,
  .term-tools {
    border-left: 0;
  }

  .term-range__item,
  .term-tool {
    min-height: 36px;
    padding: 0 8px;
    font-size: 11px;
  }

  .term-menu__item {
    min-height: 38px;
    padding: 8px;
  }

  .term-menu__title {
    margin: 6px 8px 2px;
  }

  /* 窄屏把次要操作收进“工具”菜单，留出可点按的触控高度。 */
  .term-tool--refresh,
  .term-tool--standard,
  .term-tool--fullscreen {
    display: none;
  }

  /* 移动端回退沉浸模式盖不住底部导航，把状态栏抬到导航上方。 */
  .term.is-immersive {
    padding-bottom: 60px;
  }

  .book__price {
    font-size: 30px;
  }

  .view--charts .chart-panel .chart-body {
    min-height: 260px;
  }

  .view--charts .chart-body--orders {
    height: 140px;
    min-height: 0;
  }

  .view--heat .heat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    grid-auto-rows: minmax(60px, 1fr);
  }

  .view--heat .heat-block {
    min-height: 58px;
  }

  .quote-table__change.is-up {
    background: var(--term-cell-up);
    color: var(--term-cell-up-text);
  }

  .quote-table__change.is-down {
    background: var(--term-cell-down);
    color: var(--term-cell-down-text);
  }
}

@media (max-width: 520px) {
  .view--charts,
  .view--heat,
  .view--list {
    padding: 2px;
  }

  .view--charts .main-grid {
    gap: 2px;
  }

  .panel-bar__meta {
    display: none;
  }

  .book__grid {
    gap: 0 8px;
  }

  .view--charts .chart-panel .chart-body {
    min-height: 220px;
  }

  .view--charts .chart-body--orders {
    height: 130px;
    min-height: 0;
  }

  .fund__ring {
    width: 68px;
    height: 68px;
  }

  .fund__hole {
    width: 40px;
    height: 40px;
  }

  .view--heat .heat-grid {
    gap: 2px;
    padding: 4px;
    grid-auto-rows: minmax(52px, 1fr);
  }

  .view--heat .heat-block {
    min-height: 50px;
  }

  .view--heat .heat-block__close {
    font-size: 14px;
  }

  .quote-table {
    min-width: 660px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .term,
  .term * {
    transition: none;
    animation: none;
  }
}
</style>
