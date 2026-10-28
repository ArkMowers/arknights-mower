<template>
  <div class="mood-page">
    <h1 class="page-title">{{ t('reports.workRestTitle') }}</h1>
    <p class="order-note">{{ t('reports.workRestHelp') }}</p>
    <div class="cleanup-toolbar">
      <n-button v-if="board.hiddenGroups.length" secondary @click="board.restoreGroups"
        >{{ t('reports.restoreHiddenPrefix') }}{{ board.hiddenGroups.length }}）
      </n-button>
      <n-date-picker
        v-model:value="selectedTime"
        type="datetime"
        :placeholder="t('reports.chooseTime')"
        style="width: 200px"
      />
      <n-button @click="showConfirm = true">{{ t('reports.clearOldMorale') }}</n-button>
    </div>
    <n-modal
      v-model:show="showConfirm"
      preset="dialog"
      :title="t('reports.confirmDelete')"
      :content="t('reports.clearMoraleConfirmation')"
      :positive-text="t('reports.confirm')"
      :negative-text="t('reports.cancel')"
      @positive-click="clearData"
    />
    <p v-if="loadError" class="load-error" role="alert">{{ reportErrorMessage(loadError) }}</p>
    <p v-if="board.saveError" class="load-error" role="alert">
      {{ reportErrorMessage(board.saveError) }}
    </p>
    <p v-if="historyLimited" class="order-note">{{ t('reports.ratioHistoryUnavailable') }}</p>
    <mood-card-grid :groups="orderedReportData" @reorder="reorderCards">
      <template #default="{ group }">
        <header class="group-head">
          <n-button
            type="info"
            secondary
            class="group-title"
            :title="t('reports.expandGroupRatio', { name: group.groupName })"
            @click="handleClick(group.boardKey)"
          >
            {{ group.groupName }}
          </n-button>
          <n-button
            size="tiny"
            secondary
            :aria-label="t('reports.hideGroup', { name: group.groupName })"
            @click="board.hideGroup(group.boardKey)"
            >{{ t('reports.hide') }}</n-button
          >
        </header>
        <p v-if="group.isCustom" class="card-hint">
          {{ t('reports.customObservationPrefix') }}{{ group.operators.length
          }}{{ t('reports.operatorsSuffix')
          }}<span v-if="group.missing.length">
            · {{ group.missing.join('、') }}{{ t('reports.noHistory') }}</span
          >
        </p>
        <div v-if="!showCard[group.boardKey] && group.hasValidRatio" class="pie-area">
          <Pie :data="group.work_break_group" :options="pieOptions" :plugins="[ChartDataLabels]" />
        </div>
        <div v-else-if="!showCard[group.boardKey]" class="no-history">
          {{ t('reports.noRatioData') }}
        </div>
        <div v-else class="agent-details">
          <button
            v-for="operator in group.operatorRatios"
            :key="operator.name"
            type="button"
            class="agent-detail"
            :aria-label="
              t('reports.defaultOperatorLabel', {
                operator: operatorDisplayName(operator.name),
                group: group.groupName
              })
            "
            :aria-pressed="group.defaultOperator === operator.name"
            @click="selectOperator(group.boardKey, operator.name)"
          >
            <span>{{ operatorDisplayName(operator.name) }}</span>
            <span>{{
              operator.ratio == null ? t('reports.noRecords') : operator.ratio.toFixed(2) + '%'
            }}</span>
          </button>
          <p
            v-if="!group.operatorRatios.length && group.moodData.datasets.length"
            class="card-hint"
          >
            {{ t('reports.allCurvesExcluded') }}
          </p>
        </div>
        <p class="card-hint">
          {{ t('reports.currentOperatorPrefix')
          }}{{ operatorDisplayName(group.defaultOperator) || t('reports.noOperator') }}
        </p>
      </template>
    </mood-card-grid>
  </div>
</template>

<script setup>
import { i18n } from '@/i18n'
import { operatorDisplayName } from '@/i18n/gameNames'
import { reportErrorMessage } from '@/i18n/reports'
const { t } = i18n.global
import { computed, onMounted, ref } from 'vue'
import axios from 'axios'
import { Pie } from 'vue-chartjs'
import 'chartjs-adapter-luxon'
import ChartDataLabels from 'chartjs-plugin-datalabels'
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
import MoodCardGrid from '@/components/MoodCardGrid.vue'
import { useMoodBoardStore } from '@/stores/mood_board'
import { useRecordStore } from '@/stores/record'
import { useMoodGroups } from '@/composables/useMoodGroups'

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

function durationRatio(points) {
  let work = 0
  let rest = 0
  if (!Array.isArray(points)) return null
  for (let index = 1; index < points.length; index++) {
    const previous = points[index - 1]
    const current = points[index]
    const hours = (new Date(current.x).getTime() - new Date(previous.x).getTime()) / 3600000
    if (!Number.isFinite(hours) || hours <= 0 || hours > 24) continue
    if (!Number.isFinite(previous.y) || !Number.isFinite(current.y)) continue
    if (previous.moodEvent || current.moodEvent) continue
    if (current.y <= previous.y) work += hours
    else rest += hours
  }
  return work + rest > 0 ? (work / (work + rest)) * 100 : null
}

function decorateGroup(group) {
  const savedHidden = board.hiddenLines[group.boardKey]
  const hidden = Array.isArray(savedHidden) ? savedHidden : []
  const ratios = (group.moodData?.datasets || [])
    .filter((dataset) => !hidden.includes(dataset.label))
    .map((dataset) => ({
      name: dataset.label,
      ratio: dataset.label === '菲亚梅塔' ? 0 : durationRatio(dataset.data)
    }))
  const quartet = ['歌蕾蒂娅', '乌尔比安', '斯卡蒂', '幽灵鲨']
  const isSpecial = quartet.every((name) => ratios.some((operator) => operator.name === name))
  const positive = ratios.filter((item) => item.ratio > 0)
  const automatic =
    positive.reduce(
      (best, item) =>
        !best || (isSpecial ? item.ratio > best.ratio : item.ratio < best.ratio) ? item : best,
      null
    ) ||
    ratios.find((item) => item.ratio != null) ||
    ratios[0]
  const selected =
    ratios.find((item) => item.name === board.defaultOperators[group.boardKey]) || automatic
  const result = selected?.ratio ?? null
  return {
    ...group,
    defaultOperator: selected?.name || '',
    operatorRatios: ratios,
    hasValidRatio: result != null,
    work_break_group: {
      datasets: [{ data: result == null ? [0, 0] : [100 - result, result] }],
      labels: [t('reports.restTime'), t('reports.workTime')]
    }
  }
}

const board = useMoodBoardStore()
const { getMoodRatios, getMoodSeries } = useRecordStore()
const reportData = ref([])
const viewHistory = useMoodGroups(board, reportData, getMoodSeries)
const { groups, historyLimited } = viewHistory
const loadError = ref('')
const showCard = ref({})
const selectedTime = ref(Date.now())
const showConfirm = ref(false)

const orderedReportData = computed(() => groups.value.map(decorateGroup))

function reorderCards(source, target) {
  board.reorder(orderedReportData.value, source, target)
}

function handleClick(key) {
  showCard.value = { ...showCard.value, [key]: !showCard.value[key] }
}

function selectOperator(key, name) {
  const group = orderedReportData.value.find((item) => item.boardKey === key)
  if (!group?.operatorRatios.some((operator) => operator.name === name)) return
  board.setDefaultOperator(key, name)
  showCard.value = { ...showCard.value, [key]: false }
}

async function clearData() {
  try {
    await axios.delete(`${import.meta.env.VITE_HTTP_URL || ''}/record/clear-data`, {
      data: { date_time: selectedTime.value }
    })
    alert(t('reports.clearedData'))
    reportData.value = await getMoodRatios({ includeWorkRest: false })
    await viewHistory.refreshSeries()
  } catch {
    alert(t('reports.clearDataFailed'))
  } finally {
    showConfirm.value = false
  }
}

onMounted(async () => {
  await board.load()
  try {
    reportData.value = await getMoodRatios({ includeWorkRest: false })
  } catch {
    loadError.value = t('reports.ratioLoadFailed')
  }
})

const pieOptions = {
  get locale() {
    return i18n.global.locale.value
  },
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    datalabels: {
      color: '#18232a',
      formatter: (value) => Number(value).toFixed(1) + '%'
    },
    legend: { display: false }
  }
}
</script>

<style scoped>
.mood-page {
  min-width: 0;
  padding: var(--page-padding);
  padding-bottom: 18px;
}

.page-title {
  text-align: center;
  font-size: 24px;
  font-weight: 600;
  margin: 6px 0 9px;
}

.order-note {
  text-align: center;
  margin: 0 auto 12px;
  font-size: 12px;
  opacity: 0.75;
}

.cleanup-toolbar {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.group-head {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 6px;
  padding: 27px 5px 3px;
}

.group-title {
  min-width: 100px;
  max-width: calc(100% - 48px);
  font-size: 16px;
}

.pie-area {
  width: 100%;
  flex: 1;
  min-height: 0;
  padding: 3px 18px;
  box-sizing: border-box;
}

.agent-details {
  overflow: auto;
  flex: 1;
  margin-top: 9px;
}

.agent-detail {
  display: flex;
  justify-content: space-between;
  padding: 6px;
  gap: 8px;
  font-size: 12px;
  width: 100%;
  border: none;
  border-bottom: 1px solid var(--n-border-color);
  background: transparent;
  color: inherit;
  cursor: pointer;
  border-radius: 4px;
  font-family: inherit;
}
.agent-detail:hover,
.agent-detail[aria-pressed='true'] {
  background: var(--n-border-color, rgba(68, 159, 134, 0.13));
}
.agent-detail:focus-visible {
  outline: 2px solid #358f78;
  outline-offset: -2px;
}

.no-history {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0.66;
}

.card-hint {
  font-size: 10px;
  text-align: center;
  opacity: 0.6;
  padding-top: 3px;
}

.load-error {
  color: #b67424;
  text-align: center;
}

@media (max-width: 640px) {
  .mood-page {
    padding: var(--page-padding-mobile);
    padding-bottom: 10px;
  }
}
</style>
