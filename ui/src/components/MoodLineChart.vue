<script setup>
import { computed, ref, watch } from 'vue'
import { DateTime } from 'luxon'
import { Line } from 'vue-chartjs'

const props = defineProps({ data: Object, options: Object, plugins: Array })
const line = ref(null)
const range = ref([0, 100])
const bounds = computed(() => {
  let min = Infinity
  let max = -Infinity
  for (const dataset of props.data.datasets) {
    for (const point of dataset.data) {
      const raw = point?.x
      const value =
        typeof raw === 'number'
          ? raw
          : typeof raw === 'string'
            ? DateTime.fromISO(raw).toMillis()
            : NaN
      if (!Number.isFinite(value)) continue
      min = Math.min(min, value)
      max = Math.max(max, value)
    }
  }
  if (!Number.isFinite(min) || max <= min) return null
  return [props.options.scales.x.min ?? min, max]
})
const minimum = computed(() =>
  bounds.value
    ? Math.min(100, Math.max(0.1, (60000 / (bounds.value[1] - bounds.value[0])) * 100))
    : 100
)
const width = computed(() => range.value[1] - range.value[0])
const zoomed = computed(() => width.value < 99.999)
const options = computed(() => {
  if (!bounds.value) return props.options
  const [min, max] = bounds.value
  const x = props.options.scales.x
  return {
    ...props.options,
    scales: {
      ...props.options.scales,
      x: {
        ...x,
        // Let the date adapter choose finer labels when the visible window is short.
        ...(x.type === 'time' ? { time: { ...x.time, unit: false } } : {}),
        min: min + ((max - min) * range.value[0]) / 100,
        max: min + ((max - min) * range.value[1]) / 100
      }
    }
  }
})
function setWindow(start, span) {
  span = Math.max(minimum.value, Math.min(100, span))
  start = Math.max(0, Math.min(100 - span, start))
  range.value = [start, start + span]
}
function selectRange(value) {
  setWindow(value[0], value[1] - value[0])
}
function zoom(factor, anchor = 0.5) {
  const span = Math.max(minimum.value, Math.min(100, width.value * factor))
  setWindow(range.value[0] + (width.value - span) * anchor, span)
}
function pan(direction) {
  setWindow(range.value[0] + direction * width.value * 0.5, width.value)
}
function reset() {
  range.value = [0, 100]
}
function wheel(event) {
  if (!(event.ctrlKey || event.metaKey) || !bounds.value || !event.deltaY) return
  const chart = line.value?.chart
  if (!chart) return
  const rect = chart.canvas.getBoundingClientRect()
  const x = ((event.clientX - rect.left) * chart.width) / rect.width
  const { left, right } = chart.chartArea
  if (x < left || x > right) return
  event.preventDefault()
  zoom(event.deltaY < 0 ? 0.8 : 1.25, (x - left) / (right - left))
}
// Visibility changes preserve the viewport; new observations or operator selections reset it.
watch(
  () => props.data.datasets.map((dataset) => dataset.data),
  (next, previous) => {
    if (
      !previous ||
      next.length !== previous.length ||
      next.some((data, i) => data !== previous[i])
    )
      reset()
  }
)
watch(
  () => props.data.datasets.map((dataset) => dataset.hidden),
  () => {
    const chart = line.value?.chart
    if (!chart) return
    props.data.datasets.forEach((dataset, index) =>
      chart.setDatasetVisibility(index, !dataset.hidden)
    )
    chart.update('none')
  }
)
defineExpose({ chart: computed(() => line.value?.chart) })
</script>

<template>
  <div class="mood-line-chart">
    <div class="zoom-tools">
      <n-button size="tiny" :disabled="!bounds || width <= minimum" @click="zoom(0.5)"
        >放大</n-button
      >
      <n-button size="tiny" :disabled="!zoomed" @click="zoom(2)">缩小</n-button>
      <n-button size="tiny" :disabled="!zoomed" @click="reset">重置</n-button>
      <n-button size="tiny" :disabled="!bounds || range[0] <= 0" @click="pan(-1)">前移</n-button>
      <n-button size="tiny" :disabled="!bounds || range[1] >= 100" @click="pan(1)">后移</n-button>
      <span>{{ (100 / width).toFixed(1) }}×</span>
    </div>
    <div class="time-range">
      <span>时间范围</span>
      <n-slider
        :value="range"
        range
        :step="0.01"
        :disabled="!bounds"
        :tooltip="false"
        @update:value="selectRange"
      />
    </div>
    <div class="chart-canvas" @wheel="wheel">
      <Line ref="line" :data="data" :options="options" :plugins="plugins" />
    </div>
  </div>
</template>

<style scoped>
.mood-line-chart {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  min-width: 0;
}
.zoom-tools {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 5px;
  font-size: 11px;
}
.time-range {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 12px;
  font-size: 11px;
}
.time-range > span {
  flex: 0 0 auto;
}
.time-range :deep(.n-slider) {
  flex: 1;
  min-width: 0;
}
.chart-canvas {
  flex: 1;
  position: relative;
  min-height: 0;
}
</style>
