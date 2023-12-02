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
      <n-gi v-if="show_iron_chart">
        <div class="report-card_1">
          <v-chart class="chart" :option="option_lmb" />
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
import {
  TitleComponent,
  ToolboxComponent,
  LegendComponent,
  TooltipComponent,
  DatasetComponent,
  GridComponent,
  DataZoomComponent,
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

import { useReportStore } from '@/stores/report'

const reportStore = useReportStore()
const { getReportData, getOrundumData } = reportStore

const show_iron_chart = ref(false)
const show_orundum_chart = ref(false)
const sum_orundum = ref(0)
const show_alert=ref(false)
const ReportData = ref([])
const HalfMonthData = ref([])
onMounted(async () => {
  try {
    ReportData.value = await getReportData()
    HalfMonthData.value = await getOrundumData  ()
    show_iron_chart.value = true
    if (HalfMonthData.value.length > 0) {

      show_orundum_chart.value = true
      sum_orundum.value = HalfMonthData.value[HalfMonthData.value.length - 1]['累计制造合成玉']
    }
  }
  catch{
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
    dataZoom: [//滚动条
      {
        show: false,
        type: 'slider',
        realtime: true,
        startValue: ReportData.value.length-7,
        endValue:ReportData.value.length,
        yAxisIndex: [0],
        bottom: '10',
        left: '30',
        height: 10,
        borderColor: 'rgba(0,0,0,0)',
        textStyle: {
          color: '#05D5FF',
        },
      },
    ],

    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    legend: {
      data: ["龙门币订单",'赤金', '作战录像'],
      selected: {
        龙门币订单: true,
        赤金: true,
        作战录像:true
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

      formatter: function(params){
        const tip=`<div style="font-size:1.4rem;">
                        <span style="font-size:16px">${params[0].data['日期']}</span>  <br>
                        ${params[0].marker}    <span style="font-size:16px">${params[0].seriesName}:${params[0].data['龙门币订单']}</span>  <br>
                        ${params[1].marker}    <span style="font-size:16px">${params[1].seriesName}:${params[0].data['赤金']}</span>  <br>
                        ${params[2].marker}    <span style="font-size:16px">${params[2].seriesName}:${-params[0].data['作战录像']}</span>  <br>
                        <span style="font-size:16px">赤金+作战录像:${params[0].data['制造总数']}</span>  <br>
                        </div>`
        return tip
      }
    },
    dataset: {
      dimensions: ['日期',"龙门币订单",'赤金','作战录像'],
      source: ReportData.value
    },
    yAxis: {
      type: 'category',
      axisPointer: {
        type: 'shadow'
      },
      axisTick: {
        show: false
      },
    },
    xAxis: {
      axisLabel: {
        formatter: function (params) {
          return Math.abs(params)
        },
        scale: true, // 设置数据自动缩放，要不然数据多的话就堆一块了
      }

    },
    series: [
      {
        type: 'bar',
        color: '#64bfec',
        label: {
          show: true,
          position: 'inside'
        },
        emphasis: {
          focus: 'series'
        }
      },
      {
        type: 'bar',
        stack: 'Total',
        color: '#f3e28f',
        label: {
          show: true,
          formatter:function(params){
            if(params.value['赤金'] === 0){
              return ''
            }
          },
        },
        emphasis: {
          focus: 'series'
        }
      },
      {
        type: 'bar',
        stack: 'Total',
        color: '#f5744f',
        label: {
          show: true,
          formatter:function(params){
            if(params.value['作战录像'] === 0){
              return ''
            }
            else if(params.value['作战录像'] < 0){
              return -params.value['作战录像']
            }
          },
        },
        emphasis: {
          focus: 'series'
        }
      }
    ]
  }
})

const option_lmb = computed(() => {
    return {
      title: [
        {
          text: '赤金贸易'
        }
      ],
      legend: {
        data: ['生产赤金',"龙门币收入",'每单获取龙门币'],
        selected: {
          生产赤金: true,
          龙门币收入: true
        }
      },
      dataZoom: {
        show: false,
        type: 'slider',
        realtime: true,
        startValue: ReportData.value.length-7, // 重点
        // // 重点-dataX.length表示x轴数据长度
        endValue: ReportData.value.length,
        xAxisIndex: [0],
        bottom: '10',
        left: '30',
        height: 10,
        borderColor: 'rgba(0,0,0,0)',
        textStyle: {
          color: '#05D5FF',
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
        dimensions: ['日期', '赤金',"龙门币订单","每单获取龙门币"],
        source: ReportData.value
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
          name:"龙门币收入",
          type: 'bar',
          yAxisIndex: 0,
          tooltip: {
            valueFormatter: function (value) {
              return value
            }
          }
        },
        {
          name:"生产赤金",
          type: 'bar',
          yAxisIndex: 0,
          color: '#faf0b5',
          tooltip: {
            valueFormatter: function (value) {
              return value
            }
          },
        },
        {
          name:"每单获取龙门币",
          type: 'line',
          yAxisIndex: 1,
          tooltip: {
            valueFormatter: function (value) {
              return value
            }
          },
        },
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
</style>
