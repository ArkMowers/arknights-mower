<template>
  <div>
    <h1 class="page-title">干员心情折线表</h1>
    <n-grid
      :x-gap="12"
      :y-gap="8"
      :collapsed="false"
      cols="1 s:1 m:2 l:3 xl:4 2xl:5"
      responsive="screen"
    >
      <n-gi
        v-for="(groupData, index) in reportData"
        :key="index"
        class="report-card"
        :class="{ 'report-card-expand': expand_card == index }"
      >
        <h2>{{ groupData.groupName }}</h2>
        <div class="line-outer-container">
          <div class="line-inner-container" :style="{ width: expand_chart[index] + '%' }">
            <Line :data="groupData.moodData" :options="chartOptions" />
          </div>
        </div>
        <n-button
          class="toggle toggle-size"
          size="small"
          @click="expand_card = expand_card == -1 ? index : -1"
          :focusable="false"
        >
          <template #icon>
            <n-icon>
              <expand-icon v-if="expand_card == index" />
              <collapse-icon v-else />
            </n-icon>
          </template>
        </n-button>
        <n-button
          class="toggle toggle-width"
          size="small"
          @click="adjust_width(index)"
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
import { ref, onMounted } from 'vue'
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

const expand_card = ref(-1)
const expand_chart = ref([])

// Mock report data
const reportData = ref([])
onMounted(async () => {
  reportData.value = await getMoodRatios()
  expand_chart.value = new Array(reportData.value.length).fill(100)
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
    tooltip: {
      backgroundColor: 'rgba(15, 15, 20, 0.92)',
      titleColor: '#ffffff',
      bodyColor: '#ffffff',
      borderColor: 'rgba(255, 255, 255, 0.18)',
      borderWidth: 1,
      callbacks: {
        afterLabel: (context) => {
          const relatedOperator = context.raw?.relatedOperator
          const moodEvent = context.raw?.moodEvent
          if (
            moodEvent === 'fiammetta_charge' ||
            (context.dataset.label === '菲亚梅塔' && relatedOperator)
          ) {
            return `被充能干员：${relatedOperator}`
          }
          if (moodEvent === 'fiammetta_before') {
            return `被肥鸭充能（交换前）`
          }
          if (moodEvent === 'fiammetta_after') {
            return `被肥鸭充能（交换后）`
          }
          return relatedOperator ? `关联干员：${relatedOperator}` : ''
        }
      }
    }
  }
})

import CollapseIcon from '@vicons/tabler/ArrowsDiagonal'
import ExpandIcon from '@vicons/tabler/ArrowsDiagonalMinimize2'
import WidthIcon from '@vicons/tabler/ArrowsHorizontal'

function adjust_width(idx) {
  if (expand_chart.value[idx] == 100) {
    expand_chart.value[idx] = 300
  } else if (expand_chart.value[idx] == 300) {
    expand_chart.value[idx] = 700
  } else {
    expand_chart.value[idx] = 100
  }
}
</script>

<style scoped>
h2 {
  margin: 0;
  font-size: 1.2rem;
  text-align: center;
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
  height: 300px;
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
