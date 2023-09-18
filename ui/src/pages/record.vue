<template>
  <div>
    <h1 class="page-title">干员基建报表</h1>
    <div class="report-switch">
      <button @click="showMoodReport">干员心情报表</button>
      <button @click="showWorkRestReport">工作休息比例报表</button>
    </div>
  </div>
  <div class="report-container">
    <div v-for="(groupData, index) in reportData" :key="index" class="report-card">
      <h2>{{ groupData.groupName }}</h2>
      <template v-if="currentReport === 'mood'">
        <Line :data="groupData.moodData" :options="chartOptions" />
      </template>
      <template v-else-if="currentReport === 'workRest'">
        <Pie :data="groupData.workRestData" :options="pieOptions" />
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Line, Pie } from 'vue-chartjs'
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

const pieOptions = ref({
  plugins: {
    datalabels: {
      color: 'black',
      formatter: function (value, context) {
        let total = context.dataset.data.reduce((sum, currentValue) => sum + currentValue, 0)
        console.log(value, total, value / total)
        return Math.round((value / total) * 100) + '%'
      }
    },
    legend: {
      // display: false
    }
  }
})

// 添加状态变量来切换报表
const currentReport = ref('mood') // 默认显示干员心情报表

// 切换报表的方法
const showMoodReport = () => {
  currentReport.value = 'mood'
}

const showWorkRestReport = () => {
  currentReport.value = 'workRest'
}
</script>

<style scoped>
.report-container {
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
}

.report-card {
  display: flex;
  flex-direction: column;
  align-items: center; /* 让内容在水平方向上居中 */
  justify-content: center; /* 让内容在垂直方向上居中 */
  width: 300px;
  height: 200px;
  padding: 20px 20px 100px 20px;
  border: 1px solid #ccc;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

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

/* Style for the switch buttons */
.report-switch button {
  padding: 10px 20px;
  border: none;
  background-color: #f2f2f2;
  color: #333;
  font-size: 16px;
  cursor: pointer;
  transition: background-color 0.3s ease;
}

.report-switch button:hover {
  background-color: #ddd;
}

.report-switch button.active {
  background-color: #007bff;
  color: white;
}
</style>
