<template>
  <div>
    <h1 class="page-title">贸易订单分析</h1>
  </div>
  <div>
    <n-button @click="restoreHistory" type="default">
      恢复历史
      <help-text>
        <p>点击后会在后台运行，请勿多次发送请求</p>
        <p>如果截图比较多，可能等待时间会比较长，请耐心</p>
      </help-text></n-button
    >
  </div>
  <div>
    <n-grid x-gap="12" y-gap="12" cols="1 1000:2 " style="text-align: center" autoresize>
      <n-gi v-if="show_analysis_chart">
        <div class="report-card_1">
          <v-chart class="chart" :option="option_analysis" />
        </div>
      </n-gi>
    </n-grid>
  </div>
</template>

<script setup>
import { registerTheme, use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart } from 'echarts/charts'
import {
  TitleComponent,
  ToolboxComponent,
  LegendComponent,
  TooltipComponent,
  DatasetComponent,
  GridComponent,
  DataZoomComponent
} from 'echarts/components'
import VChart, { THEME_KEY } from 'vue-echarts'
import { ref, provide, onMounted, computed } from 'vue'

use([
  TitleComponent,
  ToolboxComponent,
  LegendComponent,
  TooltipComponent,
  DatasetComponent,
  GridComponent,
  BarChart,
  LineChart,
  DataZoomComponent,
  CanvasRenderer
])
import { useConfigStore } from '@/stores/config'
const store = useConfigStore()
import { storeToRefs } from 'pinia'
const { theme } = storeToRefs(store)

import roma from './theme/roma.json'
import dark from './theme/dark.json'
registerTheme('dark', dark)
if (theme.value == 'dark') {
  provide(THEME_KEY, 'dark')
} else {
  registerTheme('roma', roma)
  provide(THEME_KEY, 'roma')
}
const priceMapping = {
  但书_2000: 2000,
  但书_2500: 2500,
  漏单_1000: 1000,
  漏单_1500: 1500,
  漏单_2000: 2000,
  龙舌兰: 2500,
  佩佩: 1000
}
const colorMapping = {
  漏单_1000: '#E57373',
  漏单_1500: '#FFB74D',
  龙舌兰: '#FFD580',
  但书_2500: '#A3C1DA',
  漏单_2000: '#7986CB',
  但书_2000: '#80CFA9',
  佩佩: '#F06292'
}
// 日期选择器绑定值

import { useReportStore } from '../stores/report'

const reportStore = useReportStore()
const { getTradingHistory, getReportData, restoreTradingHistory } = reportStore

const show_analysis_chart = ref(false)
const TradingHistoryData = ref([])
const ReportData = ref([])
const StackedChartData = ref([])

const restoreHistory = async () => {
  try {
    await restoreTradingHistory()
    TradingHistoryData.value = await getTradingHistory()
    StackedChartData.value = processData()
  } catch (error) {
    console.error('恢复历史数据失败:', error)
  }
}

const processData = () => {
  const combinedData = []

  ReportData.value.forEach((report) => {
    const matchingTradingData = TradingHistoryData.value.find(
      (trading) => trading['日期'] === report['日期']
    )
    const date = report['日期']

    // 初始化订单总数和交易详情
    let tradingDetails = {}
    let totalTradingOrders = 0
    let totalTradingAmount = 0

    if (matchingTradingData) {
      // 计算 TradingHistoryData 中每种类型的金额和订单数
      tradingDetails = Object.keys(matchingTradingData).reduce((acc, key) => {
        if (priceMapping[key]) {
          const count = matchingTradingData[key] || 0
          const price = priceMapping[key]
          const amount = count * price
          acc[key] = amount // 计算金额
          totalTradingOrders += count // 累计订单数
          totalTradingAmount += amount // 累计金额
        }
        return acc
      }, {})
    }

    const totalReportedOrders = report['龙门币订单数'] || 0
    const totalReportedAmount = report['龙门币订单'] || 0
    const unknownOrderAmount = totalReportedAmount - totalTradingAmount

    if (unknownOrderAmount > 0) {
      tradingDetails['未知订单'] = unknownOrderAmount
    }

    // 合并数据
    combinedData.push({
      日期: date,
      ...tradingDetails,
      总订单数: totalReportedOrders,
      龙门币订单: totalReportedAmount,
      订单质量: report['每单获取龙门币'],
      赤金: report['赤金'],
      总未知订单数: totalReportedOrders - totalTradingOrders
    })
  })
  return combinedData
}

onMounted(async () => {
  try {
    TradingHistoryData.value = await getTradingHistory()
    ReportData.value = await getReportData()
    StackedChartData.value = processData()
    show_analysis_chart.value = true
  } catch (error) {
    console.error('Error during getTradingHistory:', error) // 调试错误
    TradingHistoryData.value = []
  }
})
const option_analysis = computed(() => ({
  title: {
    text: '订单分布'
  },
  legend: {
    data: ['赤金', '订单质量'],
    selected: {
      赤金: false,
      订单质量: true
    }
  },
  dataZoom: {
    show: false,
    type: 'slider',
    realtime: true,
    startValue: ReportData.value.length - 7,
    endValue: ReportData.value.length,
    xAxisIndex: [0],
    bottom: '10',
    left: '30',
    height: 10,
    borderColor: 'rgba(0,0,0,0)',
    textStyle: {
      color: '#05D5FF'
    }
  },
  tooltip: {
    trigger: 'axis',
    axisPointer: {
      type: 'shadow'
    },
    formatter: function (params) {
      return [
        `总订单数量: ${params[0].value['龙门币订单']}`,
        ...params
          .filter((p) => p.value[p.seriesName] !== undefined)
          .map((p) => {
            var txt = `${p.marker} ${p.seriesName}: ${p.value[p.seriesName]}`
            if (priceMapping[p.seriesName]) {
              txt += `(${p.value[p.seriesName] / priceMapping[p.seriesName]})`
            } else if (p.seriesName == '未知订单') {
              txt += `(${p.value['总未知订单数']})`
            }
            return txt
          })
      ].join('<br />')
    }
  },
  dataset: {
    dimensions: [
      '日期',
      ...Object.keys(priceMapping),
      '未知订单',
      '订单质量',
      '赤金',
      '龙门币订单'
    ],
    source: StackedChartData.value
  },
  xAxis: {
    type: 'category',
    axisPointer: {
      type: 'shadow'
    }
  },
  yAxis: [
    {
      type: 'value',
      axisLine: {
        show: true,
        symbol: ['none', 'path://M5,20 L5,5 L8,8 L5,2 L2,8 L5,5 L5.3,6 L5.3,20 '],
        symbolOffset: 10, //箭头距离x轴末端距离
        symbolSize: [35, 38] //箭头的宽高
      },
      axisLabel: {
        formatter: '{value}'
      }
    },
    {
      type: 'value',
      axisLabel: {
        formatter: '{value}'
      }
    }
  ],
  series: [
    {
      name: '赤金',
      type: 'bar',
      yAxisIndex: 0,
      color: '#f5744f',
      stack: null, // 使用独立堆叠
      tooltip: {
        valueFormatter: function (value) {
          return value
        }
      },
      emphasis: {
        focus: 'series'
      },
      encode: {
        x: '日期', // 横轴绑定到日期
        y: '赤金' // 纵轴绑定到赤金
      },
      barGap: '30%'
    },
    ...Object.keys(priceMapping).map((type) => ({
      name: type,
      type: 'bar',
      yAxisIndex: 0,
      stack: '总量',
      color: colorMapping[type],
      emphasis: {
        focus: 'series'
      }
    })),
    {
      name: '未知订单',
      type: 'bar',
      yAxisIndex: 0,
      stack: '总量',
      color: '#64bfec',
      emphasis: {
        focus: 'series'
      }
    },
    {
      name: '订单质量',
      type: 'line',
      yAxisIndex: 1,
      tooltip: {
        valueFormatter: function (value) {
          return value
        }
      }
    }
  ]
}))
</script>

<style scoped>
.chart {
  height: 400px;
}

.report-card_1 {
  display: gird;
  flex-direction: column;
  align-items: center;
  /* 让内容在水平方向上居中 */
  justify-content: center;
  /* 让内容在垂直方向上居中 */

  width: 800px;
  height: 400px;
  padding: 20px 20px 80px 20px;
  border: 1px solid #ccc;
}
</style>
