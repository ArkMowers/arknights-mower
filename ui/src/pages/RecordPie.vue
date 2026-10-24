<template>
  <div class="mood-page">
    <h1 class="page-title">工作休息比例报表</h1>
    <p class="order-note">
      拖动卡片调整顺序，折线图自动同步。点击编组标题展开干员，点击干员设为默认。
    </p>
    <div class="cleanup-toolbar">
      <n-button v-if="board.hiddenGroups.length" secondary @click="board.restoreGroups">
        还原隐藏窗口（{{ board.hiddenGroups.length }}）
      </n-button>
      <n-date-picker
        v-model:value="selectedTime"
        type="datetime"
        placeholder="选择时间"
        style="width: 200px"
      />
      <n-button @click="showConfirm = true">清除时间之前的心情数据</n-button>
    </div>
    <n-modal
      v-model:show="showConfirm"
      preset="dialog"
      title="确认删除"
      content="您确定要删除选择时间之前的所有心情数据吗？该行为不可逆，如有需要，请前往 temp 文件夹备份数据库。"
      positive-text="确定"
      negative-text="取消"
      @positive-click="clearData"
    />
    <p v-if="loadError" class="load-error" role="alert">{{ loadError }}</p>
    <p v-if="board.saveError" class="load-error" role="alert">{{ board.saveError }}</p>
    <p v-if="historyLimited" class="order-note">
      当前历史查询接口不可用：自选表暂时只能使用默认报表中已有的干员记录。
    </p>
    <mood-card-grid :groups="orderedReportData" @reorder="reorderCards">
      <template #default="{ group }">
        <header class="group-head">
          <n-button
            type="info"
            secondary
            class="group-title"
            :title="'点击展开或收起 ' + group.groupName + ' 的干员占比'"
            @click="handleClick(group.boardKey)"
          >
            {{ group.groupName }}
          </n-button>
          <n-button
            size="tiny"
            secondary
            :aria-label="'隐藏' + group.groupName + '窗口'"
            @click="board.hideGroup(group.boardKey)"
          >
            隐藏
          </n-button>
        </header>
        <p v-if="group.isCustom" class="card-hint">
          自选观察表 · {{ group.operators.length }} 位干员
          <span v-if="group.missing.length"> · {{ group.missing.join('、') }} 暂无历史 </span>
        </p>
        <div v-if="!showCard[group.boardKey] && group.hasValidRatio" class="pie-area">
          <Pie :data="group.work_break_group" :options="pieOptions" :plugins="[ChartDataLabels]" />
        </div>
        <div v-else-if="!showCard[group.boardKey]" class="no-history">暂无有效工休比数据</div>
        <div v-else class="agent-details">
          <button
            v-for="operator in group.operatorRatios"
            :key="operator.name"
            type="button"
            class="agent-detail"
            :aria-label="'将' + operator.name + '设为' + group.groupName + '的默认干员'"
            :aria-pressed="group.defaultOperator === operator.name"
            @click="selectOperator(group.boardKey, operator.name)"
          >
            <span>{{ operator.name }}</span>
            <span>{{ operator.ratio == null ? '暂无记录' : operator.ratio.toFixed(2) + '%' }}</span>
          </button>
          <p
            v-if="!group.operatorRatios.length && group.moodData.datasets.length"
            class="card-hint"
          >
            所有干员均已在心情曲线中排除
          </p>
        </div>
        <p class="card-hint">当前干员：{{ group.defaultOperator || '无可用干员' }}</p>
      </template>
    </mood-card-grid>
  </div>
</template>

<script setup>
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
      labels: ['休息时间', '工作时间']
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
    alert('数据已清除')
    reportData.value = await getMoodRatios({ includeWorkRest: false })
    await viewHistory.refreshSeries()
  } catch {
    alert('清除数据失败；若当前为只读验收页面，请先返回主界面确认操作权限。')
  } finally {
    showConfirm.value = false
  }
}

onMounted(async () => {
  await board.load()
  try {
    reportData.value = await getMoodRatios({ includeWorkRest: false })
  } catch {
    loadError.value = '工休比数据读取失败，请检查本地 Mower 后端。'
  }
})

const pieOptions = {
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
