<template>
  <div class="mood-page" :class="{ simulation: !!simulation }">
    <h1 v-if="!simulation" class="page-title">干员心情折线表</h1>
    <div class="mood-page-tools">
      <span>{{
        simulation
          ? '按排班绑组显示；自定义观察表可跨组选择干员。↓消耗 ↑恢复，单位：点/小时。'
          : '拖动卡片调整顺序；工休比报表自动同步。↓消耗 ↑恢复，单位：点/小时。'
      }}</span>
      <n-button type="primary" secondary @click="newView">＋ 新建自定义观察表</n-button>
    </div>
    <p v-if="historyLimited" class="history-note">
      当前历史查询接口不可用：自选表暂时只能组合默认报表中已有的干员。完整数据库查询需启用只读历史服务。
    </p>
    <p v-if="loadError" role="alert" class="history-note">{{ loadError }}</p>
    <p v-if="formError" role="alert" class="history-note">{{ formError }}</p>

    <mood-card-grid :groups="orderedReportData" @reorder="reorderCards">
      <template #default="{ group }">
        <header class="group-head">
          <h2 :title="group.groupName">{{ group.groupName }}</h2>
          <div class="group-head-actions">
            <n-button v-if="group.isCustom" size="tiny" secondary @click="editView(group.customId)">
              编辑
            </n-button>
            <n-button
              size="tiny"
              secondary
              :aria-label="'全屏查看' + group.groupName"
              @click="fullscreenKey = group.boardKey"
            >
              全屏
            </n-button>
          </div>
        </header>
        <div v-if="group.isCustom" class="observation-description">
          自选观察表 · {{ group.operators.length }} 位干员
          <span v-if="group.missing.length" class="observation-missing">
            · {{ group.missing.join('、') }} {{ simulation ? '暂无演算记录' : '暂无历史' }}
          </span>
        </div>
        <div class="card-controls">
          <span>点击彩色标签可显隐曲线</span>
          <n-button size="tiny" secondary @click="setGroupVisibility(group.boardKey, true)">
            显示全部
          </n-button>
          <n-button size="tiny" secondary @click="setGroupVisibility(group.boardKey, false)">
            隐藏全部
          </n-button>
        </div>
        <mood-rate-legend
          :group-name="group.groupName"
          :entries="rateEntries.get(group.boardKey) ?? []"
          @toggle="toggleLine(group.boardKey, $event)"
        />
        <div class="line-outer-container">
          <div v-if="group.moodData.datasets.length" class="line-inner-container">
            <MoodLineChart
              :key="group.boardKey"
              :ref="(instance) => setChartRef(group.boardKey, instance)"
              :data="group.moodData"
              :options="effectiveChartOptions"
              :plugins="simulation ? [samplingBoundary] : []"
            />
          </div>
          <div v-else class="no-history">
            {{
              simulation
                ? '暂无可绘制的演算心情记录，可编辑自定义观察表选择干员。'
                : '暂无可绘制的心情记录，等待 Mower 采样后会自动显示。'
            }}
          </div>
        </div>
      </template>
    </mood-card-grid>

    <n-modal
      :show="!!fullscreenGroup"
      preset="card"
      :title="fullscreenGroup?.groupName || '心情曲线'"
      style="width: min(96vw, 1600px); height: 92vh"
      content-style="display:flex; flex-direction:column; min-height:0"
      @update:show="
        (show) => {
          if (!show) fullscreenKey = ''
        }
      "
    >
      <template v-if="fullscreenGroup">
        <mood-rate-legend
          :group-name="fullscreenGroup.groupName"
          :entries="rateEntries.get(fullscreenGroup.boardKey) ?? []"
          @toggle="toggleLine(fullscreenGroup.boardKey, $event)"
        />
        <div class="fullscreen-chart">
          <MoodLineChart
            v-if="fullscreenGroup.moodData.datasets.length"
            :key="fullscreenGroup.boardKey"
            :data="fullscreenGroup.moodData"
            :options="effectiveChartOptions"
            :plugins="simulation ? [samplingBoundary] : []"
          />
          <p v-else class="no-history">{{ simulation ? '暂无演算记录' : '暂无历史记录' }}</p>
        </div>
      </template>
    </n-modal>
    <mood-observation-editor
      :simulation="!!simulation"
      v-model:show="editorShow"
      :view="editingView"
      :catalog="fullCatalog"
      @save="saveView"
      @remove="deleteView"
    />
  </div>
</template>

<script setup>
import { computed, reactive, ref, onMounted, watch } from 'vue'
import MoodLineChart from '@/components/MoodLineChart.vue'
import 'chartjs-adapter-luxon'
import {
  CategoryScale,
  TimeScale,
  TimeSeriesScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  Colors,
  LineElement,
  PointElement,
  Title,
  Tooltip
} from 'chart.js'
import MoodCardGrid from '@/components/MoodCardGrid.vue'
import MoodRateLegend from '@/components/MoodRateLegend.vue'
import MoodObservationEditor from '@/components/MoodObservationEditor.vue'
import { createMoodBoard, useMoodBoardStore } from '@/stores/mood_board'
import { useRecordStore } from '@/stores/record'
import { moodStroke } from '@/utils/mood_colors'
import { buildObservationGroups, mergeOperatorCatalog } from '@/utils/mood_observation'
import {
  calculateMoodIntervals,
  describeMoodEvent,
  describeMoodInterval,
  setAllMoodDatasetsVisible,
  summarizeMoodRates
} from '@/utils/mood_rate'

ChartJS.register(
  CategoryScale,
  LinearScale,
  TimeScale,
  TimeSeriesScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Colors
)

const props = defineProps({ simulation: { type: Object, default: null } })
const board = props.simulation ? reactive(createMoodBoard(() => null)) : useMoodBoardStore()
const { getMoodRatios, getMoodCatalog, getMoodSeries } = useRecordStore()
const reportData = ref([])
const catalog = ref([])
const fetchedSeries = ref([])
const historyLimited = ref(false)
const loadError = ref('')
const formError = ref('')
const editorShow = ref(false)
const editingId = ref('')
const fullscreenKey = ref('')
const hiddenLines = ref({})
const chartRefs = new Map()
const chartIntervalCache = new WeakMap()

const fullCatalog = computed(() => mergeOperatorCatalog(catalog.value, reportData.value))
const editingView = computed(() => board.views.find((view) => view.id === editingId.value) || null)
const fullscreenGroup = computed(
  () => orderedReportData.value.find((group) => group.boardKey === fullscreenKey.value) || null
)
const customGroups = computed(() =>
  buildObservationGroups(board.views, reportData.value, fetchedSeries.value)
)
const orderedReportData = computed(() => {
  const custom = customGroups.value
  const original = reportData.value.map((group) => ({ ...group, boardKey: group.groupName }))
  // Newly created observation cards lead unless the user has dragged them elsewhere.
  const manual = board.groupOrder
  const preferred = [
    ...custom.map((group) => group.boardKey).filter((key) => !manual.includes(key)),
    ...manual
  ]
  const rank = new Map(preferred.map((key, index) => [key, index]))
  const groups = [...custom, ...original].sort(
    (a, b) => (rank.get(a.boardKey) ?? Infinity) - (rank.get(b.boardKey) ?? Infinity)
  )
  return groups.map((group) => {
    const key = group.boardKey
    const hidden = hiddenLines.value[key] || []
    return {
      ...group,
      moodData: {
        ...group.moodData,
        datasets: (group.moodData?.datasets || []).map((dataset, index) => {
          const color = moodStroke(index)
          return {
            ...dataset,
            backgroundColor: color,
            borderColor: color,
            pointBackgroundColor: color,
            hidden: hidden.includes(dataset.label),
            tension: props.simulation ? 0 : 0.14,
            spanGaps: false,
            borderWidth: 2,
            pointRadius: props.simulation ? 0 : 2
          }
        })
      }
    }
  })
})
const rateEntries = computed(
  () =>
    new Map(
      orderedReportData.value.map((group) => [
        group.boardKey,
        group.moodData.datasets.map((dataset, index) => ({
          name: dataset.label,
          color: moodStroke(index),
          visible: !(hiddenLines.value[group.boardKey] || []).includes(dataset.label),
          ...summarizeMoodRates(dataset.data)
        }))
      ])
    )
)

function reorderCards(source, target) {
  board.reorder(orderedReportData.value, source, target)
}

function setChartRef(key, instance) {
  if (instance) chartRefs.set(key, instance)
  else chartRefs.delete(key)
}

function setGroupVisibility(key, visible) {
  const group = orderedReportData.value.find((item) => item.boardKey === key)
  if (!group) return
  hiddenLines.value = {
    ...hiddenLines.value,
    [key]: visible ? [] : group.moodData.datasets.map((dataset) => dataset.label)
  }
  setAllMoodDatasetsVisible(chartRefs.get(key)?.chart, visible)
}

function toggleLine(key, index) {
  const group = orderedReportData.value.find((item) => item.boardKey === key)
  const name = group?.moodData.datasets[index]?.label
  if (!name) return
  const next = new Set(hiddenLines.value[key] || [])
  if (next.has(name)) next.delete(name)
  else next.add(name)
  hiddenLines.value = { ...hiddenLines.value, [key]: [...next] }
  const chart = chartRefs.get(key)?.chart
  if (chart) {
    chart.setDatasetVisibility(index, !next.has(name))
    chart.update('none')
  }
}

function newView() {
  formError.value = ''
  editingId.value = ''
  editorShow.value = true
}
function editView(id) {
  formError.value = ''
  editingId.value = id
  editorShow.value = true
}
function saveView(view) {
  const id = board.upsertView(view, view.id)
  if (!id) {
    formError.value = '保存失败：名称不可重复，每张表最多 16 位干员，最多 12 张自选表。'
    return
  }
  editorShow.value = false
  editingId.value = ''
  formError.value = ''
}
function deleteView(id) {
  if (!props.simulation && !window.confirm('确定删除这张自定义观察表？不会删除任何历史记录。'))
    return
  board.removeView(id)
  editorShow.value = false
  editingId.value = ''
}

let requestNumber = 0
async function refreshSeries() {
  if (props.simulation) return
  const id = ++requestNumber
  const names = [...new Set(board.views.flatMap((view) => view.operators))].slice(0, 192)
  if (!names.length) {
    fetchedSeries.value = []
    return
  }
  const combined = []
  try {
    // Backend enforces a maximum of sixteen names per request.
    for (let index = 0; index < names.length; index += 16) {
      const batch = await getMoodSeries(names.slice(index, index + 16))
      if (id !== requestNumber) return
      combined.push(...batch)
    }
    fetchedSeries.value = combined
  } catch {
    if (id === requestNumber) {
      historyLimited.value = true
      fetchedSeries.value = []
    }
  }
}
watch(
  () => JSON.stringify(board.views.map((view) => view.operators)),
  () => refreshSeries()
)

onMounted(async () => {
  if (props.simulation) return
  board.load()
  try {
    reportData.value = await getMoodRatios()
  } catch {
    loadError.value = '心情报表读取失败，请检查本地 Mower 后端。'
    return
  }
  try {
    catalog.value = await getMoodCatalog()
  } catch {
    historyLimited.value = true
  }
  await refreshSeries()
})

watch(
  () => props.simulation,
  (data) => {
    if (!data) return
    reportData.value = data.groups
    catalog.value = data.catalog
    fetchedSeries.value = data.series
    hiddenLines.value = {}
  },
  { immediate: true }
)

const samplingBoundary = {
  id: 'simulation-sampling-boundary',
  afterDraw(chart) {
    if (!props.simulation?.warmupHours) return
    const x = chart.scales.x.getPixelForValue(props.simulation.warmupHours * 3600000)
    const { top, bottom, left, right } = chart.chartArea
    if (x < left || x > right) return
    const ctx = chart.ctx
    ctx.save()
    ctx.strokeStyle = '#49996d'
    ctx.setLineDash([4, 4])
    ctx.beginPath()
    ctx.moveTo(x, top)
    ctx.lineTo(x, bottom)
    ctx.stroke()
    ctx.fillStyle = '#49996d'
    ctx.fillText('采样开始', Math.min(x + 4, right - 52), top + 12)
    ctx.restore()
  }
}

function getMoodInterval(points, index) {
  if (!Array.isArray(points)) return null
  if (!chartIntervalCache.has(points)) {
    chartIntervalCache.set(points, calculateMoodIntervals(points))
  }
  return chartIntervalCache.get(points)[index] || null
}

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  animation: false,
  parsing: true,
  scales: {
    x: { type: 'time', time: { unit: 'day' }, ticks: { maxTicksLimit: 7 } },
    y: { beginAtZero: true, suggestedMax: 24, ticks: { stepSize: 4 } }
  },
  plugins: {
    // Other chart routes must not enable per-point text in high-density mood curves.
    datalabels: { display: false },
    legend: { display: false },
    tooltip: {
      backgroundColor: 'rgba(15,15,20,.92)',
      titleColor: '#fff',
      bodyColor: '#fff',
      callbacks: {
        afterLabel: (context) => {
          const lines = []
          const event = describeMoodEvent(context.raw, context.dataset?.label)
          if (event) lines.push(event)
          const interval = getMoodInterval(context.dataset?.data, context.dataIndex)
          if (interval) lines.push(describeMoodInterval(interval))
          else if (context.raw?.moodEvent) lines.push('特殊事件点不计入常规速率')
          return lines
        }
      }
    }
  }
}
const effectiveChartOptions = computed(() => {
  if (!props.simulation) return chartOptions
  return {
    ...chartOptions,
    scales: {
      ...chartOptions.scales,
      x: {
        type: 'linear',
        min: 0,
        title: { display: true, text: '演算天数（含预热）' },
        ticks: { maxTicksLimit: 7, callback: (value) => Number((value / 86400000).toFixed(2)) }
      }
    },
    plugins: {
      ...chartOptions.plugins,
      tooltip: {
        ...chartOptions.plugins.tooltip,
        callbacks: {
          ...chartOptions.plugins.tooltip.callbacks,
          title: (items) => `演算第 ${Number((items[0]?.parsed.x / 86400000).toFixed(3))} 天`,
          label: (context) => `${context.dataset.label}：${Number(context.parsed.y.toFixed(2))}`
        }
      }
    }
  }
})
</script>

<style scoped>
.simulation :deep(.mood-card-grid) {
  grid-template-columns: minmax(0, 1fr);
}

.mood-page {
  min-width: 0;
  padding: 4px 12px 20px;
}
.page-title {
  text-align: center;
  font-size: 24px;
  margin: 6px 0 12px;
}
.mood-page-tools {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 9px 18px;
  flex-wrap: wrap;
  font-size: 12px;
  opacity: 0.86;
  margin: 0 auto 14px;
}
.history-note {
  text-align: center;
  font-size: 12px;
  color: #b07b18;
  padding: 5px;
}
.group-head {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding-left: 28px;
  min-height: 33px;
}
.group-head h2 {
  font-size: 18px;
  text-align: center;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  margin: 0;
}
.group-head-actions {
  display: flex;
  flex: 0 0 auto;
}
.observation-description {
  text-align: center;
  font-size: 11px;
  opacity: 0.72;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.observation-missing {
  color: #b77a26;
}
.card-controls {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  align-items: center;
  gap: 5px;
  font-size: 10px;
  padding: 3px 0 2px;
}
.card-controls span {
  opacity: 0.7;
}
.line-outer-container {
  flex: 1;
  min-height: 130px;
  overflow-x: auto;
  overflow-y: hidden;
  min-height: 0;
  margin-top: 4px;
}
.line-inner-container {
  box-sizing: border-box;
  height: 100%;
  padding: 0 3px 12px;
  min-width: 100%;
}
.fullscreen-chart {
  flex: 1;
  min-height: 0;
  height: 100%;
  overflow: hidden;
}
.fullscreen-chart :deep(canvas),
.line-inner-container :deep(canvas) {
  max-height: 100%;
}
.no-history {
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 12px;
  height: 100%;
  font-size: 12px;
  opacity: 0.66;
}
@media (max-width: 450px) {
  .mood-page {
    padding: 3px 5px 12px;
  }
  .group-head h2 {
    font-size: 16px;
  }
}
</style>
