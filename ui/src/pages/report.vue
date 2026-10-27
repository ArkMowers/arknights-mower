<script setup>
import { i18n } from '@/i18n'
import { operatorDisplayName } from '@/i18n/gameNames'
import { reportErrorMessage } from '@/i18n/reports'
const { t } = i18n.global
defineOptions({ name: 'BaseReportPage' })

import PageLayout from '@/components/PageLayout.vue'
import PageHeader from '@/components/PageHeader.vue'
import { registerTheme, use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart } from 'echarts/charts'
import { LabelLayout } from 'echarts/features'
import {
  AriaComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  ToolboxComponent,
  TooltipComponent
} from 'echarts/components'
import VChart, { THEME_KEY } from 'vue-echarts'
import dark from './theme/dark.json'
import roma from './theme/roma.json'
import { computed, inject, onMounted, provide, reactive, ref } from 'vue'
import { storeToRefs } from 'pinia'
import TrendingUpOutline from '@vicons/ionicons5/es/TrendingUpOutline'
import TrendingDownOutline from '@vicons/ionicons5/es/TrendingDownOutline'
import RefreshOutline from '@vicons/ionicons5/es/RefreshOutline'
import TrophyOutline from '@vicons/ionicons5/es/TrophyOutline'
import ChevronBackOutline from '@vicons/ionicons5/es/ChevronBackOutline'
import ChevronForwardOutline from '@vicons/ionicons5/es/ChevronForwardOutline'
import { useConfigStore } from '@/stores/config'
import { useReportStore } from '@/stores/report'
import { useResolvedTheme } from '@/composables/theme'
import { useCountUp } from '@/composables/useCountUp'
import {
  loadIncomeSettings,
  incomeAlgorithmLabel,
  incomeAlgorithms,
  incomeSettingsUrl
} from '@/utils/incomeSettings'
import {
  CLOSURE_GOLD,
  ORUNDUM_PER_PULL,
  TEQUILA_GOLD,
  buildReportDays,
  formatCount,
  formatDay,
  formatIncome,
  formatPercent,
  isReading,
  relativeChange,
  reportRanges,
  selectRange,
  summarize,
  tradingRange,
  withIncome
} from '@/utils/baseReport'

use([
  AriaComponent,
  BarChart,
  CanvasRenderer,
  GridComponent,
  LegendComponent,
  LabelLayout,
  LineChart,
  MarkLineComponent,
  ToolboxComponent,
  TooltipComponent
])
registerTheme('dark', dark)
registerTheme('roma', roma)

const axios = inject('axios')
const { theme: themePreference } = storeToRefs(useConfigStore())
const theme = useResolvedTheme(themePreference)
provide(
  THEME_KEY,
  computed(() => (theme.value === 'dark' ? 'dark' : 'roma'))
)
const isDark = computed(() => theme.value === 'dark')
const { getReportData, getOrundumData, getTradingHistory } = useReportStore()

// ---- 收益算法 ----
const valuation = ref(null)
let valuationRevision = 0
const algorithmBusy = ref(false)
const algorithmError = ref('')
const showCustomAlgorithm = ref(false)
const customRatios = reactive({ experience: 0.9568, gold: 0.76544, order: 0.23456 })
const customFields = [
  {
    key: 'gold',
    get label() {
      return t('reports.pureGold')
    }
  },
  {
    key: 'order',
    get label() {
      return t('reports.orders')
    }
  },
  {
    key: 'experience',
    get label() {
      return t('reports.experience')
    }
  }
]
const algorithmOptions = computed(() =>
  incomeAlgorithms.map((option) => ({ ...option, key: option.value }))
)
const algorithmLabel = computed(() => incomeAlgorithmLabel(valuation.value?.base_algorithm))
const algorithmShortLabel = computed(() => algorithmLabel.value.split('（')[0])

function selectAlgorithm(key) {
  if (!valuation.value || algorithmBusy.value) return
  if (key === -1) {
    Object.assign(customRatios, valuation.value.ratios)
    showCustomAlgorithm.value = true
    return
  }
  const option = incomeAlgorithms.find((row) => row.value === key)
  if (option?.ratios) return saveAlgorithm(key, option.ratios)
}

async function saveAlgorithm(algorithm, ratios) {
  if (!valuation.value || algorithmBusy.value) return
  algorithmBusy.value = true
  algorithmError.value = ''
  try {
    const response = await axios.put(incomeSettingsUrl, {
      base_algorithm: algorithm,
      ratios: { ...ratios, efficiency: valuation.value.ratios.efficiency }
    })
    valuationRevision++
    valuation.value = response.data
    showCustomAlgorithm.value = false
  } catch (error) {
    algorithmError.value = error.response?.data?.error || t('reports.algorithmSaveError')
  } finally {
    algorithmBusy.value = false
  }
}

// ---- 数据读取 ----
const loading = ref(true)
const loadError = ref('')
const partialWarning = ref('')
const reportRows = ref([])
const orundumRows = ref([])
const tradingRows = ref([])
let loadVersion = 0

async function load() {
  const version = ++loadVersion
  const settingsRevision = valuationRevision
  loading.value = true
  loadError.value = ''
  partialWarning.value = ''
  try {
    const [settings, report] = await Promise.all([loadIncomeSettings(axios), getReportData()])
    // 基报文件不存在时后端可能返回 false，按空记录处理。
    const rows = Array.isArray(report) ? report : []
    const span = tradingRange(rows)
    const [orundum, trading] = await Promise.allSettled([
      getOrundumData(),
      span ? getTradingHistory(span.start, span.end) : Promise.resolve([])
    ])
    if (version !== loadVersion) return
    if (settingsRevision === valuationRevision) valuation.value = settings
    reportRows.value = rows
    orundumRows.value = orundum.status === 'fulfilled' ? orundum.value : []
    tradingRows.value = trading.status === 'fulfilled' ? trading.value : []
    const missing = [
      orundum.status === 'rejected' && t('reports.orundumRecords'),
      trading.status === 'rejected' && t('reports.tradingRecords')
    ].filter(Boolean)
    if (missing.length)
      partialWarning.value = t('reports.partialReadFailed', { names: missing.join(', ') })
  } catch (error) {
    if (version !== loadVersion) return
    loadError.value = error.response?.data?.error || t('reports.reportReadError')
  } finally {
    if (version === loadVersion) loading.value = false
  }
}
onMounted(load)

// ---- 派生数据 ----
const range = ref('14')
const chartView = ref('income')
const rangeOptions = computed(() =>
  reportRanges.map((row) => ({ value: row.value, label: row.label }))
)
const allDays = computed(() =>
  valuation.value
    ? withIncome(
        buildReportDays(reportRows.value, orundumRows.value, tradingRows.value),
        valuation.value.ratios
      )
    : []
)
const days = computed(() => selectRange(allDays.value, range.value))
const summary = computed(() => summarize(days.value))
const ready = computed(() => !loading.value && !loadError.value && Boolean(valuation.value))
const hasData = computed(() => days.value.length > 0)
// 产物配色在明暗主题下分别校准，保证与卡片背景的对比度。
const palette = computed(() =>
  isDark.value
    ? {
        gold: '#f5744f',
        special: '#b69cf5',
        order: '#6bb4f0',
        experience: '#f3e28f',
        orundum: '#f07f9a',
        income: '#63e2b7',
        grid: 'rgba(255, 255, 255, 0.07)',
        axis: 'rgba(255, 255, 255, 0.45)',
        tooltip: 'rgba(36, 38, 44, 0.96)',
        tooltipBorder: 'rgba(255, 255, 255, 0.1)',
        text: 'rgba(255, 255, 255, 0.88)'
      }
    : {
        gold: '#f5744f',
        special: '#8b63de',
        order: '#2f87d6',
        experience: '#f3e28f',
        orundum: '#d64b6f',
        income: '#18a058',
        grid: 'rgba(31, 34, 37, 0.07)',
        axis: 'rgba(31, 34, 37, 0.5)',
        tooltip: 'rgba(255, 255, 255, 0.98)',
        tooltipBorder: 'rgba(31, 34, 37, 0.1)',
        text: 'rgba(31, 34, 37, 0.88)'
      }
)

const compositionParts = [
  {
    key: 'gold',
    get label() {
      return t('reports.pureGold')
    }
  },
  {
    key: 'special',
    get label() {
      return t('reports.specialGold')
    }
  },
  {
    key: 'order',
    get label() {
      return t('reports.lmdOrders')
    }
  },
  {
    key: 'experience',
    get label() {
      return t('reports.experience')
    }
  }
]
// ---- 单日详情：选中日与它在全部记录中的前一条读数对比 ----
const selectedDate = ref(null)
const selectedIndex = computed(() => {
  const index = days.value.findIndex((day) => day.date === selectedDate.value)
  return index >= 0 ? index : days.value.length - 1
})
const selectedDay = computed(() => days.value[selectedIndex.value] || null)
const previousDay = computed(() => {
  const index = allDays.value.findIndex((day) => day.date === selectedDay.value?.date)
  return index > 0 ? allDays.value[index - 1] : null
})
function selectDay(date) {
  selectedDate.value = date
}
function stepDay(offset) {
  const day = days.value[selectedIndex.value + offset]
  if (day) selectDay(day.date)
}
function onChartClick(params) {
  const day = days.value[params?.dataIndex]
  if (day) selectDay(day.date)
}

function compare(value, base) {
  const delta = isReading(value) && isReading(base) ? value - base : null
  return { value, base, delta, change: relativeChange(value, base) }
}

const specialGold = (day) => day.tequilaGold + day.closureGold
const detailItems = [
  {
    key: 'gold',
    get label() {
      return t('reports.pureGold')
    },
    icon: '赤金',
    pick: (day) => day.gold,
    note: () => t('reports.manufacturingValue')
  },
  {
    key: 'special',
    get label() {
      return t('reports.specialGold')
    },
    icon: '赤金',
    pick: specialGold,
    note: (day) =>
      specialGold(day)
        ? [
            day.tequilaGold &&
              t('reports.operatorOrders', {
                name: operatorDisplayName('龙舌兰'),
                count: day.tequilaGold / TEQUILA_GOLD
              }),
            day.closureGold &&
              t('reports.operatorOrders', {
                name: operatorDisplayName('可露希尔'),
                count: day.closureGold / CLOSURE_GOLD
              })
          ]
            .filter(Boolean)
            .join(' · ')
        : t('reports.noSpecialOrders', {
            first: operatorDisplayName('龙舌兰'),
            second: operatorDisplayName('可露希尔')
          })
  },
  {
    key: 'experience',
    get label() {
      return t('reports.experience')
    },
    icon: '中级作战记录',
    pick: (day) => day.experience
  },
  {
    key: 'orders',
    get label() {
      return t('reports.lmdOrders')
    },
    icon: '龙门币',
    pick: (day) => day.orders,
    note: (day) =>
      isReading(day.orderCount)
        ? t('reports.orderSummary', {
            count: formatCount(day.orderCount),
            value: formatCount(day.perOrder)
          })
        : ''
  },
  {
    key: 'orundum',
    get label() {
      return t('reports.orundum')
    },
    icon: '合成玉',
    pick: (day) => day.orundum,
    note: (day) =>
      isReading(day.orundum)
        ? t('reports.approxPulls', { count: (day.orundum / ORUNDUM_PER_PULL).toFixed(1) })
        : ''
  }
]
const detailRows = computed(() => {
  const day = selectedDay.value
  if (!day) return []
  const base = previousDay.value
  return detailItems.map((item) => ({
    key: item.key,
    label: item.label,
    icon: item.icon,
    note: item.note?.(day) || '',
    ...compare(item.pick(day), base ? item.pick(base) : null)
  }))
})

// 收益拆分：两日各项折算值，条长按两日中的最大项归一。
const incomeRows = computed(() => {
  const day = selectedDay.value
  if (!day) return []
  const base = previousDay.value
  const rows = compositionParts.map((part) => ({
    ...part,
    color: palette.value[part.key],
    ...compare(day.income[part.key], base?.income[part.key] ?? null)
  }))
  const max = Math.max(...rows.flatMap((row) => [row.value || 0, row.base || 0]), 0)
  return rows.map((row) => ({
    ...row,
    width: max ? ((row.value || 0) / max) * 100 : 0,
    baseWidth: max ? ((row.base || 0) / max) * 100 : 0
  }))
})
const incomeCompare = computed(() =>
  compare(selectedDay.value?.income.total ?? null, previousDay.value?.income.total ?? null)
)
const animatedIncome = useCountUp(computed(() => incomeCompare.value.value))

function deltaText(row, digits) {
  if (!isReading(row.delta)) return ''
  const sign = row.delta > 0 ? '+' : row.delta < 0 ? '−' : '±'
  const size = Math.abs(row.delta)
  return `${sign}${digits === undefined ? formatCount(size) : size.toFixed(digits)}`
}
function deltaClass(row) {
  if (!isReading(row.delta) || row.delta === 0) return 'is-flat'
  return row.delta > 0 ? 'is-up' : 'is-down'
}

const failedIcons = reactive(new Set())

// ---- 图表 ----
function tooltipBase() {
  return {
    trigger: 'axis',
    confine: true,
    backgroundColor: palette.value.tooltip,
    borderColor: palette.value.tooltipBorder,
    borderWidth: 1,
    padding: [10, 12],
    textStyle: { color: palette.value.text, fontSize: 12 },
    extraCssText: 'border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,.14);'
  }
}

function axisBase() {
  return {
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: palette.value.axis, fontSize: 11 },
    splitLine: { lineStyle: { color: palette.value.grid } }
  }
}

function marker(color) {
  return `<span style="display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:6px;background:${color}"></span>`
}

function tooltipRow(color, label, value) {
  return `<div style="display:flex;justify-content:space-between;gap:16px;line-height:1.7"><span>${marker(color)}${label}</span><b style="font-variant-numeric:tabular-nums">${value}</b></div>`
}

function incomeNote(income) {
  if (!income.partial) return ''
  return isReading(income.total) ? t('reports.partialIncome') : t('reports.missingIncome')
}

function lineLabel(format) {
  return {
    show: true,
    position: 'top',
    distance: 6,
    color: palette.value.text,
    fontSize: 11,
    formatter: ({ value }) => (isReading(value) ? format(value) : '')
  }
}

function chartToolbox(name) {
  return {
    top: 0,
    right: 0,
    iconStyle: { borderColor: palette.value.axis },
    feature: {
      saveAsImage: {
        show: true,
        title: t('reports.saveChartImage'),
        name: `${t('reports.baseReportTitle')}-${name}`,
        backgroundColor: isDark.value ? '#18181c' : '#fff'
      }
    }
  }
}

const dates = computed(() => days.value.map((day) => formatDay(day.date)))

const incomeOption = computed(() => {
  const colors = palette.value
  const average = summary.value.averageIncome
  return {
    backgroundColor: 'transparent',
    aria: { enabled: true },
    animationDuration: 700,
    animationEasing: 'cubicOut',
    toolbox: chartToolbox(t('reports.dailyIncomeTitle')),
    grid: { top: 56, right: 12, bottom: 4, left: 4, containLabel: true },
    legend: {
      top: 0,
      left: 0,
      right: 30,
      icon: 'roundRect',
      itemWidth: 10,
      itemHeight: 10,
      textStyle: { color: colors.axis }
    },
    tooltip: {
      ...tooltipBase(),
      axisPointer: { type: 'shadow', shadowStyle: { color: colors.grid } },
      formatter(params) {
        const day = days.value[params[0]?.dataIndex]
        if (!day) return ''
        const income = day.income
        const rows = compositionParts
          .map((part) =>
            tooltipRow(colors[part.key], part.label, formatIncome(income[part.key], 3))
          )
          .join('')
        const raw = [
          t('reports.metricValue', { label: t('reports.pureGold'), value: formatCount(day.gold) }),
          day.tequilaGold || day.closureGold
            ? t('reports.metricValue', {
                label: t('reports.specialGold'),
                value: formatCount(day.tequilaGold + day.closureGold)
              })
            : '',
          t('reports.metricValue', { label: t('reports.orders'), value: formatCount(day.orders) }),
          t('reports.metricValue', {
            label: t('reports.experience'),
            value: formatCount(day.experience)
          })
        ]
          .filter(Boolean)
          .join(' · ')
        return `<div style="min-width:200px">
          <div style="font-weight:600;margin-bottom:4px">${day.date}</div>
          ${rows}
          <div style="border-top:1px solid ${colors.grid};margin-top:6px;padding-top:6px">
            ${tooltipRow(colors.income, t('reports.income10k'), formatIncome(income.total, 3))}
          </div>
          <div style="opacity:.65;margin-top:4px;font-size:11px">${raw}</div>
          ${income.partial ? `<div style="opacity:.65;font-size:11px">${incomeNote(income)}</div>` : ''}
        </div>`
      }
    },
    xAxis: { type: 'category', data: dates.value, ...axisBase(), splitLine: { show: false } },
    yAxis: {
      type: 'value',
      ...axisBase(),
      name: t('reports.tenThousandUnit'),
      nameTextStyle: { color: colors.axis }
    },
    series: [
      ...compositionParts.map((part, index) => ({
        name: part.label,
        type: 'bar',
        stack: 'income',
        barMaxWidth: 28,
        color: colors[part.key],
        itemStyle: {
          borderRadius: index === compositionParts.length - 1 ? [5, 5, 0, 0] : 0,
          ...(part.key === 'experience' ? { borderWidth: 1, borderColor: '#c5ac59' } : {})
        },
        emphasis: { focus: 'series' },
        // 选中日保持原色，其余日期降低不透明度，与单日详情对应。
        data: days.value.map((day, dayIndex) => ({
          value: day.income[part.key],
          itemStyle: dayIndex === selectedIndex.value ? undefined : { opacity: 0.42 }
        }))
      })),
      {
        name: t('reports.income'),
        type: 'line',
        smooth: 0.3,
        symbol: 'circle',
        symbolSize: 6,
        showAllSymbol: true,
        label: lineLabel(formatIncome),
        labelLayout: { hideOverlap: true },
        color: colors.income,
        lineStyle: { width: 2 },
        z: 5,
        data: days.value.map((day) => day.income.total),
        markLine: isReading(average)
          ? {
              silent: true,
              symbol: 'none',
              lineStyle: { type: 'dashed', color: colors.axis, width: 1 },
              label: {
                position: 'insideEndTop',
                color: colors.axis,
                formatter: t('reports.meanValue', { value: formatIncome(average) })
              },
              data: [{ yAxis: average }]
            }
          : undefined
      }
    ]
  }
})

const productionOption = computed(() => {
  const colors = palette.value
  const parts = [
    {
      key: 'gold',
      label: t('reports.pureGold'),
      tooltip: t('reports.goldManufacturingValue'),
      pick: (day) => day.gold
    },
    {
      key: 'special',
      label: t('reports.specialGold'),
      tooltip: t('reports.specialGoldValue'),
      pick: specialGold
    },
    { key: 'experience', label: t('reports.experience'), pick: (day) => day.experience },
    { key: 'order', label: t('reports.lmdOrders'), pick: (day) => day.orders }
  ]
  return {
    backgroundColor: 'transparent',
    aria: { enabled: true },
    animationDuration: 700,
    toolbox: chartToolbox(t('reports.dailyProductionTitle')),
    grid: { top: 56, right: 12, bottom: 4, left: 4, containLabel: true },
    legend: {
      top: 0,
      left: 0,
      right: 30,
      icon: 'roundRect',
      itemWidth: 10,
      itemHeight: 10,
      textStyle: { color: colors.axis }
    },
    tooltip: {
      ...tooltipBase(),
      axisPointer: { type: 'shadow', shadowStyle: { color: colors.grid } },
      formatter(params) {
        const day = days.value[params[0]?.dataIndex]
        if (!day) return ''
        return `<div style="font-weight:600;margin-bottom:4px">${day.date}</div>${parts
          .map((part) =>
            tooltipRow(colors[part.key], part.tooltip || part.label, formatCount(part.pick(day)))
          )
          .join('')}`
      }
    },
    xAxis: { type: 'category', data: dates.value, ...axisBase(), splitLine: { show: false } },
    yAxis: { type: 'value', ...axisBase() },
    series: parts.map((part) => ({
      name: part.label,
      type: 'bar',
      stack: part.key === 'gold' || part.key === 'special' ? 'gold' : undefined,
      barMaxWidth: 18,
      color: colors[part.key],
      itemStyle: part.key === 'experience' ? { borderWidth: 1, borderColor: '#c5ac59' } : undefined,
      emphasis: { focus: 'series' },
      data: days.value.map((day, index) => ({
        value: part.pick(day),
        itemStyle: { opacity: index === selectedIndex.value ? 1 : 0.72 }
      }))
    }))
  }
})
const mainChartOption = computed(() =>
  chartView.value === 'production' ? productionOption.value : incomeOption.value
)

const orundumOption = computed(() => {
  const colors = palette.value
  return {
    backgroundColor: 'transparent',
    aria: { enabled: true },
    toolbox: chartToolbox(t('reports.orundum')),
    grid: { top: 16, right: 4, bottom: 4, left: 4, containLabel: true },
    tooltip: {
      ...tooltipBase(),
      axisPointer: { type: 'shadow', shadowStyle: { color: colors.grid } },
      formatter(params) {
        const day = days.value[params[0]?.dataIndex]
        if (!day) return ''
        return `<div style="font-weight:600;margin-bottom:4px">${day.date}</div>
          ${tooltipRow(colors.orundum, t('reports.orundum'), formatCount(day.orundum))}
          ${tooltipRow(colors.axis, t('reports.orundumOrders'), formatCount(day.orundumOrders))}
          ${tooltipRow(colors.axis, t('reports.equivalentPulls'), isReading(day.orundum) ? (day.orundum / ORUNDUM_PER_PULL).toFixed(1) : '—')}`
      }
    },
    xAxis: { type: 'category', data: dates.value, ...axisBase(), splitLine: { show: false } },
    yAxis: { type: 'value', ...axisBase() },
    series: [
      {
        name: t('reports.orundum'),
        type: 'bar',
        barMaxWidth: 22,
        color: colors.orundum,
        itemStyle: { borderRadius: [4, 4, 0, 0] },
        data: days.value.map((day) => day.orundum)
      }
    ]
  }
})

const orderOption = computed(() => {
  const colors = palette.value
  return {
    backgroundColor: 'transparent',
    aria: { enabled: true },
    toolbox: chartToolbox(t('reports.tradingOrders')),
    grid: { top: 48, right: 4, bottom: 4, left: 4, containLabel: true },
    legend: {
      top: 0,
      left: 0,
      right: 30,
      icon: 'roundRect',
      itemWidth: 10,
      itemHeight: 10,
      textStyle: { color: colors.axis }
    },
    tooltip: {
      ...tooltipBase(),
      axisPointer: { type: 'shadow', shadowStyle: { color: colors.grid } },
      formatter(params) {
        const day = days.value[params[0]?.dataIndex]
        if (!day) return ''
        return `<div style="font-weight:600;margin-bottom:4px">${day.date}</div>
          ${tooltipRow(colors.order, t('reports.lmdOrders'), formatCount(day.orders))}
          ${tooltipRow(colors.axis, t('reports.orderCount'), formatCount(day.orderCount))}
          ${tooltipRow(colors.gold, t('reports.lmdPerOrder'), formatCount(day.perOrder))}`
      }
    },
    xAxis: { type: 'category', data: dates.value, ...axisBase(), splitLine: { show: false } },
    yAxis: [
      { type: 'value', ...axisBase() },
      { type: 'value', ...axisBase(), splitLine: { show: false } }
    ],
    series: [
      {
        name: t('reports.lmdOrders'),
        type: 'bar',
        barMaxWidth: 22,
        color: colors.order,
        itemStyle: { borderRadius: [4, 4, 0, 0] },
        data: days.value.map((day) => day.orders)
      },
      {
        name: t('reports.lmdPerOrder'),
        type: 'line',
        yAxisIndex: 1,
        smooth: 0.3,
        symbol: 'circle',
        symbolSize: 5,
        showAllSymbol: true,
        label: lineLabel(formatCount),
        labelLayout: { hideOverlap: true },
        color: colors.gold,
        connectNulls: false,
        data: days.value.map((day) => day.perOrder)
      }
    ]
  }
})

// ---- 逐日明细 ----
const tableRows = computed(() => days.value.slice().reverse())
const bestDate = computed(() => summary.value.best?.date)
// 较前日按全部记录计算，区间第一天也能与更早一天对比。
const changeByDate = computed(
  () =>
    new Map(
      allDays.value.map((day, index) => [
        day.date,
        index ? relativeChange(day.income.total, allDays.value[index - 1].income.total) : null
      ])
    )
)
const detailPanel = ref(null)
function pickRow(date) {
  selectDay(date)
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  detailPanel.value?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'nearest' })
}
function changeClass(date) {
  const change = changeByDate.value.get(date)
  if (!isReading(change) || change === 0) return ''
  return change > 0 ? 'is-up' : 'is-down'
}
const tableColumns = [
  {
    key: 'date',
    get label() {
      return t('reports.date')
    }
  },
  {
    key: 'income',
    get label() {
      return t('reports.income10k')
    }
  },
  {
    key: 'change',
    get label() {
      return t('reports.comparedPrevious')
    }
  },
  {
    key: 'gold',
    get label() {
      return t('reports.goldValue')
    }
  },
  {
    key: 'special',
    get label() {
      return t('reports.specialGold')
    }
  },
  {
    key: 'experience',
    get label() {
      return t('reports.experience')
    }
  },
  {
    key: 'orders',
    get label() {
      return t('reports.lmdOrders')
    }
  },
  {
    key: 'orderCount',
    get label() {
      return t('reports.orderCount')
    }
  },
  {
    key: 'perOrder',
    get label() {
      return t('reports.perOrder')
    }
  },
  {
    key: 'orundum',
    get label() {
      return t('reports.orundum')
    }
  }
]
function cell(day, key) {
  switch (key) {
    case 'date':
      return formatDay(day.date)
    case 'income':
      return formatIncome(day.income.total)
    case 'change':
      return formatPercent(changeByDate.value.get(day.date)) || '—'
    case 'special':
      return day.tequilaGold + day.closureGold
        ? formatCount(day.tequilaGold + day.closureGold)
        : '0'
    default:
      return formatCount(day[key])
  }
}
</script>

<template>
  <PageLayout max-width="1280px">
    <template #header>
      <PageHeader
        >{{ t('reports.baseReportTitle')
        }}<help-text>
          <p>{{ t('reports.baseReportSourceHelp') }}</p>
          <p>{{ t('reports.baseReportDateHelp') }}</p>
          <p>{{ t('reports.baseReportGoldHelp') }}</p>
          <p>{{ t('reports.baseReportRangeHelp') }}</p>
          <p>{{ t('reports.baseReportIncomeHelp') }}</p>
        </help-text>
        <template #actions>
          <div class="report-actions">
            <n-radio-group
              v-model:value="range"
              size="small"
              name="report-range"
              :aria-label="t('reports.reportRange')"
              :disabled="!ready"
            >
              <n-radio-button
                v-for="option in rangeOptions"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}
              </n-radio-button>
            </n-radio-group>
            <n-dropdown
              :options="algorithmOptions"
              placement="bottom-end"
              trigger="click"
              :disabled="!valuation || algorithmBusy"
              @select="selectAlgorithm"
            >
              <n-button secondary size="small" :disabled="!valuation" :loading="algorithmBusy"
                >{{ t('reports.algorithmPrefix') }}{{ algorithmShortLabel }}
              </n-button>
            </n-dropdown>
            <n-button
              quaternary
              circle
              size="small"
              :loading="loading"
              :aria-label="t('reports.refreshBaseReport')"
              :title="t('reports.refresh')"
              @click="load"
            >
              <template #icon><n-icon :component="RefreshOutline" /></template>
            </n-button>
            <SessionLink to="/settings#task-accounts">{{ t('reports.manageIncome') }}</SessionLink>
          </div>
        </template>
      </PageHeader>
    </template>

    <div class="report" :class="{ 'is-dark': isDark }">
      <n-card
        v-if="showCustomAlgorithm"
        size="small"
        :title="t('reports.customCoefficients')"
        class="custom-card"
      >
        <n-space align="center" wrap>
          <label v-for="field in customFields" :key="field.key" class="custom-field">
            <span>{{ field.label }}</span>
            <n-input-number
              v-model:value="customRatios[field.key]"
              size="small"
              :min="field.key === 'experience' ? 0.000001 : 0"
              :max="1000"
              :disabled="algorithmBusy"
              :show-button="false"
            />
          </label>
          <n-button size="small" :disabled="algorithmBusy" @click="showCustomAlgorithm = false">{{
            t('reports.cancel')
          }}</n-button>
          <n-button
            size="small"
            type="primary"
            :loading="algorithmBusy"
            @click="saveAlgorithm(-1, customRatios)"
            >{{ t('reports.saveCustom') }}</n-button
          >
        </n-space>
      </n-card>

      <n-alert v-if="algorithmError" type="error" closable @close="algorithmError = ''">
        {{ reportErrorMessage(algorithmError) }}
      </n-alert>
      <n-alert v-if="loadError" type="error" :title="t('reports.readFailed')">
        <p>{{ reportErrorMessage(loadError) }}</p>
        <p>{{ t('reports.readFailedHelp') }}</p>
        <n-button size="small" secondary class="retry" @click="load">{{
          t('reports.retry')
        }}</n-button>
      </n-alert>
      <n-alert v-if="partialWarning" type="warning">{{ partialWarning }}</n-alert>

      <div
        v-if="loading && !hasData"
        class="skeleton"
        aria-busy="true"
        :aria-label="t('reports.loadingBaseReport')"
      >
        <n-skeleton class="skeleton__overview" />
        <div class="skeleton__grid">
          <n-skeleton class="skeleton__chart" />
          <n-skeleton class="skeleton__chart" />
        </div>
      </div>

      <section v-else-if="ready && !hasData" class="empty reveal">
        <h2>{{ t('reports.noBaseReport') }}</h2>
        <p>{{ t('reports.enableBaseReportHelp') }}</p>
        <p>{{ t('reports.baseReportAfterRead') }}</p>
      </section>

      <template v-else-if="hasData">
        <section class="overview reveal" :aria-busy="loading">
          <div class="overview__day">
            <div class="overview__label">
              {{ formatDay(selectedDay.date) }}{{ t('reports.income')
              }}<span v-if="selectedDay.date === summary.latest.date" class="tag">{{
                t('reports.latestRecord')
              }}</span>
            </div>
            <div class="overview__value">
              <span class="overview__number">{{ formatIncome(animatedIncome) }}</span>
              <span class="overview__unit">{{ t('reports.tenThousandUnit') }}</span>
              <span
                v-if="isReading(incomeCompare.change)"
                class="delta delta--pill"
                :class="deltaClass(incomeCompare)"
              >
                <n-icon
                  :component="incomeCompare.delta >= 0 ? TrendingUpOutline : TrendingDownOutline"
                  aria-hidden="true"
                />
                {{ formatPercent(incomeCompare.change) }}
              </span>
            </div>
            <p class="overview__caption">
              {{ t('reports.usingPrefix') }}{{ algorithmShortLabel
              }}{{ t('reports.calculatedSuffix')
              }}<template v-if="isReading(incomeCompare.delta)"
                >{{ t('reports.comparedWithPrefix') }}{{ formatDay(previousDay.date) }}
                {{ deltaText(incomeCompare, 2) }}{{ t('reports.tenThousandUnit') }}</template
              ><template v-if="selectedDay.income.partial"
                >；{{ incomeNote(selectedDay.income) }}</template
              >
            </p>
          </div>
          <dl class="overview__facts">
            <div>
              <dt>{{ t('reports.dailyIncome') }}</dt>
              <dd>
                {{ formatIncome(summary.averageIncome)
                }}<small>{{ t('reports.tenThousandUnit') }}</small>
              </dd>
            </div>
            <div>
              <dt>{{ t('reports.totalIncome') }}</dt>
              <dd>
                {{ formatIncome(summary.totalIncome, 1)
                }}<small>{{ t('reports.tenThousandUnit') }}</small>
              </dd>
            </div>
            <div v-if="summary.best">
              <dt>
                <n-icon :component="TrophyOutline" aria-hidden="true" />{{
                  t('reports.bestIncome')
                }}
              </dt>
              <dd>
                <button type="button" class="link" @click="selectDay(summary.best.date)">
                  {{ formatDay(summary.best.date) }}
                </button>
                <span class="overview__best"
                  >{{ formatIncome(summary.best.income.total)
                  }}{{ t('reports.tenThousandUnit') }}</span
                >
              </dd>
            </div>
          </dl>
        </section>

        <div class="main-grid">
          <section class="panel reveal" style="--delay: 60ms">
            <header class="panel__head panel__head--chart">
              <div>
                <h2>
                  {{
                    chartView === 'production'
                      ? t('reports.dailyProductionTitle')
                      : t('reports.dailyIncomeTitle')
                  }}
                </h2>
                <p v-if="chartView === 'income'">
                  {{ t('reports.usingPrefix') }}{{ algorithmShortLabel
                  }}{{ t('reports.incomeChartHelpSuffix') }}
                </p>
                <p v-else>{{ t('reports.productionChartHelp') }}</p>
              </div>
              <n-radio-group
                v-model:value="chartView"
                size="small"
                name="report-chart"
                :aria-label="t('reports.chartContent')"
              >
                <n-radio-button value="income">{{ t('reports.weightedIncome') }}</n-radio-button>
                <n-radio-button value="production">{{
                  t('reports.baseProduction')
                }}</n-radio-button>
              </n-radio-group>
            </header>
            <v-chart
              class="chart chart--main"
              :option="mainChartOption"
              autoresize
              @click="onChartClick"
            />
          </section>

          <section
            ref="detailPanel"
            class="panel day reveal"
            style="--delay: 120ms"
            aria-labelledby="report-day-title"
          >
            <header class="day__head">
              <n-button
                quaternary
                circle
                size="small"
                :disabled="selectedIndex <= 0"
                :aria-label="t('reports.previousRecord')"
                @click="stepDay(-1)"
              >
                <template #icon><n-icon :component="ChevronBackOutline" /></template>
              </n-button>
              <div class="day__title">
                <h2 id="report-day-title">{{ formatDay(selectedDay.date) }}</h2>
                <p>
                  {{
                    previousDay
                      ? t('reports.compareDate', { date: formatDay(previousDay.date) })
                      : t('reports.noEarlierRecord')
                  }}
                </p>
              </div>
              <n-button
                quaternary
                circle
                size="small"
                :disabled="selectedIndex >= days.length - 1"
                :aria-label="t('reports.nextRecord')"
                @click="stepDay(1)"
              >
                <template #icon><n-icon :component="ChevronForwardOutline" /></template>
              </n-button>
            </header>

            <ul class="items" :aria-label="t('reports.dailyProduction')">
              <li v-for="row in detailRows" :key="row.key" class="item">
                <span class="item__icon">
                  <img
                    v-if="!failedIcons.has(row.icon)"
                    :src="`/depot/${encodeURIComponent(row.icon)}.webp`"
                    alt=""
                    @error="failedIcons.add(row.icon)"
                  />
                </span>
                <span class="item__body">
                  <span class="item__label">{{ row.label }}</span>
                  <span v-if="row.note" class="item__note">{{ row.note }}</span>
                </span>
                <span class="item__figures">
                  <strong>{{ formatCount(row.value) }}</strong>
                  <span v-if="deltaText(row)" class="delta" :class="deltaClass(row)">
                    {{ deltaText(row) }}
                  </span>
                </span>
              </li>
            </ul>

            <div class="split">
              <div class="split__head">
                <h3>{{ t('reports.incomeBreakdown') }}</h3>
                <span v-if="previousDay" class="split__legend">
                  <i class="is-day" aria-hidden="true" />{{ t('reports.currentDay')
                  }}<i class="is-base" aria-hidden="true" />{{ t('reports.previousReading') }}</span
                >
              </div>
              <ul>
                <li v-for="row in incomeRows" :key="row.key" class="split__row">
                  <span class="split__label">{{ row.label }}</span>
                  <span class="split__bars" aria-hidden="true">
                    <span
                      class="split__bar"
                      :style="{ width: `${row.width}%`, background: row.color }"
                    />
                    <span
                      v-if="previousDay"
                      class="split__bar split__bar--base"
                      :style="{ width: `${row.baseWidth}%` }"
                    />
                  </span>
                  <span class="split__value">{{ formatIncome(row.value, 3) }}</span>
                  <span class="delta" :class="deltaClass(row)">{{ deltaText(row, 3) }}</span>
                </li>
              </ul>
              <div class="split__row split__row--total">
                <span class="split__label">{{ t('reports.total') }}</span>
                <span />
                <span class="split__value">{{ formatIncome(incomeCompare.value, 3) }}</span>
                <span class="delta" :class="deltaClass(incomeCompare)">
                  {{ deltaText(incomeCompare, 3) }}
                </span>
              </div>
            </div>
          </section>
        </div>

        <div class="panels">
          <section class="panel reveal" style="--delay: 180ms">
            <header class="panel__head">
              <div>
                <h2>{{ t('reports.tradingOrders') }}</h2>
                <p>{{ t('reports.tradingOrdersSubtitle') }}</p>
              </div>
              <span class="panel__stat"
                >{{ t('reports.averageOrder') }}<strong>{{ formatCount(summary.perOrder) }}</strong
                >{{ t('reports.lmd') }}</span
              >
            </header>
            <v-chart class="chart" :option="orderOption" autoresize @click="onChartClick" />
          </section>
          <section class="panel reveal" style="--delay: 220ms">
            <header class="panel__head">
              <div>
                <h2>{{ t('reports.orundum') }}</h2>
                <p>{{ t('reports.dailyOrundum') }}</p>
              </div>
              <span v-if="isReading(summary.pulls)" class="panel__stat"
                >{{ t('reports.equivalentAboutPrefix')
                }}<strong>{{ summary.pulls.toFixed(1) }}</strong
                >{{ t('reports.pullsUnit') }}</span
              >
            </header>
            <v-chart
              v-if="isReading(summary.orundum)"
              class="chart"
              :option="orundumOption"
              autoresize
              @click="onChartClick"
            />
            <div v-else class="panel__empty">{{ t('reports.noOrundumData') }}</div>
          </section>
        </div>

        <section class="panel reveal" style="--delay: 260ms">
          <header class="panel__head">
            <div>
              <h2>{{ t('reports.dailyDetails') }}</h2>
              <p>
                {{ t('reports.dailyDetailsHelp')
                }}<template v-if="summary.missingDays"
                  >{{ t('reports.partialDaysPrefix') }}{{ summary.missingDays
                  }}{{ t('reports.partialDaysSuffix') }}</template
                >
              </p>
            </div>
          </header>
          <div
            class="table-wrap"
            tabindex="0"
            role="region"
            :aria-label="t('reports.dailyDetails')"
          >
            <table class="table">
              <thead>
                <tr>
                  <th v-for="column in tableColumns" :key="column.key" scope="col">
                    {{ column.label }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="day in tableRows"
                  :key="day.date"
                  tabindex="0"
                  :class="{ 'is-selected': day.date === selectedDay.date }"
                  :aria-current="day.date === selectedDay.date ? 'true' : undefined"
                  @click="pickRow(day.date)"
                  @keydown.enter.prevent="pickRow(day.date)"
                  @keydown.space.prevent="pickRow(day.date)"
                >
                  <td
                    v-for="column in tableColumns"
                    :key="column.key"
                    :class="[`col-${column.key}`, column.key === 'change' && changeClass(day.date)]"
                  >
                    <template v-if="column.key === 'date'">
                      {{ cell(day, 'date') }}
                      <n-icon
                        v-if="day.date === bestDate"
                        :component="TrophyOutline"
                        class="best-mark"
                        :aria-label="t('reports.bestIncome')"
                      />
                    </template>
                    <template v-else>{{ cell(day, column.key) }}</template>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </template>
    </div>
  </PageLayout>
</template>

<style scoped>
.report {
  --ink: var(--mower-text, #1f2225);
  --muted: var(--mower-text-muted, #76808a);
  --line: var(--mower-divider, rgba(31, 34, 37, 0.09));
  --surface: var(--mower-surface, #fff);
  --accent: var(--mower-primary, #18a058);
  --up: var(--mower-success-text, #18a058);
  --down: var(--mower-error-text, #d03050);
  display: flex;
  flex-direction: column;
  gap: 16px;
  color: var(--ink);
  font-variant-numeric: tabular-nums;
}

.custom-card {
  max-width: 640px;
}

.custom-field {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.custom-field .n-input-number {
  width: 110px;
}

.retry {
  margin-top: 8px;
}

.reveal {
  animation: report-rise 0.4s ease-out both;
  animation-delay: var(--delay, 0ms);
}

@keyframes report-rise {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
}

.overview,
.panel,
.empty {
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--surface);
}

.report-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

:deep(.page-header__actions) {
  min-width: 0;
  max-width: 100%;
}

/* ---- 概览 ---- */
.overview {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr);
  align-items: center;
  gap: 24px;
  padding: 20px 24px;
}

.overview__label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--muted);
}

.tag {
  padding: 0 6px;
  border-radius: 4px;
  font-size: 11px;
  line-height: 18px;
  color: var(--muted);
  background: var(--mower-control-hover, rgba(0, 0, 0, 0.05));
}

.overview__value {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-top: 6px;
}

.overview__number {
  font-size: 40px;
  font-weight: 650;
  line-height: 1.1;
  letter-spacing: -0.5px;
}

.overview__unit {
  font-size: 15px;
  color: var(--muted);
}

.overview__caption {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--muted);
}

.overview__facts {
  display: grid;
  gap: 10px;
  margin: 0;
  padding-left: 24px;
  border-left: 1px solid var(--line);
}

.overview__facts > div {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.overview__facts dt {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--muted);
}

.overview__facts dd {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.overview__facts small {
  margin-left: 2px;
  font-size: 12px;
  font-weight: 400;
  color: var(--muted);
}

.overview__best {
  margin-left: 8px;
}

.link {
  padding: 0;
  border: none;
  background: none;
  font: inherit;
  color: var(--accent);
  cursor: pointer;
}

.link:hover {
  text-decoration: underline;
}

.link:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
  border-radius: 2px;
}

/* ---- 涨跌 ---- */
.delta {
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
}

.delta.is-up {
  color: var(--up);
}

.delta.is-down {
  color: var(--down);
}

.delta.is-flat {
  color: var(--muted);
}

.delta--pill {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  align-self: center;
  margin-left: 6px;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 13px;
}

.delta--pill.is-up {
  background: var(--mower-success-block, rgba(24, 160, 88, 0.12));
}

.delta--pill.is-down {
  background: var(--mower-error-block, rgba(208, 48, 80, 0.12));
}

/* ---- 面板 ---- */
.main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.65fr) minmax(320px, 1fr);
  gap: 16px;
  align-items: start;
}

.panels {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.panel {
  padding: 18px 20px;
  min-width: 0;
}

.panel__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.panel__head--chart {
  flex-wrap: wrap;
}

.panel h2,
.empty h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.panel__head p {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--muted);
}

.panel__stat {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--muted);
}

.panel__stat strong {
  font-size: 15px;
  color: var(--ink);
}

.panel__empty {
  display: grid;
  place-items: center;
  height: 240px;
  font-size: 13px;
  color: var(--muted);
}

.chart {
  height: 240px;
}

.chart--main {
  height: 420px;
}

/* ---- 单日详情 ---- */
.day {
  scroll-margin-top: 16px;
}

.day__head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.day__title {
  flex: 1;
  text-align: center;
}

.day__title p {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--muted);
}

.items {
  margin: 0;
  padding: 0;
  list-style: none;
}

.item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 0;
  border-top: 1px solid var(--line);
}

.item:first-child {
  border-top: none;
}

.item__icon {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 34px;
  height: 34px;
  border-radius: 8px;
  background: var(--mower-control-hover, rgba(0, 0, 0, 0.04));
}

.item__icon img {
  width: 28px;
  height: 28px;
  object-fit: contain;
}

.item__body {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
}

.item__label {
  font-size: 13px;
}

.item__note {
  overflow: hidden;
  font-size: 11px;
  color: var(--muted);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item__figures {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.item__figures strong {
  font-size: 15px;
  font-weight: 600;
}

.split {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
}

.split__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.split h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
}

.split__legend {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--muted);
}

.split__legend i {
  width: 10px;
  height: 4px;
  border-radius: 2px;
  margin-left: 6px;
  background: var(--muted);
}

.split__legend i.is-day {
  background: var(--accent);
}

.split__legend i.is-base {
  opacity: 0.55;
}

.split ul {
  margin: 0;
  padding: 0;
  list-style: none;
}

.split__row {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr) 52px 52px;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 12px;
}

.split__label {
  color: var(--muted);
}

.split__bars {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.split__bar {
  display: block;
  min-width: 1px;
  height: 6px;
  border-radius: 3px;
  transition: width 0.3s ease;
}

.split__bar--base {
  height: 3px;
  background: var(--muted);
  opacity: 0.55;
}

.split__value,
.split__row .delta {
  text-align: right;
}

.split__row--total {
  margin-top: 4px;
  padding-top: 8px;
  border-top: 1px dashed var(--line);
  font-weight: 600;
}

.split__row--total .split__label {
  color: var(--ink);
}

/* ---- 逐日明细 ---- */
.table-wrap {
  max-height: 440px;
  overflow: auto;
  border-radius: 8px;
  border: 1px solid var(--line);
}

.table-wrap:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  white-space: nowrap;
}

.table th {
  position: sticky;
  top: 0;
  z-index: 1;
  padding: 9px 14px;
  text-align: right;
  font-size: 12px;
  font-weight: 600;
  color: var(--muted);
  background: var(--surface);
  box-shadow: inset 0 -1px var(--line);
}

.table td {
  padding: 8px 14px;
  text-align: right;
  border-top: 1px solid var(--line);
}

.table tbody tr {
  cursor: pointer;
}

.table tbody tr:first-child td {
  border-top: none;
}

.table th:first-child,
.table td:first-child {
  text-align: left;
}

.table tbody tr:hover td {
  background: var(--mower-control-hover, rgba(0, 0, 0, 0.03));
}

.table tbody tr:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}

.table tbody tr.is-selected td {
  background: color-mix(in srgb, var(--accent) 10%, transparent);
}

.table .col-income {
  font-weight: 600;
}

.table .col-change {
  color: var(--muted);
}

.table .col-change.is-up {
  color: var(--up);
}

.table .col-change.is-down {
  color: var(--down);
}

.best-mark {
  margin-left: 4px;
  vertical-align: -2px;
  color: var(--mower-warning-text, #d98a1c);
}

/* ---- 空状态与骨架 ---- */
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 48px 24px;
  text-align: center;
}

.empty p {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--muted);
}

.skeleton {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.skeleton__overview {
  height: 128px;
  border-radius: 12px;
}

.skeleton__grid {
  display: grid;
  grid-template-columns: minmax(0, 1.65fr) minmax(320px, 1fr);
  gap: 16px;
}

.skeleton__chart {
  height: 480px;
  border-radius: 12px;
}

@media (max-width: 1100px) {
  .overview {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }

  .main-grid,
  .skeleton__grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .chart--main {
    height: 340px;
  }
}

@media (max-width: 860px) {
  .panels {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 640px) {
  .overview {
    grid-template-columns: minmax(0, 1fr);
    gap: 16px;
    padding: 16px;
  }

  .overview__facts {
    padding: 12px 0 0;
    border-left: none;
    border-top: 1px solid var(--line);
  }

  .overview__number {
    font-size: 34px;
  }

  .panel {
    padding: 14px;
  }

  .chart--main {
    height: 280px;
  }

  .chart {
    height: 220px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .reveal {
    animation: none;
  }

  .split__bar {
    transition: none;
  }
}
</style>
