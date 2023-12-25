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
        <Line :data="groupData.moodData" :options="chartOptions" />
        <n-button
          class="toggle-size"
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
      </n-gi>
    </n-grid>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Line } from 'vue-chartjs'
import 'chartjs-adapter-luxon'
import ChartDataLabels from 'chartjs-plugin-datalabels'
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
  ArcElement,
  ChartDataLabels
)

const expand_card = ref(-1)

// Mock report data
const reportData = ref([])
onMounted(async () => {
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
    datalabels: {
      display: false
    }
  }
})

import CollapseIcon from '@vicons/tabler/ArrowsDiagonal'
import ExpandIcon from '@vicons/tabler/ArrowsDiagonalMinimize2'
</script>

<style scoped>
h2 {
  margin-bottom: 10px;
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

.toggle-size {
  position: absolute;
  top: 10px;
  right: 10px;
}
</style>
