<template>
  <div>
    <n-grid x-gap="12" y-gap="12" cols="1 1000:2 " style="text-align: center" autoresize >
      <n-gi  v-if=show_iron_chart >
        <div class="report-card_1">
          <v-chart class="chart" :option="option_iron" />
        </div>
      </n-gi>
      <n-gi  v-if=show_orundum_chart >
        <div class="report-card_1">
          <v-chart class="chart" :option="option_orundum"/>
        </div>
      </n-gi>
      <n-gi  v-if=show_exp_chart >
        <div class="report-card_1">
          <v-chart class="chart" :option="option_exp"/>
        </div>
      </n-gi>
    </n-grid>
  </div>

</template>

<script setup>
import {registerTheme, use} from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { BarChart, LineChart } from 'echarts/charts'
import {
  TitleComponent,
  ToolboxComponent,
  LegendComponent,
  TooltipComponent,
  DatasetComponent,
  GridComponent
} from 'echarts/components'
import VChart, { THEME_KEY} from 'vue-echarts';
import { ref, provide,onMounted,computed } from 'vue';

use([
  TitleComponent,
  ToolboxComponent,
  LegendComponent,
  TooltipComponent,
  DatasetComponent,
  GridComponent,
  BarChart,
  LineChart,
  CanvasRenderer
])
import { useConfigStore } from '@/stores/config'
const store = useConfigStore()
import { storeToRefs } from 'pinia'
const { theme } =storeToRefs(store)

import roma from './theme/roma.json'
import dark from './theme/dark.json'
registerTheme('dark',dark)
if(theme.value=='dark'){
  provide(THEME_KEY, 'dark');
}
else{
  registerTheme('roma',roma)
  provide(THEME_KEY, 'roma');
}


import { useReportStore } from '@/stores/report'

const reportStore = useReportStore()
const { getReportData,getHalfMonthData } = reportStore

const show_iron_chart = ref(false)
const show_exp_chart = ref(true)
const show_orundum_chart = ref(false)
const sum_orundum = ref(0)

const ReportData=ref([])
const HalfMonthData=ref([])
onMounted(async () => {
  ReportData.value = await getReportData()
  HalfMonthData.value= await getHalfMonthData()
  show_iron_chart.value = true

  for(let item in ReportData.value){
    console.log("ReportData.value[item]['作战录像']",ReportData.value[item]['作战录像'])
    if(ReportData.value[item]['作战录像']>0){
      show_exp_chart.value=true;
    }
  }
  if(HalfMonthData.value.length>0){
    show_orundum_chart.value=true;
    sum_orundum.value = HalfMonthData.value[HalfMonthData.value.length-1]['累计制造合成玉']
  }
})


const option_iron = computed(() => {
  return {
    title: [
      {
        text: '赤金'
      }
    ],
    toolbox: {
      feature: {
        dataView: { show: true, readOnly: false },
        magicType: { show: true, type: ['line', 'bar'] },
        restore: { show: true },
        saveAsImage: {
          show: true,
          backgroundColor: '#FFFFFF'
        }
      }
    },
    legend: {
      data: ["龙门币订单",'赤金', '每单获取龙门币'],
      selected:{
        '龙门币订单':true,
        '赤金':true,
        '每单获取龙门币':false
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
      dimensions: ['日期','每单获取龙门币',"龙门币订单",'赤金'],
      source: ReportData.value
    },
    xAxis: {
      type: 'category',
      axisPointer: {
        type: 'shadow'
      }},
    yAxis: [
      {
        name: '龙门币',
        type: 'value',
        axisLine:{
          show:true
        },
        axisLabel: {
          formatter: '{value}'
        }
      },
      {
        name: '每单平均龙门币',
        type: 'value',
        axisLine:{
          show:true
        },
        position: 'right',
        offset: 25,
      }
    ],
    series: [
      {
        type: 'bar',
        yAxisIndex: 1,
        color:'#faf0b5',
        tooltip: {
          valueFormatter: function (value) {
            return value
          }
        },
      },
      {
        type: 'line',
        yAxisIndex: 0,
        color:'#e70000',
        tooltip: {
          valueFormatter: function (value) {
            return value
          }
        },
      },
      {
        type: 'line',
        yAxisIndex: 0,
        color:'#64a8ff',
        tooltip: {
          valueFormatter: function (value) {
            return value
          }
        },
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
      data: ['合成玉','抽数'],
      selected:{
        '合成玉':true,
        '抽数':false
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
      dimensions: ['日期','合成玉','抽数'],
      source: HalfMonthData.value
    },
    xAxis: {
      type: 'category',
      axisPointer: {
        type: 'shadow'
      }},
    yAxis: [
      {
        type: 'value',
        axisLine:{
          show:true
        },
        axisLabel: {
          formatter: '{value}'
        }
      },
      {
        type: 'value',
        axisLine:{
          show:true
        },
        position: 'right',
      }
    ],
    series: [
      {
        type: 'line',
        yAxisIndex: 0,
        color:'#faf0b5',
        tooltip: {
          valueFormatter: function (value) {
            return value
          }
        },
      },
      {
        type: 'bar',
        yAxisIndex: 1,
        color:'#e70000',
        tooltip: {
          valueFormatter: function (value) {
            return value
          }
        },
      }
    ]
  }
})
const option_exp = computed(() => {
  return {
    title: [
      {
        text: '作战录像'
      }
    ],
    toolbox: {
      feature: {
        dataView: { show: false, readOnly: false },
        magicType: { show: true, type: ['line', 'bar'] },
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
      dimensions: ['日期','作战录像'],
      source: ReportData.value
    },
    xAxis: {
      type: 'category',
      axisPointer: {
        type: 'shadow'
      }},
    yAxis: [
      {
        type: 'value',
        axisLine:{
          show:true
        },
        axisLabel: {
          formatter: '{value}'
        }
      }
    ],
    series: [
      {
        type: 'line',
        yAxisIndex: 0,
        color:'#e70000',
        tooltip: {
          valueFormatter: function (value) {
            return value
          }
        },
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