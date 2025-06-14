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
      <n-gi
        v-for="(groupData, index) in reportData"
        :key="index"
        class="report-card"
        draggable="true"
        @dragover.prevent
        @dragenter.prevent
        @dragstart="onDragStart(index, $event)"
        @drop="onDrop(index, $event)"
        @dragend="saveOrder"
      >
        <n-button type="info" secondary class="button_class" @click="handleClick(index)">{{
          groupData.groupName
        }}</n-button>
        <Pie v-if="!showCard[index]" :data="groupData.work_break_group" :options="pieOptions" />
        <n-card v-if="showCard[index]" style="margin-top: 10px">
          <div
            class="text_agent"
            v-for="(agent_work, index2) in groupData.moodData.datasets"
            :key="index2"
          >
            <span>{{ agent_work.label }}</span>

            <span
              :style="{
                color:
                  groupData.work_break_group.datasets[0].data[1] == agent_work.work_break_ratio
                    ? 'red'
                    : ''
              }"
            >
              {{ agent_work.work_break_ratio + '%' }}
            </span>
          </div>
        </n-card>
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
  // 读取本地持久化的顺序数据
  const savedOrder = JSON.parse(localStorage.getItem('reportDataOrder') || '[]')
  if (savedOrder.length) {
    reportData.value.sort((a, b) => {
      return savedOrder.indexOf(a.groupName) - savedOrder.indexOf(b.groupName)
    })
  }
  reportData.value.forEach((i) => {
    i.moodData.datasets.forEach((item) => {
      // 是一个数组，里面有x,y两个值，x是时间戳，y是心情值，对其遍历，如果y小于前一个值的y，说明在工作，反之说明在休息
      item.data.map((a, b) => {
        if (b === 0) return
        if (a.y <= (item.data[b - 1] ? item.data[b - 1].y : 0)) {
          a.working_status = '工作'
        } else {
          a.working_status = '休息'
        }
        // 计算工作或休息时间
        // 将x转换为时间戳（毫秒）
        const currentTimestamp = new Date(a.x).getTime()
        const prevTimestamp = new Date(item.data[b - 1].x).getTime()
        a.status_duration = Number(((currentTimestamp - prevTimestamp) / 3600000).toFixed(3))
      })
      // 统计工作和休息的总时长
      let work_time = 0
      let break_time = 0
      item.data.forEach((point) => {
        if (point.working_status === '工作') {
          work_time += point.status_duration || 0
        } else if (point.working_status === '休息') {
          break_time += point.status_duration || 0
        }
      })
      item.work_time = work_time

      item.break_time = break_time
      item.work_break_ratio = Number(((work_time / (work_time + break_time)) * 100).toFixed(2)) || 0
    })
  })
  // 饼图工休比计算更新：1、有组的，计算组内所有的干员心情工休比，取最低值显示；
  // 遍历每组数据，计算组内工休比
  reportData.value.forEach((group) => {
    // 特殊干员名单
    // 必须同时包含这四名干员
    const specialOperators = ['歌蕾蒂娅', '乌尔比安', '斯卡蒂', '幽灵鲨']
    // 判断组内是否同时包含全部特殊干员
    const hasSpecial = specialOperators.every((op) =>
      group.moodData.datasets.some((ds) => ds.label === op)
    )

    if (group.moodData.datasets.length === 1) {
      // 只有一个人，直接取该人的工休比
      const agent = group.moodData.datasets[0]
      // 如果是菲娅梅塔，设置工作时间为0
      if (agent.label === '菲亚梅塔') {
        group.work_break_group = {
          datasets: [
            {
              data: [100, 0]
            }
          ],
          labels: ['休息时间', '工作时间']
        }
      } else {
        group.work_break_group = {
          datasets: [
            {
              data: [(100 - agent.work_break_ratio).toFixed(2), agent.work_break_ratio]
            }
          ],
          labels: ['休息时间', '工作时间']
        }
      }
    } else if (group.moodData.datasets.length > 1) {
      // 多个人，取最大或最小的工休比
      const ratios = group.moodData.datasets.map((ds) => ds.work_break_ratio)
      const filtered = ratios.filter((r) => r > 0)
      let ratioValue = 0
      if (filtered.length > 0) {
        ratioValue = hasSpecial ? Math.max(...filtered) : Math.min(...filtered)
      }
      group.work_break_group = {
        datasets: [{ data: [(100 - ratioValue).toFixed(2), ratioValue] }],
        labels: ['休息时间', '工作时间']
      }
    } else {
      group.work_break_group = {
        datasets: [{ data: [0, 0] }],
        labels: ['休息时间', '工作时间']
      }
    }
  })
})

// Chart.js options

const pieOptions = ref({
  plugins: {
    datalabels: {
      color: 'black',
      formatter: function (value, context) {
        let total = context.dataset.data.reduce((sum, currentValue) => sum + currentValue, 0)
        return value + '%'
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

const onDragStart = (index, event) => {
  event.dataTransfer.setData('text/plain', index)
}

const onDrop = (index, event) => {
  const draggedIndex = parseInt(event.dataTransfer.getData('text/plain'))
  if (draggedIndex !== index) {
    // Swap the two items
    const temp = reportData.value[index]
    reportData.value[index] = reportData.value[draggedIndex]
    reportData.value[draggedIndex] = temp
  }
  event.preventDefault()
}
const saveOrder = () => {
  // 保存顺序到本地存储或服务器
  localStorage.setItem(
    'reportDataOrder',
    JSON.stringify(reportData.value.map((item) => item.groupName))
  )
  console.log(
    '保存顺序:',
    reportData.value.map((item) => item.groupName)
  )
}

const showCard = ref(reportData.value.map(() => false))
function handleClick(index) {
  showCard.value[index] = !showCard.value[index]
}
</script>

<style scoped>
.button_class {
  margin-top: 40px;
  margin-bottom: 10px;
}

.page-title {
  text-align: center;
  font-size: 24px;
  margin-bottom: 20px;
}

.text_agent {
  display: flex;
  justify-content: space-between;
  padding: 5px 10px;
  border-bottom: 1px solid #eaeaea;
  font-size: 12.5px;
  box-sizing: border-box;
  background-color: #81d8cf;
  max-width: 100%;
  max-height: 100%;
  overflow: auto;
}
</style>
