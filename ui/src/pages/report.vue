<template>
  <div>
    <h1 class="page-title">
      基建报表
      <help-text>
        <p>若没有数据显示，请查看tmp文件夹中的report.csv文件</p>
        <p>若存在空数据删掉对应行或自行填补一个数据</p>
        <p>report.csv不存在建议先让mower看看你的基报</p>
      </help-text>
    </h1>
  </div>
  <n-dropdown
    :options="algorithm_options"
    placement="bottom-start"
    trigger="click"
    @select="handleSelect"
  >
    <n-button>收益算法选择（默认82算法）</n-button>
  </n-dropdown>
  <n-card title="收益系数输入" v-show="isShow">
    <div>
      <span>赤金<n-input-number v-model:value="value_coefficient_gold" /></span>
      <span>订单<n-input-number v-model:value="value_coefficient_lmb" /></span>
      <span>经验<n-input-number v-model:value="value_coefficient_exp" /></span>
    </div>
    <div class="button_class">
      <n-button type="tertiary" @click="isShow = false">取消</n-button>
      <n-button type="primary" @click="handleClick">确认</n-button>
    </div>
  </n-card>
  <n-alert title="数据错误" type="error" v-if="show_alert">
    <p>若没有数据显示，请查看tmp文件夹中的report.csv文件</p>
    <p>若存在空数据删掉对应行或自行填补一个数据</p>
    <p>report.csv不存在建议先让mower看看你的基报</p>
  </n-alert>
  <div>
    <n-grid x-gap="12" y-gap="12" cols="1 1000:2 " style="text-align: center" autoresize>
      <n-gi v-if="show_iron_chart">
        <div class="report-card_1">
          <v-chart class="chart" :option="option_manufactor" />
        </div>
      </n-gi>
      <n-gi v-if="show_earnings_chart">
        <div class="report-card_1">
          <v-chart class="chart" :option="option_earnings" />
        </div>
      </n-gi>
      <n-gi v-if="show_orundum_chart">
        <div class="report-card_1">
          <v-chart class="chart" :option="option_orundum" />
        </div>
      </n-gi>
    </n-grid>
  </div>
</template>

<script setup>
import { registerTheme, use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart } from 'echarts/charts'
import { useMessage } from 'naive-ui'
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
// 基报显示收益
const value_coefficient_gold = ref(0.8)
const value_coefficient_lmb = ref(0.2)
const value_coefficient_exp = ref(1)
const total_earnings = ref(0)
const isShow = ref(false)
const algorithm_options = [
  {
    label: '82算法',
    key: '收益公式：赤金*0.8+订单*0.2+经验*1',
    id: 0
  },
  {
    label: 'CE6&LS6算法',
    key: '收益公式：赤金*0.8+订单*0.245+经验*1',
    id: 1
  },
  {
    label: '其他算法，点击输入产物系数',
    key: '自定义收益',
    id: 2
  }
]
const message = useMessage()
function handleSelect(key, option) {
  message.info(key)
  if (option.id == 0) {
    value_coefficient_gold.value = 0.8
    value_coefficient_lmb.value = 0.2
    value_coefficient_exp.value = 1
  } else if (option.id == 1) {
    value_coefficient_gold.value = 0.8
    value_coefficient_lmb.value = 0.245
    value_coefficient_exp.value = 1
  } else {
    isShow.value = true
  }
  // 同步更新收益数据
  ReportData.value.forEach((item) => {
    getTradingHistory.value.forEach((count) => {
      if (count['日期'] == item['日期']) {
        if (count['龙舌兰']) {
          item.龙舌兰赤金 = count['龙舌兰'] * 500
        }
      }
    })
    item.收益 =
      ((item['赤金'] + (item.龙舌兰赤金 || 0)) * value_coefficient_gold.value +
        item['龙门币订单'] * value_coefficient_lmb.value +
        item['作战录像'] * value_coefficient_exp.value) /
      10000
  })
}
function handleClick() {
  isShow.value = false
  ReportData.value.forEach((item) => {
    getTradingHistory.value.forEach((count) => {
      if (count['日期'] == item['日期']) {
        if (count['龙舌兰']) {
          item.龙舌兰赤金 = count['龙舌兰'] * 500
        }
      }
    })
    item.收益 =
      ((item['赤金'] + (item.龙舌兰赤金 || 0)) * value_coefficient_gold.value +
        item['龙门币订单'] * value_coefficient_lmb.value +
        item['作战录像'] * value_coefficient_exp.value) /
      10000
  })
}

registerTheme('dark', dark)
if (theme.value == 'dark') {
  provide(THEME_KEY, 'dark')
} else {
  registerTheme('roma', roma)
  provide(THEME_KEY, 'roma')
}

import { useReportStore } from '@/stores/report'

const reportStore = useReportStore()
const { getReportData, getOrundumData, getTradingHistory } = reportStore

const show_iron_chart = ref(false)
const show_orundum_chart = ref(false)
const show_earnings_chart = ref(false)
const sum_orundum = ref(0)
const show_alert = ref(false)
const ReportData = ref([])
const HalfMonthData = ref([])
onMounted(async () => {
  try {
    ReportData.value = await getReportData()
    HalfMonthData.value = await getOrundumData()
    getTradingHistory.value = await getTradingHistory()
    //往ReportData.value添加龙舌兰赤金数据
    ReportData.value.forEach((item) => {
      getTradingHistory.value.forEach((count) => {
        if (count['日期'] == item['日期']) {
          if (count['龙舌兰']) {
            item.龙舌兰赤金 = count['龙舌兰'] * 500
          }
        }
      })
      item.收益 =
        ((item['赤金'] + (item.龙舌兰赤金 || 0)) * value_coefficient_gold.value +
          item['龙门币订单'] * value_coefficient_lmb.value +
          item['作战录像'] * value_coefficient_exp.value) /
        10000
    })
    show_iron_chart.value = true
    show_earnings_chart.value = true
    if (HalfMonthData.value.length > 0) {
      show_orundum_chart.value = true
      sum_orundum.value = HalfMonthData.value[HalfMonthData.value.length - 1]['累计制造合成玉']
    }
  } catch {
    show_alert.value = true
  }
})

const option_manufactor = computed(() => {
  return {
    title: [
      {
        text: '制造与龙门币'
      }
    ],
    toolbox: {
      feature: {
        saveAsImage: {
          show: true,
          backgroundColor: '#FFFFFF'
        }
      }
    },
    dataZoom: [
      //滚动条
      {
        show: false,
        type: 'slider',
        realtime: true,
        startValue: ReportData.value.length - 7,
        endValue: ReportData.value.length,
        yAxisIndex: [0],
        bottom: '10',
        left: '30',
        height: 10,
        borderColor: 'rgba(0,0,0,0)',
        textStyle: {
          color: '#05D5FF'
        }
      }
    ],

    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    legend: {
      data: ['订单', '赤金', '经验', '龙舌兰赤金'],
      selected: {
        订单收入: true,
        赤金: true,
        龙门币订单: true
      }
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross',
        crossStyle: {
          color: '#999'
        }
      },

      formatter: function (params) {
        if (params[0].data['龙舌兰赤金']) {
          total_earnings.value =
            (params[0].data['赤金'] + params[0].data['龙舌兰赤金']) * value_coefficient_gold.value +
            params[0].data['龙门币订单'] * value_coefficient_lmb.value +
            params[0].data['作战录像'] * value_coefficient_exp.value
        } else {
          params[0].data['龙舌兰赤金'] = 0
          total_earnings.value =
            (params[0].data['赤金'] + params[0].data['龙舌兰赤金']) * value_coefficient_gold.value +
            params[0].data['龙门币订单'] * value_coefficient_lmb.value +
            params[0].data['作战录像'] * value_coefficient_exp.value
        }
        const tip = `<div style="font-size:1.4rem;">
                        <span style="font-size:15px">${params[0].data['日期']}</span>  <br>
                        ${params[0].marker}    <span style="font-size:14px">${params[0].seriesName}:${params[0].data['赤金']}</span>  <br>
                        ${params[2].marker}    <span style="font-size:14px">${params[2].seriesName}:${params[0].data['龙门币订单']}</span>  <br>
                        ${params[1].marker}    <span style="font-size:14px">${params[1].seriesName}:${params[0].data['作战录像']}</span>  <br>
                        ${params[3].marker}    <span style="font-size:14px">${params[3].seriesName}:${params[0].data['龙舌兰赤金']}</span> <br>
                                               <span style="font-size:14px">收益:${total_earnings.value}</span>  <br>
          </div>`
        return tip
      }
    },
    dataset: {
      dimensions: ['日期', '赤金', '反向作战录像', '龙门币订单', '龙舌兰赤金'],
      source: ReportData.value
    },
    yAxis: {
      type: 'category',
      axisPointer: {
        type: 'shadow'
      },
      axisTick: {
        show: false
      }
    },
    xAxis: {
      axisLabel: {
        formatter: function (params) {
          return Math.abs(params)
        },
        scale: true // 设置数据自动缩放，要不然数据多的话就堆一块了
      }
    },
    series: [
      {
        name: '赤金',
        type: 'bar',
        stack: 'gold',
        color: '#f5744f',
        position: 'inside',
        label: {
          show: true,
          formatter: function (params) {
            if (params.value['龙门币订单'] === 0) {
              return ''
            }
          }
        },
        emphasis: {
          focus: 'series'
        }
      },
      {
        name: '经验',
        type: 'bar',
        stack: 'Total',
        color: '#f3e28f',

        position: 'inside',
        label: {
          show: true,
          formatter: function (params) {
            if (params.value['反向作战录像'] === 0) {
              return ''
            } else if (params.value['反向作战录像'] < 0) {
              return -params.value['反向作战录像']
            }
          }
        },
        emphasis: {
          focus: 'series'
        }
      },
      {
        name: '订单',
        type: 'bar',
        stack: 'Total',
        color: '#64bfec',
        label: {
          show: true,
          formatter: function (params) {
            if (params.value['赤金'] === 0) {
              return ''
            } else if (params.value['赤金'] < 0) {
              return -params.value['赤金']
            }
          }
        },
        emphasis: {
          focus: 'series'
        }
      },
      {
        name: '龙舌兰赤金',
        type: 'bar',
        stack: 'gold',
        color: '#8A2BE2',
        label: {
          show: true,
          formatter: function (params) {
            if (params.value['龙舌兰赤金'] === 0) {
              return ''
            } else if (params.value['龙舌兰赤金'] < 0) {
              return -params.value['龙舌兰赤金']
            }
          }
        },
        emphasis: {
          focus: 'series'
        }
      }
    ]
  }
})
// 收益折线图
const option_earnings = computed(() => {
  // 只取最近7天的数据
  const source = ReportData.value.length > 7 ? ReportData.value.slice(-7) : ReportData.value

  // 过滤出有效的收益数据
  const validEarnings = source.filter((item) => typeof item.收益 === 'number' && !isNaN(item.收益))
  const avgEarnings =
    validEarnings.length > 0
      ? (validEarnings.reduce((sum, item) => sum + item.收益, 0) / validEarnings.length).toFixed(2)
      : '0.00'

  return {
    title: [
      {
        text: '收益(近七日平均值：' + avgEarnings + ' 万)'
      }
    ],
    legend: {
      data: ['收益'],
      selected: {
        收益: true
      }
    },
    toolbox: {
      feature: {
        dataView: { show: false, readOnly: false },
        magicType: { show: true, type: ['line', 'bar'] },
        restore: { show: true },
        saveAsImage: {
          show: true,
          backgroundColor: '#FFFFFF'
        }
      }
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross',
        crossStyle: {
          color: '#999'
        }
      }
    },
    dataset: {
      dimensions: ['日期', '收益'],
      source
    },
    xAxis: {
      type: 'category',
      axisPointer: {
        type: 'shadow'
      }
    },
    yAxis: {
      type: 'value',
      axisLine: {
        show: true,
        symbolOffset: 10, //箭头距离x轴末端距离
        symbolSize: [35, 38] //箭头的宽高
      },
      axisLabel: {
        formatter: '{value}'
      }
    },
    series: [
      {
        type: 'line',
        color: '#f5744f',
        tooltip: {
          valueFormatter(value) {
            return value
          }
        },
        label: {
          show: true,
          position: 'top'
        }
      }
    ]
  }
})

const option_orundum = computed(() => {
  return {
    title: [
      {
        text: '合成玉'
      }
    ],
    legend: {
      data: ['合成玉', '抽数'],
      selected: {
        合成玉: true,
        抽数: false
      }
    },
    toolbox: {
      feature: {
        dataView: { show: false, readOnly: false },
        magicType: { show: true, type: ['line', 'bar'] },
        restore: { show: true },
        saveAsImage: {
          show: true,
          backgroundColor: '#FFFFFF'
        }
      }
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross',
        crossStyle: {
          color: '#999'
        }
      }
    },
    dataset: {
      dimensions: ['日期', '合成玉', '抽数'],
      source: HalfMonthData.value
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
        axisLine: {
          show: true
        },
        position: 'right'
      }
    ],
    series: [
      {
        type: 'line',
        yAxisIndex: 0,
        color: '#faf0b5',
        tooltip: {
          valueFormatter: function (value) {
            return value
          }
        }
      },
      {
        type: 'bar',
        yAxisIndex: 1,
        color: '#e70000',
        tooltip: {
          valueFormatter: function (value) {
            return value
          }
        }
      }
    ]
  }
})
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

.n-card {
  max-width: 520px;
}

.button_class {
  margin-top: 30px;
  display: flex;
  justify-content: center;
  gap: 30px;
}
</style>
