<template>
  <div>

    <h1 class="page-title">干员基建报表</h1>
    <div class="report-container">
      <div v-for="(groupData, index) in reportData" :key="index" class="report-card">
        <h2>{{ groupData.groupName }}</h2>
        <Pie :data="groupData.workRestData" :options="pieOptions" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Pie } from 'vue-chartjs'
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
      display: false
    }
  }
})

// 添加状态变量来切换报表
const currentReport = ref('mood') // 默认显示干员心情报表

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
  align-items: center;
  /* 让内容在水平方向上居中 */
  justify-content: center;
  /* 让内容在垂直方向上居中 */
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
</style>
