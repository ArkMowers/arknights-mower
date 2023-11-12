<template>
  <e-charts v-if=show_iron_chart class="chart" :option="option_iron" />
  <e-charts v-if=show_orundum_chart  class="chart" :option="option_orundum" />
</template>

<script setup>
import {computed, onMounted, ref} from 'vue';
import ECharts from 'vue-echarts';
import 'echarts';
import { useReportStore } from '@/stores/report'
const reportStore = useReportStore()
const { getReportData } = reportStore
const date_array=ref([])
const exp_array=ref([])
const iron_array=ref([])
const iron_order_array=ref([])
const lmb_array=ref([])
const orundum_array=ref([])
const orundum_order_array=ref([])
const show_iron_chart=ref(false)
const show_orundum_chart=ref(false)
onMounted(async () => {
  const report_data=await getReportData()
  console.log(await getReportData())
  for (let item in report_data) {
    date_array.value.push(item)
    exp_array.value.push(report_data[item]['作战录像'])
    iron_array.value.push(report_data[item]['赤金'])
    lmb_array.value.push(report_data[item]['龙门币订单'])
    iron_order_array.value.push(report_data[item]['龙门币订单数'])
    orundum_array.value.push(report_data[item]['合成玉'])
    orundum_order_array.value.push(report_data[item]['合成玉订单数量'])
  }
  show_iron_chart.value=true
  for (let item in orundum_array.value){
    if (orundum_array.value[item]>0){
      show_orundum_chart.value=true;
    }
  }
})
const option_iron = computed(() => {
  return {
    title: [
      {
        text: '       赤金'
      }
    ],
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross',
        crossStyle: {
          color: '#999'
        }
      }
    },
    toolbox: {
      feature: {
        dataView: { show: true, readOnly: true },
        magicType: { show: true, type: ['line', 'bar'] },
        restore: { show: true },
        saveAsImage: { show: true }
      }
    },
    legend: {
      data: ['作战录像','赤金','龙门币','赤金贸易订单数']
    },
    xAxis: [
      {
        type: 'category',
        data: date_array.value,
        axisPointer: {
          type: 'shadow'
        },
      }
    ],
    yAxis: [
      {
        type: 'value',
        min: 0,
        max: 150000,
        interval: 10000,
        axisLabel: {
          formatter: '{value}'
        }
      },
      {
        type: 'value',
        name: '订单数',
        min: 0,
        max: 100,
        interval: 10,
        axisLabel: {
          formatter: '{value}'
        },
      }
    ],
    dataZoom:[
      {
        yAxisIndex :0
      }
    ],
    series: [
      {
        name: '作战录像',
        type: 'bar',
        yAxisIndex: 0,
        tooltip: {
          valueFormatter: function (value) {
            return value;
          }
        },
        data: exp_array.value
      },
      {
        name: '赤金',
        type: 'line',
        yAxisIndex: 0,
        tooltip: {
          valueFormatter: function (value) {
            return value;
          }
        },
        data: iron_array.value
      },
      {
        name: '龙门币',
        type: 'line',
        yAxisIndex: 0,
        tooltip: {
          valueFormatter: function (value) {
            return value;
          }
        },
        data: lmb_array.value
      },
      {
        name: '赤金贸易订单数',
        type: 'bar',
        yAxisIndex: 1,
        tooltip: {
          valueFormatter: function (value) {
            return value;
          }
        },
        data: iron_order_array.value
      }
    ]
  }
});
const option_orundum = computed(() => {
  return {
    title: [
      {
        text: '       合成玉'
      }
    ],
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross',
        crossStyle: {
          color: '#999'
        }
      }
    },
    toolbox: {
      feature: {
        dataView: { show: true, readOnly: true },
        restore: { show: true },
        saveAsImage: { show: true }
      }
    },
    legend: {
      data: ["合成玉","合成玉订单数"]
    },
    xAxis: [
      {
        type: 'category',
        data: date_array.value,
        axisPointer: {
          type: 'shadow'
        },
      }
    ],
    yAxis: [
      {
        type: 'value',
        name: '合成玉',
        min: 0,
        max: 1000,
        interval: 100,
        axisLabel: {
          formatter: '{value}'
        }
      },
      {
        type: 'value',
        name: '订单数',
        min: 0,
        max: 100,
        interval: 10,
        axisLabel: {
          formatter: '{value}'
        },
      }
    ],
    dataZoom:[
      {
        yAxisIndex :0
      }
    ],
    series: [
      {
        name: '合成玉',
        type: 'line',
        tooltip: {
          valueFormatter: function (value) {
            return value;
          }
        },
        data: orundum_array.value
      },
      {
        name: '合成玉订单数',
        type: 'bar',
        yAxisIndex: 1,
        tooltip: {
          valueFormatter: function (value) {
            return value;
          }
        },
        data: orundum_order_array.value
      },
    ]
  }
});
</script>

<style scoped>
.chart {
  height: 400px;
}
</style>
