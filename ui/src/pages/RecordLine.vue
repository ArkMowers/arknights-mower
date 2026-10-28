<template>
  <div class="mood-page">
    <h1 class="page-title">{{ t('reports.moraleLineTitle') }}</h1>
    <div class="mood-page-tools">
      <span>{{ t('reports.moraleLineHelp') }}</span>
      <n-button type="primary" secondary @click="newView">{{
        t('reports.newObservation')
      }}</n-button>
      <n-button v-if="board.hiddenGroups.length" secondary @click="board.restoreGroups"
        >{{ t('reports.restoreHiddenPrefix') }}{{ board.hiddenGroups.length }}）
      </n-button>
    </div>
    <p v-if="historyLimited || catalogLimited" class="history-note">
      {{ t('reports.historyUnavailableHelp') }}
    </p>
    <p v-if="loadError" role="alert" class="history-note">{{ reportErrorMessage(loadError) }}</p>
    <p v-if="board.saveError" role="alert" class="history-note">
      {{ reportErrorMessage(board.saveError) }}
    </p>
    <p v-if="formError" role="alert" class="history-note">{{ reportErrorMessage(formError) }}</p>

    <mood-card-grid :groups="orderedReportData" @reorder="reorderCards">
      <template #default="{ group }">
        <header class="group-head">
          <h2 :title="group.groupName">{{ group.groupName }}</h2>
          <div class="group-head-actions">
            <n-button
              size="tiny"
              secondary
              :aria-label="t('reports.hideGroup', { name: group.groupName })"
              @click="board.hideGroup(group.boardKey)"
              >{{ t('reports.hide') }}</n-button
            >
            <n-button
              v-if="group.isCustom"
              size="tiny"
              secondary
              @click="editView(group.customId)"
              >{{ t('reports.edit') }}</n-button
            >
            <n-button
              size="tiny"
              secondary
              :aria-label="t('reports.fullscreenGroup', { name: group.groupName })"
              @click="fullscreenKey = group.boardKey"
              >{{ t('reports.fullscreen') }}</n-button
            >
          </div>
        </header>
        <div v-if="group.isCustom" class="observation-description">
          {{ t('reports.customObservationPrefix') }}{{ group.operators.length
          }}{{ t('reports.operatorsSuffix')
          }}<span v-if="group.missing.length" class="observation-missing">
            · {{ group.missing.join('、') }}{{ t('reports.noHistory') }}</span
          >
        </div>
        <div class="card-controls">
          <span>{{ t('reports.toggleCurvesHelp') }}</span>
          <n-button size="tiny" secondary @click="setGroupVisibility(group.boardKey, true)">{{
            t('reports.showAll')
          }}</n-button>
          <n-button size="tiny" secondary @click="setGroupVisibility(group.boardKey, false)">{{
            t('reports.hideAll')
          }}</n-button>
          <n-button
            size="tiny"
            secondary
            @click="adjustWidth(group.boardKey)"
            :title="t('reports.widenChart')"
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
          <div v-else class="no-history">{{ t('reports.noMoraleData') }}</div>
        </div>
      </template>
    </mood-card-grid>

    <n-modal
      :show="!!fullscreenGroup"
      preset="card"
      :title="fullscreenGroup?.groupName || t('reports.moraleCurve')"
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
          <p v-else class="no-history">{{ t('reports.noHistoryRecords') }}</p>
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
import { i18n } from '@/i18n'
import { operatorDisplayName } from '@/i18n/gameNames'
import { reportErrorMessage } from '@/i18n/reports'
const { t } = i18n.global
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
const formError = ref('')
const editorShow = ref(false)
const editingId = ref('')
const fullscreenKey = ref('')
const expandChart = ref({})
const hiddenLines = computed(() => board.hiddenLines)
const chartRefs = new Map()
const chartIntervalCache = new WeakMap()

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
    formError.value = t('reports.observationSaveFailed')
    return
  }
  editorShow.value = false
  editingId.value = ''
  formError.value = ''
}
function deleteView(id) {
  if (!window.confirm(t('reports.deleteObservationConfirm'))) return
  board.removeView(id)
  editorShow.value = false
  editingId.value = ''
}

onMounted(async () => {
  await board.load()
  try {
    reportData.value = await getMoodRatios({ includeWorkRest: false })
  } catch {
    loadError.value = t('reports.moraleLoadFailed')
    return
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
  get locale() {
    return i18n.global.locale.value
  },
  responsive: true,
  maintainAspectRatio: false,
  animation: false,
  parsing: true,
  scales: {
    x: {
      type: 'time',
      time: { unit: 'day' },
      ticks: { maxTicksLimit: 7 },
      adapters: {
        date: {
          get locale() {
            return i18n.global.locale.value
          }
        }
      }
    },
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
        label: (context) =>
          `${operatorDisplayName(context.dataset?.label || '')}: ${context.formattedValue}`,
        afterLabel: (context) => {
          const lines = []
          const event = describeMoodEvent(context.raw, context.dataset?.label)
          if (event) lines.push(event)
          const interval = getMoodInterval(context.dataset?.data, context.dataIndex)
          if (interval) lines.push(describeMoodInterval(interval))
          else if (context.raw?.moodEvent) lines.push(t('reports.specialPointRateHelp'))
          return lines
        }
      }
    }
  }
}
</script>

<style scoped>
.mood-page {
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
