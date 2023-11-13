<template>
  <div>
    <n-grid x-gap="12" y-gap="12" cols="1 1000:2 " style="text-align: center">
      <n-gi>
        <div class="report-card_1">
          <n-card>
            <e-charts v-if="show_iron_chart" class="chart" :option="option_iron" />
          </n-card>
        </div>
      </n-gi>
      <n-gi>
        <div class="report-card_1">
          <n-card>
            <e-charts v-if="show_iron_chart" class="chart" :option="option_exp" />
          </n-card>
        </div>
      </n-gi>
      <n-gi>
        <div class="report-card_1">
          <n-card>
            <e-charts v-if="show_orundum_chart" class="chart" :option="option_orundum" />
          </n-card>
        </div>
      </n-gi>
    </n-grid>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import ECharts from 'vue-echarts'
import 'echarts'
import { useReportStore } from '@/stores/report'
const reportStore = useReportStore()
const { getReportData } = reportStore
const date_array = ref([])
const orundum_date_array = ref([])
const exp_array = ref([])
const iron_array = ref([])
const iron_order_array = ref([])
const lmb_array = ref([])
const orundum_array = ref([])
const orundum_order_array = ref([])
const show_iron_chart = ref(false)
const show_orundum_chart = ref(false)
const show_orundum_chart_days = ref(15)
const max_lmb_y = ref()
const min_lmb_y = ref()
const max_exp_y = ref()
const min_exp_y = ref()
const each_order_lmb = ref([])
onMounted(async () => {
  const report_data = await getReportData()
  const date = ref([])
  for (let item in report_data) {
    date.value.push(item)
  }
  for (let item in report_data) {
    date_array.value.push(report_data[item]['Unnamed: 0'])
    orundum_date_array.value.push(report_data[item]['Unnamed: 0'])
    exp_array.value.push(report_data[item]['作战录像'])
    iron_array.value.push(report_data[item]['赤金'])
    lmb_array.value.push(report_data[item]['龙门币订单'])
    iron_order_array.value.push(report_data[item]['龙门币订单数'])
    each_order_lmb.value[item] = (Math.floor(report_data[item]['龙门币订单'] / report_data[item]['龙门币订单数']))
    orundum_array.value.push(report_data[item]['合成玉'])
    orundum_order_array.value.push(report_data[item]['合成玉订单数量'])
  }

  max_lmb_y.value = Math.floor(Math.max(...lmb_array.value) / 50000 + 1) * 50000
  min_lmb_y.value = 0 //Math.min(...lmb_array.value)
  max_exp_y.value = Math.floor(Math.max(...exp_array.value) / 30000 + 1) * 30000
  min_exp_y.value = 0 //Math.min(...exp_array.value)

  show_iron_chart.value = true
  if (orundum_date_array.value.length > show_orundum_chart_days.value) {
    for (var i = orundum_order_array.value.length - 1; i >= 0; i--) {
      if (i < orundum_date_array.value.length - show_orundum_chart_days.value) {
        console.log(i, orundum_date_array.value[i])
        orundum_date_array.value.splice(i, 1)
        orundum_array.value.splice(i, 1)
        orundum_order_array.value.splice(i, 1)
      }
    }
  }
  for (let item in orundum_array.value) {
    if (orundum_array.value[item] > 0) {
      show_orundum_chart.value = true
      break
    }
  }
})
const option_iron = computed(() => {
  return {
    title: [
      {
        text: '赤金'
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
      data: ['赤金', '龙门币', '贸易站龙门币订单数']
    },
    xAxis: [
      {
        type: 'category',
        data: date_array.value,
        axisPointer: {
          type: 'shadow'
        }
      }
    ],
    yAxis: [
      {
        type: 'value',
        min: min_lmb_y.value,
        max: max_lmb_y.value,
        interval: 20000,
        axisLabel: {
          formatter: '{value}'
        }
      },
      {
        type: 'value',
        name: '订单数',
        min: 0,
        max: 50,
        interval: 10,
        axisLabel: {
          formatter: '{value}'
        }
      }
    ],
    dataZoom: [
      {
        xAxisIndex: 0
      }
    ],
    series: [
      {
        name: '赤金',
        type: 'line',
        yAxisIndex: 0,
        tooltip: {
          valueFormatter: function (value) {
            return value
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
            return value
          }
        },
        data: lmb_array.value
      },
      {
        name: '贸易站龙门币订单数',
        type: 'bar',
        yAxisIndex: 1,
        tooltip: {
          valueFormatter: function (value) {
            return value
          }
        },
        data: iron_order_array.value
      },
      {
        name: '每订单龙门币',
        type: 'line',
        tooltip: {
          valueFormatter: function (value) {
            return value
          }
        },
        data: each_order_lmb.value
      },

    ]
  }
})
const option_exp = computed(() => {
  return {
    title: [
      {
        text: '经验'
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
      data: ['作战录像']
    },
    xAxis: [
      {
        type: 'category',
        data: date_array.value,
        axisPointer: {
          type: 'shadow'
        }
      }
    ],
    yAxis: [
      {
        type: 'value',
        min: min_exp_y.value,
        max: max_exp_y.value,
        interval: 10000,
        axisLabel: {
          formatter: '{value}'
        }
      }
    ],
    dataZoom: [
      {
        xAxisIndex: 0
      }
    ],
    series: [
      {
        name: '作战录像',
        type: 'line',
        yAxisIndex: 0,
        tooltip: {
          valueFormatter: function (value) {
            return value
          }
        },
        data: exp_array.value
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
      data: ['合成玉', '合成玉订单数']
    },
    xAxis: [
      {
        type: 'category',
        data: orundum_date_array.value,
        axisPointer: {
          type: 'shadow'
        }
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
        max: 50,
        interval: 5,
        axisLabel: {
          formatter: '{value}'
        }
      }
    ],
    series: [
      {
        name: '合成玉',
        type: 'line',
        tooltip: {
          valueFormatter: function (value) {
            return value
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
            return value
          }
        },
        data: orundum_order_array.value
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

  width: 600px;
  height: 400px;
  padding: 20px 20px 80px 20px;
  border: 1px solid #ccc;
}
</style>
