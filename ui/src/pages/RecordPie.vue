<template>
  <div>
    <h1 class="page-title">工作休息比例报表</h1>
    <n-grid :x-gap="12" :y-gap="8" :collapsed="false" cols="1 s:1 m:2 l:3 xl:4 2xl:5" responsive="screen">
      <n-gi v-for="(groupData, index) in reportData" :key="index" class="report-card">
        <h2>{{ groupData.groupName }}</h2>
        <Pie :data="groupData.workRestData" :options="pieOptions" />
      </n-gi>
    </n-grid>
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
</style>
