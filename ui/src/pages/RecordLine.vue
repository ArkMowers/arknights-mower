<template>
  <div>
    <h1 class="page-title">干员心情折线表</h1>
    <mood-order-controls
      :group-options="groupOptions"
      :operator-options="operatorOptions"
      :pinned-groups="moodPrefs.pinnedGroups"
      :pinned-operators="moodPrefs.pinnedOperators"
      @update:pinned-groups="setPinnedGroups"
      @update:pinned-operators="setPinnedOperators"
    />
    <p class="rate-caption">
      根据相邻有效心情记录估算平均消耗与恢复速率，充能等事件及数据间隔异常时不计算。
    </p>
    <n-grid
      :x-gap="12"
      :y-gap="8"
      :collapsed="false"
      cols="1 s:1 m:2 l:3 xl:4 2xl:5"
      responsive="screen"
    >
      <n-gi
        v-for="groupData in orderedReportData"
        :key="groupData.groupName"
        class="report-card"
        :class="{ 'report-card-expand': expand_card == groupData.groupName }"
      >
        <h2>{{ groupData.groupName }}</h2>
        <div class="rate-toolbar">
          <span>点击图例可单独隐藏或恢复干员曲线</span>
          <n-button size="tiny" secondary @click="setGroupVisibility(groupData.groupName, true)">
            显示全部
          </n-button>
          <n-button size="tiny" secondary @click="setGroupVisibility(groupData.groupName, false)">
            隐藏全部
          </n-button>
        </div>
        <div class="rate-summary" aria-label="干员心情平均变化速率">
          <span
            v-for="operator in rateSummaryByGroup.get(groupData.groupName) ?? []"
            :key="operator.name"
            class="rate-entry"
          >
            <strong>{{ operator.name }}</strong>
            消耗 {{ formatMoodRate(operator.consumption) }}/小时 · 恢复
            {{ formatMoodRate(operator.recovery) }}/小时
          </span>
          <span v-if="!rateSummaryByGroup.get(groupData.groupName)?.length" class="rate-entry">
            暂无可计算的历史数据
          </span>
        </div>
        <div class="line-outer-container">
          <div
            class="line-inner-container"
            :style="{ width: (expand_chart[groupData.groupName] ?? 100) + '%' }"
          >
            <Line
              :ref="(instance) => setChartRef(groupData.groupName, instance)"
              :data="groupData.moodData"
              :options="chartOptions"
            />
          </div>
        </div>
        <n-button
          class="toggle toggle-size"
          size="small"
          @click="expand_card = expand_card == groupData.groupName ? '' : groupData.groupName"
          :focusable="false"
        >
          <template #icon>
            <n-icon>
              <expand-icon v-if="expand_card == groupData.groupName" />
              <collapse-icon v-else />
            </n-icon>
          </template>
        </n-button>
        <n-button
          class="toggle toggle-width"
          size="small"
          @click="adjust_width(groupData.groupName)"
          :focusable="false"
        >
          <template #icon>
            <n-icon>
              <width-icon />
            </n-icon>
          </template>
        </n-button>
      </n-gi>
    </n-grid>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import MoodOrderControls from '@/components/MoodOrderControls.vue'
import {
  calculateMoodIntervals,
  describeMoodInterval,
  describeMoodEvent,
  formatMoodRate,
  setAllMoodDatasetsVisible,
  summarizeMoodRates
} from '@/utils/mood_rate'
import {
  normalizeMoodPreferences,
  orderMoodGroups,
  readMoodPreferences,
  saveMoodPreferences
} from '@/utils/mood_order'
import { Line } from 'vue-chartjs'
import 'chartjs-adapter-luxon'
import { useRecordStore } from '@/stores/record'
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
  Tooltip,
  ArcElement
} from 'chart.js'
const recordStore = useRecordStore()
const { getMoodRatios } = recordStore

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
  Colors,
  ArcElement
)

const expand_card = ref('')
const expand_chart = ref({})
const reportData = ref([])
const moodPrefs = ref(normalizeMoodPreferences())
const orderedReportData = computed(() => orderMoodGroups(reportData.value, moodPrefs.value))
const rateSummaryByGroup = computed(
  () =>
    new Map(
      orderedReportData.value.map((group) => [
        group.groupName,
        (group.moodData?.datasets ?? []).map((dataset) => ({
          name: dataset.label,
          ...summarizeMoodRates(dataset.data)
        }))
      ])
    )
)

// The child Line component exposes its Chart.js instance as .chart.
const chartRefs = new Map()
function setChartRef(groupName, instance) {
  if (instance) chartRefs.set(groupName, instance)
  else chartRefs.delete(groupName)
}
function setGroupVisibility(groupName, visible) {
  setAllMoodDatasetsVisible(chartRefs.get(groupName)?.chart, visible)
}

const moodIntervalCache = new WeakMap()
function getMoodInterval(points, index) {
  if (!Array.isArray(points)) return null
  if (!moodIntervalCache.has(points)) {
    moodIntervalCache.set(points, calculateMoodIntervals(points))
  }
  return moodIntervalCache.get(points)[index] ?? null
}
const groupOptions = computed(() =>
  [...new Set(reportData.value.map((item) => item.groupName))].map((name) => ({
    label: name,
    value: name
  }))
)
const operatorOptions = computed(() =>
  [
    ...new Set(
      reportData.value.flatMap((item) => item.moodData?.datasets?.map((d) => d.label) ?? [])
    )
  ]
    .filter(Boolean)
    .map((name) => ({ label: name, value: name }))
)

function setPinnedGroups(names) {
  moodPrefs.value = normalizeMoodPreferences({ ...moodPrefs.value, pinnedGroups: names })
  saveMoodPreferences(window.localStorage, moodPrefs.value)
}
function setPinnedOperators(names) {
  moodPrefs.value = normalizeMoodPreferences({ ...moodPrefs.value, pinnedOperators: names })
  saveMoodPreferences(window.localStorage, moodPrefs.value)
}

onMounted(async () => {
  moodPrefs.value = readMoodPreferences(window.localStorage)
  reportData.value = await getMoodRatios()
})

// Chart.js options
const chartOptions = ref({
  responsive: true,
  maintainAspectRatio: false,
  scales: {
    x: {
      autoSkip: true,
      type: 'time',
      time: {
        unit: 'day'
      }
    },
    y: {
      beginAtZero: true,
      ticks: {
        min: 0,
        max: 24,
        stepSize: 4
      }
    }
  },
  plugins: {
    legend: { display: true },
    tooltip: {
      backgroundColor: 'rgba(15, 15, 20, 0.92)',
      titleColor: '#ffffff',
      bodyColor: '#ffffff',
      borderColor: 'rgba(255, 255, 255, 0.18)',
      borderWidth: 1,
      callbacks: {
        afterLabel: (context) => {
          const details = []
          const eventInfo = describeMoodEvent(context.raw, context.dataset?.label)
          if (eventInfo) details.push(eventInfo)

          const interval = getMoodInterval(context.dataset?.data, context.dataIndex)
          if (interval) details.push(describeMoodInterval(interval))
          else if (context.raw?.moodEvent) details.push('特殊事件点不计入常规速率')
          return details
        }
      }
    }
  }
})

import CollapseIcon from '@vicons/tabler/ArrowsDiagonal'
import ExpandIcon from '@vicons/tabler/ArrowsDiagonalMinimize2'
import WidthIcon from '@vicons/tabler/ArrowsHorizontal'

function adjust_width(groupName) {
  const current = expand_chart.value[groupName] ?? 100
  expand_chart.value[groupName] = current === 100 ? 300 : current === 300 ? 700 : 100
}
</script>

<style scoped>
h2 {
  margin: 0;
  font-size: 1.2rem;
  text-align: center;
}

.rate-caption {
  margin: -10px auto 12px;
  max-width: 1000px;
  text-align: center;
  font-size: 12px;
  opacity: 0.72;
}
.rate-toolbar {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 11px;
  padding: 2px 0;
}
.rate-summary {
  display: flex;
  flex-shrink: 0;
  gap: 6px;
  overflow-x: auto;
  white-space: nowrap;
  padding: 2px 0 6px;
}
.rate-entry {
  flex-shrink: 0;
  font-size: 11px;
  padding: 2px 6px;
  border: 1px solid var(--n-border-color);
  border-radius: 4px;
}
.rate-entry strong {
  margin-right: 4px;
}
.page-title {
  text-align: center;
  font-size: 24px;
  margin-bottom: 20px;
}

.report-card {
  position: relative;
  background-color: var(--n-color);
  padding: 10px 20px 16px 20px;
  height: 355px;
  box-sizing: border-box;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
}

.report-card-expand {
  position: absolute;
  width: calc(100% - 24px);
  height: calc(100% - 24px);
  top: 12px;
  left: 12px;
  box-sizing: border-box;
  z-index: 9;
}

.toggle {
  position: absolute;
  top: 10px;
}

.toggle-size {
  right: 10px;
}

.toggle-width {
  left: 10px;
}

.line-outer-container {
  width: 100%;
  overflow-x: scroll;
  flex: 1;
  min-height: 0;
}

.line-inner-container {
  padding: 0 12px 16px 12px;
  height: 100%;
  box-sizing: border-box;
}
</style>
