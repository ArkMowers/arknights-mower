<template>
  <div>
    <h1 class="page-title">工作休息比例报表</h1>
    <div style="text-align: center; display: flex; justify-content: center; margin-bottom: 20px">
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
      content="您确定要删除选择时间之前的所有心情数据吗？该行为不可逆，如有需要，请前往temp文件夹备份db文件"
      positive-text="确定"
      negative-text="取消"
      @positive-click="clearData"
    />
    <n-grid
      :x-gap="12"
      :y-gap="8"
      :collapsed="false"
      cols="1 s:1 m:2 l:3 xl:4 2xl:5"
      responsive="screen"
    >
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
import axios from 'axios'
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
const selectedTime = ref(new Date().getTime())
const showConfirm = ref(false)
const clearData = async () => {
  try {
    const req = { date_time: selectedTime.value }
    await axios.delete(`${import.meta.env.VITE_HTTP_URL}/record/clear-data`, { data: req })
    alert('数据已清除')
  } catch (error) {
    console.error('清除数据失败', error)
    alert('清除数据失败，请重试')
  } finally {
    showConfirm.value = false
  }
}
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
