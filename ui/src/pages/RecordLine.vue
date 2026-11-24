<template>
  <div class="mood-page">
    <h1 class="page-title">干员心情折线表</h1>
    <div class="mood-page-tools">
      <span>拖动卡片调整顺序；工休比报表自动同步。↓消耗 ↑恢复，单位：点/小时。</span>
      <n-button type="primary" secondary @click="newView">＋ 新建自定义观察表</n-button>
      <n-button v-if="board.hiddenGroups.length" secondary @click="board.restoreGroups">
        还原隐藏窗口（{{ board.hiddenGroups.length }}）
      </n-button>
    </div>
    <p v-if="historyLimited || catalogLimited" class="history-note">
      当前历史查询接口不可用：自选表暂时只能组合默认报表中已有的干员。完整数据库查询需启用只读历史服务。
    </p>
    <p v-if="loadError" role="alert" class="history-note">{{ loadError }}</p>
    <p v-if="board.saveError" role="alert" class="history-note">{{ board.saveError }}</p>
    <p v-if="formError" role="alert" class="history-note">{{ formError }}</p>

    <mood-card-grid
      :groups="orderedReportData"
      :loading="loading"
      shape-key="record-line"
      :load-failed="!!loadError"
      loading-label="正在读取心情记录"
      @reorder="reorderCards"
    >
      <!-- 读取中的卡片：按钮和说明照常显示，标题、图例和坐标轴的刻度先占位，
           折线图只画出与图表相同位置的横向网格线。 -->
      <template #placeholder="{ operators }">
        <header class="group-head">
          <h2><span class="skeleton-bone skeleton-text" style="--skeleton-w: 4.5em" /></h2>
          <div class="group-head-actions">
            <n-button size="tiny" secondary>隐藏</n-button>
            <n-button size="tiny" secondary>全屏</n-button>
          </div>
        </header>
        <div class="card-controls">
          <span>点击彩色标签可显隐曲线</span>
          <n-button size="tiny" secondary>显示全部</n-button>
          <n-button size="tiny" secondary>隐藏全部</n-button>
          <n-button size="tiny" secondary>↔</n-button>
        </div>
        <mood-rate-legend :placeholder="operators" />
        <div class="line-outer-container">
          <div class="line-inner-container">
            <div class="chart-placeholder">
              <span class="chart-placeholder__grid" />
              <span
                v-for="tick in 7"
                :key="'y' + tick"
                class="skeleton-bone chart-placeholder__y"
                :style="{ '--tick': tick - 1 }"
              />
              <span
                v-for="tick in CHART_PLACEHOLDER_X"
                :key="'x' + tick"
                class="skeleton-bone chart-placeholder__x"
                :style="{ '--tick': tick }"
              />
            </div>
          </div>
        </div>
      </template>
      <template #default="{ group }">
        <header class="group-head">
          <h2 :title="group.groupName">{{ group.groupName }}</h2>
          <div class="group-head-actions">
            <n-button
              size="tiny"
              secondary
              :aria-label="'隐藏' + group.groupName + '窗口'"
              @click="board.hideGroup(group.boardKey)"
            >
              隐藏
            </n-button>
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
            · {{ group.missing.join('、') }} 暂无历史
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
          <n-button
            size="tiny"
            secondary
            @click="adjustWidth(group.boardKey)"
            title="拓宽图表以便水平滚动"
            >↔</n-button
          >
        </div>
        <mood-rate-legend
          :group-name="group.groupName"
          :entries="rateEntries.get(group.boardKey) ?? []"
          @toggle="toggleLine(group.boardKey, $event)"
        />
        <div class="line-outer-container">
          <div
            v-if="group.moodData.datasets.length"
            class="line-inner-container"
            :style="{ width: (expandChart[group.boardKey] ?? 100) + '%' }"
          >
            <Line
              :key="group.boardKey"
              :ref="(instance) => setChartRef(group.boardKey, instance)"
              :data="group.moodData"
              :options="chartOptions"
            />
          </div>
          <div v-else class="no-history">暂无可绘制的心情记录，等待 Mower 采样后会自动显示。</div>
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
          <Line
            v-if="fullscreenGroup.moodData.datasets.length"
            :data="fullscreenGroup.moodData"
            :options="chartOptions"
          />
          <p v-else class="no-history">暂无历史记录</p>
        </div>
      </template>
    </n-modal>
    <mood-observation-editor
      v-model:show="editorShow"
      :view="editingView"
      :catalog="fullCatalog"
      @save="saveView"
      @remove="deleteView"
    />
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { Line } from 'vue-chartjs'
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
import { useMoodBoardStore } from '@/stores/mood_board'
import { useRecordStore } from '@/stores/record'
import { moodStroke } from '@/utils/mood_colors'
import { mergeOperatorCatalog } from '@/utils/mood_observation'
import { useMoodGroups } from '@/composables/useMoodGroups'
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

const board = useMoodBoardStore()
const { getMoodRatios, getMoodCatalog, getMoodSeries } = useRecordStore()
const reportData = ref([])
const catalog = ref([])
const viewHistory = useMoodGroups(board, reportData, getMoodSeries)
const { groups, historyLimited } = viewHistory
const catalogLimited = ref(false)
const loadError = ref('')
// 心情报表第一次读到之前，卡片区显示骨架屏。
const loading = ref(true)
const formError = ref('')
const editorShow = ref(false)
const editingId = ref('')
const fullscreenKey = ref('')
const expandChart = ref({})
const hiddenLines = computed(() => board.hiddenLines)
const chartRefs = new Map()
const chartIntervalCache = new WeakMap()
// 横轴刻度在绘图区里的大致位置（比例），图表读完后换成按时间排的真实刻度。
const CHART_PLACEHOLDER_X = [0.29, 0.62, 0.96]

const fullCatalog = computed(() => mergeOperatorCatalog(catalog.value, reportData.value))
const editingView = computed(() => board.views.find((view) => view.id === editingId.value) || null)
const fullscreenGroup = computed(
  () => orderedReportData.value.find((group) => group.boardKey === fullscreenKey.value) || null
)
const orderedReportData = computed(() => {
  return groups.value.map((group) => {
    const key = group.boardKey
    const hidden = Array.isArray(hiddenLines.value[key]) ? hiddenLines.value[key] : []
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
            tension: 0.14,
            borderWidth: 2,
            pointRadius: 2
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
          visible: !dataset.hidden,
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
  board.setHiddenLines(key, visible ? [] : group.moodData.datasets.map((dataset) => dataset.label))
  setAllMoodDatasetsVisible(chartRefs.get(key)?.chart, visible)
}

function toggleLine(key, index) {
  const group = orderedReportData.value.find((item) => item.boardKey === key)
  const name = group?.moodData.datasets[index]?.label
  if (!name) return
  const next = new Set(Array.isArray(hiddenLines.value[key]) ? hiddenLines.value[key] : [])
  if (next.has(name)) next.delete(name)
  else next.add(name)
  board.setHiddenLines(key, [...next])
  const chart = chartRefs.get(key)?.chart
  if (chart) {
    chart.setDatasetVisibility(index, !next.has(name))
    chart.update('none')
  }
}

function adjustWidth(key) {
  const value = expandChart.value[key] || 100
  expandChart.value = {
    ...expandChart.value,
    [key]: value === 100 ? 200 : value === 200 ? 300 : 100
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
  if (!window.confirm('确定删除这张自定义观察表？不会删除任何历史记录。')) return
  board.removeView(id)
  editorShow.value = false
  editingId.value = ''
}

onMounted(async () => {
  await board.load()
  try {
    reportData.value = await getMoodRatios({ includeWorkRest: false })
  } catch {
    loadError.value = '心情报表读取失败，请检查本地 Mower 后端。'
    return
  } finally {
    loading.value = false
  }
  try {
    catalog.value = await getMoodCatalog()
  } catch {
    catalogLimited.value = true
  }
})

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
</script>

<style scoped>
/* 页面铺满内容区，卡片的宽度不随读取中或读完后的卡片内容变化。 */
.mood-page {
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  padding: var(--page-padding);
  padding-bottom: 20px;
}

.page-title {
  text-align: center;
  font-size: 24px;
  font-weight: 600;
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

/* 折线图占位：绘图区与图表的绘图区重合（左侧 27px 是纵轴刻度，下方 28px 是横轴刻度），
   纵轴 0 到 24 每 4 点一条网格线，颜色与图表的网格线相同。 */
.chart-placeholder {
  --plot-top: 10px;
  --plot-right: 16px;
  --plot-bottom: 28px;
  --plot-left: 27px;
  position: relative;
  height: 100%;
}

.chart-placeholder__grid {
  position: absolute;
  inset: var(--plot-top) var(--plot-right) var(--plot-bottom) var(--plot-left);
  background: repeating-linear-gradient(
    to bottom,
    rgb(0 0 0 / 0.1) 0 1px,
    transparent 1px calc((100% - 1px) / 6)
  );
}

.chart-placeholder__y,
.chart-placeholder__x {
  position: absolute;
  height: 7px;
  border-radius: 3px;
}

.chart-placeholder__y {
  right: calc(100% - var(--plot-left) + 6px);
  top: calc(
    var(--plot-top) + (100% - var(--plot-top) - var(--plot-bottom)) * (6 - var(--tick)) / 6 - 3px
  );
  width: 12px;
}

.chart-placeholder__x {
  top: calc(100% - var(--plot-bottom) + 10px);
  left: calc(var(--plot-left) + (100% - var(--plot-left) - var(--plot-right)) * var(--tick) - 18px);
  width: 36px;
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

@media (max-width: 640px) {
  .mood-page {
    padding: var(--page-padding-mobile);
    padding-bottom: 12px;
  }

  .group-head h2 {
    font-size: 16px;
  }
}
</style>
